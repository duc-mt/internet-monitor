-- Internet Monitor database schema.
-- Applied idempotently at startup (CREATE TABLE IF NOT EXISTS).

-- journal_mode / synchronous / temp_store are set per connection in
-- app/database/connection.py (they are not properties of this script).
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    host            TEXT NOT NULL,
    protocol        TEXT NOT NULL CHECK (protocol IN ('icmp', 'tcp')),
    port            INTEGER,
    is_gateway      INTEGER NOT NULL DEFAULT 0,
    enabled         INTEGER NOT NULL DEFAULT 1,
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    created_at      TEXT NOT NULL
);

-- One row per completed check: since the Burst Probing engine, one burst of
-- 10-20 probes against a single target, reduced in memory to the summary
-- statistics below (the raw per-packet RTTs are never stored).
--   latency_ms / jitter_ms are the long-standing columns; for burst rows they
--   mirror median_ms / jitter_rfc3550 so older readers keep working. They are
--   NULL when every probe in the burst failed.
--   The percentile columns are NULL on rows written before the upgrade.
CREATE TABLE IF NOT EXISTS measurements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id       INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    timestamp       TEXT NOT NULL,
    latency_ms      REAL,
    packet_loss     REAL NOT NULL,
    jitter_ms       REAL,
    success         INTEGER NOT NULL,
    error           TEXT,
    -- Best-effort Wi-Fi SSID / "Wired (iface)" label, e.g. for telling
    -- "50ms because you're on cafe Wi-Fi" apart from "50ms on your home
    -- LAN". NULL when it couldn't be determined. See app/monitoring/network_info.py.
    network_name    TEXT,
    -- Burst Probing summary (all in milliseconds)
    median_ms       REAL,
    p25_ms          REAL,
    p75_ms          REAL,
    p95_ms          REAL,
    min_ms          REAL,
    max_ms          REAL,
    iqr_ms          REAL,
    jitter_rfc3550  REAL,
    packet_count    INTEGER
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

-- Long-term tier: one row per target per UTC hour, built by the hourly rollup
-- job from raw rows older than raw_retention_days (default 7) and kept for
-- data_retention_days (default 90). hour_bucket is 'YYYY-MM-DDTHH:00:00+00:00'
-- so it sorts and compares like the ISO timestamps in `measurements`.
-- min_ms / max_ms / avg_jitter_ms are extras beyond the minimum spec so
-- multi-day statistics can still report them.
CREATE TABLE IF NOT EXISTS ping_metrics_hourly (
    target_id     INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    hour_bucket   TEXT NOT NULL,
    avg_median_ms REAL,
    avg_iqr_ms    REAL,
    max_p95_ms    REAL,
    avg_loss_pct  REAL NOT NULL,
    sample_count  INTEGER NOT NULL,
    min_ms        REAL,
    max_ms        REAL,
    avg_jitter_ms REAL,
    PRIMARY KEY (target_id, hour_bucket)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_hourly_bucket ON ping_metrics_hourly(hour_bucket);

CREATE INDEX IF NOT EXISTS idx_outages_started ON outages(started_at);
CREATE INDEX IF NOT EXISTS idx_outages_active ON outages(ended_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
