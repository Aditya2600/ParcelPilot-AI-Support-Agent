-- ParcelPilot state-changing actions and escalations schema.
--
-- Pending actions are prepared server-side with verified account/ticket links
-- and an expiry timestamp (15 minutes).
-- Escalations are append-only confirmed state-changing records with canonical
-- escalation_id generated directly from identity.

CREATE TABLE IF NOT EXISTS escalations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    escalation_id text GENERATED ALWAYS AS ('ESC-' || lpad(id::text, 4, '0')) STORED UNIQUE,
    ticket_id text,
    account_id text NOT NULL,
    reason text NOT NULL,
    severity text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (severity IN ('P1', 'P2', 'P3'))
);

CREATE INDEX IF NOT EXISTS escalations_account_idx ON escalations (account_id);
CREATE INDEX IF NOT EXISTS escalations_ticket_idx ON escalations (ticket_id);

CREATE TABLE IF NOT EXISTS pending_actions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    confirmation_token text NOT NULL UNIQUE,
    action text NOT NULL DEFAULT 'create_escalation',
    ticket_id text,
    account_id text NOT NULL,
    reason text NOT NULL,
    severity text NOT NULL,
    prepared_by text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    escalation_id text REFERENCES escalations (escalation_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '15 minutes'),
    confirmed_at timestamptz,
    CHECK (severity IN ('P1', 'P2', 'P3')),
    CHECK (status IN ('pending', 'confirmed', 'cancelled', 'expired'))
);

CREATE INDEX IF NOT EXISTS pending_actions_token_idx ON pending_actions (confirmation_token);
CREATE INDEX IF NOT EXISTS pending_actions_account_idx ON pending_actions (account_id);
CREATE INDEX IF NOT EXISTS pending_actions_prepared_by_idx ON pending_actions (prepared_by);
CREATE INDEX IF NOT EXISTS pending_actions_status_idx ON pending_actions (status);
