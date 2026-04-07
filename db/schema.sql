-- Genesis AlloyDB Schema
-- Run once on your AlloyDB primary instance

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
-- Requires AlloyDB Omni / AlloyDB with google_ml_integration enabled:
-- CREATE EXTENSION IF NOT EXISTS google_ml_integration;

-- ── Core tables ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS projects (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name        TEXT NOT NULL,
  raw_input   TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tool_artifacts (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  tool        TEXT NOT NULL,          -- 'google_doc' | 'google_tasks' | 'google_calendar'
  external_id TEXT,                   -- resource ID in the external service
  url         TEXT,                   -- human-readable link
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_steps (
  id          BIGSERIAL PRIMARY KEY,
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  step        TEXT NOT NULL,          -- e.g. 'archivist', 'dispatcher', 'timekeeper'
  status      TEXT NOT NULL,          -- 'started' | 'done' | 'failed' | 'compensated'
  error       TEXT,
  ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Vector / embedding table ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS brain_dump_embeddings (
  id          BIGSERIAL PRIMARY KEY,
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  chunk       TEXT NOT NULL,
  embedding   vector(768)             -- text-embedding-004 produces 768-dim vectors
);

-- IVFFlat index for fast ANN search (build after bulk load)
-- CREATE INDEX ON brain_dump_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── Helpers ───────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

CREATE TRIGGER projects_updated_at
  BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
