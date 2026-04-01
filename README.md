# Dockie Copilot — Shipment Tracking Backend

A production-minded MVP backend for a shipment-tracking copilot for customers shipping vehicles by sea on the US–West Africa ro-ro corridor.

Note: a `.env.example` file is included at the repository root — copy it to `.env` and edit values before running the project.

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3.11+ (for local dev / tests without Docker)

### Run with Docker

```bash
# 1. Copy env config
cp .env.example .env

# 2. Build and start
docker compose up --build

# 3. In a separate terminal — run migrations + ingest fixtures
docker compose exec app alembic upgrade head
docker compose exec app python -m app.cli.commands ingest

# 4. Verify
curl http://localhost:8000/health
curl http://localhost:8000/shipments
```

The API will be live at **http://localhost:8000**.  
Interactive docs: **http://localhost:8000/docs**

Tip: to open an interactive shell in the running container, run:

```bash
docker exec -it dockie-app /bin/sh
```

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

