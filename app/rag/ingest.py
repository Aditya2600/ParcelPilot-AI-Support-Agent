"""Turn source documents into versioned, embedded, metadata-tagged chunks.

Three rules shape this module:

* Account ownership comes from the explicit `accounts.contract_file` mapping in
  the workbook, never from the `Account: ACCT-001` string inside an agreement's
  text. The binding that decides who may read a contract is not something to
  re-derive from the contract's own prose.
* Document text may *retire* a document but never *activate* one. `Status:
  DEPRECATED` is honoured because demotion is safe; `Status: ACTIVE` is ignored,
  because a PDF asserting its own authority is exactly what an attacker would
  write. Activation is a human act -- see `activate_version`.
* Changing a document creates a new version. Nothing is deleted: the previous
  version is marked `superseded` and its chunks stay queryable for audit, while
  the eligibility filter keeps them out of every normal search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader

from .store import content_hash, lexical_text, vector_literal

# Source authority, unchanged from the original trust model: a signed agreement
# outranks the current policy and SOP, which outrank the product guide, which
# outranks anything historical. Embeddings never touch these numbers.
AUTHORITY = {
    "agreement": 100,
    "current_policy": 80,
    "sop": 80,
    "product_guide": 60,
    "historical_ticket": 10,
}

# Below this, a chunk is context and may never be used as governing evidence.
AUTHORITATIVE_FLOOR = 60

# Chunk sizing. Tokens are whitespace-delimited words, which for English prose
# runs about 0.75 of a model token -- close enough to size chunks by, and
# inspectable in a way a tokenizer-dependent count is not.
MAX_CHUNK_TOKENS = 400
OVERLAP_TOKENS = 50
MIN_CHUNK_TOKENS = 8

_DATE = r"\d{1,2}\s+[A-Z][a-z]+\s+\d{4}"
_EFFECTIVE = re.compile(rf"Effective:\s*({_DATE})")
_UPDATED = re.compile(rf"Updated:\s*({_DATE})")
_TERM = re.compile(rf"Term:\s*({_DATE})\s*to\s*({_DATE})")
_STATUS = re.compile(r"Status:\s*([A-Za-z_-]+)")
_RETIRED = re.compile(r"\b(DEPRECATED|SUPERSEDED|EXPIRED|REVOKED|DO\s+NOT\s+USE)\b", re.IGNORECASE)
_SUPERSEDED_BY = re.compile(r"Superseded\s+by:", re.IGNORECASE)

# What counts as a heading, in priority order. The first three are the shapes
# this pack happens to use; the rest generalise to documents it does not, so a
# contract that numbers its clauses differently still splits on its own
# structure instead of being cut mid-sentence by the window fallback.
_HEADING_PATTERNS = (
    re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\S"),          # '1. Scope', '4.3.1 Payment'
    re.compile(r"^\s*KI-\d+"),                          # known-issue ids
    re.compile(r"^\s*(?:Status|Effective|Term|Account|Updated):"),
    re.compile(r"^\s*(?:Section|Clause|Article|Appendix|Schedule|Exhibit)\s+[\dIVXA-Z]"),
)

# The generic fallback: a short title-ish line with no full stop. It requires at
# least two words, and that is not cosmetic. pypdf renders a wrapped paragraph
# as one word per line, so a single-word pattern matches every capitalised word
# that happens to start a line -- 'Before', 'Once', 'This', 'When' all did -- and
# each match cut the paragraph there. That is how KI-211's identifier ended up in
# one chunk and its actual instruction ("verify the carrier status or wait
# through the known delay window") in another, leaving the first truncated
# mid-clause at "A parcel may physically be collected while". A real heading in
# running text is a phrase; one capitalised word is a sentence continuing.
_TITLE_HEADING = re.compile(r"^[A-Z][A-Za-z0-9,&/'\-]*(?:\s+[A-Za-z0-9,&/'\-]+)+$")


@dataclass(frozen=True)
class IngestChunk:
    chunk_index: int
    page: int | None
    section: str
    char_start: int
    char_end: int
    text: str
    embed_text: str
    content_hash: str


@dataclass(frozen=True)
class IngestDocument:
    document_id: str
    source_file: str
    title: str
    document_type: str
    account_id: str | None
    authority: int
    effective_from: date | None
    effective_to: date | None
    content_hash: str
    # `True` only when the document text itself says it is retired. Never the
    # other way round: nothing a document claims can promote it.
    retired_by_text: bool = False
    chunks: list[IngestChunk] = field(default_factory=list)


# ------------------------------------------------------------------- parsing


def _flow(text: str) -> str:
    """Collapse pypdf's one-word-per-line output back into readable prose."""
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(_flow(value), "%d %B %Y").date()


def _document_type(filename: str) -> str:
    if "Agreement" in filename:
        return "agreement"
    if "SOP" in filename:
        return "sop"
    if "Product_Operations" in filename:
        return "product_guide"
    return "current_policy"


def _retirement_and_dates(page_text: str) -> tuple[bool, date | None, date | None]:
    """Read the effective window, and whether the text retires the document.

    Deliberately asymmetric: a document may say it is out of force and be
    believed, because that only ever removes it from retrieval. A document
    saying it is in force is ignored -- see `activate_version`.
    """
    flowed = _flow(page_text)
    status = _STATUS.search(flowed)
    retired = bool(
        (status and _RETIRED.search(status.group(1)))
        or _SUPERSEDED_BY.search(flowed)
        or (status is None and _RETIRED.search(flowed[:400]))
    )

    term = _TERM.search(flowed)
    if term:
        return retired, _parse_date(term.group(1)), _parse_date(term.group(2))

    effective = _EFFECTIVE.search(flowed) or _UPDATED.search(flowed)
    return retired, _parse_date(effective.group(1)) if effective else None, None


# ------------------------------------------------------------------ chunking


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return False
    if any(pattern.match(stripped) for pattern in _HEADING_PATTERNS):
        return True
    return len(stripped) <= 71 and bool(_TITLE_HEADING.match(stripped))


def _heading_sections(page_text: str) -> list[tuple[str, int, int]]:
    """Split a page at its headings. Returns (heading, char_start, char_end).

    Structure first: a document's own headings are the best chunk boundaries it
    has, because they are where its author decided one idea ends. The token
    window below is only what happens when a section is too long to embed well.
    """
    lines = page_text.split("\n")
    starts: list[tuple[int, str]] = []
    offset = 0
    for line in lines:
        if _is_heading(line):
            starts.append((offset, _flow(line)[:120]))
        offset += len(line) + 1

    if not starts or starts[0][0] > 0:
        starts.insert(0, (0, _flow(lines[0])[:120] if lines else ""))

    sections = []
    for index, (start, heading) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(page_text)
        sections.append((heading, start, end))
    return sections


def _token_windows(body: str) -> list[str]:
    """Slice an over-long section into overlapping windows.

    The overlap exists so a rule that straddles a window boundary is complete in
    at least one chunk. Without it, "after 30 minutes, charge INR 250 unless a
    customer agreement waives the fee" can be cut between the amount and the
    exception, and either half retrieved alone reads as a different rule.
    """
    words = body.split()
    if len(words) <= MAX_CHUNK_TOKENS:
        return [body]
    windows, start = [], 0
    step = MAX_CHUNK_TOKENS - OVERLAP_TOKENS
    while start < len(words):
        windows.append(" ".join(words[start:start + MAX_CHUNK_TOKENS]))
        if start + MAX_CHUNK_TOKENS >= len(words):
            break
        start += step
    return windows


def _build_chunks(title: str, source_file: str, pages: list[str]) -> list[IngestChunk]:
    """Heading-aware split, then a token window for anything still too long.

    `text` is the exact source clause and the only thing ever quoted back.
    `embed_text` prepends the document title, its filename and the section
    heading: that context is what makes "the current support policy" findable,
    and it never becomes a citation because those words are not in the clause.
    """
    chunks: list[IngestChunk] = []
    for page_number, page_text in enumerate(pages, start=1):
        for heading, start, end in _heading_sections(page_text):
            body = _flow(page_text[start:end])
            if len(body.split()) < MIN_CHUNK_TOKENS:
                continue
            for window in _token_windows(body):
                index = len(chunks) + 1
                chunks.append(IngestChunk(
                    chunk_index=index,
                    page=page_number,
                    section=heading,
                    char_start=start,
                    char_end=end,
                    text=window,
                    embed_text=f"{title} [{source_file}] - {heading}\n{window}",
                    content_hash=content_hash(window),
                ))
    return chunks


# ------------------------------------------------------------------ builders


def build_pdf_documents(data_dir: Path, contract_owner: dict[str, str]) -> list[IngestDocument]:
    documents: list[IngestDocument] = []
    for path in sorted(data_dir.glob("*.pdf")):
        pages = [page.extract_text() or "" for page in PdfReader(path).pages]
        retired, effective_from, effective_to = _retirement_and_dates(pages[0] if pages else "")
        document_type = _document_type(path.name)
        title = (_flow(pages[0].split("\n", 1)[0]) if pages else "") or path.name
        chunks = _build_chunks(title, path.name, pages)
        documents.append(IngestDocument(
            document_id=path.name,
            source_file=path.name,
            title=title,
            document_type=document_type,
            # Only an agreement is private, and only to the account the workbook
            # says signed it.
            account_id=contract_owner.get(path.name) if document_type == "agreement" else None,
            authority=0 if retired else AUTHORITY[document_type],
            effective_from=effective_from,
            effective_to=effective_to,
            content_hash=_document_hash(pages, chunks),
            retired_by_text=retired,
            chunks=chunks,
        ))
    return documents


def _document_hash(pages: list[str], chunks: list[IngestChunk]) -> str:
    """Identity of "this document, as this pipeline renders it".

    Hashing the raw pages alone would be wrong: a change to the chunker or to
    how `embed_text` is built produces different rows from identical bytes, and
    an ingest keyed on the source text would decide there was nothing to do and
    leave the old chunks in place. Including the derived output means the only
    no-op is a genuine one.
    """
    parts = ["\n".join(pages)]
    parts += [f"{c.chunk_index}\x00{c.text}\x00{c.embed_text}" for c in chunks]
    return content_hash("\x01".join(parts))


def build_ticket_documents(tickets: Iterable[dict[str, Any]]) -> list[IngestDocument]:
    """Closed tickets whose recorded resolution is context, not policy.

    The workbook warns that some past resolutions are wrong, and two of them are
    (TKT-450 quotes a fee Northstar's agreement waives; TKT-451 quotes a row
    limit the product guide contradicts). They are indexed anyway, because an
    agent asking "has this come up before?" should find them -- at authority 10,
    which puts them in the context set that can never govern an answer, and
    scoped to the account that raised them.
    """
    documents: list[IngestDocument] = []
    for ticket in tickets:
        resolution = str(ticket.get("historical_resolution") or "").strip()
        if not resolution or resolution.lower() == "nan":
            continue
        ticket_id = str(ticket["ticket_id"])
        document_id = f"ticket:{ticket_id}"
        title = f"{ticket_id} (closed) - {ticket.get('subject', '')}".strip()
        body = _flow(
            f"Historical support ticket {ticket_id}. Subject: {ticket.get('subject', '')}. "
            f"Description: {ticket.get('description', '')}. "
            f"Past agent resolution (context only, may be incorrect): {resolution}"
        )
        chunk = IngestChunk(
            chunk_index=1,
            page=None,
            section=f"{ticket_id} historical resolution",
            char_start=0,
            char_end=len(body),
            text=body,
            embed_text=f"{title} (historical ticket, context only)\n{body}",
            content_hash=content_hash(body),
        )
        created = ticket.get("created_at")
        documents.append(IngestDocument(
            document_id=document_id,
            source_file=document_id,
            title=title,
            document_type="historical_ticket",
            account_id=str(ticket["account_id"]),
            authority=AUTHORITY["historical_ticket"],
            effective_from=created.date() if hasattr(created, "date") else None,
            effective_to=None,
            content_hash=content_hash(body),
            chunks=[chunk],
        ))
    return documents


# ------------------------------------------------------------------ persisting


def ingest_documents(conn, documents: list[IngestDocument], encoder, *,
                     embedding_dim: int = 768, trusted_seed: bool = False) -> dict[str, int]:
    """Persist documents as versions. Re-ingesting identical content is a no-op.

    `trusted_seed` is the difference between the shipped source pack and anything
    that arrives later. The pack is the assessment's ground truth and is admitted
    directly as `active`; every other document lands in `draft` and stays
    invisible to retrieval until a human calls `activate_version`. A PDF cannot
    talk its way into being authoritative by containing the word ACTIVE.
    """
    stats = {"unchanged": 0, "versions": 0, "chunks": 0, "superseded": 0}
    # The revision is part of the identity: a moved tag produces different
    # vectors from the same model name, and mixing them is silently wrong.
    model_name = getattr(encoder, "fingerprint", None) or getattr(
        encoder, "model_name", encoder.__class__.__name__
    )

    for document in documents:
        latest = conn.execute(
            "SELECT document_version_id, version_number, content_hash, lifecycle_state "
            "FROM rag_documents WHERE document_id = %s ORDER BY version_number DESC LIMIT 1",
            (document.document_id,),
        ).fetchone()

        if latest and latest["content_hash"] == document.content_hash and not _needs_reembed(
            conn, latest["document_version_id"], model_name
        ):
            stats["unchanged"] += 1
            continue

        if latest and latest["content_hash"] == document.content_hash:
            # Same content, stale vectors: re-embed in place rather than minting
            # a version, because nothing about the document actually changed.
            _reembed_version(conn, latest["document_version_id"], document, encoder,
                             model_name, embedding_dim)
            stats["versions"] += 0
            stats["chunks"] += len(document.chunks)
            continue

        version_number = (latest["version_number"] + 1) if latest else 1
        version_id = f"{document.document_id}@v{version_number}"
        lifecycle = _initial_state(document, trusted_seed)

        embeddings = encoder.encode([chunk.embed_text for chunk in document.chunks])
        with conn.transaction():
            if latest:
                # Retire the previous version. Its chunks are kept: an answer
                # given last month cited them, and deleting the rows would make
                # that citation unresolvable.
                conn.execute(
                    "UPDATE rag_documents SET lifecycle_state = 'superseded' "
                    "WHERE document_version_id = %s",
                    (latest["document_version_id"],),
                )
                conn.execute(
                    "UPDATE rag_chunks SET lifecycle_state = 'superseded' "
                    "WHERE document_version_id = %s",
                    (latest["document_version_id"],),
                )
                stats["superseded"] += 1

            document_db_id = _insert_version(
                conn, document, version_id, version_number,
                latest["document_version_id"] if latest else None, lifecycle,
            )
            for chunk, embedding in zip(document.chunks, embeddings):
                _insert_chunk(conn, document, version_id, document_db_id, chunk,
                              embedding, model_name, embedding_dim, lifecycle)
        stats["versions"] += 1
        stats["chunks"] += len(document.chunks)

    conn.commit()
    return stats


def _initial_state(document: IngestDocument, trusted_seed: bool) -> str:
    if document.retired_by_text:
        return "superseded"
    return "active" if trusted_seed else "draft"


def activate_version(conn, document_version_id: str, *, verified_by: str) -> str:
    """Promote a draft through verification into force. The only route to `active`.

    Requires a named human. Everything a new document asserts about itself --
    its status, its dates, who it binds -- is reviewed before it can influence a
    single answer, which is what stops an uploaded "agreement" from granting
    itself authority it was never given.
    """
    if not str(verified_by).strip():
        raise ValueError("activation requires the identity of the person verifying the document")
    row = conn.execute(
        "SELECT lifecycle_state FROM rag_documents WHERE document_version_id = %s",
        (document_version_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"No such document version {document_version_id!r}")
    if row["lifecycle_state"] == "superseded":
        raise ValueError(f"{document_version_id} is superseded; activate its successor instead")

    with conn.transaction():
        for table in ("rag_documents", "rag_chunks"):
            conn.execute(
                f"UPDATE {table} SET lifecycle_state = 'active' WHERE document_version_id = %s",
                (document_version_id,),
            )
        conn.execute(
            "UPDATE rag_documents SET verified_by = %s, verified_at = now() "
            "WHERE document_version_id = %s",
            (verified_by, document_version_id),
        )
    conn.commit()
    return "active"


def _needs_reembed(conn, document_version_id: str, model_name: str) -> bool:
    """True when any stored vector was produced by a different model, or none was.

    Two encoders that happen to share a width do not share a vector space: an old
    vector scored against a new query embedding yields a plausible cosine number
    that means nothing. Silently wrong retrieval is worse than no retrieval, so a
    model change re-embeds rather than reusing rows that merely fit the column.
    """
    return conn.execute(
        "SELECT 1 FROM rag_chunks WHERE document_version_id = %s "
        "AND (embedding IS NULL OR embedding_model IS DISTINCT FROM %s) LIMIT 1",
        (document_version_id, model_name),
    ).fetchone() is not None


def _reembed_version(conn, version_id: str, document: IngestDocument, encoder,
                     model_name: str, embedding_dim: int) -> None:
    embeddings = encoder.encode([chunk.embed_text for chunk in document.chunks])
    with conn.transaction():
        for chunk, embedding in zip(document.chunks, embeddings):
            conn.execute(
                "UPDATE rag_chunks SET embedding = %s::vector, embedding_model = %s "
                "WHERE chunk_id = %s",
                (vector_literal(embedding, expected_dim=embedding_dim), model_name,
                 f"{version_id}#{chunk.chunk_index}"),
            )
    conn.commit()


def _insert_version(conn, document: IngestDocument, version_id: str, version_number: int,
                    supersedes: str | None, lifecycle: str) -> int:
    return conn.execute(
        """
        INSERT INTO rag_documents (
            document_version_id, document_id, version_number, supersedes_version_id,
            source_file, title, document_type, lifecycle_state, account_id, authority,
            effective_from, effective_to, content_hash
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            version_id, document.document_id, version_number, supersedes,
            document.source_file, document.title, document.document_type, lifecycle,
            document.account_id, document.authority, document.effective_from,
            document.effective_to, document.content_hash,
        ),
    ).fetchone()["id"]


def _insert_chunk(conn, document, version_id, document_db_id, chunk, embedding,
                  model_name, embedding_dim, lifecycle) -> None:
    conn.execute(
        """
        INSERT INTO rag_chunks (
            chunk_id, document_db_id, document_version_id, document_id, chunk_index,
            source_file, page, section, char_start, char_end, text, embed_text, lexical_text,
            account_id, document_type, lifecycle_state, authority, effective_from,
            effective_to, content_hash, embedding, embedding_model
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s::vector, %s
        )
        """,
        (
            f"{version_id}#{chunk.chunk_index}", document_db_id, version_id,
            document.document_id, chunk.chunk_index, document.source_file, chunk.page,
            chunk.section, chunk.char_start, chunk.char_end, chunk.text, chunk.embed_text,
            lexical_text(chunk.embed_text), document.account_id, document.document_type,
            lifecycle, document.authority, document.effective_from, document.effective_to,
            chunk.content_hash, vector_literal(embedding, expected_dim=embedding_dim),
            model_name,
        ),
    )
