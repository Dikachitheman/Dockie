# Dockie Copilot — Shipment Tracking Backend

A production-minded MVP backend for a shipment-tracking copilot for customers shipping vehicles by sea on the US–West Africa ro-ro corridor.

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3.11+ (for local dev / tests without Docker)

### Run with Docker

```bash
# 1. Copy env config
cp .env.example .env

# 2. Build and start (migrations, conditional fixture ingest if DB is empty, API + standby worker)
docker compose up --build

# 3. Verify
curl http://localhost:8000/health
curl http://localhost:8000/shipments
```

The API will be live at **http://localhost:8000**.  
Interactive docs: **http://localhost:8000/docs**

---

### Run Locally (without Docker)

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Start Postgres (requires PostGIS)
# e.g. docker run -e POSTGRES_PASSWORD=dockie_secret -p 5432:5432 postgis/postgis:16-3.4

# 3. Set environment
cp .env.example .env
# Edit DATABASE_URL and SYNC_DATABASE_URL to point to localhost

# 4. Run migrations
alembic upgrade head

# 5. Ingest fixtures
python -m app.cli.commands ingest

# 6. Start API
uvicorn app.main:app --reload
```

---

## CLI Commands

```bash
# Load fixtures into the database
python -m app.cli.commands ingest

# Load fixtures only if there are no shipments (used by Docker Compose bootstrap)
python -m app.cli.commands ingest_if_empty

# Apply the challenge refresh fixture pack.
python -m app.cli.commands refresh

# Refresh configured source connectors and update source health.
python -m app.cli.commands live_refresh

# Print source health table
python -m app.cli.commands health
```

## Fixture + Live Source Model

- Fixtures remain in place as the stable baseline dataset
- Live sources are refreshed as overlays when enabled/configured
- Newer trusted live records can replace older baseline-derived records
- If live sources are unavailable, the fixture baseline still powers the product
- Source readiness is visible at `GET /sources/readiness`

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + DB check |
| GET | `/app-bootstrap` | First-load bootstrap payload for shipments, source health, agents, notifications, and outputs |
| GET | `/source-health` | Source health and freshness |
| GET | `/shipments` | List all shipments |
| GET | `/shipments/{id}` | Shipment detail with vessels + evidence |
| GET | `/shipments/{id}/bundle` | Shipment detail, status, and history in one request |
| GET | `/shipments/{id}/status` | Copilot status: position, ETA confidence, freshness |
| GET | `/shipments/{id}/history` | Full track + voyage events |
| GET | `/agent/shipments` | Agent tool: list shipments |
| GET | `/agent/shipments/{id}/status` | Agent tool: shipment status |
| GET | `/agent/shipments/{id}/history` | Agent tool: shipment history |
| GET | `/agent/vessel/position?mmsi=...` | Agent tool: vessel position |

---

## Running Tests

```bash
# All tests (no DB required — domain logic and normalization tests are pure)
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=term-missing
```

---

## Project Structure

```
app/
├── core/            # Config, logging, security utilities
├── domain/          # Pure business logic (no I/O)
│   ├── models.py    # Domain dataclasses
│   └── logic.py     # Freshness, ETA confidence, change detection
├── application/     # Orchestration layer
│   ├── services.py  # ShipmentService, SourceHealthService
│   └── agent_tools.py  # Structured JSON tools for AI agents
├── infrastructure/  # I/O adapters
│   ├── database.py  # Async SQLAlchemy engine + session
│   ├── ingest.py    # Fixture ingest pipeline
│   ├── normalizer.py   # Validation + normalization
│   ├── source_policy.py # Source classification
│   └── repositories/   # DB access layer
├── interfaces/
│   ├── api/         # FastAPI routes
│   └── cli/         # CLI commands
├── models/          # SQLAlchemy ORM models
└── schemas/         # Pydantic response schemas

alembic/             # Database migrations
tests/               # pytest test suite
  fixtures/          # JSON test fixtures
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Async DB URL (asyncpg) | `postgresql+asyncpg://...` |
| `SYNC_DATABASE_URL` | Sync DB URL (for Alembic) | `postgresql://...` |
| `POSTGRES_DB` | Database name | `dockie_copilot` |
| `POSTGRES_USER` | DB username | `dockie` |
| `POSTGRES_PASSWORD` | DB password | `dockie_secret` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `APP_ENV` | Environment name | `development` |

---

## Cache Behavior

- `CACHE_ENABLED=true` with no `REDIS_URL`: caching falls back cleanly to the null backend, which is fine for lightweight local development.
- `CACHE_ENABLED=true` with `REDIS_URL` set: shipment lists, shipment status, shipment history, and source health use Redis-backed JSON caching.
- Cache misses for expensive shipment status rebuilds use a single-flight lock so one worker rebuilds while others wait briefly for the filled cache instead of stampeding the database.
- `CACHE_PREFIX` namespaces keys by environment or deployment.
- `CACHE_LIST_SHIPMENTS_TTL_SECONDS`, `CACHE_SHIPMENT_STATUS_TTL_SECONDS`, `CACHE_SHIPMENT_HISTORY_TTL_SECONDS`, and `CACHE_SOURCE_HEALTH_TTL_SECONDS` tune freshness independently.
- `CACHE_SINGLEFLIGHT_LOCK_TTL_SECONDS`, `CACHE_SINGLEFLIGHT_WAIT_TIMEOUT_MS`, and `CACHE_SINGLEFLIGHT_POLL_INTERVAL_MS` control lock lease duration and waiter behavior.

Recommended setup:
- Local dev: keep Redis optional; use the null backend unless you are actively testing cache behavior.
- Shared dev/staging: set `REDIS_URL` so multi-process workers share cache state and single-flight coordination.
- Production: set `REDIS_URL` and a deployment-specific `CACHE_PREFIX` so cache state and lock keys stay isolated per environment.

## Parallel Tooling

- Safe bundled parallel path: `search_supporting_context` runs `search_knowledge_base` and `web_search` together and returns them in fixed `knowledge_base` and `web_search` slots.
- Use `search_supporting_context` instead of manually calling both tools when the user needs internal evidence plus external narrative context in one answer.
- `web_search` now uses bounded source fan-out and bounded fetch concurrency so new external search requests do not explode into unbounded remote index fetches.
- Shipment-critical calculations should still come from shipment/status/history tools; `web_search` is supporting context, not the source of truth for vessel state.

## Key Design Decisions

- **Raw payloads are always persisted first** before any normalization
- **Stale positions never overwrite fresher data** — enforced at the repository layer
- **Malicious/invalid payloads are quarantined** with reason codes, never silently dropped
- **Source policy metadata** drives trust, freshness thresholds, and degradation behavior
- **All text input is treated as untrusted** — sanitized via bleach, HTML-escaped on output
- **javascript: URLs are rejected** at the normalization layer
- **Parameterized queries only** — no string interpolation into SQL

## Key Features

- **Standby agents**: background watchers that evaluate semantic conditions against shipments, configurable via the CLI and a long-running worker (`python -m app.cli.commands standby_worker`). See [dockie-copilot/app/application/standby_services.py](dockie-copilot/app/application/standby_services.py) and CLI helpers in [dockie-copilot/app/cli/commands.py](dockie-copilot/app/cli/commands.py).

- **Simulated web search (FakeWeb)**: a remote-first fake web corpus used by the `web_search` and `search_supporting_context` tools to provide narrative context without depending on third-party search APIs. See [dockie-copilot/app/infrastructure/fake_web.py](dockie-copilot/app/infrastructure/fake_web.py) and the agent tooling in [dockie-copilot/app/application/agent_tools.py](dockie-copilot/app/application/agent_tools.py).

- **Agent runtime (Google ADK + AG-UI)**: the agent runtime is implemented using Google ADK and exposed via AG-UI-compatible streaming routes. See [dockie-copilot/app/application/adk_agent.py](dockie-copilot/app/application/adk_agent.py).

- **Structured agent tools**: list_shipments, get_shipment_status, get_shipment_history, search_supporting_context (parallel KB + web), web_search, ETA and demurrage helpers, PostGIS geospatial tools, and more. Tool implementations live in [dockie-copilot/app/application/agent_tools.py](dockie-copilot/app/application/agent_tools.py).

- **Standby digests & notifications**: standby agents can enqueue digest items and trigger email notifications. By default the project uses a Supabase Edge Function pattern for sending standby emails (see [dockie-copilot/app/infrastructure/email.py](dockie-copilot/app/infrastructure/email.py)); ADK-hosted integration connectors are left as TODOs.

- **Geospatial & caching**: PostGIS-powered spatial queries and Redis-backed caching with single-flight rebuild locking for expensive shipment-status calculations.

## Project definition — what we implemented

- **Satisfied**:
  - **Python backend (FastAPI)**: implemented under [dockie-copilot/app](dockie-copilot/app).
  - **Postgres + PostGIS**: Docker Compose + migrations are provided (see [dockie-copilot/alembic](dockie-copilot/alembic) and `docker-compose.yml`).
  - **Agent runtime (Google ADK) + AG-UI**: implemented (see [dockie-copilot/app/application/adk_agent.py](dockie-copilot/app/application/adk_agent.py) and agent tools).
  - **Frontend features**: shipment list, multi-shipment switching, chat UI, voice input and spoken playback, and map cards (see [frontend/src/components/ChatPanel.tsx](frontend/src/components/ChatPanel.tsx)).
  - **Structured retrieval & tools**: `search_supporting_context` and `web_search` (fake-web) implemented and audited.

- **Partially implemented / Not used**:
  - **Google ADK integrations (catalog connectors)** such as ADK-hosted email/reminder connectors were NOT integrated in this submission. The code uses a Supabase Edge Function for standby emails instead ([dockie-copilot/app/infrastructure/email.py](dockie-copilot/app/infrastructure/email.py)). These ADK integrations are documented as TODOs and straightforward to wire in as next steps.
  - **Full agent-emitted AG-UI structured card state**: the frontend currently uses UI-side heuristics to render rich cards; moving card emission to explicit agent-directed AG-UI state is a planned improvement.

## Where to look

- Agent runtime & tools: [dockie-copilot/app/application/adk_agent.py](dockie-copilot/app/application/adk_agent.py), [dockie-copilot/app/application/agent_tools.py](dockie-copilot/app/application/agent_tools.py)
- Standby agents & CLI: [dockie-copilot/app/application/standby_services.py](dockie-copilot/app/application/standby_services.py), [dockie-copilot/app/cli/commands.py](dockie-copilot/app/cli/commands.py)
- Fake web search: [dockie-copilot/app/infrastructure/fake_web.py](dockie-copilot/app/infrastructure/fake_web.py)
- Email (standby digests): [dockie-copilot/app/infrastructure/email.py](dockie-copilot/app/infrastructure/email.py)

---

If you'd like, I can add repository TODOs for ADK integration wiring, or draft an example ADK integration for email reminders.

## Scenario & standby-agent testing

Useful commands for exercising standby agents and quick scenario-driven tests. These complement the existing CLI examples above — do not repeat `alembic upgrade head`, `ingest`, or `uvicorn` which are documented earlier.

Reset the database schema and ensure PostGIS (and pgvector if available) are installed:

```bash
python - <<'PY'
import psycopg2
conn = psycopg2.connect("postgresql://postgres:jambrothers@localhost:5432/dockie_copilot")
conn.autocommit = True
cur = conn.cursor()
cur.execute("DROP SCHEMA IF EXISTS public CASCADE;")
cur.execute("CREATE SCHEMA public;")
cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")  # only if pgvector is installed
cur.close()
conn.close()
print("database schema reset")
PY

alembic upgrade head
python -m app.cli.commands ingest
uvicorn app.main:app --reload
```

Create a standby watcher (CLI example):

The test flow

#ship-004 (GREAT ACCRA → GHTEM/Tema, status: booked)

Trigger: anchorage_status — FALSE when vessel is underway, TRUE when at anchor

FALSE base state — vessel is underway approaching Tema, no anchor:


python -m app.cli.commands apply_scenario scenario_ship_004_underway
Create the agent (should NOT fire because vessel is underway):


python -m app.cli.commands create_standby_agent \
  "Alert me when the vessel reaches anchorage at Tema." \
  email \
  ship-004 \
  30 \
  test-user \
  dikachi.anosike@gmail.com
Copy the agent id from the output.

First run — expect will_fire=False, condition_matched=False:


python -m app.cli.commands run_standby_agent <agent-id> test-user
You'll see standby_agent_fire_decision log with will_fire=False.

Flip to TRUE state — vessel arrives at anchor:


python -m app.cli.commands apply_scenario scenario_ship_004_anchor_arrival
Second run — expect will_fire=True, agent fires:


python -m app.cli.commands run_standby_agent <agent-id> test-user
You'll see standby_agent_fire_decision with will_fire=True and action_executed=email_queued.

These commands are intended for local investigation and smoke-testing of standby logic, digest generation, and notification output flows. If you'd like, I can add a short `tools/` script to automate these sequences and capture the created agent ids for scripted runs.


## Run the standby worker container (Docker)

`docker compose up` starts `standby-worker` with the API. It waits for the `app` container to start, then runs migrations, `ingest_if_empty` (same as `ingest` when there are no shipments), and the long-running `standby_worker` loop.

```bash
# API only (no background standby loop)
docker compose up db app

# Full stack (default compose file)
docker compose up --build

docker compose logs -f standby-worker
docker compose stop standby-worker
```

To force a full re-ingest on top of existing rows, use `docker compose exec app python -m app.cli.commands ingest` (see CLI section).

## Some useful commands to update Database state.

Use apply_scenario when you want to change analytics cards/tables in a visible way. Use simulated_refresh when you want to change position/freshness/tracking-derived analytics.

## What each command is used for

### `python -m app.cli.commands refresh`
Loads the base fixture dataset used for local development and testing.

### `python -m app.cli.commands simulated_refresh run_001`
Applies the first simulated position snapshot.

### `python -m app.cli.commands simulated_refresh run_002`
Applies the second simulated position snapshot.

### `python -m app.cli.commands simulated_refresh run_003`
Applies the third simulated position snapshot, including a newer anchored position update for a vessel.

### `python -m app.cli.commands apply_scenario scenario_eta_delay`
Simulates an ETA delay state.

### `python -m app.cli.commands apply_scenario scenario_stale_position_feed`
Simulates stale position data for freshness-warning testing.

### `python -m app.cli.commands apply_scenario scenario_ship_004_anchor_arrival`
Simulates a vessel arriving at anchorage so standby monitoring can detect a false-to-true transition.

### `python -m app.cli.commands apply_scenario scenario_eta_slip`
Simulates an ETA revision/slip for analytics and monitoring tests.

### `python -m app.cli.commands apply_scenario scenario_clearance_not_ready`
Sets `ship-001` into an incomplete customs/clearance state.

### `python -m app.cli.commands apply_scenario scenario_demurrage_risk`
Adds incomplete clearance for `ship-005` and a congestion spike at `NGLOS` to simulate demurrage risk.


## Known issues, load-test findings & hardening

Summary of high-priority problems discovered during code review and checklist verification (see [notes/claude_analysis.txt](notes/claude_analysis.txt#L1-L182)) and where to look to fix them.

- **Session state is in-memory by default**: ADK session storage defaults to in-memory which breaks when running multiple backend processes. Fix: set `ADK_SESSION_BACKEND=redis` and provide `REDIS_URL` (Upstash or local) so the `RedisSessionService` is used. See [app/application/adk_agent.py](app/application/adk_agent.py) and the `ADK_SESSION_BACKEND` setting in [app/core/config.py](app/core/config.py).

- **Cache is effectively disabled in local envs**: `CACHE_ENABLED=true` with no `REDIS_URL` selects the null cache backend. Enable Redis in `.env` to activate caching and single-flight stampede protection. See [app/infrastructure/cache.py](app/infrastructure/cache.py) and `CACHE_*` settings in [app/core/config.py](app/core/config.py).

- **Front-end bootstrap fan-out**: the initial page load performs multiple parallel calls (shipments, source-health, bundle, threads) which can saturate the backend. The app exposes `/app-bootstrap` to collapse these calls; prefer that endpoint for first-load. See [frontend/src/lib/api.ts](frontend/src/lib/api.ts) and [app/application/services.py](app/application/services.py).

- **Duplicate and eager data fetching**: several endpoints reload the same shipment and eagerly load `evidence_items` for list views. Change `ShipmentRepository.get_all()` to return summary rows or add a lightweight `get_shipments_summary()` call to avoid over-fetching during list renders. See [app/infrastructure/repositories/shipment_repo.py](app/infrastructure/repositories/shipment_repo.py).

- **Knowledge search is expensive / double-called**: the frontend calls knowledge search twice per chat turn and the backend ranks many artifacts in Python. Remove the double-call on the UI and consider lightweight pre-filtering, caching, or synonym expansion to reduce CPU. Key files: [frontend/src/components/ChatPanel.tsx](frontend/src/components/ChatPanel.tsx) and [app/application/services.py](app/application/services.py).

- **Chat streaming causes frequent re-renders**: the UI updates assistant deltas very frequently causing layout thrash. Throttle streaming updates or batch DOM updates in `ChatPanel.tsx` to improve main-thread performance.

- **Missing indexes on position tables**: add indexes on `positions.mmsi`, `positions.imo`, and `positions.observed_at` to speed history queries and prevent table scans. See [app/models/orm.py](app/models/orm.py).

- **Map & list scaling**: the frontend renders full lists and recreates maps per card; add pagination/virtualization and reuse map instances. See [frontend/src/components/ShipmentList.tsx](frontend/src/components/ShipmentList.tsx) and [frontend/src/components/ShipmentMap.tsx](frontend/src/components/ShipmentMap.tsx).

### Verified fixes in this repo

Per the implementation checklist, the repo already contains a number of hardening and UX fixes (review `notes/claude_analysis.txt` for the full checklist). Notable items implemented:

- Redis-backed ADK session service and fallback behavior to in-memory sessions when Redis is unavailable.
- Cache single-flight / stampede protection wiring for expensive shipment-status rebuilds.
- Reduced frontend bootstrap fan-out by using a consolidated `/app-bootstrap` payload.
- Avoided eager-loading heavy evidence in list endpoints and added lighter summary endpoints.
- Improved standby-agent deletion cleanup and added digest/email plumbing (Supabase Edge Function pattern by default).
- Added segmented thick map lines, event stamps, and multi-shipment overlays in the tracking map.
- Hardened the streaming failure path so failed runs return a friendly assistant message instead of leaving empty placeholders.

### Remaining recommended next steps (short list)

1. Switch ADK session backend to Redis in staging and production (`ADK_SESSION_BACKEND=redis`, provide `REDIS_URL`) and verify session restore across multiple workers.
2. Add database indexes for `positions` access patterns and verify with a simple explain plan on large datasets.
3. Add a short-lived lock for cache-miss rebuilds where Redis is enabled (SETNX-based single-flight) and increase DB pool for API vs worker processes.
4. Remove double knowledge-search from the frontend; consider a backend-side prefetch that returns both knowledge and supporting context in one call.
5. Add a small k6/wrk/hey load-test harness under `tools/loadtest/` (I can add this for you).

### Quick verification & load-test commands

Run the usual local setup, then run these checks:

```bash
# Start services
cp .env.example .env
# configure REDIS_URL and ADK_SESSION_BACKEND in .env for Redis-backed sessions
docker compose up --build

# Migrate + ingest (usually unnecessary: compose runs these on startup)
docker compose exec app alembic upgrade head
docker compose exec app python -m app.cli.commands ingest

# Run a single standby evaluation (light-weight check)
docker compose exec app python -m app.cli.commands standby_worker_once

# Run an embedding backfill smoke test (if keys present)
docker compose exec app python -m app.cli.commands embed_backfill 1

# Run unit tests
docker compose exec app pytest tests/ -qexpensive shipment-status calculations.

## Fake websites (deployed on Vercel)

The project includes a set of fake web sources used by the `web_search` and `search_supporting_context` tools. These are deployed to Vercel under the repository `github/dikachitheman/fake-websites`.

Available site base URLs (from `fake-websites/sources.json`):

- https://fake-websites-zqv2.vercel.app/
- https://fake-websites-3cew.vercel.app/
- https://fake-websites-84bc.vercel.app/
- https://fake-websites-ex12.vercel.app/
- https://fake-websites-qyi7.vercel.app/
- https://fake-websites-kauf.vercel.app/
- https://fake-websites-22.vercel.app/
- https://fake-websites-93w7.vercel.app/
- https://fake-websites.vercel.app/
- https://fake-websites-2.vercel.app/
- https://fake-websites-itjp.vercel.app/
- https://fake-websites-d9wp.vercel.app/

Each site exposes a `search-index.json` endpoint (for example `https://fake-websites-zqv2.vercel.app/search-index.json`) which is used by the fake web search indexer.

