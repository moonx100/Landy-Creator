# LANDY Creator

Contract review and negotiation coaching for Indonesian content creators.
Creators upload brand/agency contracts; the app flags legal risks, explains
them in Bahasa Indonesia, and produces a redlined DOCX + negotiation email.

Invite-only beta (10–20 users). Full spec: `attached_assets/LANDY_Creator_Replit_Prompt_1784780781852.md`

---

## Architecture

| Layer | Technology | Location |
|---|---|---|
| Frontend | React 18 + Vite + TypeScript | `artifacts/landy-web/` |
| API | Python 3.11 + FastAPI + SQLAlchemy | `artifacts/landy-api/` |
| Database | PostgreSQL 15 + pgvector | Replit managed DB |
| Object storage | S3-compatible (MinIO dev / Indonesian cloud prod) | via `S3_*` env vars |
| Background jobs | Python worker process | `artifacts/landy-api/worker.py` |

---

## Monorepo layout

```
artifacts/
  landy-api/        Python FastAPI application + Alembic migrations
  landy-web/        React/Vite frontend
  api-server/       Replit artifact shell (run command points to landy-api)
  mockup-sandbox/   Component preview server (design only)
docker-compose.yml  Full local dev stack (Postgres + MinIO + API + worker)
.env.example        All environment variables documented with defaults
```

---

## Running locally

```bash
# 1. Configure environment
cp .env.example .env   # fill in SESSION_SECRET, LLM_API_KEY, ADMIN_SECRET

# 2. Start all services
docker-compose up

# 3. Apply migrations (first run only)
docker-compose run api alembic upgrade head

# 4. Create invite codes
ADMIN_SECRET=... python -m landy.admin seed-invites --count 5
```

---

## Running on Replit

Three workflows are configured:

| Workflow | Command |
|---|---|
| `artifacts/api-server: API Server` | `cd artifacts/landy-api && uvicorn landy.main:app --host 0.0.0.0 --port $PORT --reload` |
| `artifacts/landy-web: web` | `pnpm --filter @workspace/landy-web run dev` |
| `artifacts/mockup-sandbox: Component Preview Server` | `pnpm --filter @workspace/mockup-sandbox run dev` |

---

## Key API routes

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/healthz` | Public | Liveness check |
| POST | `/api/auth/redeem` | Public | Exchange invite code for account |
| POST | `/api/auth/login` | Public | Email → magic-link / OTP |
| GET | `/api/auth/me` | Bearer | Current user profile + quota |
| POST | `/api/auth/logout` | Bearer | Revoke session |

---

## Environment variables

All documented in `.env.example`. Required for production:

- `DATABASE_URL` — PostgreSQL connection string
- `SESSION_SECRET` — long random string (64 hex chars)
- `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_CLASS_B`
- `LLM_API_KEY` — set in Task #3
- `ADMIN_SECRET` — CLI guard

---

## Admin CLI

```bash
# Generate invite codes
ADMIN_SECRET=... python -m landy.admin seed-invites --count 10
ADMIN_SECRET=... python -m landy.admin seed-invites --count 1 --email creator@example.com

# List invites
ADMIN_SECRET=... python -m landy.admin list-invites --unused-only

# Deactivate a user
ADMIN_SECRET=... python -m landy.admin deactivate-user --email bad@example.com
```

---

## Database

Schema managed with Alembic. Migration files: `artifacts/landy-api/migrations/versions/`

```bash
cd artifacts/landy-api
alembic upgrade head      # apply all pending migrations
alembic downgrade -1      # roll back one step
alembic revision --autogenerate -m "add xyz"  # create new migration
```

Row-level security is enforced on 8 tables. The app sets `app.current_user_id`
per request inside `engine.begin()`. RLS policies use
`nullif(current_setting('app.current_user_id', true), '')::uuid`
to avoid cast errors on unauthenticated connections.

---

## User preferences

- Python FastAPI preferred for all backend work (better document-processing ecosystem)
- No Next.js; no Replit-proprietary services
- Server-side DB sessions (not JWT) — instant revocation
- No `print()` in Python code — use structlog logger
- Indonesian-first UX (Bahasa Indonesia copy; legal professionalism aesthetic)
