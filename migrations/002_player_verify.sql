ALTER TABLE players ADD COLUMN ladder_uid TEXT;
ALTER TABLE players ADD COLUMN verify_nonce TEXT;
ALTER TABLE players ADD COLUMN verify_expires TEXT;
ALTER TABLE players ADD COLUMN linked_at TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_players_ladder_uid ON players(ladder_uid) WHERE ladder_uid IS NOT NULL;
