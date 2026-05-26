CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS meetings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    title TEXT NOT NULL,
    meeting_date DATE NOT NULL,
    speaker_count INT NOT NULL CHECK (speaker_count >= 0),
    duration_seconds INT NOT NULL CHECK (duration_seconds >= 0),
    summary TEXT,
    topics JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_language VARCHAR(10) NOT NULL DEFAULT 'ja' CHECK (source_language = 'ja'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS passages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    passage_index INT NOT NULL CHECK (passage_index >= 0),
    content TEXT NOT NULL,
    topics JSONB NOT NULL DEFAULT '[]'::jsonb,
    entities JSONB NOT NULL DEFAULT '[]'::jsonb,
    keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    turn_types TEXT[] NOT NULL DEFAULT '{}',
    has_action_item BOOLEAN NOT NULL DEFAULT FALSE,
    action_item_text TEXT,
    has_question BOOLEAN NOT NULL DEFAULT FALSE,
    question_text TEXT,
    amounts JSONB NOT NULL DEFAULT '[]'::jsonb,
    dates_mentioned JSONB NOT NULL DEFAULT '[]'::jsonb,
    sentiment VARCHAR(20) NOT NULL CHECK (sentiment IN ('positive', 'negative', 'neutral')),
    importance_score INT NOT NULL CHECK (importance_score BETWEEN 1 AND 5),
    enrichment_status VARCHAR(20) NOT NULL DEFAULT 'success' CHECK (enrichment_status IN ('success', 'llm_failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_passage_per_meeting UNIQUE (meeting_id, passage_index)
);

CREATE TABLE IF NOT EXISTS turns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    passage_id UUID NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    turn_index INT NOT NULL CHECK (turn_index >= 0),
    speaker TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_turn_per_passage UNIQUE (passage_id, turn_index)
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    id SERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    alias TEXT NOT NULL,
    language CHAR(2) NOT NULL CHECK (language = 'ja'),
    entity_type VARCHAR(50),
    UNIQUE (alias, language)
);

CREATE TABLE IF NOT EXISTS commitments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    passage_id UUID NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    person TEXT NOT NULL,
    action TEXT NOT NULL,
    deadline TEXT,
    deadline_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_passages_meeting_id ON passages (meeting_id);
CREATE INDEX IF NOT EXISTS idx_turns_passage_id ON turns (passage_id);
CREATE INDEX IF NOT EXISTS idx_turns_meeting_id ON turns (meeting_id);
CREATE INDEX IF NOT EXISTS idx_meetings_meeting_date ON meetings (meeting_date);
CREATE INDEX IF NOT EXISTS idx_passages_sentiment ON passages (sentiment);
CREATE INDEX IF NOT EXISTS idx_passages_importance ON passages (importance_score);
CREATE INDEX IF NOT EXISTS idx_commitments_passage_id ON commitments (passage_id);
CREATE INDEX IF NOT EXISTS idx_commitments_meeting_id ON commitments (meeting_id);
CREATE INDEX IF NOT EXISTS idx_commitments_person ON commitments (person);
CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments (status);
CREATE INDEX IF NOT EXISTS idx_passages_topics ON passages USING gin (topics);
CREATE INDEX IF NOT EXISTS idx_passages_entities ON passages USING gin (entities);
CREATE INDEX IF NOT EXISTS idx_passages_amounts ON passages USING gin (amounts);
CREATE INDEX IF NOT EXISTS idx_passages_turn_types ON passages USING gin (turn_types);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_trgm ON entity_aliases USING gin (alias gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_turns_embedding ON turns USING hnsw (embedding vector_cosine_ops);

CREATE OR REPLACE VIEW v_topics AS
SELECT
    m.id AS meeting_id,
    m.title AS meeting_title,
    m.meeting_date,
    p.id AS passage_id,
    t.value::text AS topic,
    'topic' AS source_type
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
CROSS JOIN LATERAL jsonb_array_elements_text(p.topics) AS t
UNION ALL
SELECT
    m.id,
    m.title,
    m.meeting_date,
    p.id,
    e.value::text AS topic,
    'entity' AS source_type
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
CROSS JOIN LATERAL jsonb_array_elements_text(p.entities) AS e;

CREATE OR REPLACE VIEW v_commitments AS
SELECT
    m.id AS meeting_id,
    m.title AS meeting_title,
    m.meeting_date,
    c.passage_id,
    c.id AS commitment_id,
    c.person,
    c.action,
    c.deadline,
    c.deadline_date,
    c.status
FROM meetings m
JOIN commitments c ON c.meeting_id = m.id;

CREATE OR REPLACE VIEW v_amounts AS
SELECT
    m.id AS meeting_id,
    m.title AS meeting_title,
    m.meeting_date,
    p.id AS passage_id,
    (a.value->>'value')::numeric AS amount_value,
    a.value->>'unit' AS amount_unit,
    a.value->>'currency' AS amount_currency,
    a.value->>'context' AS amount_context
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
CROSS JOIN LATERAL jsonb_array_elements(p.amounts) AS a;

CREATE OR REPLACE VIEW v_action_items AS
SELECT
    m.id AS meeting_id,
    m.title AS meeting_title,
    m.meeting_date,
    p.id AS passage_id,
    p.action_item_text,
    p.importance_score
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
WHERE p.has_action_item = true;

CREATE OR REPLACE VIEW v_open_questions AS
SELECT
    m.id AS meeting_id,
    m.title AS meeting_title,
    m.meeting_date,
    p.id AS passage_id,
    p.question_text,
    p.importance_score
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
WHERE p.has_question = true;

CREATE OR REPLACE VIEW v_statements AS
SELECT
    m.id AS meeting_id,
    m.title AS meeting_title,
    m.meeting_date,
    p.id AS passage_id,
    p.turn_types,
    p.has_action_item,
    p.has_question,
    p.sentiment,
    p.importance_score,
    p.content
FROM meetings m
JOIN passages p ON p.meeting_id = m.id;

CREATE OR REPLACE VIEW v_dates AS
SELECT
    m.id AS meeting_id,
    m.title AS meeting_title,
    m.meeting_date,
    p.id AS passage_id,
    d.value->>'raw_text' AS date_raw_text,
    NULLIF(d.value->>'resolved_date', '')::date AS date_resolved,
    (d.value->>'confidence')::numeric AS confidence
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
CROSS JOIN LATERAL jsonb_array_elements(p.dates_mentioned) AS d;

CREATE OR REPLACE VIEW v_speaker_turns AS
SELECT
    m.id AS meeting_id,
    m.title AS meeting_title,
    m.meeting_date,
    t.speaker,
    t.content AS turn_content,
    t.timestamp,
    p.turn_types,
    p.sentiment,
    p.importance_score
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
JOIN turns t ON t.passage_id = p.id;

ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE passages ENABLE ROW LEVEL SECURITY;
ALTER TABLE turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE commitments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_policy ON meetings;
CREATE POLICY tenant_isolation_policy ON meetings
USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

DROP POLICY IF EXISTS tenant_isolation_policy ON passages;
CREATE POLICY tenant_isolation_policy ON passages
USING (meeting_id IN (SELECT id FROM meetings));

DROP POLICY IF EXISTS tenant_isolation_policy ON turns;
CREATE POLICY tenant_isolation_policy ON turns
USING (meeting_id IN (SELECT id FROM meetings));

DROP POLICY IF EXISTS tenant_isolation_policy ON commitments;
CREATE POLICY tenant_isolation_policy ON commitments
USING (meeting_id IN (SELECT id FROM meetings));
