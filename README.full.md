# Grecia Planner — SaaS API (FastAPI)

Verificare licență PRO pentru aplicațiile Grecia Planner.

## Modele de licență (hibrid)

| Ghid | Model | Activare plată | Verificare app |
|------|--------|----------------|----------------|
| **Thassos** | Legacy `users.is_pro` | `POST /internal/grant-pro` fără `island_id` | `GET /check-status?email=` (fără `island`) |
| **Kassandra** | `license_entitlements` | `POST /internal/grant-pro` cu `island_id=kassandra` | `GET /check-status?email=&island=kassandra` |

Kassandra **nu** folosește `is_pro` — cumpărarea Thassos **nu** deblochează Kassandra.

## Endpoint

| Metodă | Rută | Răspuns |
|--------|------|---------|
| GET | `/check-status?email=&device_id=&island=` | `{"status":"ok"}` sau `{"status":"error","reason":"..."}` |
| POST | `/internal/grant-pro` | `{ email, island_id?, source_order_id? }` — apel intern Stripe |
| GET | `/health` | health check |

## Setup rapid (local)

```bash
cd saas-api
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env
python scripts/seed_user.py client@example.com
uvicorn app.main:app --reload --port 8000
```

Test Thassos (legacy):

```bash
curl "http://localhost:8000/check-status?email=client@example.com&device_id=abcd12345678"
```

Test Kassandra (entitlement):

```bash
curl -X POST http://localhost:8000/internal/grant-pro \
  -H "Content-Type: application/json" \
  -H "X-Internal-Secret: YOUR_SECRET" \
  -d '{"email":"kassandra@example.com","island_id":"kassandra"}'

curl "http://localhost:8000/check-status?email=kassandra@example.com&device_id=abcd12345678&island=kassandra"
```

## Backfill Kassandra

```bash
python scripts/backfill_kassandra_entitlements.py --emails client@example.com
```

## PostgreSQL (producție)

1. Setează `DATABASE_URL` în `.env`.
2. Pornește API-ul — creează tabelele + `license_entitlements` la startup.
3. Firebase Functions:
   ```env
   SAAS_API_URL=https://api.greciaplanner.ro
   SAAS_INTERNAL_SECRET=același secret ca INTERNAL_API_SECRET
   ```
