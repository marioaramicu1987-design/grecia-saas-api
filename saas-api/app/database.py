import secrets
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

ENTITLEMENT_ISLANDS = frozenset({"kassandra", "sithonia", "lefkada"})
UNLOCK_ISLANDS = frozenset({"thassos", "kassandra", "sithonia", "lefkada"})
UNLOCK_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    is_pro = Column(Boolean, nullable=False, default=False)
    bound_device_id = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UnlockCode(Base):
    __tablename__ = "unlock_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(24), unique=True, nullable=False, index=True)
    island_id = Column(String(32), nullable=False, index=True)
    note = Column(String(255), nullable=True)
    created_by = Column(String(255), nullable=True)
    bound_device_id = Column(String(128), nullable=True)
    redeemed_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class LicenseEntitlement(Base):
    __tablename__ = "license_entitlements"
    __table_args__ = (UniqueConstraint("email", "island_id", name="uq_license_entitlements_email_island"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    island_id = Column(String(32), nullable=False, index=True)
    bound_device_id = Column(String(128), nullable=True)
    source_order_id = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    # Neon / managed Postgres: reconnect după sleep
    return {
        "pool_recycle": 280,
        "pool_size": 2,
        "max_overflow": 2,
    }


engine = create_engine(settings.database_url, pool_pre_ping=True, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Creează tabelele. Aruncă eroarea reală — startup-ul face retry."""
    dialect = engine.dialect.name
    print(f"[saas-api] init_db dialect={dialect}", flush=True)
    Base.metadata.create_all(bind=engine)
    _migrate_bound_device_id()
    _migrate_license_entitlements()
    _migrate_unlock_codes()
    print("[saas-api] init_db OK", flush=True)


def _migrate_bound_device_id() -> None:
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS bound_device_id VARCHAR(128)"
                )
            )
        elif dialect == "sqlite":
            cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
            }
            if "bound_device_id" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN bound_device_id VARCHAR(128)"))


def _migrate_license_entitlements() -> None:
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS license_entitlements (
                      id SERIAL PRIMARY KEY,
                      email VARCHAR(255) NOT NULL,
                      island_id VARCHAR(32) NOT NULL,
                      bound_device_id VARCHAR(128),
                      source_order_id VARCHAR(128),
                      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                      CONSTRAINT uq_license_entitlements_email_island UNIQUE (email, island_id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_license_entitlements_email_island "
                    "ON license_entitlements (email, island_id)"
                )
            )
        elif dialect == "sqlite":
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS license_entitlements (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      email VARCHAR(255) NOT NULL,
                      island_id VARCHAR(32) NOT NULL,
                      bound_device_id VARCHAR(128),
                      source_order_id VARCHAR(128),
                      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      UNIQUE (email, island_id)
                    )
                    """
                )
            )


def _migrate_unlock_codes() -> None:
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS unlock_codes (
                      id SERIAL PRIMARY KEY,
                      code VARCHAR(24) NOT NULL UNIQUE,
                      island_id VARCHAR(32) NOT NULL,
                      note VARCHAR(255),
                      created_by VARCHAR(255),
                      bound_device_id VARCHAR(128),
                      redeemed_at TIMESTAMPTZ,
                      revoked_at TIMESTAMPTZ,
                      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_unlock_codes_island ON unlock_codes (island_id)")
            )
        elif dialect == "sqlite":
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS unlock_codes (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      code VARCHAR(24) NOT NULL UNIQUE,
                      island_id VARCHAR(32) NOT NULL,
                      note VARCHAR(255),
                      created_by VARCHAR(255),
                      bound_device_id VARCHAR(128),
                      redeemed_at DATETIME,
                      revoked_at DATETIME,
                      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_device_id(device_id: str | None) -> str:
    return (device_id or "").strip().lower()


def normalize_entitlement_island(island_id: str | None) -> str | None:
    value = (island_id or "").strip().lower()
    if value in ENTITLEMENT_ISLANDS:
        return value
    return None


def normalize_unlock_island(island_id: str | None) -> str | None:
    value = (island_id or "").strip().lower()
    if value in UNLOCK_ISLANDS:
        return value
    return None


def normalize_unlock_code(code: str | None) -> str:
    return (code or "").strip().upper().replace(" ", "")


def is_valid_unlock_code_format(code: str) -> bool:
    if len(code) < 4 or len(code) > 24:
        return False
    return all(ch.isalnum() for ch in code)


def is_valid_device_id(device_id: str) -> bool:
    if len(device_id) < 8 or len(device_id) > 128:
        return False
    return all(ch.isalnum() or ch in "-_" for ch in device_id)


def is_multi_device_test_email(email: str) -> bool:
    normalized = normalize_email(email)
    allowed = {
        item.strip().lower()
        for item in settings.multi_device_test_emails.split(",")
        if item.strip()
    }
    return normalized in allowed


def user_has_active_pro(email: str) -> bool:
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized:
        return False

    with SessionLocal() as session:
        row = session.scalar(
            select(User.is_pro).where(User.email == normalized, User.is_pro.is_(True))
        )
        return row is True


def check_pro_license(email: str, device_id: str | None) -> tuple[bool, str | None]:
    """
    Verifică licența PRO legacy (Thassos) și leagă contul de primul dispozitiv folosit.
    Returnează (allowed, reason) — reason: no_license | device_required | device_mismatch.
    """
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized:
        return False, "no_license"

    if is_multi_device_test_email(normalized):
        return True, None

    device = normalize_device_id(device_id)
    if not is_valid_device_id(device):
        return False, "device_required"

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == normalized))
        if user is None or not user.is_pro:
            return False, "no_license"

        bound = normalize_device_id(user.bound_device_id)
        if not bound:
            user.bound_device_id = device
            session.commit()
            return True, None

        if bound == device:
            return True, None

        return False, "device_mismatch"


def check_island_entitlement(
    email: str,
    island_id: str,
    device_id: str | None,
) -> tuple[bool, str | None]:
    """
    Verifică entitlement per ghid (ex. Kassandra). Ignoră users.is_pro.
    """
    normalized = normalize_email(email)
    island = normalize_entitlement_island(island_id)
    if not normalized or "@" not in normalized or island is None:
        return False, "no_license"

    if is_multi_device_test_email(normalized):
        return True, None

    device = normalize_device_id(device_id)
    if not is_valid_device_id(device):
        return False, "device_required"

    with SessionLocal() as session:
        entitlement = session.scalar(
            select(LicenseEntitlement).where(
                LicenseEntitlement.email == normalized,
                LicenseEntitlement.island_id == island,
            )
        )
        if entitlement is None:
            return False, "no_license"

        bound = normalize_device_id(entitlement.bound_device_id)
        if not bound:
            entitlement.bound_device_id = device
            session.commit()
            return True, None

        if bound == device:
            return True, None

        return False, "device_mismatch"


def grant_pro_license(email: str) -> bool:
    """Activează is_pro pentru email (Thassos / legacy)."""
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized:
        return False

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == normalized))
        if user is None:
            user = User(email=normalized, is_pro=True)
            session.add(user)
        else:
            user.is_pro = True
        session.commit()
        return True


def grant_island_entitlement(
    email: str,
    island_id: str,
    source_order_id: str | None = None,
) -> bool:
    """Acordă entitlement per ghid (ex. Kassandra), fără is_pro global."""
    normalized = normalize_email(email)
    island = normalize_entitlement_island(island_id)
    if not normalized or "@" not in normalized or island is None:
        return False

    order_id = (source_order_id or "").strip() or None

    with SessionLocal() as session:
        entitlement = session.scalar(
            select(LicenseEntitlement).where(
                LicenseEntitlement.email == normalized,
                LicenseEntitlement.island_id == island,
            )
        )
        if entitlement is None:
            entitlement = LicenseEntitlement(
                email=normalized,
                island_id=island,
                source_order_id=order_id,
            )
            session.add(entitlement)
        elif order_id and not entitlement.source_order_id:
            entitlement.source_order_id = order_id
        session.commit()
        return True


def _generate_unlock_code() -> str:
    return "".join(secrets.choice(UNLOCK_CODE_CHARS) for _ in range(8))


def serialize_unlock_code(row: UnlockCode) -> dict:
    revoked = row.revoked_at is not None
    bound = bool(normalize_device_id(row.bound_device_id))
    if revoked:
        status = "revoked"
    elif bound:
        status = "active"
    else:
        status = "unused"
    return {
        "code": row.code,
        "island_id": row.island_id,
        "note": row.note or "",
        "created_by": row.created_by or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "redeemed_at": row.redeemed_at.isoformat() if row.redeemed_at else None,
        "revoked": revoked,
        "bound": bound,
        "status": status,
    }


def check_unlock_code(
    code: str,
    island_id: str | None,
    device_id: str | None,
) -> tuple[bool, str | None]:
    """Licență de deblocare: o aplicație, un dispozitiv — același contract ca emailul plătit."""
    normalized = normalize_unlock_code(code)
    island = normalize_unlock_island(island_id) or "thassos"
    if not is_valid_unlock_code_format(normalized):
        return False, "no_license"

    device = normalize_device_id(device_id)
    if not is_valid_device_id(device):
        return False, "device_required"

    with SessionLocal() as session:
        row = session.scalar(select(UnlockCode).where(UnlockCode.code == normalized))
        if row is None or row.revoked_at is not None:
            return False, "no_license"
        if row.island_id != island:
            return False, "no_license"

        bound = normalize_device_id(row.bound_device_id)
        if not bound:
            row.bound_device_id = device
            row.redeemed_at = datetime.now(timezone.utc)
            session.commit()
            return True, None

        if bound == device:
            return True, None

        return False, "device_mismatch"


def create_unlock_code(
    island_id: str,
    code: str | None = None,
    note: str | None = None,
    created_by: str | None = None,
) -> dict | None:
    island = normalize_unlock_island(island_id)
    if island is None:
        return None

    requested = normalize_unlock_code(code)
    if requested and not is_valid_unlock_code_format(requested):
        return None

    clean_note = (note or "").strip()[:255] or None
    author = (created_by or "").strip()[:255] or None

    with SessionLocal() as session:
        for _ in range(12):
            value = requested or _generate_unlock_code()
            existing = session.scalar(select(UnlockCode).where(UnlockCode.code == value))
            if existing is not None:
                if requested:
                    return None
                continue
            row = UnlockCode(
                code=value,
                island_id=island,
                note=clean_note,
                created_by=author,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return serialize_unlock_code(row)
    return None


def list_unlock_codes(island_id: str) -> list[dict]:
    island = normalize_unlock_island(island_id)
    if island is None:
        return []
    with SessionLocal() as session:
        rows = session.scalars(
            select(UnlockCode)
            .where(UnlockCode.island_id == island)
            .order_by(UnlockCode.created_at.desc())
        ).all()
        return [serialize_unlock_code(row) for row in rows]


def revoke_unlock_code(code: str) -> bool:
    normalized = normalize_unlock_code(code)
    if not is_valid_unlock_code_format(normalized):
        return False
    with SessionLocal() as session:
        row = session.scalar(select(UnlockCode).where(UnlockCode.code == normalized))
        if row is None:
            return False
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            session.commit()
        return True
