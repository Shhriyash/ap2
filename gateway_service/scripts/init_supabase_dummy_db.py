from __future__ import annotations

import argparse
from decimal import Decimal
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_unified_env() -> None:
    env_path = ROOT.parent / ".env.agent"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, value.strip())


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Standalone initializer for Supabase dummy DB: creates schema, applies compatibility alters, "
            "and seeds dummy users/accounts/beneficiaries."
        )
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing users/accounts/beneficiaries/transactions/ledger and reseed.",
    )
    parser.add_argument(
        "--set-all-balance",
        action="store_true",
        help="After seed, set all users' active AED accounts to a fixed balance.",
    )
    parser.add_argument(
        "--balance-amount",
        default="5000",
        help="Balance amount used with --set-all-balance (default: 5000).",
    )
    args = parser.parse_args()

    _load_unified_env()
    from scripts.bootstrap_dummy_data import seed
    from scripts.set_all_balances import set_all_balances

    seed(reset=args.reset)
    print("Schema + dummy seed completed.")

    if args.set_all_balance:
        amount = Decimal(args.balance_amount).quantize(Decimal("0.01"))
        updated, created = set_all_balances(amount=amount, currency="AED")
        print(
            f"Applied balance {amount} AED to all users. Updated accounts: {updated}, created accounts: {created}."
        )


if __name__ == "__main__":
    main()
