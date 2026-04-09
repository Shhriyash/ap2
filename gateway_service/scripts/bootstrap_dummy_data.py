from __future__ import annotations

import argparse
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, text

from app.db.models import Account, Base, Beneficiary, LedgerEntry, Transaction, User
from app.db.session import engine, SessionLocal


def seed(reset: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS supabase_user_id TEXT"))
        db.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS session_id TEXT"))
        db.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS auth_context_id TEXT"))
        db.execute(text("UPDATE transactions SET session_id = COALESCE(session_id, 'legacy_session')"))
        db.execute(text("UPDATE transactions SET auth_context_id = COALESCE(auth_context_id, 'legacy_auth_context')"))
        db.execute(text("ALTER TABLE transactions ALTER COLUMN session_id SET NOT NULL"))
        db.execute(text("ALTER TABLE transactions ALTER COLUMN auth_context_id SET NOT NULL"))
        db.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_users_supabase_user_id') THEN "
                "ALTER TABLE users ADD CONSTRAINT uq_users_supabase_user_id UNIQUE (supabase_user_id); "
                "END IF; "
                "END $$;"
            )
        )
        db.commit()

        if reset:
            db.execute(delete(LedgerEntry))
            db.execute(delete(Transaction))
            db.execute(delete(Beneficiary))
            db.execute(delete(Account))
            db.execute(delete(User))
            db.commit()

        users = [
            User(
                id="user_shriyash",
                supabase_user_id="sb_user_shriyash",
                full_name="Shriyash",
                phone="+971500001001",
                email="shriyash@example.com",
            ),
            User(
                id="user_riya",
                supabase_user_id="sb_user_riya",
                full_name="Riya",
                phone="+971500001002",
                email="riya@example.com",
            ),
            User(
                id="user_ahmed",
                supabase_user_id="sb_user_ahmed",
                full_name="Ahmed",
                phone="+971500001003",
                email="ahmed@example.com",
            ),
        ]
        for row in users:
            existing = db.get(User, row.id)
            if not existing:
                db.add(row)
            else:
                existing.supabase_user_id = row.supabase_user_id
                existing.email = row.email
        db.commit()

        accounts = [
            Account(
                id=UUID("11111111-1111-1111-1111-111111111111"),
                user_id="user_shriyash",
                currency="AED",
                available_balance=Decimal("12500.00"),
                held_balance=Decimal("0.00"),
                status="active",
            ),
            Account(
                id=UUID("22222222-2222-2222-2222-222222222222"),
                user_id="user_riya",
                currency="AED",
                available_balance=Decimal("4200.00"),
                held_balance=Decimal("0.00"),
                status="active",
            ),
            Account(
                id=UUID("33333333-3333-3333-3333-333333333333"),
                user_id="user_ahmed",
                currency="AED",
                available_balance=Decimal("3100.00"),
                held_balance=Decimal("0.00"),
                status="active",
            ),
        ]
        for row in accounts:
            existing = db.get(Account, row.id)
            if not existing:
                db.add(row)
            else:
                existing.user_id = row.user_id
                existing.currency = row.currency
                existing.available_balance = row.available_balance
                existing.held_balance = row.held_balance
                existing.status = row.status
        db.commit()

        beneficiaries = [
            Beneficiary(
                id="ben_riya",
                owner_user_id="user_shriyash",
                beneficiary_user_id="user_riya",
                display_name="riya",
                identifier="user_riya@wallet",
                rail_type="wallet",
                is_verified=True,
                status="active",
            ),
            Beneficiary(
                id="ben_ahmed",
                owner_user_id="user_shriyash",
                beneficiary_user_id="user_ahmed",
                display_name="ahmed",
                identifier="user_ahmed@wallet",
                rail_type="wallet",
                is_verified=True,
                status="active",
            ),
            Beneficiary(
                id="ben_shriyash",
                owner_user_id="user_riya",
                beneficiary_user_id="user_shriyash",
                display_name="shriyash",
                identifier="user_shriyash@wallet",
                rail_type="wallet",
                is_verified=True,
                status="active",
            ),
        ]
        for row in beneficiaries:
            existing = db.get(Beneficiary, row.id)
            if not existing:
                db.add(row)
            else:
                existing.owner_user_id = row.owner_user_id
                existing.beneficiary_user_id = row.beneficiary_user_id
                existing.display_name = row.display_name
                existing.identifier = row.identifier
                existing.rail_type = row.rail_type
                existing.is_verified = row.is_verified
                existing.status = row.status

        db.commit()
        print("Dummy users, accounts, and beneficiaries are ready.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create tables and seed dummy payment data.")
    parser.add_argument("--reset", action="store_true", help="Delete existing users/accounts/beneficiaries and reseed.")
    args = parser.parse_args()
    seed(reset=args.reset)


if __name__ == "__main__":
    main()
