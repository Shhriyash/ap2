from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.models import Account, Base, User
from app.db.session import SessionLocal, engine


def set_all_balances(amount: Decimal, currency: str = "AED") -> tuple[int, int]:
    Base.metadata.create_all(bind=engine)

    updated = 0
    created = 0

    with SessionLocal() as db:
        users = db.execute(select(User)).scalars().all()

        for user in users:
            account = db.execute(
                select(Account).where(
                    Account.user_id == user.id,
                    Account.currency == currency,
                    Account.status == "active",
                )
            ).scalar_one_or_none()

            if account is None:
                db.add(
                    Account(
                        user_id=user.id,
                        currency=currency,
                        available_balance=amount,
                        held_balance=Decimal("0.00"),
                        status="active",
                    )
                )
                created += 1
                continue

            account.available_balance = amount
            updated += 1

        db.commit()

    return updated, created


def main() -> None:
    parser = argparse.ArgumentParser(description="Set all users' active AED account balances to a fixed amount.")
    parser.add_argument("--amount", default="5000", help="Amount to apply to each active currency account")
    parser.add_argument("--currency", default="AED", help="Currency to update (default: AED)")
    args = parser.parse_args()

    amount = Decimal(args.amount).quantize(Decimal("0.01"))
    updated, created = set_all_balances(amount=amount, currency=args.currency.upper())

    print(
        f"Applied balance {amount} {args.currency.upper()} to all users. "
        f"Updated accounts: {updated}, created accounts: {created}."
    )


if __name__ == "__main__":
    main()
