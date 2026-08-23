"""Hybrid retrieval: eligibility, then BM25 + exact vector, then RRF, then authority.

The order is the point.

    tenant + lifecycle filter -> BM25 + exact vector -> RRF
      -> authority/conflict resolution -> authoritative/context split -> Medha

Fusion decides *relevance* and nothing else. Authority is a separate, later
step that reorders already-relevant candidates by which source governs the
question -- not a multiplier folded into a similarity score, because a weight
large enough to guarantee a contract wins also lets an irrelevant clause of that
contract win, and a weight small enough to avoid that guarantees nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, Sequence

from .ingest import AUTHORITATIVE_FLOOR, AUTHORITY
from .store import CandidateChunk, DenseRetriever, LexicalRetriever, RetrievalFilters

RRF_K = 60
LEXICAL_WEIGHT = 1.0
DENSE_WEIGHT = 1.0
CANDIDATE_LIMIT = 40

# How the final top-k is filled. A tier boundary is a strict, not a graded,
# preference: `resolve_authority` places every chunk of a higher tier ahead of
# every chunk of a lower one regardless of how each scored during fusion. That
# is right for a genuine conflict -- it is the whole point of the
# governing-agreement override -- but taking the top-k straight off that order
# makes authority *equal* relevance: an account's own agreement is tier 0 for
# that account no matter which of its clauses matched, so on a question the
# agreement says nothing about ("what is the bulk upload row limit") its
# barely-relevant clauses still filled every slot ahead of the product guide
# chunk that both BM25 and the encoder ranked first. Measured on this corpus at
# the tool's own top_k=4, the guide was present in the tiered candidate set and
# absent from the returned evidence for every bulk-upload and pickup-delay
# query.
#
# So selection reserves the first slots for the best tier present -- precedence
# survives, and the governing agreement still leads the list -- then fills the
# rest in fused relevance order, capped per document so no single source takes
# them all. See `_select_diversified`.
MAX_CHUNKS_PER_DOCUMENT = 2
AUTHORITY_RESERVED_SLOTS = 2

# There is deliberately no fixed cosine-distance cutoff here. Measured on this
# corpus: the correct match for a genuine paraphrase sits at distance 0.658, and
# the single nearest neighbour for a wholly unrelated question ("what customs
# duty applies to international air freight into Germany") sits at 0.662 --
# 0.004 apart. Dense distance does not separate "relevant" from "the least-bad
# option in a small corpus" for this encoder, so a threshold here would be a
# number that looks principled and is not. The honest abstention signal is
# `hybrid_search` returning nothing at all -- see the empty-candidate-set check
# -- and, beyond that, it is Medha's job to decide an excerpt does not answer
# the question, exactly as the system prompt already instructs it to.

# Tiers for the authority resolver, best first. An agreement enters the top tier
# only for the account it binds; see `_tier`.
GOVERNING_AGREEMENT_TIER = 0
POLICY_TIER = 1
GUIDE_TIER = 2
CONTEXT_TIER = 3


class Reranker(Protocol):
    """Optional relevance reordering. Runs before authority, never after."""

    def rerank(self, query: str, candidates: Sequence[CandidateChunk]) -> list[str]:
        """Return candidate chunk_ids, most relevant first."""


@dataclass(frozen=True)
class EvidenceChunk:
    """One compact piece of evidence, with its location and how it got here."""

    chunk_id: str
    document_id: str
    document_version_id: str
    source_file: str
    page: int | None
    section: str
    document_type: str
    lifecycle_state: str
    authority: int
    account_id: str | None
    effective_from: date | None
    effective_to: date | None
    text: str
    lexical_rank: int | None
    dense_rank: int | None
    dense_distance: float | None
    rrf_score: float
    tier: int

    @property
    def excerpt(self) -> str:
        return self.text[:600]

    @property
    def is_authoritative(self) -> bool:
        return self.tier < CONTEXT_TIER


@dataclass(frozen=True)
class AuthorityDecision:
    """A record of one source being preferred over another, and why."""

    winner: str
    overrides: list[str]
    reason: str


@dataclass
class RetrievalResult:
    """What retrieval hands the agent.

    Two lists, not one ranked list with a flag. A single list invites whatever
    reads it to treat position as standing, and the entire point of the
    historical-ticket rule is that position never confers that.
    """

    query: str
    authoritative: list[EvidenceChunk] = field(default_factory=list)
    context: list[EvidenceChunk] = field(default_factory=list)
    decisions: list[AuthorityDecision] = field(default_factory=list)
    needs_review: bool = False
    review_reason: str = ""

    def __iter__(self):
        """Iterating a result yields the evidence that may govern an answer."""
        return iter(self.authoritative)

    def __len__(self) -> int:
        return len(self.authoritative)


def weighted_rrf(
    lexical_ranked_ids: list[str],
    dense_ranked_ids: list[str],
    *,
    k: int = RRF_K,
    lexical_weight: float = LEXICAL_WEIGHT,
    dense_weight: float = DENSE_WEIGHT,
) -> list[tuple[str, float, int | None, int | None]]:
    """Weighted reciprocal rank fusion over two ranked chunk_id lists.

        fused = lexical_weight / (k + lexical_rank) + dense_weight / (k + dense_rank)

    Ranks start at 1. A chunk in only one list still competes, with just that
    term. Ranks, never scores: BM25 relevance and cosine distance are not on a
    common scale, and normalising them into one would invent a comparison the
    numbers do not support. Sorted by score, tie-broken on chunk_id so the same
    query twice produces the same citations.
    """
    lexical_rank_by_id = {chunk_id: rank for rank, chunk_id in enumerate(lexical_ranked_ids, start=1)}
    dense_rank_by_id = {chunk_id: rank for rank, chunk_id in enumerate(dense_ranked_ids, start=1)}

    fused: list[tuple[str, float, int | None, int | None]] = []
    for chunk_id in set(lexical_rank_by_id) | set(dense_rank_by_id):
        lexical_rank = lexical_rank_by_id.get(chunk_id)
        dense_rank = dense_rank_by_id.get(chunk_id)
        score = 0.0
        if lexical_rank is not None:
            score += lexical_weight / (k + lexical_rank)
        if dense_rank is not None:
            score += dense_weight / (k + dense_rank)
        fused.append((chunk_id, score, lexical_rank, dense_rank))

    fused.sort(key=lambda item: (-item[1], item[0]))
    return fused


def _tier(candidate: CandidateChunk, scope_account: str | None) -> int:
    """Which authority tier this chunk occupies *for this request*.

    An agreement is the highest authority for the account that signed it and
    ordinary evidence to everyone else. Without that distinction, an internal
    question about response times in general was answered by whichever customer
    contract the encoder happened to like best.
    """
    if candidate.authority < AUTHORITATIVE_FLOOR:
        return CONTEXT_TIER
    if candidate.document_type == "agreement":
        governs = candidate.account_id is not None and candidate.account_id == scope_account
        return GOVERNING_AGREEMENT_TIER if governs else POLICY_TIER
    if candidate.authority >= AUTHORITY["current_policy"]:
        return POLICY_TIER
    return GUIDE_TIER


def resolve_authority(
    ranked: list[CandidateChunk], scope_account: str | None
) -> tuple[list[tuple[CandidateChunk, int]], list[tuple[CandidateChunk, int]], list[AuthorityDecision]]:
    """Reorder relevance-ranked candidates by which source governs the question.

    Relevance has already happened: `ranked` is in fused order and every chunk in
    it is a genuine match. This step only decides precedence among them, so the
    agreement override is a consequence of the agreement being *relevant*, not of
    a number large enough to drag an irrelevant clause to the top.

    Returns (authoritative, context, decisions), each entry paired with its tier.
    """
    tiered = [(candidate, _tier(candidate, scope_account)) for candidate in ranked]
    authoritative = [item for item in tiered if item[1] < CONTEXT_TIER]
    context = [item for item in tiered if item[1] == CONTEXT_TIER]

    # Stable sort by tier alone: within a tier the fused relevance order stands.
    authoritative.sort(key=lambda item: item[1])

    decisions = []
    governing = [c for c, tier in authoritative if tier == GOVERNING_AGREEMENT_TIER]
    overridden = [c for c, tier in authoritative if tier > GOVERNING_AGREEMENT_TIER]
    if governing and overridden:
        decisions.append(AuthorityDecision(
            winner=governing[0].chunk_id,
            overrides=[c.chunk_id for c in overridden],
            reason=(
                f"{governing[0].source_file} is the signed agreement for {scope_account} and "
                "governs where it conflicts with the default policy or SOP."
            ),
        ))
    if context:
        decisions.append(AuthorityDecision(
            winner="",
            overrides=[c.chunk_id for c, _ in context],
            reason="Historical ticket content is context only and never governs an answer.",
        ))
    return authoritative, context, decisions


def _select_diversified(
    tiered: list[tuple[CandidateChunk, int]],
    relevance_rank: dict[str, int],
    top_k: int,
    *,
    max_per_document: int = MAX_CHUNKS_PER_DOCUMENT,
    reserved_slots: int = AUTHORITY_RESERVED_SLOTS,
) -> list[tuple[CandidateChunk, int]]:
    """Fill the final top-k: precedence first, then relevance, capped per document.

    `tiered` is `resolve_authority`'s output -- tier first, fused order within a
    tier -- and `relevance_rank` maps chunk_id to its position in the fused
    ranking, which is the only ordering that reflects what the question actually
    asked.

    Three passes:

    1. *Reserve.* The best tier present takes up to `reserved_slots`. This is
       what keeps the governing agreement at the head of the list when it is
       relevant, so a contractual override is still the first thing the planner
       reads.
    2. *Relevance.* Everything else competes in fused order, not tier order, so
       a product-guide chunk that both branches ranked first is not buried under
       whichever policy clauses happened to be eligible.
    3. *Backfill.* Candidates skipped by the per-document cap fill any slots
       still empty, so a question genuinely answered by one document alone still
       gets a full top-k from it. The cap bounds monopolisation; it never
       truncates a source that has no competition.
    """
    selected: list[tuple[CandidateChunk, int]] = []
    taken: set[str] = set()
    per_document: dict[str, int] = {}

    def take(candidate: CandidateChunk, tier: int) -> None:
        selected.append((candidate, tier))
        taken.add(candidate.chunk_id)
        per_document[candidate.document_id] = per_document.get(candidate.document_id, 0) + 1

    def has_room(candidate: CandidateChunk) -> bool:
        return per_document.get(candidate.document_id, 0) < max_per_document

    # 1. Precedence: the best tier present leads.
    if tiered:
        best_tier = tiered[0][1]
        for candidate, tier in tiered:
            if len(selected) >= min(reserved_slots, top_k):
                break
            if tier == best_tier and has_room(candidate):
                take(candidate, tier)

    # 2. Relevance decides the remaining slots.
    by_relevance = sorted(tiered, key=lambda item: relevance_rank.get(item[0].chunk_id, len(relevance_rank)))
    for candidate, tier in by_relevance:
        if len(selected) >= top_k:
            break
        if candidate.chunk_id not in taken and has_room(candidate):
            take(candidate, tier)

    # 3. Backfill from whatever the cap held back.
    for candidate, tier in by_relevance:
        if len(selected) >= top_k:
            break
        if candidate.chunk_id not in taken:
            take(candidate, tier)

    return selected


class HybridRetriever:
    """Owns one connection and one encoder; every search is principal-scoped.

    There is no unscoped search method. `hybrid_search` builds a
    `RetrievalFilters` from the caller's principal and both branches are issued
    against the predicate it produces, so eligibility is applied before candidate
    generation rather than to its output.
    """

    def __init__(self, conn, encoder, *, as_of: date, embedding_dim: int = 768,
                 reranker: Reranker | None = None):
        self.conn = conn
        self.encoder = encoder
        self.as_of = as_of
        self.lexical = LexicalRetriever(conn)
        self.dense = DenseRetriever(conn, embedding_dim=embedding_dim)
        self.reranker = reranker

    # ------------------------------------------------------------ A. filtering

    def filters_for(self, principal: Any, account_id: str | None) -> RetrievalFilters:
        """Translate a session principal into what SQL is allowed to match.

        A customer's scope comes from `principal.account_id` -- the session --
        not from `account_id`, which on a customer path is model-influenced. The
        tool layer already refuses a mismatch with HTTP 403; ignoring the
        argument here means even a bug there cannot widen a customer's reach.
        """
        return RetrievalFilters(
            role=getattr(principal, "role", "customer"),
            principal_account_id=getattr(principal, "account_id", None),
            account_id=account_id,
            as_of=self.as_of,
        )

    def candidates(self, query: str, filters: RetrievalFilters, limit: int
                   ) -> tuple[list[CandidateChunk], list[CandidateChunk]]:
        """The raw BM25 and vector candidate sets, both already filtered.

        Exposed so tests can assert on what each branch *considered*, not only on
        what survived fusion: "never retrieved" is a weaker claim than "never a
        candidate", and this is the one that can be checked.
        """
        lexical_hits = self.lexical.search(query, filters, limit)          # B. BM25
        query_embedding = self.encoder.encode_query(query)
        dense_hits = self.dense.search(query_embedding, filters, limit)    # C. exact vector
        return lexical_hits, dense_hits

    # ----------------------------------------------------------- the full flow

    def hybrid_search(self, query: str, principal: Any, account_id: str | None = None,
                      top_k: int = 8) -> RetrievalResult:
        filters = self.filters_for(principal, account_id)
        limit = max(CANDIDATE_LIMIT, top_k * 4)
        lexical_hits, dense_hits = self.candidates(query, filters, limit)

        by_id: dict[str, CandidateChunk] = {}
        for hit in dense_hits + lexical_hits:
            existing = by_id.setdefault(hit.chunk_id, hit)
            existing.lexical_rank = existing.lexical_rank or hit.lexical_rank
            existing.dense_rank = existing.dense_rank or hit.dense_rank
            if existing.lexical_score is None:
                existing.lexical_score = hit.lexical_score
            if existing.dense_score is None:
                existing.dense_score = hit.dense_score
        if not by_id:
            return RetrievalResult(
                query=query, needs_review=True,
                review_reason="No eligible passage matched this question at all.",
            )

        # There is deliberately no score-derived "this question is off-topic"
        # signal here. Two were measured and rejected on this corpus: an
        # absolute dense-distance cutoff (the genuine paraphrase match and the
        # single hit for a wholly unrelated question land 0.004 apart) and a
        # corpus-relative z-score (the nonsense query "octopus wristwatch tax
        # bracket jellyfish" scores a *stronger* outlier, z=-2.87, than the real
        # paraphrase, z=-1.86). A 31-chunk corpus against a general-purpose
        # encoder does not carry enough signal for either, and zero BM25 overlap
        # is not usable as a proxy: it also fires on true paraphrases, which are
        # defined by sharing no vocabulary with their answer. Whether an excerpt
        # actually answers the question is left to Medha reading it, per the
        # system prompt -- this layer's job is only to not manufacture false
        # authority, not to judge topical relevance from a similarity score.

        # D. Fusion -- relevance, and only relevance.
        fused = weighted_rrf(
            [hit.chunk_id for hit in lexical_hits],
            [hit.chunk_id for hit in dense_hits],
        )
        rrf_by_id = {chunk_id: score for chunk_id, score, _, _ in fused}
        ranked = [by_id[chunk_id] for chunk_id, _, _, _ in fused if chunk_id in by_id]

        # E1. Optional relevance rerank, still before any authority reasoning.
        if self.reranker is not None:
            order = {cid: rank for rank, cid in enumerate(self.reranker.rerank(query, ranked))}
            ranked.sort(key=lambda c: order.get(c.chunk_id, len(order)))

        # E2. Authority and conflict resolution, on candidates already known relevant.
        authoritative, context, decisions = resolve_authority(ranked, filters.scope_account)

        # F. Precedence, then relevance, capped per document. `decisions` was
        # already built from the full tiered `authoritative` above, so a genuine
        # override is still reported in full even when the losing side's chunks
        # do not all make the final top-k.
        # From `ranked`, not `fused`, so an enabled reranker's ordering is the
        # relevance this uses.
        relevance_rank = {candidate.chunk_id: rank for rank, candidate in enumerate(ranked)}
        selected = _select_diversified(authoritative, relevance_rank, top_k)

        result = RetrievalResult(
            query=query,
            authoritative=[self._evidence(c, tier, rrf_by_id) for c, tier in selected],
            context=[self._evidence(c, tier, rrf_by_id) for c, tier in context[:top_k]],
            decisions=decisions,
        )
        if not result.authoritative:
            result.needs_review = True
            result.review_reason = (
                "Only context-only material matched; no current policy, SOP or agreement "
                "supports an answer here."
            )
        return result

    @staticmethod
    def _evidence(candidate: CandidateChunk, tier: int, rrf_by_id: dict[str, float]) -> EvidenceChunk:
        return EvidenceChunk(
            chunk_id=candidate.chunk_id,
            document_id=candidate.document_id,
            document_version_id=candidate.document_version_id,
            source_file=candidate.source_file,
            page=candidate.page,
            section=candidate.section or "",
            document_type=candidate.document_type,
            lifecycle_state=candidate.lifecycle_state,
            authority=candidate.authority,
            account_id=candidate.account_id,
            effective_from=candidate.effective_from,
            effective_to=candidate.effective_to,
            text=candidate.text,
            lexical_rank=candidate.lexical_rank,
            dense_rank=candidate.dense_rank,
            dense_distance=round(candidate.dense_score, 6) if candidate.dense_score is not None else None,
            rrf_score=round(rrf_by_id.get(candidate.chunk_id, 0.0), 6),
            tier=tier,
        )


class CrossEncoderReranker:
    """Opt-in cross-encoder rerank (`PARCELPILOT_RERANKER_MODEL`).

    Off by default: it reorders relevance only, and the authority resolver that
    runs after it is what the answers actually depend on.
    """

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def rerank(self, query: str, candidates: Sequence[CandidateChunk]) -> list[str]:
        if not candidates:
            return []
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        scores = self._model.predict([(query, c.text) for c in candidates], show_progress_bar=False)
        ranked = sorted(zip(candidates, scores), key=lambda pair: (-float(pair[1]), pair[0].chunk_id))
        return [candidate.chunk_id for candidate, _ in ranked]
