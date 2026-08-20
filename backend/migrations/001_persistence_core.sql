BEGIN;

CREATE TABLE IF NOT EXISTS app_users (
    user_id uuid PRIMARY KEY,
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    roles text[] NOT NULL DEFAULT ARRAY['viewer']::text[],
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS job_executions (
    execution_id uuid PRIMARY KEY,
    job_type text NOT NULL,
    status text NOT NULL,
    requested_by uuid NULL REFERENCES app_users(user_id),
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NULL,
    completed_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_job_executions_type_created
    ON job_executions (job_type, created_at DESC);

CREATE TABLE IF NOT EXISTS job_results (
    execution_id uuid PRIMARY KEY REFERENCES job_executions(execution_id) ON DELETE CASCADE,
    result jsonb NOT NULL,
    schema_version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS collector_states (
    collector_name text PRIMARY KEY,
    state jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS funds_flow_snapshots (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    as_of_date date NULL,
    generated_at timestamptz NOT NULL UNIQUE,
    schema_version integer NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_funds_flow_snapshots_as_of
    ON funds_flow_snapshots (as_of_date DESC, generated_at DESC);

CREATE TABLE IF NOT EXISTS funds_flow_snapshot_summaries (
    generated_at timestamptz PRIMARY KEY,
    as_of_date date NULL,
    period text NOT NULL,
    summary jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS market_timeseries (
    series_key text NOT NULL,
    observed_at timestamptz NOT NULL,
    value double precision NULL,
    dimensions jsonb NOT NULL DEFAULT '{}'::jsonb,
    source text NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT now()
) PARTITION BY RANGE (observed_at);

CREATE TABLE IF NOT EXISTS market_timeseries_default
    PARTITION OF market_timeseries DEFAULT;

CREATE INDEX IF NOT EXISTS ix_market_timeseries_lookup
    ON market_timeseries (series_key, observed_at DESC);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id uuid PRIMARY KEY,
    execution_id uuid NULL REFERENCES job_executions(execution_id),
    kind text NOT NULL,
    storage_uri text NOT NULL,
    content_type text NULL,
    checksum_sha256 text NULL,
    size_bytes bigint NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
