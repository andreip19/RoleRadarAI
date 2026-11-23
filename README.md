# RoleRadar AI

RoleRadar AI is an intelligent job aggregation and analysis platform. It collects public job postings from Greenhouse and Lever, stores normalized listings, and uses Gemini AI to analyze job descriptions and organize skills for job seekers.

## Production

| Service | URL |
| --- | --- |
| Frontend | [https://role-radar-ai-delta.vercel.app/](https://role-radar-ai-delta.vercel.app/) |
| Backend | [https://roleradar-api-tsi1.onrender.com](https://roleradar-api-tsi1.onrender.com) |
| Health | [https://roleradar-api-tsi1.onrender.com/health](https://roleradar-api-tsi1.onrender.com/health) |
| Readiness | [https://roleradar-api-tsi1.onrender.com/ready](https://roleradar-api-tsi1.onrender.com/ready) |

The free Render instance may sleep after inactivity. Its first request after sleep can take longer while the service starts (cold start). `/health` reports process liveness; `/ready` also checks the database and returns HTTP 503 if it cannot connect.

## Features

- Collects job postings from public Greenhouse and Lever endpoints.
- Normalizes postings and stores them in PostgreSQL through SQLAlchemy.
- Tracks job lifecycle, including active and inactive listings.
- Searches and filters postings, including by source and query.
- Analyzes job descriptions with Gemini and extracts concrete skills.
- Classifies extracted skills as **Required** or **Preferred** and groups them by category.
- Classifies role seniority and professional domain.
- Provides dashboard statistics and a searchable Skills Library with related jobs.

## Architecture

| Component | Technology and role |
| --- | --- |
| Frontend | React + Vite dashboard |
| Backend | FastAPI HTTP API |
| ORM | SQLAlchemy |
| Database | Supabase PostgreSQL |
| AI analysis | Gemini AI for skill extraction and classification |
| Job sources | Greenhouse and Lever public job endpoints |
| HTTP collection | HTTPX asynchronous clients |
| CI and scheduled collection | GitHub Actions |
| Backend hosting | Render |
| Frontend hosting | Vercel |

## Production deployment

### Render backend

The Render Web Service is named `roleradar-api`. Its Blueprint configuration is in [`render.yaml`](render.yaml): Python runtime, Free plan, one Uvicorn worker, `/ready` health check, and automatic deployment after checks pass (`autoDeployTrigger: checksPass`). The GitHub repository branch used for releases is `master`. The start command binds to Render's `$PORT`.

Configure the following values in the Render service settings:

- `DATABASE_URL`: Supabase PostgreSQL connection URL with SSL required. Use the appropriate pooler URL for the service.
- `ADMIN_API_TOKEN`: private token for administrative write routes.
- `GEMINI_API_KEY`: Gemini API credential.
- `CORS_ORIGINS`: the exact frontend origin `https://role-radar-ai-delta.vercel.app` (additional explicit origins may be comma-separated). Wildcards are rejected.

The Blueprint sets `APP_ENV=production`, `GEMINI_MODEL=gemini-3.5-flash-lite` and database pool defaults. Production startup requires a PostgreSQL URL with `sslmode=require`, `verify-ca`, or `verify-full`, a configured admin token, and explicit CORS origins.

### Vercel frontend

Configure the Vercel project with:

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Environment Variable | `VITE_API_BASE_URL=https://roleradar-api-tsi1.onrender.com` |

`VITE_API_BASE_URL` is public build-time configuration. The frontend centralizes API requests in `frontend/src/api.js`; the local Vite development proxy is not needed in production. Never put database URLs, Gemini keys, or administrative tokens in Vercel or any `VITE_` variable.

### CORS and deployment order

The backend allows only origins listed in `CORS_ORIGINS` in production. Keep the Vercel origin and backend URL aligned with the values above. For a new deployment, configure the Render backend and its environment first, deploy the Vercel frontend with `VITE_API_BASE_URL`, then confirm the exact Vercel origin in Render's `CORS_ORIGINS` setting.

The Render Blueprint requests deployment after CI checks pass. The repository's CI workflow runs for pushes and pull requests targeting `master` (and `main`). Vercel normally deploys through project-level Git integration, but its production branch and automatic deployment settings are not represented in this repository; verify in Vercel that production deploys from `master` before relying on that behavior.

Verify the service after deployment:

```text
GET https://roleradar-api-tsi1.onrender.com/health
GET https://roleradar-api-tsi1.onrender.com/ready
```

Administrative write endpoints require `Authorization: Bearer <ADMIN_API_TOKEN>` outside local development. The protected routes are:

- `POST /api/v1/ingestion/run-all`
- `POST /api/v1/jobs/greenhouse/{board_token}/sync`
- `POST /api/v1/jobs/lever/{site}/sync`

Read routes remain public. Verify that a protected route returns HTTP 401 without a token. Send the token only from a trusted operator or server-side client, never from browser code.

## Environment variables

### Backend (Render and local development)

| Variable | Purpose | Configuration |
| --- | --- | --- |
| `APP_ENV` | Selects development or production behavior | `production` on Render; defaults to development locally |
| `DATABASE_URL` | SQLAlchemy database connection | Supabase PostgreSQL with an SSL mode in production; SQLite is the local fallback when unset |
| `ADMIN_API_TOKEN` | Bearer token protecting administrative write endpoints | Required in production; keep private |
| `GEMINI_API_KEY` | Authenticates Gemini analysis requests | Configure in backend environment only |
| `GEMINI_MODEL` | Gemini model used for analysis | Render default: `gemini-3.5-flash-lite` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins | Explicit origin(s) in production; local Vite origins are added in development |
| `DB_POOL_SIZE` | SQLAlchemy connection pool size | Render default: `2` |
| `DB_MAX_OVERFLOW` | Extra SQLAlchemy connections above pool size | Render default: `2` |
| `DB_POOL_TIMEOUT` | Seconds to wait for a pooled connection | Render default: `30` |
| `DB_POOL_RECYCLE` | Connection recycle interval in seconds | Render default: `1800` |

### Frontend (Vercel)

| Variable | Purpose | Configuration |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Public base URL for the FastAPI backend | Set to the Render backend URL in Vercel; leave empty for local Vite proxy use |

Do not place credentials in the frontend environment. Vite embeds `VITE_*` values in the client bundle.

## Local development

Use Python 3.13 and Node.js 24.

### Backend

From the repository root:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
```

The backend loads the repository-root `.env`. In development, administrative routes are open only when `ADMIN_API_TOKEN` is unset; when set, provide a Bearer token. Do not use this local development behavior in shared or production environments. `/health` reports liveness and `/ready` checks database connectivity.

### Frontend

In a second terminal:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Vite serves the frontend at `http://localhost:5173`. With an empty `VITE_API_BASE_URL`, Vite proxies `/api` and `/health` to `http://127.0.0.1:8010`.

## CI and scheduled ingestion

The existing `.github/workflows/ci.yml` workflow runs on pushes and pull requests to `main` and `master`, and can be started manually. It installs pinned Python and npm dependencies, checks Python dependencies, runs Ruff and pytest, then runs frontend lint and production build.

`.github/workflows/ingestion.yml` runs the job ingestion workflow on its configured daily schedule or manually. It uses the GitHub Actions `DATABASE_URL` secret and invokes `scripts.run_ingestion` directly; it does not call the administrative HTTP API and does not require `ADMIN_API_TOKEN`.

Useful local checks:

```powershell
python -m ruff check backend scraper scripts
python -m pytest -v
cd frontend
npm run lint
npm run build
```

## Database and migrations

The deployed database is the existing Supabase PostgreSQL project. Keep its connection URL private, require SSL, and size the pool against the database connection limit. With the current Render configuration, the maximum pool connections per service process are `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × 1 worker`.

Alembic is configured with an initial baseline for the five SQLAlchemy tables. It can create the schema on a new database, and supports offline and online PostgreSQL/SQLite runs. The backend still calls `Base.metadata.create_all()` at startup and retains its SQLite schema migration helper while the baseline is reviewed. The existing Supabase database has **not** been migrated or stamped; do not assume its migration history is recorded. Before adopting Alembic for production, verify the live schema independently and plan a reviewed baseline stamp procedure.
