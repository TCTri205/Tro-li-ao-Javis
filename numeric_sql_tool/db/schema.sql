CREATE TABLE IF NOT EXISTS public.alembic_version (
    version_num character varying(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

CREATE TABLE IF NOT EXISTS public.transcripts (
    id uuid NOT NULL,
    session_id character varying(64) NOT NULL,
    user_id uuid NOT NULL,
    meeting_date date NOT NULL,
    participants jsonb NOT NULL,
    speaker_count integer,
    duration_seconds integer,
    content_hash character(64) NOT NULL,
    raw_text text NOT NULL,
    summary text,
    summary_metadata jsonb,
    status character varying(20) NOT NULL,
    error text,
    qdrant_synced boolean DEFAULT false NOT NULL,
    ingest_tokens_in integer DEFAULT 0 NOT NULL,
    ingest_tokens_out integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    project_id uuid NOT NULL,
    CONSTRAINT transcripts_pkey PRIMARY KEY (id),
    CONSTRAINT transcripts_session_id_key UNIQUE (session_id)
);

CREATE TABLE IF NOT EXISTS public.chunks_passage (
    id uuid NOT NULL,
    transcript_id uuid NOT NULL,
    passage_index integer NOT NULL,
    time_start_sec integer,
    time_end_sec integer,
    speaker_list jsonb,
    text text NOT NULL,
    chunk_metadata jsonb NOT NULL,
    importance_score smallint,
    enrich_error text,
    qdrant_synced boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chunks_passage_pkey PRIMARY KEY (id),
    CONSTRAINT chunks_passage_transcript_id_passage_index_key UNIQUE (transcript_id, passage_index),
    CONSTRAINT chunks_passage_transcript_id_fkey FOREIGN KEY (transcript_id) REFERENCES public.transcripts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.chunks_turn (
    id uuid NOT NULL,
    transcript_id uuid NOT NULL,
    passage_id uuid,
    turn_index integer NOT NULL,
    speaker character varying(32) NOT NULL,
    time_start_sec integer NOT NULL,
    time_end_sec integer NOT NULL,
    text text NOT NULL,
    sub_chunk_index integer DEFAULT 0 NOT NULL,
    chunk_metadata jsonb NOT NULL,
    importance_score smallint,
    enrich_error text,
    qdrant_synced boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chunks_turn_pkey PRIMARY KEY (id),
    CONSTRAINT chunks_turn_transcript_id_turn_index_sub_chunk_index_key UNIQUE (transcript_id, turn_index, sub_chunk_index),
    CONSTRAINT chunks_turn_transcript_id_fkey FOREIGN KEY (transcript_id) REFERENCES public.transcripts(id) ON DELETE CASCADE,
    CONSTRAINT chunks_turn_passage_id_fkey FOREIGN KEY (passage_id) REFERENCES public.chunks_passage(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.company_documents (
    id uuid NOT NULL,
    filename character varying(255) NOT NULL,
    content_type character varying(255),
    size_bytes integer NOT NULL,
    stored_path text NOT NULL,
    content_hash character(64) NOT NULL,
    status character varying(20) NOT NULL,
    page_count integer,
    raw_text text,
    summary text,
    qdrant_synced boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT company_documents_pkey PRIMARY KEY (id),
    CONSTRAINT company_documents_content_hash_key UNIQUE (content_hash)
);

CREATE TABLE IF NOT EXISTS public.company_chunks (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    chunk_index integer NOT NULL,
    page_number integer,
    section_title text,
    text text NOT NULL,
    chunk_metadata jsonb,
    enrich_error text,
    qdrant_synced boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT company_chunks_pkey PRIMARY KEY (id),
    CONSTRAINT company_chunks_document_id_chunk_index_key UNIQUE (document_id, chunk_index),
    CONSTRAINT company_chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.company_documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_company_chunks_doc ON public.company_chunks USING btree (document_id);
CREATE INDEX IF NOT EXISTS ix_passage_metadata ON public.chunks_passage USING gin (chunk_metadata);
CREATE INDEX IF NOT EXISTS ix_passage_transcript ON public.chunks_passage USING btree (transcript_id);
CREATE INDEX IF NOT EXISTS ix_turn_metadata ON public.chunks_turn USING gin (chunk_metadata);
CREATE INDEX IF NOT EXISTS ix_turn_passage ON public.chunks_turn USING btree (passage_id);
CREATE INDEX IF NOT EXISTS ix_turn_speaker ON public.chunks_turn USING btree (speaker);
CREATE INDEX IF NOT EXISTS ix_turn_transcript ON public.chunks_turn USING btree (transcript_id);
CREATE INDEX IF NOT EXISTS ix_transcripts_project_date ON public.transcripts USING btree (project_id, meeting_date);
CREATE INDEX IF NOT EXISTS ix_transcripts_sync ON public.transcripts USING btree (qdrant_synced) WHERE (qdrant_synced = false);
CREATE INDEX IF NOT EXISTS ix_transcripts_user_date ON public.transcripts USING btree (user_id, meeting_date);
CREATE INDEX IF NOT EXISTS ix_transcripts_user_project_date ON public.transcripts USING btree (user_id, project_id, meeting_date);
