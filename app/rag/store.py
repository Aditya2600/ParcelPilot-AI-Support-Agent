"""Postgres/ParadeDB persistence and the two scoped candidate generators.

The security property this module exists to enforce: `RetrievalFilters` is
built once per request and turned into a single SQL predicate that *both*
`LexicalRetriever` and `DenseRetriever` are constructed on top of. Neither has
a search method that runs without one, so an ineligible chunk is never a
candidate -- it is not retrieved and then dropped, it is never selected.

Vectors travel as pgvector text literals, so psycopg is the only client
dependency (no pgvector Python package).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

import psycopg
from psycopg.rows import dict_row

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

DEFAULT_DATABASE_URL = "postgresql://parcelpilot:parcelpilot_local_dev@localhost:5434/parcelpilot"


class RetrievalUnavailable(RuntimeError):
    """The retrieval store is missing or misconfigured.

    Raised rather than degrading to some weaker search: a support agent that
    quietly stops consulting the source pack and starts answering from the
    planner's memory is exactly the failure this system is built to prevent.
    """


# ------------------------------------------------------------------ connection


def connect(database_url: str, *, autocommit: bool = False) -> psycopg.Connection:
    try:
        return psycopg.connect(database_url, row_factory=dict_row, autocommit=autocommit)
    except psycopg.OperationalError as exc:
        raise RetrievalUnavailable(
            f"Could not reach the retrieval database at {database_url!r}: {exc}\n"
            "Start it with:  docker compose up -d db"
        ) from exc


def verify_extensions(conn: psycopg.Connection) -> dict[str, str | None]:
    """Return installed versions for pg_search/vector; raise if either is missing."""
    rows = conn.execute(
        "SELECT name, installed_version FROM pg_available_extensions "
        "WHERE name IN ('pg_search', 'vector')"
    ).fetchall()
    found = {row["name"]: row["installed_version"] for row in rows}
    for required in ("pg_search", "vector"):
        if not found.get(required):
            raise RetrievalUnavailable(
                f"Required extension {required!r} is not available on this Postgres instance. "
                "The compose file pins paradedb/paradedb, which ships both."
            )
    return found


def apply_migrations(conn: psycopg.Connection, *, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply each .sql file in filename order, tracked in schema_migrations.

    No migration framework: filenames sort lexicographically and each file's DDL
    is written with IF NOT EXISTS, so re-running against a migrated database is
    a no-op.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    applied: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if conn.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (path.name,)).fetchone():
            continue
        conn.execute(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
        applied.append(path.name)
    conn.commit()
    return applied


def vector_literal(embedding: Sequence[float] | None, *, expected_dim: int) -> str | None:
    if embedding is None:
        return None
    if len(embedding) != expected_dim:
        raise ValueError(f"embedding has dimension {len(embedding)}, expected {expected_dim}")
    return "[" + ",".join(repr(float(value)) for value in embedding) + "]"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ filtering


@dataclass(frozen=True)
class RetrievalFilters:
    """Who is asking, and therefore what may be considered at all.

    Built from the session principal, never from model-supplied arguments: a
    customer's visible account is `principal_account_id`, so a planner that asks
    for another account's documents changes nothing about what SQL will match.
    """

    role: str
    principal_account_id: str | None
    account_id: str | None
    as_of: date
    include_superseded: bool = False

    @property
    def visible_accounts(self) -> list[str] | None:
        """Account ids whose private documents this request may see.

        `None` means "no account restriction" and is reachable only for internal
        staff who named no account -- the existing broader internal behaviour.
        """
        if self.role == "customer":
            return [self.principal_account_id] if self.principal_account_id else []
        if self.account_id:
            return [self.account_id]
        return None

    @property
    def scope_account(self) -> str | None:
        """The one account this request is about, when it is about one at all."""
        visible = self.visible_accounts
        return visible[0] if visible else None


def eligibility_sql(filters: RetrievalFilters) -> tuple[str, dict[str, Any]]:
    """The one predicate every candidate must satisfy, for both branches.

    Order of the clauses is the order of the rules:
      1. lifecycle  -- superseded/deprecated and not-yet-approved drafts are out
      2. currentness -- an expired agreement is not a candidate, not a low-ranked one
      3. eligibility -- private documents only for the accounts entitled to them
    """
    clauses = []
    params: dict[str, Any] = {"as_of": filters.as_of}

    if filters.include_superseded:
        clauses.append("lifecycle_state IN ('active', 'superseded')")
    else:
        clauses.append("lifecycle_state = 'active'")

    clauses.append("(effective_from IS NULL OR effective_from <= %(as_of)s)")
    clauses.append("(effective_to IS NULL OR effective_to >= %(as_of)s)")

    visible = filters.visible_accounts
    if visible is None:
        clauses.append("TRUE")
    else:
        clauses.append("(account_id IS NULL OR account_id = ANY(%(visible_accounts)s))")
        params["visible_accounts"] = visible

    return " AND ".join(clauses), params


# ------------------------------------------------------------------ retrieval

_ROW_COLUMNS = (
    "id, chunk_id, document_id, document_version_id, chunk_index, source_file, page, "
    "section, char_start, char_end, text, account_id, document_type, lifecycle_state, "
    "authority, effective_from, effective_to"
)


@dataclass
class CandidateChunk:
    """One eligible chunk plus where it placed in the branch that found it."""

    chunk_id: str
    document_id: str
    document_version_id: str
    source_file: str
    chunk_index: int
    page: int | None
    section: str | None
    char_start: int
    char_end: int
    text: str
    account_id: str | None
    document_type: str
    lifecycle_state: str
    authority: int
    effective_from: date | None
    effective_to: date | None
    lexical_rank: int | None = None
    dense_rank: int | None = None
    lexical_score: float | None = None
    dense_score: float | None = None


def _row_to_candidate(row: dict[str, Any]) -> CandidateChunk:
    return CandidateChunk(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        document_version_id=row["document_version_id"],
        source_file=row["source_file"],
        chunk_index=row["chunk_index"],
        page=row["page"],
        section=row["section"],
        char_start=row["char_start"],
        char_end=row["char_end"],
        text=row["text"],
        account_id=row["account_id"],
        document_type=row["document_type"],
        lifecycle_state=row["lifecycle_state"],
        authority=row["authority"],
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
    )


def active_chunks(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Every chunk currently in force, for callers that need whole documents.

    Read back from the database rather than kept from the ingest call, so it
    reflects what was actually persisted -- including versions ingested by
    another process and documents still sitting in `draft`, which are correctly
    absent.
    """
    return conn.execute(
        f"SELECT {_ROW_COLUMNS} FROM rag_chunks WHERE lifecycle_state = 'active' "
        "ORDER BY document_id, chunk_index"
    ).fetchall()


class LexicalRetriever:
    """BM25 over `lexical_text` via pg_search. Evidence returned is always `text`.

    Both sides of the match go through `tokenize()`: `lexical_text` is its output
    stored at ingest, and the query is its output at search time. There is one
    tokenizer, so the index and the query cannot drift apart.
    """

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def search(self, query: str, filters: RetrievalFilters, limit: int) -> list[CandidateChunk]:
        terms = tokenize(query)
        if not terms:
            return []
        predicate, params = eligibility_sql(filters)
        params.update({"query": " ".join(terms), "limit": limit})
        rows = self.conn.execute(
            f"""
            SELECT {_ROW_COLUMNS}, pdb.score(id) AS score
            FROM rag_chunks
            WHERE lexical_text ||| %(query)s
              AND {predicate}
            ORDER BY score DESC, chunk_id ASC
            LIMIT %(limit)s
            """,
            params,
        ).fetchall()
        hits = []
        for rank, row in enumerate(rows, start=1):
            candidate = _row_to_candidate(row)
            candidate.lexical_rank = rank
            candidate.lexical_score = float(row["score"])
            hits.append(candidate)
        return hits


class DenseRetriever:
    """Exact pgvector cosine retrieval over the eligible set.

    Index scans are turned off for this statement on purpose. HNSW is
    approximate: with a restrictive filter it searches its own graph and returns
    whatever survives, which is not necessarily the true top-k of the eligible
    rows. Recall loss is an acceptable trade for a ranking preference and a bad
    one for a rule about which account may see which contract -- and at this
    corpus size an exact scan costs nothing. The index stays in the schema for
    when the corpus makes that trade worth revisiting.
    """

    def __init__(self, conn: psycopg.Connection, *, embedding_dim: int = 768):
        self.conn = conn
        self.embedding_dim = embedding_dim

    def search(
        self, query_embedding: Sequence[float], filters: RetrievalFilters, limit: int
    ) -> list[CandidateChunk]:
        predicate, params = eligibility_sql(filters)
        params.update({
            "embedding": vector_literal(query_embedding, expected_dim=self.embedding_dim),
            "limit": limit,
        })
        with self.conn.transaction():
            # Exact search: force a sequential scan so ORDER BY distance is the
            # true ordering of every eligible row, not the HNSW graph's estimate.
            self.conn.execute("SET LOCAL enable_indexscan = off")
            self.conn.execute("SET LOCAL enable_bitmapscan = off")
            rows = self.conn.execute(
                f"""
                SELECT {_ROW_COLUMNS}, embedding <=> %(embedding)s::vector AS distance
                FROM rag_chunks
                WHERE embedding IS NOT NULL
                  AND {predicate}
                ORDER BY distance ASC, chunk_id ASC
                LIMIT %(limit)s
                """,
                params,
            ).fetchall()
        hits = []
        for rank, row in enumerate(rows, start=1):
            candidate = _row_to_candidate(row)
            candidate.dense_rank = rank
            candidate.dense_score = float(row["distance"])
            hits.append(candidate)
        return hits


# The one tokenizer. `lexical_text` is built with it at ingest and the query is
# reduced with it at search time, so a change here changes both sides together.
#
# It is also the sanitiser: pg_search parses its own query syntax, so a raw
# question mark, colon or quote from a user would be a syntax error rather than
# a search. Stripping to bare terms removes that class of input entirely, and
# `|||` gives the surviving terms OR semantics.
_TERM = re.compile(r"[a-z0-9][a-z0-9\-]*")

_STOPWORDS = frozenset(
    "the a an and or of to for in on at is are was were be been it its this that "
    "with as by from we you our your can could should would do does did what "
    "when where which who how why if not no yes any all".split()
)


def tokenize(text: str) -> list[str]:
    terms = [t for t in _TERM.findall(str(text).lower()) if len(t) > 2]
    kept = [t for t in terms if t not in _STOPWORDS]
    # A query made entirely of stopwords still deserves a lexical branch.
    return kept or terms


def lexical_text(embed_text: str) -> str:
    """What actually gets BM25-indexed for a chunk."""
    return " ".join(tokenize(embed_text))
