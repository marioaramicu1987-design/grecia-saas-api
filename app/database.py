from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint, create_engine, func, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

ENTITLEMENT_ISLANDS = frozenset({"kassandra"})


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
    return {}


engine = create_engine(settings.database_url, pool_pre_ping=True, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_bound_device_id()
    _migrate_license_entitlements()


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


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_device_id(device_id: str | None) -> str:
    return (device_id or "").strip().lower()


def normalize_entitlement_island(island_id: str | None) -> str | None:
    value = (island_id or "").strip().lower()
    if value in ENTITLEMENT_ISLANDS:
        return value
    return None


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
