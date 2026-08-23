"""Hybrid retrieval over the ParcelPilot source pack.

    query
      |
      A. eligibility  -- one SQL predicate from the session principal
      |                  (lifecycle -> effective window -> account entitlement)
      +--> B. BM25 (pg_search)        \
      |                                >-- D. reciprocal rank fusion
      +--> C. vector (pgvector HNSW)  /
                                          |
                                          E. optional rerank, then authority
                                             and currentness
                                          |
                                          F. compact evidence chunks
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .embeddings import EMBEDDING_DIM, EmbeddingUnavailable, GteEncoder
from .ingest import (
    AUTHORITATIVE_FLOOR,
    AUTHORITY,
    IngestDocument,
    activate_version,
    build_pdf_documents,
    build_ticket_documents,
    ingest_documents,
)
from .retriever import (
    AuthorityDecision,
    CrossEncoderReranker,
    EvidenceChunk,
    HybridRetriever,
    RetrievalResult,
    resolve_authority,
    weighted_rrf,
)
from .store import (
    DEFAULT_DATABASE_URL,
    RetrievalFilters,
    RetrievalUnavailable,
    apply_migrations,
    connect,
    eligibility_sql,
    tokenize,
    verify_extensions,
)

__all__ = [
    "AUTHORITATIVE_FLOOR", "AUTHORITY", "AuthorityDecision", "EMBEDDING_DIM", "EvidenceChunk",
    "GteEncoder", "HybridRetriever", "IngestDocument", "RetrievalFilters", "RetrievalResult",
    "RetrievalUnavailable", "activate_version", "build_retrieval", "eligibility_sql",
    "resolve_authority", "tokenize", "weighted_rrf",
]


def database_url() -> str:
    return os.getenv("PARCELPILOT_DATABASE_URL", DEFAULT_DATABASE_URL)


def build_retrieval(
    data_dir: Path,
    accounts: Iterable[dict[str, Any]],
    tickets: Iterable[dict[str, Any]],
    *,
    as_of: date,
    url: str | None = None,
    encoder: Any | None = None,
) -> HybridRetriever:
    """Connect, migrate, ingest, and hand back a ready retriever.

    Ingestion runs on every start and is free when nothing changed: each
    document's content hash is compared first, so an unchanged pack costs one
    SELECT per document and no embedding work at all.
    """
    contract_owner = {
        str(row["contract_file"]).strip(): str(row["account_id"])
        for row in accounts
        if str(row.get("contract_file", "")).strip() not in ("", "nan")
    }
    documents = build_pdf_documents(data_dir, contract_owner) + build_ticket_documents(tickets)

    conn = connect(url or database_url())
    verify_extensions(conn)
    apply_migrations(conn)

    encoder = encoder or GteEncoder()
    # The shipped pack is the assessment's ground truth and is admitted directly
    # as `active`. Anything ingested later goes through draft -> verified ->
    # active with a named human on the record; see `activate_version`.
    ingest_documents(conn, documents, encoder, embedding_dim=EMBEDDING_DIM, trusted_seed=True)

    reranker_model = os.getenv("PARCELPILOT_RERANKER_MODEL", "").strip()
    retriever = HybridRetriever(
        conn,
        encoder,
        as_of=as_of,
        embedding_dim=EMBEDDING_DIM,
        reranker=CrossEncoderReranker(reranker_model) if reranker_model else None,
    )
    return retriever
