-- ============================================================
-- pgvector similarity search function
-- Run this in the Supabase SQL Editor (or it's included in schema.sql already)
-- ============================================================
-- This function is called via: supabase.rpc('match_document_chunks', {...})
--
-- NOTE: vector(1024) = Voyage AI voyage-3-large.
--       Change to vector(1536) if using OpenAI text-embedding-3-small.

CREATE OR REPLACE FUNCTION match_document_chunks(
  query_embedding        vector(1024),
  p_org_id               uuid,
  match_count            int     DEFAULT 5,
  similarity_threshold   float   DEFAULT 0.3
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
  ORDER BY dc.embedding <=> query_embedding   -- cosine distance (ascending = more similar)
  LIMIT match_count;
END;
$$;

-- Grant execute permission to authenticated users
-- (backend uses service_role which already bypasses this, but good practice)
GRANT EXECUTE ON FUNCTION match_document_chunks TO authenticated;
GRANT EXECUTE ON FUNCTION match_document_chunks TO service_role;
