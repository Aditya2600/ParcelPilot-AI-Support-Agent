-- ParcelPilot hybrid retrieval schema (ParadeDB: pg_search + pgvector).
--
-- Idempotent by construction (IF NOT EXISTS everywhere) so re-running this file
-- against an already-migrated database is a safe no-op.
--
-- Documents are versioned and append-only. A changed document does not rewrite
-- its chunks: it becomes a new version, the previous version is marked
-- `superseded`, and its chunks stay queryable for audit. Retrieval never sees
-- them because the eligibility predicate admits `active` only.

CREATE EXTENSION IF NOT EXISTS pg_search;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Identity of one *version*: '05_Northstar....pdf@v2'. Citations pin this,
    -- so a quote can always be traced to the exact text that was in force.
    document_version_id  text NOT NULL UNIQUE,
    -- Identity of the logical document across all its versions. Not unique.
    document_id          text NOT NULL,
    version_number       integer NOT NULL,
    supersedes_version_id text REFERENCES rag_documents (document_version_id),

    source_file          text NOT NULL,
    title                text NOT NULL,
    document_type        text NOT NULL,   -- agreement|current_policy|sop|product_guide|historical_ticket
    lifecycle_state      text NOT NULL,   -- draft|verified|active|superseded
    account_id           text,            -- NULL = globally applicable
    authority            integer NOT NULL,
    effective_from       date,
    effective_to         date,

    -- sha256 over the source text *and* the chunks derived from it. Re-ingesting
    -- identical bytes through an unchanged pipeline compares equal and returns
    -- without touching a row; a chunker change does not.
    content_hash         text NOT NULL,
    -- Who moved this out of `draft`, and when. NULL means nobody has.
    verified_by          text,
    verified_at          timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    ingested_at          timestamptz NOT NULL DEFAULT now(),

    UNIQUE (document_id, version_number),
    UNIQUE (document_id, content_hash),
    CHECK (lifecycle_state IN ('draft', 'verified', 'active', 'superseded'))
);

CREATE INDEX IF NOT EXISTS rag_documents_document_idx ON rag_documents (document_id, version_number DESC);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chunk_id            text NOT NULL UNIQUE,   -- '<document_version_id>#<n>', the citation id
    document_db_id      bigint NOT NULL REFERENCES rag_documents (id) ON DELETE CASCADE,
    document_version_id text NOT NULL,
    document_id         text NOT NULL,
    chunk_index         integer NOT NULL,
    source_file         text NOT NULL,
    page                integer,
    section             text,                   -- nearest heading above this chunk
    char_start          integer NOT NULL,       -- offset into the page's extracted text
    char_end            integer NOT NULL,

    -- Exact source text. This, and only this, is ever quoted back to a user.
    text                text NOT NULL,
    -- Enriched retrieval surface: title, status, section heading, then the text.
    -- It is what the encoder embeds and what the lexical field is derived from.
    -- It is never returned as evidence, because those headers are not in the clause.
    embed_text          text NOT NULL,
    -- `embed_text` after the *same* tokenizer the query goes through, stored as
    -- whitespace-joined terms. Indexing this instead of raw prose is what makes
    -- ingest-time and query-time tokenization provably identical rather than two
    -- implementations that agree until one of them is edited.
    lexical_text        text NOT NULL,

    -- Denormalised from rag_documents so one WHERE clause filters both branches.
    account_id          text,
    document_type       text NOT NULL,
    lifecycle_state     text NOT NULL,
    authority           integer NOT NULL,
    effective_from      date,
    effective_to        date,

    content_hash        text NOT NULL,          -- sha256 of this chunk's text
    embedding           vector(768),
    embedding_model     text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    ingested_at         timestamptz NOT NULL DEFAULT now(),

    UNIQUE (document_version_id, chunk_index),
    CHECK (char_end >= char_start),
    CHECK (lifecycle_state IN ('draft', 'verified', 'active', 'superseded'))
);

CREATE INDEX IF NOT EXISTS rag_chunks_document_idx ON rag_chunks (document_id);
CREATE INDEX IF NOT EXISTS rag_chunks_version_idx ON rag_chunks (document_version_id);
-- The eligibility predicate, in the order it is most selective.
CREATE INDEX IF NOT EXISTS rag_chunks_eligibility_idx
    ON rag_chunks (lifecycle_state, account_id, document_type);

-- BM25 lexical index (pg_search, post-0.20 syntax: no paradedb.create_bm25
-- helper). key_field must be the numeric primary key. The eligibility columns
-- are indexed fields too, so the filter is applied inside the index scan rather
-- than as a heap filter after a LIMIT has already been taken.
CREATE INDEX IF NOT EXISTS rag_chunks_bm25_idx ON rag_chunks
USING bm25 (
    id,
    lexical_text,
    account_id,
    document_type,
    lifecycle_state,
    source_file
)
WITH (key_field = 'id');

-- Present for scale, not for correctness. Dense search runs exact today (see
-- `DenseRetriever`): an approximate index does not by itself guarantee that a
-- filtered query returns the true top-k of the eligible set, and eligibility is
-- a security property here rather than a ranking preference.
CREATE INDEX IF NOT EXISTS rag_chunks_embedding_hnsw_idx ON rag_chunks
USING hnsw (embedding vector_cosine_ops);
