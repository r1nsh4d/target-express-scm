# Target Express — Delivery Management Platform

Web application and driver portal for Target Express Logistics.

- Functional specification: [TARGET-EXPRESS-PROJECT-BRIEF.md](TARGET-EXPRESS-PROJECT-BRIEF.md)
- Server deployment: [DEPLOYMENT.md](DEPLOYMENT.md) — the Hetzner host also runs
  another application, so read the isolation section before the first deploy.

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (Python 3.12), SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 |
| Frontend | React 19, TypeScript, Vite 8, Tailwind CSS 4 |
| Object storage | MinIO in development, S3-compatible in production |

SQLAlchemy is used synchronously on purpose. This is a CRUD-heavy internal
system at modest concurrency, and FastAPI's threadpool covers the load with
large headroom. Sync avoids an entire class of greenlet and lazy-load faults
that cost a small team days. Async can be introduced later on a specific hot
path if one appears.

## Running it

### 1. Infrastructure

```bash
docker compose up -d
```

Ports are deliberately unusual and bound to `127.0.0.1`, because this stack
shares hosts with other applications: Postgres on **55432**, MinIO on **19000**
with its console on **19001**. All are overridable in `.env`.

### 2. Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows
cp .env.example .env

./.venv/Scripts/python.exe -m alembic revision --autogenerate -m "initial schema"
./.venv/Scripts/python.exe -m alembic upgrade head

# Minimum to walk the workflow: 3 logins and one vehicle, nothing else
./.venv/Scripts/python.exe -m app.bootstrap
# ...or full demo data with Godrej masters and worked trips
./.venv/Scripts/python.exe -m app.seed

./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/api/docs

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

http://localhost:5173 — Vite proxies `/api` to port 8000.

### Logins

All use password `target123`.

**`app.bootstrap`** — the minimum to walk the workflow:

| Phone | Role | |
|---|---|---|
| 9000000001 | Super admin | |
| 9000000002 | Operations admin | creates vendors, customers, trips |
| 9000000010 | Driver | runs the trip from `/driver` |

Plus one owned vehicle `KL07AA1234` and a DOST vehicle type. Everything else —
vendors, divisions, warehouses, customers, rate cards, trips — is created
through the application.

**`app.seed`** — full demo data instead: Godrej with both divisions, real rate
cards, seven vehicles including a rented one, four drivers, seven customers, and
six worked trips that reproduce two real odometer anomalies.

### Walking the workflow

1. Sign in as **9000000002** (operations admin)
2. **Vendors** → create a vendor, then a division under it, then a warehouse
3. **Rate cards** → add a card for that division (defaults are the verified
   Godrej terms)
4. **Customers** → add a few delivery points, with phone numbers
5. **Trips** → new trip: pick the division, warehouse, date and points
6. On the trip: assign the vehicle and driver, confirm loading per point,
   then **Dispatch** — the LR is issued and tracking links open
7. Sign in as **9000000010** on `/driver`: enter the opening odometer, deliver
   each point, then close with the returning reading
8. Back on the trip, the odometer chain, the box counts and the billing total
   are all filled in

## Tests

```bash
cd backend
./.venv/Scripts/python.exe -m pytest -q
```

The rating tests are anchored on real invoices — 191/2026-27/022 and /023 to
Godrej. They reproduce twelve printed line totals exactly and reconcile the
invoice's column totals to ₹3,13,275. If a change to the rate engine breaks
those, it has broken billing.

## Layout

```
backend/
  app/
    api/routes/     auth, dashboard, driver
    core/           settings, password hashing, JWT
    db/             declarative base, session
    models/         25 tables - the domain
    services/       rating (billing), controls (odometer + box checks)
    seed.py         Godrej masters and worked trips
  tests/
frontend/
  src/
    components/     design system, app shell
    lib/            api client, auth context
    pages/          login, dashboard, driver portal
```

## Notes for developers

**Rate cards are versioned and never edited in place.** A freight stores a
snapshot of its rate terms at dispatch, so re-printing an old invoice
reproduces the original numbers. Add a new card with a later `effective_from`
instead of changing one.

**A trip is composed of legs.** Never hang `vehicle_id` off `Freight`. Vendor
billing rolls up to the trip; vehicle hire and driver pay compute per leg.
This is what makes a mid-trip vehicle change work.

**Unloading is two independent numbers.** `unloading_billed` comes from the
vendor rate card, `unloading_paid` from the driver's pay terms. Never collapse
them into one field — the difference is margin, and on spare-parts trips the
billed side is zero while the paid side is not.

**The driver's odometer entry is never overwritten.** Admin corrections are
their own record, carrying the original value, the corrected value, the reason
and the author.
