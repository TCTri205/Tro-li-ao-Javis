-- Migration: Create golden_queries table and vector index
CREATE TABLE IF NOT EXISTS golden_queries (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL UNIQUE,
    sql TEXT NOT NULL,
    embedding vector(1536)
);

CREATE INDEX IF NOT EXISTS idx_golden_queries_embedding ON golden_queries USING hnsw (embedding vector_cosine_ops);
