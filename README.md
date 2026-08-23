# ParcelPilot Support Agent

A runnable assessment submission that supports both customer-facing and internal support contexts. It deliberately uses the supplied source pack as the only business-information base.

## Run

Requires Python 3.10+ and Docker (for the retrieval store).

```bash
cd parcelpilot-agent
docker compose up -d db          # ParadeDB: pg_search (BM25) + pgvector (HNSW)
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`. The UI has mock principals for two customers and two internal roles.

First start applies `app/rag/migrations/`, downloads the embedding model (~550 MB, once) and
ingests the source pack. Later starts re-check each document's content hash and do nothing when
nothing changed. Configure with `PARCELPILOT_DATABASE_URL` and `PARCELPILOT_EMBEDDING_MODEL`.

## Run the full stack in Docker

One command starts the API (which also serves the static frontend at `/`) and PostgreSQL/ParadeDB
together. There is no separate frontend service or Dockerfile -- the UI is static files the FastAPI
app already mounts and serves itself.

```bash
cd parcelpilot-agent
cp .env.example .env    # adjust MEDHA_API_KEY etc. if needed
docker compose up --build
```

Then open `http://localhost:8000`.

- **Health checks**: `db` uses `pg_isready`; `api` polls `GET /api/health` (checks it can reach
  Postgres through its connection pool). `api` won't start until `db` reports healthy.
- **Migrations, connection pooling, and RAG bootstrap** all happen automatically on `api` startup,
  the same way they do outside Docker (see above) -- there is nothing extra to run. Ingest is
  content-hash-gated, so restarting the stack, or rebuilding the image, re-checks every document and
  does no embedding work and creates no duplicate document versions when nothing changed.
- **Persistence**: Postgres data lives in the `parcelpilot_pg` named volume and the downloaded
  embedding model lives in `parcelpilot_model_cache`. `docker compose down` (without `-v`) followed by
  `docker compose up` comes back with the same data and does not re-download the model.
- **Config**: all values in `.env.example` are read from the environment already (see `app/llm.py`,
  `app/rag/store.py`, `app/rag/embeddings.py`) -- `docker-compose.yml` only wires them through.
  `MEDHA_BASE_URL`/`MEDHA_API_KEY`/`MEDHA_MODEL` point at Medha/vLLM, which stays external and is
  never bundled into the application image.

Makefile shortcuts:

```bash
make up      # docker compose up --build -d
make down    # docker compose down
make logs    # docker compose logs -f
make test    # deterministic tests, host .venv, against the compose db (localhost:5434)
make eval    # live 28-case evaluation benchmark, host .venv
```

`make test` and `make eval` run on the host (not inside the container) against the same Postgres the
compose stack publishes on `localhost:5434`, so they need `python -m venv .venv && pip install -r
requirements.txt` done once, same as the dev flow above.

## What it demonstrates

- Natural-language chat with visible tool trace.
- Three distinct tools: `document_search` (hybrid retrieval, below), scoped structured order/ticket lookup and credit calculation, and a mocked `create_escalation` action.
- Explicit confirmation: escalation requests only create a pending action. The UI must click **Confirm escalation**, calling a separate confirmation endpoint.
- Multi-step reasoning driven by an LLM planner: the model chooses tools, extracts arguments, and writes the reply. A cancellation question typically runs order lookup, resolves account ownership, retrieves that account's agreement plus the current SOP, then applies whichever governs.
- The planner/tool/observation cycle is orchestrated as a LangGraph state machine (`app/graph.py`):

  ```
  planner -> execute_tool -> (observation) -> planner -> ... -> finalize
                  |
                  +-> confirmation_gate -> planner (final answer only)
  ```

  LangGraph owns only the control flow. Planning, tools, prompts and permission checks are unchanged, and the graph adds one enforceable property: staging an action routes into `confirmation_gate`, which drops the planner to a final-answer-only schema, so after staging the model *cannot* call another tool rather than merely being told not to.
- Hybrid retrieval over the source pack (`app/rag/`), persisted in ParadeDB — pg_search BM25 and
  exact pgvector cosine search over the same rows, under the same `WHERE` clause:

  ```
  tenant + lifecycle filter
    |
    A. eligibility ---- one SQL predicate built from the session principal
    |                   lifecycle -> effective window -> account entitlement
    +--> B. BM25 (pg_search, shared tokenizer)  \
    |                                             >-- C. reciprocal rank fusion (ranks, k=60)
    +--> B'. exact pgvector cosine search        /
                                                     |
                                                     D. authority/conflict resolution
                                                     |
                                                     E. authoritative/context split
                                                     |
                                                     F. compact evidence -> Medha
  ```

  **Eligibility is applied before candidate generation, not after retrieval.** `eligibility_sql()`
  produces one predicate and both branches are issued on top of it, so another customer's agreement
  is never in the BM25 candidate set *or* the vector candidate set — there is nothing to filter out
  later. A customer's scope comes from `principal.account_id` on the session, never from an argument
  the planner supplied. Tests assert on the raw candidate sets, because "never retrieved" is a
  weaker claim than "never a candidate".

  **Vector search is exact, not approximate.** An HNSW index exists in the schema for future scale,
  but the query path forces a sequential scan (`SET LOCAL enable_indexscan/enable_bitmapscan = off`)
  so `ORDER BY distance` is the true ordering of every eligible row. Eligibility is a security
  property here, not a ranking preference, and an approximate index does not guarantee it returns
  the true top-k of a filtered set — at this corpus size the exact scan costs nothing.

  **BM25 and the query use one tokenizer.** `tokenize()` builds both `rag_chunks.lexical_text` at
  ingest time and the query's search terms at request time, so the two cannot silently drift apart —
  a risk with two independent implementations that happen to agree today.

  **Authority is a separate step from relevance, run after fusion.** Fusion (RRF) ranks candidates by
  relevance only. `resolve_authority()` then reorders the *already-relevant* candidates into tiers —
  the account's own signed agreement, then current policy/SOP, then the product guide — and splits
  the result into two lists: `authoritative` (may answer the question) and `context` (historical
  ticket material only). A historical ticket can never land in `authoritative`, however close its
  embedding; it is a hard tier, not a score penalty large enough to usually win. This also means an
  agreement only tops the ranking for the account that signed it — for anyone else it is ordinary
  policy-tier evidence, so an unscoped internal question is answered by the source that governs
  everyone, not by whichever customer's contract the encoder liked best.

  **Documents are versioned, never overwritten.** A changed document mints `<id>@v<n+1>`; the
  previous version is marked `superseded` and its chunks are kept (an old citation stays
  resolvable) but excluded from every normal search by the eligibility predicate. Re-ingesting
  identical content is a no-op: each document's content hash — which covers the derived chunks, not
  just the source bytes, so a chunker change is detected too — is compared first.

  **New documents start in `draft`, never `active`.** A PDF's own `Status: ACTIVE` text is not
  trusted: only the shipped source pack is admitted directly as `active` (`trusted_seed=True` at
  startup); anything ingested afterward requires a human to call `activate_version(...,
  verified_by=...)` before it can influence a single answer. A document can *demote* itself
  (`Status: DEPRECATED` is honoured) but cannot promote itself — that asymmetry is what stops an
  uploaded "agreement" from granting itself authority it was never given.

  **Two texts per chunk.** `text` is the exact source clause and the only thing ever quoted;
  `embed_text` prepends the document title, filename and section heading and is what the encoder
  embeds. Context helps *find* a clause and can never *become* the citation.

  **No score-derived topical-relevance gate.** Two were measured on this corpus and rejected: an
  absolute dense-distance cutoff (a genuine paraphrase and the best hit for a wholly unrelated
  question land 0.004 apart in cosine distance) and a corpus-relative z-score (a nonsense query
  scored a *stronger* statistical outlier than the real paraphrase). A 31-chunk corpus against a
  general-purpose encoder does not carry enough signal for either. Retrieval abstains
  (`needs_review`) only on the two facts it can actually verify — nothing eligible matched at all,
  or everything that matched was context-only — and leaves judging whether an excerpt answers the
  question to Medha, per the system prompt.
- Data privacy at the tool boundary: every structured lookup and document lookup checks customer `account_id`; cross-account access produces HTTP 403. This is not a prompt-only restriction.
- Internal proactive queue: each open ticket is classified against the current severity definitions and known-issue list, so tickets worded differently from the sample data are still triaged on their substance.
- Deterministic rule tools: service-credit and SLA answers come from code, not from the model re-reading a garbled PDF table, so they hold for any plan/severity or account/order combination.

## Trust model

| Source | Usage |
|---|---|
| Signed customer agreement | Highest authority for that account; it can override a default policy/SOP. |
| Current Support Policy v3 and current SOP | Default rule source. |
| Current product operations guide | Product capabilities and known issues. |
| Deprecated Support Policy v2 | Stored with `lifecycle_state='superseded'`; the retrieval predicate admits `active` only, so it is never a candidate. |
| Historical ticket resolutions | Indexed as context at authority 10 and account-scoped, in a hard band below every governing source. Never used to determine policy or actions. |

The dataset snapshot is fixed at `2026-08-16 11:00 Asia/Kolkata`, so credit lateness calculations do not depend on the machine clock.

## Deliberate limits / escalation behaviour

- The app does not execute a cancellation or issue a credit; only a mock escalation action exists, and it requires confirmation.
- It refuses to promise a credit when carrier/customer fault or pickup timing is unknown.
- Customer-facing operations are account scoped. Internal staff can access all assessment accounts; production should map SSO claims to a team/region/account entitlement table.
- The planner is an LLM (`Medha`, an OpenAI-compatible vLLM endpoint) and the app needs it to answer; if it is unreachable the API returns 503 rather than degrading to guesswork. Configure with `MEDHA_BASE_URL`, `MEDHA_API_KEY`, `MEDHA_MODEL`.
- That endpoint runs without `--enable-auto-tool-choice`, so native `tools` calls are rejected. Tool calls are driven through `response_format: json_schema` instead, which vLLM enforces during decoding: the model cannot emit a tool outside the set its role is allowed.
- Permission checks, source authority and the confirmation gate live in `Toolbox`/`app/rag`, not in
  the prompt, so prompt injection cannot widen access. The retrieval predicate is built from the
  session principal, so a planner that asks for another account's documents changes nothing about
  what SQL matches.
- Retrieval needs ParadeDB; if it is unreachable the API returns 503 rather than answering a policy
  question from the model's own memory of other companies' terms.
- Section chunking is tuned to these single-page, numbered-clause PDFs. A multi-page contract would
  want a token-window chunker with overlap, and the `draft`/`verified` lifecycle states exist in the
  schema but nothing in the supplied pack occupies them — everything here arrives already approved.
- `Alibaba-NLP/gte-base-en-v1.5` ships custom modelling code, so it loads with
  `trust_remote_code=True`, pinned to a specific commit (`PARCELPILOT_EMBEDDING_REVISION`) rather
  than a moving branch, and cached under `~/.cache/parcelpilot/models` rather than the ambient HF
  cache. Swapping to a model that does not need remote code (`gte-modernbert-base` is also 768-dim)
  is a `PARCELPILOT_EMBEDDING_MODEL` change; the ingest pipeline detects the model/revision change
  via `embedding_model` and re-embeds automatically rather than silently mixing vector spaces.
- Chunking is heading-aware (numbered clauses, `KI-` ids, `Section`/`Article` headers, or a generic
  short-title-line fallback) with a 400-token/50-token-overlap window for anything a heading-based
  section doesn't bound tightly enough. It has not been tuned against a multi-page contract with
  deeply nested numbering.

## If I continued the product

1. **Authenticated identity and audit ledger** — SSO/OIDC claims, row-level database security, immutable tool/action audit events, and action idempotency. This is the trust foundation.
2. **Document lifecycle controls** — the ingest pipeline, effective dates, agreement-to-account binding, versioning/supersession and human-gated activation (`draft -> verified -> active`, `app/rag/ingest.py`) now exist; what remains is a UI for the review step (today `activate_version()` is called directly) and semantic/version diff between two versions of a document.
3. **Quality system** — a scenario test set, retrieval citations checked by humans, policy-conflict tests, calibration/abstention metrics, and sampled support-QA review.
4. **Operational intelligence** — time-series anomaly detection, carrier/account clusters, SLA-clock computation with business calendars, and routing to an incident channel.
5. **Safe actions** — cancellation/credit workflows connected to real systems with policy checks repeated at execution time, manager approval thresholds, and customer notification drafts rather than automatic sends.

## Tests

```bash
pytest -q
```

`tests/test_agent.py` covers contract precedence, cross-account denial, a contract-specific
service-credit rule, confirmation before a state-changing escalation, SLA and credit resolution for
accounts with no signed agreement, and the graph's confirmation-gate topology.

`tests/test_rag.py` covers retrieval (36 tests): paraphrase recall through the dense branch, that a
customer with no agreement never gets another account's contract or tickets into either candidate
set, that the account which signed one gets it ranked first, that the superseded policy never
participates while the current one does, that a historical ticket can never land in `authoritative`
regardless of relevance score, that an agreement only governs the account that signed it, that
changing a document mints a new version and supersedes the old one without deleting its chunks, that
a document cannot self-promote to `active` and `activate_version` requires a named human, that
ingest/query tokenization is provably the same function, that a model/revision change re-embeds
instead of silently mixing vector spaces, an embedding smoke test, that re-ingesting identical
content writes nothing, and that citations are stable and carry page/section provenance.

Both need the database (`docker compose up -d db`) and network access to the planner endpoint.
There is no in-memory retrieval fallback to run against: a hybrid retriever verified against a
stand-in would prove nothing about the BM25 index, the exact vector search, or the SQL predicate
that is the security boundary.
