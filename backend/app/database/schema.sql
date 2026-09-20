-- Internet Monitor database schema.
-- Applied idempotently at startup (CREATE TABLE IF NOT EXISTS).

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    host            TEXT NOT NULL,
    protocol        TEXT NOT NULL CHECK (protocol IN ('icmp', 'tcp')),
    port            INTEGER,
    is_gateway      INTEGER NOT NULL DEFAULT 0,
    enabled         INTEGER NOT NULL DEFAULT 1,
    interval_seconds INTEGER NOT NULL DEFAULT 5,
    created_at      TEXT NOT NULL
);

-- One row per completed check (a small batch of pings/connects against a
-- single target). latency_ms/jitter_ms are NULL when every attempt in the
-- batch failed.
CREATE TABLE IF NOT EXISTS measurements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id       INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    timestamp       TEXT NOT NULL,
    latency_ms      REAL,
    packet_loss     REAL NOT NULL,
    jitter_ms       REAL,
    success         INTEGER NOT NULL,
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_measurements_target_ts ON measurements(target_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_measurements_ts ON measurements(timestamp);

CREATE TABLE IF NOT EXISTS outages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT NOT NULL,
    ended_at         TEXT,
    duration_seconds REAL,
    reason           TEXT,
    affected_targets TEXT NOT NULL DEFAULT '[]',
    failed_checks    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_outages_started ON outages(started_at);
CREATE INDEX IF NOT EXISTS idx_outages_active ON outages(ended_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
