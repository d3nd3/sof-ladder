CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id TEXT NOT NULL UNIQUE,
    sof_name TEXT,
    elo INTEGER NOT NULL DEFAULT 1000,
    games_played INTEGER NOT NULL DEFAULT 0,
    strikes INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'idle',
    cooldown_until TEXT,
    active_match_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'pending_accept',
    port INTEGER,
    map_name TEXT NOT NULL DEFAULT 'dm/jpntclx',
    password TEXT,
    rcon_password TEXT,
    player_a_id INTEGER NOT NULL REFERENCES players(id),
    player_b_id INTEGER NOT NULL REFERENCES players(id),
    winner_id INTEGER REFERENCES players(id),
    accept_deadline TEXT,
    server_started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (player_a_id) REFERENCES players(id),
    FOREIGN KEY (player_b_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS match_players (
    match_id INTEGER NOT NULL REFERENCES matches(id),
    player_id INTEGER NOT NULL REFERENCES players(id),
    rating_before INTEGER,
    rating_after INTEGER,
    delta INTEGER,
    k_used INTEGER,
    frags INTEGER DEFAULT 0,
    connected_at TEXT,
    PRIMARY KEY (match_id, player_id)
);

CREATE TABLE IF NOT EXISTS queue_entries (
    player_id INTEGER PRIMARY KEY REFERENCES players(id),
    enqueued_at TEXT NOT NULL DEFAULT (datetime('now')),
    elo_at_queue INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS penalty_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    reason TEXT NOT NULL,
    penalty_type TEXT NOT NULL,
    match_id INTEGER REFERENCES matches(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS queue_join_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_players_state ON players(state);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_queue_enqueued ON queue_entries(enqueued_at);
