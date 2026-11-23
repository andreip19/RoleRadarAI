# RoleRadar AI

Job discovery dashboard with a FastAPI API, React/Vite frontend, and PostgreSQL storage.

## Local development

### Backend

Use Python 3.13 and install the pinned dependencies:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
```

The application loads `.env` from the repository root. For local work, `APP_ENV=development` permits the three administrative POST routes without a token only when `ADMIN_API_TOKEN` is unset. If a token is configured, send it as `Authorization: Bearer <token>`. Do not use the development exception in a shared or production environment. SQLite remains the local fallback when `DATABASE_URL` is absent.

`/health` reports process liveness. `/ready` runs `SELECT 1` and reports whether the configured database is reachable.

### Frontend

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Vite serves the UI at `http://localhost:5173`. If `VITE_API_BASE_URL` is empty, `frontend/vite.config.js` proxies API requests to `http://127.0.0.1:8010` for development. `VITE_API_BASE_URL` is public build-time configuration, never a place for credentials.

## Environment variables

| Variable | Purpose | Production requirement |
| --- | --- | --- |
| `APP_ENV` | `development` or `production` behavior | `production` |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection string | Supabase PostgreSQL URL with `sslmode=require` |
| `ADMIN_API_TOKEN` | Bearer token for administrative write routes | Required; keep only in backend secrets |
| `GEMINI_API_KEY` | Credential for Gemini-backed analysis | Set in Render; never expose to the frontend |
| `GEMINI_MODEL` | Gemini model name | `gemini-3.5-flash-lite` in deployment |
| `CORS_ORIGINS` | Comma-separated browser origins | Explicit Vercel origin(s); no wildcard |
| `DB_POOL_SIZE` | SQLAlchemy pool connections per worker | Size against Supabase limits |
| `DB_MAX_OVERFLOW` | Temporary extra connections per worker | Size against Supabase limits |
| `DB_POOL_TIMEOUT` | Seconds to wait for a pooled connection | Optional; defaults to 30 |
| `DB_POOL_RECYCLE` | Connection recycling interval in seconds | Optional; defaults to 1800 |
| `VITE_API_BASE_URL` | Public FastAPI origin compiled into frontend | Set in Vercel after the API URL exists |

Never define `ADMIN_API_TOKEN`, `DATABASE_URL`, or other credentials with a `VITE_` prefix. Vite embeds `VITE_*` values in browser assets.

## API access

The dashboard GET endpoints remain public. The following write routes require the backend Bearer token outside local development:

- `POST /api/v1/ingestion/run-all`
- `POST /api/v1/jobs/greenhouse/{board_token}/sync`
- `POST /api/v1/jobs/lever/{site}/sync`

The configured token is compared in constant time and is not logged. Do not put it in the frontend. Scheduled GitHub ingestion calls `scripts.run_ingestion` directly with its database secret; it does not call these HTTP routes.

## Deployment architecture

### Vercel: React + Vite

1. Import the GitHub repository as a Vercel project.
2. Configure **Root Directory** as `frontend`, **Build Command** as `npm run build`, and **Output Directory** as `dist`. Vercel installs the npm dependencies from `frontend/package-lock.json` (`npm ci`).
3. Add `VITE_API_BASE_URL` in Vercel project environment settings when the Render API URL has been created. This value is public.
4. Add the resulting exact Vercel origin to the Render `CORS_ORIGINS` setting. No Vercel domain is assumed in this repository.
5. Preview deployments have distinct origins; add only the preview origins you intend to permit.

### Render: FastAPI

`render.yaml` defines a Python web service; creating/importing the Blueprint provisions it. It installs `requirements.txt`, starts Uvicorn on Render's `$PORT` with two workers, checks `/ready`, and keeps `autoDeploy: false` until the first deployment has been tested successfully. It defines `APP_ENV=production`, `GEMINI_MODEL=gemini-3.5-flash-lite`, and the database pool defaults. `DATABASE_URL`, `ADMIN_API_TOKEN`, `GEMINI_API_KEY`, and `CORS_ORIGINS` are dashboard-managed values (`sync: false`). Review the worker and pool sizes against the selected Render instance and Supabase connection limits before creating the service.

The Blueprint supplies `APP_ENV`, `GEMINI_MODEL`, and pool defaults. Set `DATABASE_URL`, `ADMIN_API_TOKEN`, `GEMINI_API_KEY`, and `CORS_ORIGINS` in Render. Production startup rejects a missing admin token, missing CORS origins, non-PostgreSQL URL, or PostgreSQL URL without an SSL mode of `require`, `verify-ca`, or `verify-full`. Use the Supabase pooler URL appropriate for the server workload and keep SSL enabled. Set `CORS_ORIGINS` to the exact frontend origin(s), comma-separated and without a wildcard. Once the Vercel project is deployed, copy its public origin into this setting and redeploy/restart the API if needed.

After deployment, check `https://<render-service-host>/health` for process liveness and `/ready` for database readiness (a database outage returns HTTP 503). The public browser frontend calls the Render API using `VITE_API_BASE_URL`; this is a public URL, never a credential. Administrative write routes require `Authorization: Bearer <ADMIN_API_TOKEN>` outside local development. Verify a protected route without a token returns HTTP 401, and send the token only from a trusted operator tool or server-side client, never from Vercel/browser code.

The application currently calls `Base.metadata.create_all()` at startup. It has not been removed because a safe migration baseline has not been generated and checked against the existing Supabase schema. Treat schema verification and the initial Alembic baseline as a deployment blocker; do not rely on production startup to evolve an existing schema.

### Supabase: existing PostgreSQL

Use the existing project and provide its PostgreSQL connection URL only to the backend and trusted automation. Enforce SSL, use a connection pool compatible with the Supabase pooler, and size total connections as `(pool_size + max_overflow) multiplied by Uvicorn workers` for each service. Confirm the plan's backup retention and test a restore procedure before production use. Do not put the database URL in Vercel or frontend variables.

## PostgreSQL migration plan (not applied)

1. Obtain read-only access to the existing database and capture its current tables, columns, constraints, indexes, and migration history. The previous audit could not connect to PostgreSQL, so this schema comparison is still blocked.
2. Add Alembic and configure its metadata from the existing SQLAlchemy `Base`; do not generate a migration from model metadata alone.
3. Compare the live schema with the models and prepare a reviewed baseline that describes the current schema without replaying destructive changes.
4. Test the baseline against a disposable PostgreSQL database, then verify its bookkeeping against a read-only snapshot of the existing schema.
5. Only after review and explicit approval, mark the existing database at the baseline revision and use explicit release-time migration commands for future changes.

No migration has been run. `Base.metadata.create_all()` remains in place until this path is safely verified.

## GitHub Actions

`.github/workflows/ci.yml` already runs Ruff, Pytest, frontend lint, and frontend build on pushes and pull requests to `main`/`master`. `.github/workflows/ingestion.yml` runs scheduled/manual ingestion using the `DATABASE_URL` repository secret. It invokes the Python ingestion service directly, so it does not need `ADMIN_API_TOKEN`. Neither workflow contains a credential value.

## Local checks

```powershell
python -m ruff check backend scraper scripts
python -m pytest -v
cd frontend; npm run lint; npm run build
```
