CREATE TABLE IF NOT EXISTS local_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name VARCHAR(255) NOT NULL,
    file_sha256 CHAR(64) NOT NULL UNIQUE,
    file_type VARCHAR(10) NOT NULL,
    page_count INTEGER,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    character_count BIGINT NOT NULL DEFAULT 0,
    imported_by UUID REFERENCES app_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS local_document_chunks (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES local_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    content TEXT NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple'::regconfig, content)
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_local_document_chunks_search
    ON local_document_chunks USING GIN (search_vector);

CREATE INDEX IF NOT EXISTS idx_local_document_chunks_document
    ON local_document_chunks(document_id, chunk_index);
