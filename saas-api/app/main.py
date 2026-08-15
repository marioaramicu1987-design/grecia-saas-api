from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import GrantProRequest, settings
from app.database import (
    check_island_entitlement,
    check_pro_license,
    grant_island_entitlement,
    grant_pro_license,
    init_db,
    normalize_entitlement_island,
)

app = FastAPI(
    title="Grecia Planner SaaS API",
    description="Verificare licență PRO — legacy Thassos (is_pro) și entitlements per ghid.",
    version="1.2.1",
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins and origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    import time

    last_error: Exception | None = None
    for attempt in range(1, 8):
        try:
            init_db()
            return
        except Exception as exc:  # noqa: BLE001 — logăm și reîncercăm (Neon cold start)
            last_error = exc
            wait_s = min(attempt * 2, 12)
            print(
                f"[saas-api] init_db failed attempt {attempt}/7: {type(exc).__name__}: {exc}",
                flush=True,
            )
            time.sleep(wait_s)
    print("[saas-api] FATAL: database unavailable after retries", flush=True)
    raise RuntimeError(f"Database init failed: {last_error}") from last_error


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "grecia-planner-saas-api", "version": "1.2.1"}


@app.get("/check-status")
def check_status(
    email: str = Query(..., min_length=3, max_length=255),
    device_id: str = Query(default="", max_length=128),
    island: str = Query(default="", max_length=32),
) -> dict:
    """
    Verifică licența și leagă email-ul de un singur dispozitiv.
    - Fără `island` (sau necunoscut): legacy Thassos via users.is_pro
    - island=kassandra|sithonia|lefkada: entitlement dedicat, ignoră is_pro
    """
    entitlement_island = normalize_entitlement_island(island)
    if entitlement_island:
        allowed, reason = check_island_entitlement(email, entitlement_island, device_id or None)
    else:
        allowed, reason = check_pro_license(email, device_id or None)

    if allowed:
        return {"status": "ok", "island": entitlement_island or "thassos"}
    return {"status": "error", "reason": reason or "no_license"}


@app.post("/internal/grant-pro")
def internal_grant_pro(
    payload: GrantProRequest,
    x_internal_secret: str = Header(default=""),
) -> dict:
    """Apel intern (Stripe webhook) — activează licența pentru email."""
    secret = (settings.internal_api_secret or "").strip()
    if not secret or x_internal_secret != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    island = normalize_entitlement_island(payload.island_id)
    email = str(payload.email).strip().lower()

    # Ghiduri cu entitlement separat (Kassandra, Sithonia) — nu deblochează Thassos is_pro
    if island:
        if grant_island_entitlement(email, island, payload.source_order_id):
            return {"ok": True, "email": email, "island": island, "model": "entitlement"}
        raise HTTPException(status_code=400, detail="Invalid email or island")

    if grant_pro_license(email):
        return {"ok": True, "email": email, "island": "thassos", "model": "legacy_is_pro"}
    raise HTTPException(status_code=400, detail="Invalid email")
