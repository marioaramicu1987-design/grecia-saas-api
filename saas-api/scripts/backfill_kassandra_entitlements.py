#!/usr/bin/env python3
"""
Backfill license_entitlements pentru plăți Kassandra existente.

Utilizare (din saas-api/, cu DATABASE_URL setat):
  python scripts/backfill_kassandra_entitlements.py --dry-run
  python scripts/backfill_kassandra_entitlements.py

Opțional — din listă de emailuri:
  python scripts/backfill_kassandra_entitlements.py --emails a@x.ro,b@y.ro
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal, LicenseEntitlement, grant_island_entitlement, normalize_email


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Kassandra entitlements")
    parser.add_argument(
        "--emails",
        default="",
        help="Emailuri separate prin virgulă (dacă lipsește, doar raportează count existent)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Nu scrie în DB")
    args = parser.parse_args()

    emails = [normalize_email(e) for e in args.emails.split(",") if e.strip()]
    if not emails:
        with SessionLocal() as session:
            count = session.query(LicenseEntitlement).filter_by(island_id="kassandra").count()
        print(f"Entitlements Kassandra existente: {count}")
        print("Pentru backfill manual: --emails client1@...,client2@...")
        return 0

    created = 0
    for email in emails:
        if "@" not in email:
            print(f"Skip invalid: {email}")
            continue
        if args.dry_run:
            print(f"[dry-run] would grant kassandra entitlement: {email}")
            created += 1
            continue
        if grant_island_entitlement(email, "kassandra", source_order_id="backfill-manual"):
            print(f"Granted: {email}")
            created += 1

    print(f"Done. Processed: {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
