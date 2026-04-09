-- Initial schema for AI agent payment prototype (AED only).

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    currency CHAR(3) NOT NULL DEFAULT 'AED',
    available_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
    held_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS beneficiaries (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(id),
    beneficiary_user_id TEXT REFERENCES users(id),
    display_name TEXT NOT NULL,
    identifier TEXT NOT NULL,
    rail_type TEXT NOT NULL DEFAULT 'wallet',
    is_verified BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT NOT NULL DEFAULT 'active'
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transaction_status') THEN
        CREATE TYPE transaction_status AS ENUM ('SUCCESS', 'FAILED', 'PENDING', 'REFUNDED', 'REVERSED');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    payer_user_id TEXT NOT NULL REFERENCES users(id),
    beneficiary_id TEXT NOT NULL REFERENCES beneficiaries(id),
    amount NUMERIC(18,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'AED',
    payment_method_id TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    status transaction_status NOT NULL DEFAULT 'PENDING',
    failure_code TEXT,
    failure_reason TEXT,
    external_ref TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id UUID PRIMARY KEY,
    transaction_id TEXT NOT NULL REFERENCES transactions(id),
    account_id UUID NOT NULL REFERENCES accounts(id),
    entry_type TEXT NOT NULL CHECK (entry_type IN ('debit', 'credit')),
    amount NUMERIC(18,2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL DEFAULT 'AED',
    balance_before NUMERIC(18,2) NOT NULL,
    balance_after NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed prototype users and balances.
INSERT INTO users (id, full_name, phone, email)
VALUES
    ('user_x', 'User X', '+971500000001', 'x@example.com'),
    ('user_y', 'User Y', '+971500000002', 'y@example.com')
ON CONFLICT (id) DO NOTHING;

INSERT INTO accounts (id, user_id, currency, available_balance, held_balance, status)
VALUES
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'user_x', 'AED', 5000.00, 0.00, 'active'),
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'user_y', 'AED', 1500.00, 0.00, 'active')
ON CONFLICT (id) DO NOTHING;

INSERT INTO beneficiaries (id, owner_user_id, beneficiary_user_id, display_name, identifier, rail_type, is_verified, status)
VALUES
    ('ben_y', 'user_x', 'user_y', 'y', 'user_y@wallet', 'wallet', TRUE, 'active')
ON CONFLICT (id) DO NOTHING;
