from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

import os

from .rag import AUTHORITY, RetrievalResult, build_retrieval  # noqa: F401  (AUTHORITY re-exported)
from .rag.store import DEFAULT_DATABASE_URL, active_chunks

# The dataset snapshot is "now" for this app, in place of the machine clock, so
# effective-date filtering and credit lateness both stay reproducible.
SNAPSHOT = "2026-08-16 11:00 Asia/Kolkata"
SNAPSHOT_DATE = date(2026, 8, 16)


@dataclass(frozen=True)
class SourceChunk:
    """One retrievable passage, in the shape the agent and UI already consume.

    `title` stays the source filename because it is what citations, the trace and
    the triage loader key on. The retrieval-side fields are additive, so nothing
    downstream had to change to gain page/section provenance.
    """

    source_id: str
    title: str
    authority: int
    status: str
    text: str
    page: int | None = None
    section: str = ""
    document_type: str = ""
    lifecycle_state: str = "active"
    account_id: str | None = None
    document_version_id: str = ""
    effective_from: date | None = None
    effective_to: date | None = None


def status_label(lifecycle_state: str) -> str:
    """Legacy status wording the UI and trace already display."""
    return "deprecated" if lifecycle_state == "superseded" else "current"


class _InternalPrincipal:
    """Staff-equivalent scope for callers that have no session of their own.

    Used only by `search_documents`, whose signature predates principals. It is
    exactly as broad as an internal user and no broader: when an `account_id` is
    supplied, the eligibility predicate narrows private documents to that
    account, so an unowned account still cannot reach another one's agreement.
    """

    role = "support_agent"
    account_id = None


class ParcelPilotData:
    def __init__(self, data_dir: Path, *, database_url: str | None = None):
        self.data_dir = data_dir
        self.database_url = database_url or os.getenv("PARCELPILOT_DATABASE_URL", DEFAULT_DATABASE_URL)
        workbook = data_dir / "ParcelPilot_Assessment_Data.xlsx"
        self.accounts = pd.read_excel(workbook, sheet_name="accounts").fillna("")
        self.orders = pd.read_excel(workbook, sheet_name="orders")
        self.tickets = pd.read_excel(workbook, sheet_name="tickets")
        self.snapshot = SNAPSHOT

        self.retriever = build_retrieval(
            data_dir,
            self.accounts.to_dict("records"),
            self.tickets.to_dict("records"),
            as_of=SNAPSHOT_DATE,
            url=database_url,
        )
        self.reload_chunks()

    def reload_chunks(self) -> None:
        """Refresh the in-memory view of everything currently in force.

        Triage reads whole documents from it and citation rendering resolves ids
        through it, so neither needs a database round-trip on the request path.
        Read back from the database, not kept from the ingest call, so a document
        still in `draft` is absent here exactly as it is absent from retrieval.
        """
        self.chunks = [
            SourceChunk(
                source_id=row["chunk_id"],
                title=row["source_file"],
                authority=row["authority"],
                status=status_label(row["lifecycle_state"]),
                text=row["text"],
                page=row["page"],
                section=row["section"] or "",
                document_type=row["document_type"],
                lifecycle_state=row["lifecycle_state"],
                account_id=row["account_id"],
                document_version_id=row["document_version_id"],
                effective_from=row["effective_from"],
                effective_to=row["effective_to"],
            )
            for row in active_chunks(self.retriever.conn)
        ]

    def account(self, account_id: str) -> dict:
        rows = self.accounts[self.accounts.account_id == account_id]
        if rows.empty:
            raise KeyError(f"Unknown account {account_id}")
        return rows.iloc[0].to_dict()

    def account_by_name(self, text: str) -> dict | None:
        normalized = text.lower()
        for _, row in self.accounts.iterrows():
            if str(row.account_name).lower() in normalized:
                return row.to_dict()
        return None

    def agreement_files(self) -> set[str]:
        """Every signed agreement in the pack, so one account never sees another's."""
        return {f for f in (str(r.contract_file).strip() for _, r in self.accounts.iterrows()) if f and f != "nan"}

    def hybrid_search(self, query: str, principal: Any, account_id: str | None = None,
                      top_k: int = 8) -> RetrievalResult:
        """Eligibility -> BM25 + exact vector -> RRF -> authority. See `app/rag`."""
        return self.retriever.hybrid_search(query, principal, account_id, top_k=top_k)

    def search_documents(self, query: str, account_id: str | None = None,
                         limit: int = 4) -> list[SourceChunk]:
        """Principal-free entry point, kept for callers that had no session."""
        result = self.hybrid_search(query, _InternalPrincipal(), account_id, top_k=limit)
        hits = result.authoritative
        return [
            SourceChunk(
                source_id=hit.chunk_id, title=hit.source_file, authority=hit.authority,
                status=status_label(hit.lifecycle_state), text=hit.text, page=hit.page,
                section=hit.section, document_type=hit.document_type,
                lifecycle_state=hit.lifecycle_state, account_id=hit.account_id,
                document_version_id=hit.document_version_id,
                effective_from=hit.effective_from, effective_to=hit.effective_to,
            )
            for hit in hits
        ]

    def citations(self, chunks: Iterable[SourceChunk]) -> list[dict[str, Any]]:
        """One entry per document, not per chunk, with full provenance metadata."""
        seen, result = set(), []
        for c in chunks:
            if c.title not in seen:
                seen.add(c.title)
                result.append({
                    "id": c.source_id,
                    "title": c.title,
                    "source_file": c.title,
                    "status": c.status,
                    "lifecycle_state": c.lifecycle_state,
                    "page": c.page,
                    "section": c.section,
                    "document_type": c.document_type,
                    "account_id": c.account_id,
                    "effective_from": str(c.effective_from) if c.effective_from else None,
                    "effective_to": str(c.effective_to) if c.effective_to else None,
                })
        return result
