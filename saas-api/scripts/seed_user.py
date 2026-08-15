"""Adaugă sau actualizează un utilizator PRO. Usage: python scripts/seed_user.py user@example.com"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal, User, init_db, normalize_email  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/seed_user.py <email> [--revoke]")
        sys.exit(1)

    email = normalize_email(sys.argv[1])
    revoke = "--revoke" in sys.argv[2:]

    init_db()
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, is_pro=not revoke)
            session.add(user)
        else:
            user.is_pro = not revoke
        session.commit()
        print(f"{'Revoked' if revoke else 'Granted'} PRO for {email} (is_pro={user.is_pro})")


if __name__ == "__main__":
    main()
