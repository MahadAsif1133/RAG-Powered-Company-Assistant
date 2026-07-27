-- ============================================================
-- Company Knowledge Assistant — Postgres / Supabase Schema
-- ============================================================
-- Run this entire file in the Supabase SQL Editor.
-- Order matters: extensions → enums → tables → indexes → functions → RLS.

-- ── 0. Extensions ────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector

-- ── 1. Enums ─────────────────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE user_role AS ENUM ('admin', 'employee');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE document_status AS ENUM ('processing', 'ready', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── 2. Core Tables ───────────────────────────────────────────

-- Organizations (tenants)
CREATE TABLE IF NOT EXISTS organizations (
  id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name        text NOT NULL,
  slug        text NOT NULL UNIQUE,           -- URL-safe identifier (e.g. "acme-corp")
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Users (mirrors Supabase auth.users)
-- id MUST match auth.users.id so JWT claims resolve directly.
CREATE TABLE IF NOT EXISTS users (
  id          uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  role        user_role NOT NULL DEFAULT 'employee',
  full_name   text,
  email       text,                           -- denormalized for convenience
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, org_id)
);

-- Documents (uploaded files metadata)
CREATE TABLE IF NOT EXISTS documents (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  filename      text NOT NULL,                -- storage key / sanitized name
  original_name text NOT NULL,               -- user-visible original filename
  file_type     text NOT NULL,               -- 'pdf' | 'docx' | 'txt'
  file_size     bigint,                       -- bytes
  uploaded_by   uuid NOT NULL REFERENCES users(id),
  status        document_status NOT NULL DEFAULT 'processing',
  chunk_count   int,                          -- populated after indexing
  error_msg     text,                         -- populated on failure
  uploaded_at   timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- Document Chunks (the actual vectorized content)
-- NOTE: vector(1024) = Voyage AI voyage-3-large dimensions.
--       If using OpenAI text-embedding-3-small, change to vector(1536).
CREATE TABLE IF NOT EXISTS document_chunks (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,  -- denormalized for fast org-scoped search
  chunk_index   int NOT NULL,
  chunk_text    text NOT NULL,
  embedding     vector(1024) NOT NULL,
  token_count   int,                          -- approximate, for debugging
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index)
);

-- Query Logs (every RAG query, for analytics)
CREATE TABLE IF NOT EXISTS query_logs (
  id                      uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id                  uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id                 uuid REFERENCES users(id) ON DELETE SET NULL,
  question                text NOT NULL,
  retrieved_chunk_ids     uuid[],             -- top-k chunk IDs used for context
  answer                  text NOT NULL,
  was_answered_confidently boolean NOT NULL DEFAULT true,
  latency_ms              int,                -- end-to-end query latency
  created_at              timestamptz NOT NULL DEFAULT now()
);

-- Slack Workspace Mapping (Milestone 5)
CREATE TABLE IF NOT EXISTS slack_workspaces (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  slack_team_id text NOT NULL UNIQUE,         -- Slack workspace/team ID (T...)
  slack_team_name text,
  installed_at  timestamptz NOT NULL DEFAULT now()
);

-- Slack Users (maps Slack user IDs to internal users)
CREATE TABLE IF NOT EXISTS slack_users (
  id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         uuid REFERENCES users(id) ON DELETE SET NULL,
  org_id          uuid NOT NULL REFERENCES organizations(id),
  slack_user_id   text NOT NULL,              -- Slack user ID (U...)
  slack_team_id   text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (slack_user_id, slack_team_id)
);

-- ── 3. Indexes ───────────────────────────────────────────────

-- HNSW vector index for fast ANN search on embeddings.
-- m=16, ef_construction=64 are good defaults for <1M chunks.
-- Recreate this index if you change the vector dimension.
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
  ON document_chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Org-scoped queries
CREATE INDEX IF NOT EXISTS idx_document_chunks_org_id
  ON document_chunks (org_id);

CREATE INDEX IF NOT EXISTS idx_documents_org_id
  ON documents (org_id);

CREATE INDEX IF NOT EXISTS idx_query_logs_org_id_created
  ON query_logs (org_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_users_org_id
  ON users (org_id);

-- ── 4. Updated_at Trigger ────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_documents_updated_at ON documents;
CREATE TRIGGER set_documents_updated_at
  BEFORE UPDATE ON documents
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── 5. Vector Similarity Search Function ─────────────────────
-- Called via supabase.rpc('match_document_chunks', {...})
-- Returns top-k chunks for a given org, ordered by cosine similarity.
CREATE OR REPLACE FUNCTION match_document_chunks(
  query_embedding  vector(1024),
  p_org_id         uuid,
  match_count      int DEFAULT 5,
  similarity_threshold float DEFAULT 0.3
)
RETURNS TABLE (
  id              uuid,
  chunk_text      text,
  similarity      float,
  document_id     uuid,
  chunk_index     int,
  filename        text,
  original_name   text
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    dc.id,
    dc.chunk_text,
    1 - (dc.embedding <=> query_embedding) AS similarity,
    dc.document_id,
    dc.chunk_index,
    d.filename,
    d.original_name
  FROM document_chunks dc
  JOIN documents d ON d.id = dc.document_id
  WHERE
    dc.org_id = p_org_id
    AND d.status = 'ready'
    AND 1 - (dc.embedding <=> query_embedding) > similarity_threshold
  ORDER BY dc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- ── 6. Row-Level Security (RLS) ──────────────────────────────
-- Enable RLS on all tables. The backend uses the service-role key
-- which bypasses RLS — this protects direct anon access.

ALTER TABLE organizations      ENABLE ROW LEVEL SECURITY;
ALTER TABLE users              ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents          ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks    ENABLE ROW LEVEL SECURITY;
ALTER TABLE query_logs         ENABLE ROW LEVEL SECURITY;
ALTER TABLE slack_workspaces   ENABLE ROW LEVEL SECURITY;
ALTER TABLE slack_users        ENABLE ROW LEVEL SECURITY;

-- Users can only see their own org's data
CREATE POLICY "users_own_org" ON users
  FOR ALL USING (org_id = (
    SELECT org_id FROM users WHERE id = auth.uid()
  ));

CREATE POLICY "documents_own_org" ON documents
  FOR ALL USING (org_id = (
    SELECT org_id FROM users WHERE id = auth.uid()
  ));

CREATE POLICY "chunks_own_org" ON document_chunks
  FOR ALL USING (org_id = (
    SELECT org_id FROM users WHERE id = auth.uid()
  ));

CREATE POLICY "query_logs_own_org" ON query_logs
  FOR ALL USING (org_id = (
    SELECT org_id FROM users WHERE id = auth.uid()
  ));

-- ── 7. Seed: Demo Organization (remove before production) ────
-- INSERT INTO organizations (name, slug) VALUES ('Demo Corp', 'demo-corp')
-- ON CONFLICT (slug) DO NOTHING;

-- ============================================================
-- DONE. Verify by checking:
--   SELECT * FROM pg_extension WHERE extname = 'vector';
--   \d document_chunks   -- should show embedding column type vector(1024)
--   SELECT indexname FROM pg_indexes WHERE tablename = 'document_chunks';
-- ============================================================
