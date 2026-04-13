-- schema.sql — Full SQLite schema for the contingency reporter
-- Execute once via db_manager.execute_script() on first run.
-- Schema version tracked via PRAGMA user_version = 1.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── Grid topology ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    voltage_kv  REAL    NOT NULL,
    node_type   TEXT,                        -- 'busbar', 'junction', 'auxiliary'
    substation  TEXT,
    x_coord     REAL,
    y_coord     REAL
);

CREATE TABLE IF NOT EXISTS branches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    from_node_id INTEGER REFERENCES nodes(id),
    to_node_id   INTEGER REFERENCES nodes(id),
    branch_type  TEXT    NOT NULL,           -- 'line', 'cable', 'transformer'
    length_km    REAL,                       -- NULL for transformers
    i_max_ka     REAL,
    voltage_kv   REAL    NOT NULL,
    sn_mva       REAL                        -- NULL for lines/cables
);

CREATE TABLE IF NOT EXISTS loads (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL UNIQUE,
    node_id INTEGER NOT NULL REFERENCES nodes(id),
    p_mw    REAL    NOT NULL,
    q_mvar  REAL    NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS generators (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT    NOT NULL UNIQUE,
    node_id  INTEGER NOT NULL REFERENCES nodes(id),
    p_mw     REAL    NOT NULL,
    gen_type TEXT                             -- 'sync', 'pv', 'wind', 'slack'
);

-- ── Base load flow results (pre-contingency) ──────────────────────────────────

CREATE TABLE IF NOT EXISTS base_loadflow (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    element_id   INTEGER NOT NULL,
    element_type TEXT    NOT NULL,            -- 'branch' or 'node'
    loading_pct  REAL,
    u_pu         REAL,
    UNIQUE(element_id, element_type)
);

-- ── Contingency definitions ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS contingencies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    outage_element_id   INTEGER NOT NULL REFERENCES branches(id),
    outage_element_name TEXT    NOT NULL,
    n_level             INTEGER NOT NULL DEFAULT 1,  -- 1 = N-1, 2 = N-2
    outage_type         TEXT    NOT NULL,             -- 'line', 'cable', 'transformer'
    timestamp           TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── Per-contingency results ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS branch_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    contingency_id INTEGER NOT NULL REFERENCES contingencies(id) ON DELETE CASCADE,
    branch_id      INTEGER NOT NULL REFERENCES branches(id),
    loading_pct    REAL    NOT NULL,
    i_ka           REAL,
    p_mw           REAL,
    q_mvar         REAL,
    UNIQUE(contingency_id, branch_id)
);

CREATE TABLE IF NOT EXISTS node_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    contingency_id INTEGER NOT NULL REFERENCES contingencies(id) ON DELETE CASCADE,
    node_id        INTEGER NOT NULL REFERENCES nodes(id),
    u_pu           REAL    NOT NULL,
    u_kv           REAL,
    angle_deg      REAL,
    UNIQUE(contingency_id, node_id)
);

-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_br_cont   ON branch_results(contingency_id);
CREATE INDEX IF NOT EXISTS idx_br_branch ON branch_results(branch_id);
CREATE INDEX IF NOT EXISTS idx_br_load   ON branch_results(loading_pct DESC);
CREATE INDEX IF NOT EXISTS idx_nr_cont   ON node_results(contingency_id);
CREATE INDEX IF NOT EXISTS idx_nr_node   ON node_results(node_id);
CREATE INDEX IF NOT EXISTS idx_nr_upu    ON node_results(u_pu);
CREATE INDEX IF NOT EXISTS idx_cont_elem ON contingencies(outage_element_id);
