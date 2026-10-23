-- Football pipeline warehouse schema.
-- Idempotent: safe to run on every DAG run (start_run task) and via docker-entrypoint-initdb.d.

CREATE SCHEMA IF NOT EXISTS football;

-- ---------------------------------------------------------------------------
-- Pipeline bookkeeping
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS football.pipeline_runs (
    run_id          TEXT PRIMARY KEY,
    competition     TEXT,
    season          INT,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'success', 'partial', 'failed')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    rows_extracted  JSONB NOT NULL DEFAULT '{}'::jsonb,
    rows_loaded     JSONB NOT NULL DEFAULT '{}'::jsonb,
    failed_tasks    TEXT[],
    error           TEXT
);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_started ON football.pipeline_runs (started_at DESC);

-- Raw landing zone: payloads exactly as returned by each source, one row per (run, source, entity).
CREATE TABLE IF NOT EXISTS football.raw_ingest (
    id            BIGSERIAL PRIMARY KEY,
    run_id        TEXT NOT NULL REFERENCES football.pipeline_runs (run_id) ON DELETE CASCADE,
    source        TEXT NOT NULL,
    entity        TEXT NOT NULL,
    record_count  INT  NOT NULL,
    payload       JSONB NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, source, entity)
);
CREATE INDEX IF NOT EXISTS ix_raw_ingest_fetched ON football.raw_ingest (fetched_at DESC);

CREATE TABLE IF NOT EXISTS football.dq_results (
    id           BIGSERIAL PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES football.pipeline_runs (run_id) ON DELETE CASCADE,
    check_name   TEXT NOT NULL,
    entity       TEXT NOT NULL,
    severity     TEXT NOT NULL CHECK (severity IN ('error', 'warning')),
    passed       BOOLEAN NOT NULL,
    failed_rows  INT NOT NULL DEFAULT 0,
    details      JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dq_results_run ON football.dq_results (run_id);

-- ---------------------------------------------------------------------------
-- Canonical (cross-source) model
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS football.teams (
    team_id        TEXT PRIMARY KEY,          -- canonical slug, e.g. 'manchester-united'
    name           TEXT NOT NULL,
    short_name     TEXT,
    tla            TEXT,
    founded        INT,
    venue          TEXT,
    crest_url      TEXT,
    website        TEXT,
    sources        TEXT[] NOT NULL DEFAULT '{}',
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every raw team label seen per source -> canonical team (audit trail for the name mapping).
CREATE TABLE IF NOT EXISTS football.team_aliases (
    alias       TEXT NOT NULL,
    source      TEXT NOT NULL,
    team_id     TEXT NOT NULL REFERENCES football.teams (team_id),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (alias, source)
);

CREATE TABLE IF NOT EXISTS football.matches (
    match_id         TEXT PRIMARY KEY,        -- '<competition>-<season>-<home>-vs-<away>'
    competition      TEXT NOT NULL,
    season           INT  NOT NULL,
    matchday         INT,
    utc_date         TIMESTAMPTZ,
    status           TEXT NOT NULL,
    home_team_id     TEXT NOT NULL REFERENCES football.teams (team_id),
    away_team_id     TEXT NOT NULL REFERENCES football.teams (team_id),
    home_score       SMALLINT CHECK (home_score >= 0),
    away_score       SMALLINT CHECK (away_score >= 0),
    source           TEXT NOT NULL,
    source_match_id  TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (home_team_id <> away_team_id)
);
CREATE INDEX IF NOT EXISTS ix_matches_comp_season_date ON football.matches (competition, season, utc_date);

CREATE TABLE IF NOT EXISTS football.standings (
    competition      TEXT NOT NULL,
    season           INT  NOT NULL,
    team_id          TEXT NOT NULL REFERENCES football.teams (team_id),
    position         INT,
    played           INT,
    won              INT,
    draw             INT,
    lost             INT,
    goals_for        INT,
    goals_against    INT,
    goal_difference  INT,
    points           INT,
    source           TEXT NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (competition, season, team_id)
);

-- Rows rejected by blocking data quality checks (quarantine branch). Never loaded into the model above.
CREATE TABLE IF NOT EXISTS football.quarantine (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES football.pipeline_runs (run_id) ON DELETE CASCADE,
    entity          TEXT NOT NULL,
    failed_checks   TEXT[] NOT NULL,
    record_count    INT NOT NULL,
    records         JSONB NOT NULL,
    quarantined_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, entity)
);
