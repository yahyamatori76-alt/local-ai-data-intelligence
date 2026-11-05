CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'analyst'
        CHECK (role IN ('admin', 'analyst', 'viewer')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE source_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_code VARCHAR(50) NOT NULL UNIQUE,
    source_name VARCHAR(150) NOT NULL,
    source_type VARCHAR(30) NOT NULL
        CHECK (source_type IN (
            'population', 'marketplace', 'system_log', 'other'
        )),
    description TEXT,
    authorized_purpose TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE import_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES source_registry(id),
    file_name VARCHAR(255),
    file_sha256 CHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    records_read INTEGER NOT NULL DEFAULT 0,
    records_loaded INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    imported_by UUID REFERENCES app_users(id),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE dukcapil_records (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES import_batches(id),
    record_ref VARCHAR(128) NOT NULL,
    masked_identity_ref VARCHAR(128),
    region_code VARCHAR(30),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    record_hash CHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (batch_id, record_ref)
);

CREATE TABLE marketplace_transactions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES import_batches(id),
    transaction_ref VARCHAR(128) NOT NULL,
    event_time TIMESTAMPTZ,
    status VARCHAR(40),
    amount NUMERIC(18,2),
    currency CHAR(3) DEFAULT 'IDR',
    authorized_join_ref VARCHAR(128),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (batch_id, transaction_ref)
);

CREATE TABLE system_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES import_batches(id),
    event_time TIMESTAMPTZ,
    severity VARCHAR(20),
    event_type VARCHAR(100),
    event_ref VARCHAR(128),
    authorized_join_ref VARCHAR(128),
    message TEXT,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE correlation_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_code VARCHAR(100) NOT NULL UNIQUE,
    rule_name VARCHAR(200) NOT NULL,
    rule_version INTEGER NOT NULL DEFAULT 1,
    rule_definition JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE correlation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES correlation_rules(id),
    batch_id UUID REFERENCES import_batches(id),
    left_source VARCHAR(50) NOT NULL,
    left_record_ref VARCHAR(128) NOT NULL,
    right_source VARCHAR(50) NOT NULL,
    right_record_ref VARCHAR(128) NOT NULL,
    match_method VARCHAR(50) NOT NULL,
    confidence NUMERIC(5,4),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_status VARCHAR(20) NOT NULL DEFAULT 'unreviewed'
        CHECK (review_status IN ('unreviewed', 'confirmed', 'rejected')),
    reviewed_by UUID REFERENCES app_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE analysis_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID REFERENCES app_users(id),
    action VARCHAR(100) NOT NULL,
    source_code VARCHAR(50),
    request_id UUID,
    parameters_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dukcapil_batch
    ON dukcapil_records(batch_id);
CREATE INDEX idx_marketplace_event_time
    ON marketplace_transactions(event_time);
CREATE INDEX idx_marketplace_join_ref
    ON marketplace_transactions(authorized_join_ref);
CREATE INDEX idx_system_events_time
    ON system_events(event_time);
CREATE INDEX idx_system_events_join_ref
    ON system_events(authorized_join_ref);
CREATE INDEX idx_correlation_created_at
    ON correlation_results(created_at);
CREATE INDEX idx_correlation_review
    ON correlation_results(review_status);
