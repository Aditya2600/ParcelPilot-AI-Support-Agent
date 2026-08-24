# ParcelPilot Support Agent

A support agent for a logistics platform that answers both customer-facing and internal
support questions, grounded entirely in a supplied source pack — policies, SOPs, signed
customer agreements, a product guide, and historical tickets. Answers only ever come from
that source pack, never from the model's own memory of how "a" logistics company works.

## Demo Videos

| # | Title | Link |
|---|---|---|
| 1 | Architecture | https://www.loom.com/share/5027e795312145d887b80b1968fd2941 |
| 2 | ParcelPilot — Contract Override & Source Authority | https://www.loom.com/share/6c8ef492a6914eac928c21332d0acd83 |
| 3 | ParcelPilot — Multi-Step AI Support & Human-in-the-Loop Actions | https://www.loom.com/share/e287086abd014e1d8b9b1f31bb8ac7f1 |
| 4 | ParcelPilot — Tenant Isolation & Cross-Account Access Control | https://www.loom.com/share/83a52c6bf3fc4e309d3d4c6d055c86c0 |

## Contents

- [Demo Videos](#demo-videos)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Running the full stack in Docker](#running-the-full-stack-in-docker)
- [What it demonstrates](#what-it-demonstrates)
- [Retrieval design](#retrieval-design)
- [Trust model](#trust-model)
- [Deliberate limits](#deliberate-limits)
- [Tests](#tests)
- [Roadmap](#roadmap)

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    USER / SUPPORT AGENT                      │
│         (customer session, or internal support/ops role)     │
└───────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────┐
│  FRONTEND — Next.js, React, TypeScript, Tailwind, Radix UI    │
│                                                                │
│  Chat · account context · evidence panel · tool trace ·       │
│  escalation confirmation                                      │
└───────────────────────────────┬────────────────────────────────┘
                                 │ HTTPS / JSON  (CORS)
                                 ▼
┌──────────────────────────────────────────────────────────────┐
│  API — FastAPI                                                │
│                                                                │
│  Principal resolution · request validation · chat endpoint ·  │
│  confirmation endpoint · health check                         │
└───────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────┐
│  AGENT LOOP — LangGraph state machine                         │
│                                                                │
│    planner → execute tool → observation → planner → ...       │
│                     │                                          │
│                     ├─ another tool call                       │
│                     └─ final answer                            │
│                                                                │
│  State-changing flow:                                          │
│    planner → tool → confirmation gate → final answer only      │
└───────────────────────────────┬────────────────────────────────┘
                                 │  structured tool call
                                 ▼
┌──────────────────────────────────────────────────────────────┐
│  TOOLBOX — the enforcement boundary                            │
│                                                                │
│  The LLM chooses what it wants to do.                         │
│  The Toolbox decides what it is actually allowed to do.       │
│                                                                │
│  document_search · order_lookup · ticket_lookup ·              │
│  account_lookup · sla_lookup · calculate_credit ·               │
│  prepare_escalation · confirm_action · triage (proactive queue) │
└───────────┬─────────────────────────────────┬────────────────┘
            │                                 │
            ▼                                 ▼
┌───────────────────────┐        ┌─────────────────────────────┐
│  STRUCTURED DATA       │        │  RAG LAYER                  │
│                        │        │                             │
│  orders · tickets ·    │        │  ingest · chunking ·        │
│  accounts · pending    │        │  BM25 · dense vectors ·     │
│  actions               │        │  RRF fusion · authority      │
│                        │        │  resolution                 │
└───────────┬────────────┘        └──────────────┬──────────────┘
            │                                    │
            └──────────────────┬─────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│  ParadeDB — Postgres + pg_search (BM25) + pgvector             │
│                                                                │
│  documents & chunks · embeddings · accounts · orders ·         │
│  tickets · pending actions                                    │
└───────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────┐
│  LLM — external, OpenAI-compatible endpoint                   │
│                                                                │
│  Chooses tools · interprets evidence · writes the final answer │
│                                                                │
│  No database credentials. No mutation privileges. Every        │
│  permission and business-rule decision is enforced in the      │
│  Toolbox, not by the model.                                    │
└──────────────────────────────────────────────────────────────┘
```

### Components

| Layer | What it is | What it owns |
|---|---|---|
| **Frontend** (`frontend/`) | Next.js 16 / React 19, TypeScript, Tailwind, Radix UI | Chat UI, account/evidence/tool-trace panels. Talks to the API only via `NEXT_PUBLIC_API_BASE_URL`, baked into the client bundle at build time. |
| **API** (`main.py`) | FastAPI | Routes, CORS allow-list, health check. Delegates everything else to the agent. |
| **Agent loop** (`app/agent.py`, `app/graph.py`) | LangGraph state machine | Sequences plan → tool → observation cycles; forces final-answer-only mode after an action is staged. |
| **Toolbox** (`app/tools.py`) | Plain Python, no LLM involved | Every permission check, every business rule (credit calc, SLA lookup), the confirmation gate. This is the trust boundary — the LLM proposes, the Toolbox disposes. |
| **RAG layer** (`app/rag/`) | Python + SQL | Ingestion, chunking, hybrid retrieval, authority resolution. |
| **Store** | ParadeDB (Postgres + `pg_search` + `pgvector`) | One database, one set of rows, so lexical and dense search can't drift apart. Also holds the structured order/ticket/account tables. |
| **LLM** | External, OpenAI-compatible (served via vLLM) | Plans, reasons over evidence, writes prose. Never touches the database and never grants itself permissions — every access decision it "requests" is re-checked in the Toolbox. |

### A chat turn, end to end

1. Frontend sends `POST /api/chat` with the message and the current principal (who is asking).
2. The agent loop asks the LLM to plan: answer directly, or call a tool.
3. If a tool is called, the **Toolbox** checks the caller's permissions and runs it — a
   structured lookup, a hybrid document search, or a calculation. The result goes back to the
   LLM as an observation.
4. This repeats until the LLM either answers, or stages a state-changing action (an
   escalation). Staging routes into a **confirmation gate**: the LLM is now structurally
   limited to producing a final answer and cannot call another tool.
5. The response — answer, cited evidence, and the full tool trace — goes back to the frontend
   for display.

## Quickstart

Requires Python 3.10+, Node 22+ (for the frontend, if run outside Docker), and Docker (for
the retrieval store).

```bash
cd parcelpilot-agent
docker compose up -d db          # ParadeDB: pg_search (BM25) + pgvector (HNSW)
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

In a second terminal, run the frontend against that API:

```bash
cd frontend
cp .env.example .env.local       # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm install
npm run dev
```

Open `http://localhost:3000`. The UI ships with mock principals for two customers and two
internal roles.

First start applies the database migrations, downloads the embedding model (~550 MB, once),
and ingests the source pack. Later starts re-check each document's content hash and do
nothing when nothing changed.

## Running the full stack in Docker

One command starts the frontend, the API, and Postgres/ParadeDB together.

```bash
cd parcelpilot-agent
cp .env.example .env    # set the LLM endpoint/key, adjust ports if needed
docker compose up --build
```

Open `http://localhost:3000` — the frontend talks to the API published at
`http://localhost:8000`.

| Detail | Behaviour |
|---|---|
| **Health checks** | `db` uses `pg_isready`; `api` polls `GET /api/health`; `frontend` polls its own `/api/health`. Each service waits on the previous one via `service_healthy`. |
| **Startup work** | Migrations, connection pooling, and RAG ingest all run automatically when `api` starts — nothing extra to run. Ingest is content-hash gated, so restarts and rebuilds re-check every document and do no embedding work when nothing changed. |
| **Persistence** | Postgres data lives in the `parcelpilot_pg` volume; the downloaded embedding model lives in `parcelpilot_model_cache`. `docker compose down` (without `-v`) then `up` comes back with the same data and no re-download. |
| **Config** | Everything in `.env.example` is read from the environment already — `docker-compose.yml` only wires it through. `NEXT_PUBLIC_API_BASE_URL` is baked into the frontend at *build* time, so changing it needs `docker compose up --build`, not just a restart. |

Makefile shortcuts:

```bash
make up      # docker compose up --build -d
make down    # docker compose down
make logs    # docker compose logs -f
make test    # deterministic tests, host .venv, against the compose db (localhost:5434)
make eval    # live 28-case evaluation benchmark, host .venv
```

`make test` and `make eval` run on the host against the same Postgres the compose stack
publishes on `localhost:5434`, so they need `python -m venv .venv && pip install -r
requirements.txt` done once, same as the dev flow above.

## What it demonstrates

- **Natural-language chat** with a visible tool trace.
- **Three distinct tool types**: hybrid document search, scoped structured lookups (orders,
  tickets, accounts, credit/SLA calculation), and a mocked `create_escalation` action.
- **Explicit confirmation for anything state-changing**: an escalation is only staged, never
  created, until the user clicks **Confirm escalation** in the UI, which calls a separate
  confirmation endpoint.
- **Multi-step reasoning**: the LLM chooses tools and extracts arguments itself. A
  cancellation question typically triggers order lookup → account ownership → that account's
  agreement and the current SOP → whichever one governs.
- **Data privacy enforced in code, not in the prompt**: every lookup checks the caller's
  `account_id`; cross-account access returns HTTP 403 regardless of what the LLM asked for.
- **Proactive triage**: open tickets are classified against current severity definitions and
  the known-issue list, so tickets worded differently from the sample data are still
  triaged correctly.
- **Deterministic rule tools**: service-credit and SLA answers come from code, not from the
  model re-reading a PDF table, so they hold for any plan/severity/account combination.

## Retrieval design

Hybrid retrieval over the source pack, persisted in ParadeDB — BM25 (`pg_search`) and exact
cosine search (`pgvector`) run over the **same rows**, under the **same `WHERE` clause**, so
the two ranking signals can never see a different candidate set.

```
                         query
                           │
                           ▼
              ┌─────────────────────────┐
              │   ELIGIBILITY FILTER     │   one SQL predicate: account + lifecycle
              └────────────┬─────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
      ┌───────────────┐        ┌───────────────────┐
      │  BM25 search   │        │  Vector search     │
      │  (pg_search)   │        │  (pgvector, exact)  │
      └───────┬────────┘        └─────────┬──────────┘
              └────────────┬───────────────┘
                           ▼
              ┌─────────────────────────┐
              │  RECIPROCAL RANK FUSION  │   combines both rankings
              └────────────┬─────────────┘
                           ▼
              ┌─────────────────────────┐
              │   AUTHORITY RESOLUTION   │   agreement > policy/SOP > product guide > tickets
              └────────────┬─────────────┘
                           ▼
              ┌─────────────────────────┐
              │ AUTHORITATIVE / CONTEXT  │   split: can answer vs. background only
              └────────────┬─────────────┘
                           ▼
                   evidence → LLM
```

Six design decisions shape this pipeline — each one exists because the obvious alternative
was tried and failed on this corpus:

| Decision | Why |
|---|---|
| **Eligibility runs before search, not after.** The account/lifecycle filter is applied inside both the BM25 and vector queries, so another customer's documents are never in either candidate set — there is nothing to filter out later. | Tests assert on the raw candidate sets: "never retrieved" is a weaker guarantee than "never a candidate." |
| **Vector search is exact, not approximate.** The query forces a sequential scan instead of using the HNSW index, so `ORDER BY distance` is the true ranking of every eligible row. | Eligibility here is a security property, not a ranking preference — an approximate index doesn't guarantee the true top-k of a *filtered* set. At this corpus size, an exact scan costs nothing. |
| **One tokenizer for ingest and query.** The same `tokenize()` function builds the indexed text and the query terms. | Two independent tokenizer implementations can silently drift apart even if they agree today. |
| **Authority is resolved after fusion, as a separate step.** Fusion ranks by relevance only; authority then re-sorts into hard tiers (signed agreement → current policy/SOP → product guide → historical tickets), and a ticket can never enter the "may answer the question" tier no matter how close its embedding is. | A close-but-wrong match (a historical ticket) must never outrank a governing policy just because it scored well. An agreement only outranks policy for the account that signed it — everyone else gets ordinary policy-tier evidence. |
| **Documents are versioned, never overwritten.** A changed document becomes `<id>@v<n+1>`; the old version is marked superseded (chunks kept, so old citations still resolve) and excluded from all normal search. Re-ingesting identical content is a no-op via content hash. | Citations must stay resolvable even after a policy update, and re-running ingest must be safe to do repeatedly. |
| **New documents start in `draft`, never `active`.** Only the original source pack is trusted at startup; anything ingested afterward needs a human to call `activate_version(..., verified_by=...)`. A document can demote itself but never promote itself. | Stops an uploaded "agreement" from granting itself authority it was never given — a PDF's own `Status: ACTIVE` text is not trusted. |

Two more things worth knowing:

- **Two texts per chunk.** `text` is the exact source clause and the only thing ever quoted.
  `embed_text` adds the document title and section heading and is what gets embedded — it
  helps *find* a clause but can never *become* the citation.
- **No score-based relevance cutoff.** Both an absolute distance cutoff and a corpus-relative
  z-score were tested and rejected — on this small, single-domain corpus, a genuine paraphrase
  and an unrelated question can land within 0.004 cosine distance of each other. Retrieval
  only abstains (`needs_review`) on the two facts it can verify directly — nothing eligible
  matched, or everything that matched was context-only — and leaves judging *relevance* of a
  match to the LLM.

## Trust model

| Source | Usage |
|---|---|
| Signed customer agreement | Highest authority for that account; can override the default policy/SOP. |
| Current Support Policy v3 + current SOP | Default rule source. |
| Current product operations guide | Product capabilities and known issues. |
| Deprecated Support Policy v2 | Marked `superseded`; the retrieval predicate admits only `active` documents, so it is never a candidate. |
| Historical ticket resolutions | Context only, account-scoped, in a hard tier below every governing source — never used to determine policy or actions. |

The dataset snapshot is fixed at `2026-08-16 11:00 Asia/Kolkata`, so credit-lateness
calculations don't depend on the machine clock.

## Deliberate limits

**Scope**
- No cancellation or credit is ever actually executed — only a mocked, confirmation-gated
  escalation action exists.
- A credit is never promised when carrier/customer fault or pickup timing is unknown.
- Customer-facing operations are account-scoped; internal staff can see all assessment
  accounts. Production would map SSO claims to a team/region/account entitlement table
  instead.

**Reliability**
- The LLM planner is required, not optional — if it's unreachable, the API returns 503 rather
  than degrading to a guess. (Config: `MEDHA_BASE_URL` / `MEDHA_API_KEY` / `MEDHA_MODEL` — the
  env var names predate this doc and point at any OpenAI-compatible endpoint, not a specific
  model.)
- The LLM endpoint runs without native tool-calling; tool selection is instead enforced via
  constrained JSON-schema decoding, so the model literally cannot emit a tool outside the set
  its role is allowed to call.
- Retrieval needs ParadeDB — if it's unreachable, the API returns 503 rather than answering a
  policy question from the model's own training-data memory of other companies' terms.

**Security**
- Permission checks, source authority, and the confirmation gate all live in code
  (`Toolbox`/`app/rag`), never in the prompt — prompt injection can't widen access, because
  the retrieval predicate is built from the session's principal, not from anything the LLM
  supplies.

**Source pack**
- Section chunking is tuned to these single-page, numbered-clause PDFs; a multi-page contract
  would want a token-window chunker with overlap. The `draft`/`verified` lifecycle states
  exist in the schema but are unused here — everything in the pack arrives pre-approved.
- The embedding model (`Alibaba-NLP/gte-base-en-v1.5`) ships custom modelling code, so it's
  pinned to a specific commit and cached outside the ambient Hugging Face cache. A model or
  revision change is detected automatically and triggers a full re-embed rather than silently
  mixing vector spaces.
- Chunking is heading-aware (numbered clauses, `KI-` ids, section headers) with a token-window
  fallback for anything a heading doesn't bound tightly. It hasn't been tuned against a
  multi-page contract with deeply nested numbering.

## Tests

```bash
pytest -q
```

- **`tests/test_agent.py`** — contract precedence, cross-account denial, a contract-specific
  service-credit rule, confirmation before a state-changing escalation, SLA/credit resolution
  for accounts with no signed agreement, and the graph's confirmation-gate topology.
- **`tests/test_rag.py`** (36 tests) — paraphrase recall, that a customer with no agreement
  never gets another account's contract or tickets into either candidate set, that the
  signing account gets its own agreement ranked first, that a superseded policy never
  participates while the current one does, that a historical ticket can never land in
  `authoritative` regardless of score, that a document version change supersedes without
  deleting old chunks, that self-promotion to `active` is impossible, that ingest and query
  use the provably same tokenizer, that a model/revision change forces a re-embed, and that
  citations are stable with page/section provenance.

Both suites need the database (`docker compose up -d db`) and network access to the LLM
endpoint — there's no in-memory retrieval fallback, since a hybrid retriever tested against a
stand-in would prove nothing about the BM25 index, the exact vector search, or the SQL
predicate that is the actual security boundary.

## Roadmap

If this went further as a product, in priority order:

1. **Authenticated identity and audit ledger** — SSO/OIDC claims, row-level database
   security, immutable tool/action audit events, action idempotency. The trust foundation
   everything else sits on.
2. **Document lifecycle UI** — versioning, supersession, and human-gated activation
   (`draft → verified → active`) already exist in the pipeline; what's missing is a review UI
   (today `activate_version()` is called directly) and a semantic diff between document
   versions.
3. **Quality system** — a scenario test set, human-checked retrieval citations,
   policy-conflict tests, calibration/abstention metrics, sampled support-QA review.
4. **Operational intelligence** — time-series anomaly detection, carrier/account clustering,
   SLA-clock computation with business calendars, routing into an incident channel.
5. **Safe actions** — cancellation/credit workflows wired to real systems, with policy checks
   re-run at execution time, manager approval thresholds, and drafted (not auto-sent) customer
   notifications.
