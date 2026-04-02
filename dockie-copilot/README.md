# Dockie Copilot Backend

This README is for the backend in `dockie-copilot/`.

- Product-facing overview: [../README.md](../README.md)
- Backend architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

## What This Service Owns

The backend owns:

- shipment APIs
- ingest, refresh, simulated refresh, and scenarios
- source health and readiness
- Google ADK agent runtime
- AG-UI streaming chat endpoint
- standby agents, notifications, digests, and generated outputs
- geospatial APIs
- fake-web supporting search

The frontend is a separate React app in `../frontend`.

## Quick Start

### Docker

Run these commands from `dockie-copilot/`:

```bash
cp .env.example .env
docker compose up --build
```

What Docker Compose actually does:

- starts Postgres with PostGIS and `vector`
- runs `alembic upgrade head`
- runs `python -m app.cli.commands ingest_if_empty`
- starts the API on `http://localhost:8000`
- starts the separate `standby-worker` container

Useful checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/shipments
curl http://localhost:8000/source-health
```

To force a full re-ingest on top of existing rows:

```bash
docker compose exec app python -m app.cli.commands ingest
```

### Local development without Docker

```bash
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python -m app.cli.commands ingest
uvicorn app.main:app --reload
```

You will need a local Postgres with PostGIS. `pgvector` is optional but recommended if you want embedding-backed retrieval to work fully.

### Frontend

The backend does not serve the frontend bundle. Run the sibling app separately from `../frontend` and point `VITE_API_BASE_URL` at `http://localhost:8000`.

## Useful CLI Commands

```bash
python -m app.cli.commands ingest
python -m app.cli.commands ingest_if_empty
python -m app.cli.commands refresh
python -m app.cli.commands live_refresh
python -m app.cli.commands simulated_refresh run_001
python -m app.cli.commands apply_scenario scenario_ship_004_anchor_arrival
python -m app.cli.commands health
python -m app.cli.commands standby_worker
python -m app.cli.commands standby_worker_once
```

When to use which:

- `ingest`: load the baseline dataset
- `refresh`: apply the challenge refresh fixture pack
- `live_refresh`: refresh configured connector-style sources
- `simulated_refresh`: change tracking and freshness state
- `apply_scenario`: push the app into a named business-state scenario
- `standby_worker_once`: run one standby evaluation cycle for testing

## Main HTTP Surface

The most important routes are:

### Core app routes

- `GET /health`
- `GET /app-bootstrap`
- `GET /source-health`
- `GET /sources/readiness`

### Shipment routes

- `GET /shipments`
- `GET /shipments/{id}`
- `GET /shipments/{id}/bundle`
- `GET /shipments/{id}/status`
- `GET /shipments/{id}/history`

### Agent routes

- `POST /agent/run`
- `POST /agent/agents/state`

### Standby routes

- `GET /standby-agents`
- `POST /standby-agents`
- `PATCH /standby-agents/{id}`
- `POST /standby-agents/{id}/run`
- `DELETE /standby-agents/{id}`
- `GET /notifications`
- `POST /notifications/read`
- `GET /agent-outputs`
- `GET /agent-outputs/{id}`

### Supporting context routes

- `GET /knowledge/search`
- `GET /web-search`
- `GET /web-search/plan`

### Dev-only worker control routes

- `POST /standby-worker/start`
- `POST /standby-worker/stop`
- `GET /standby-worker/status`

## Grounded Notes About The Current Backend

- The Docker setup is still local and demo oriented. The API container uses `uvicorn ... --reload`.
- The fake-web search is a simulated supporting-context layer, not real internet search.
- Voice is not handled by this backend today. The current voice flow lives in the frontend using browser APIs.
- Vector embeddings already exist here for document-chunk retrieval when embeddings and `pgvector` are available, but the product is not yet fully built around hybrid retrieval.
- Standby agents use a real persisted worker flow, but the worker model is still a polling loop rather than a dedicated workflow system.

## Standby-Agent Demo Flow

A short grounded example:

```bash
# create a watcher
python -m app.cli.commands create_standby_agent \
  "When this shipment reaches anchorage, send me an email." \
  email \
  ship-004 \
  30 \
  test-user \
  test@example.com

# flip the system into a known state
python -m app.cli.commands apply_scenario scenario_ship_004_anchor_arrival

# run one worker cycle
python -m app.cli.commands standby_worker_once
```

For the demo, scenarios and simulated refreshes are what change the watched conditions from false to true. In a live system, those changes would come from carrier, AIS, port, and workflow updates automatically.

## Where To Look

- App factory: `app/interfaces/api/app.py`
- Agent runtime: `app/application/adk_agent.py`
- Agent tools: `app/application/agent_tools.py`
- Core services: `app/application/services.py`
- Standby agents: `app/application/standby_services.py`
- CLI commands: `app/cli/commands.py`
- Fake web client: `app/infrastructure/fake_web.py`
- ORM models: `app/models/orm.py`

## Two More Weeks

If I had two more weeks on the backend, I would focus on:

- Better use of vector embeddings so retrieval can connect document chunks, shipment notes, events, and operational context more effectively.
- Real ETL for ingestion instead of relying so heavily on CLI-driven fixture and scrape flows.
- Better worker tech and more worker functionality for standby evaluation, long-running report generation, and other async jobs.
- AWS deployment for API, worker, Postgres, Redis, logs, secrets, and storage.
- Proper web search to replace the fake-web demo layer with a real search and source-ingestion stack.
- Better voice using live Google ADK rather than keeping voice as a browser-only frontend feature.
- A stronger likely-vessel discovery engine that ranks vessel candidates from weak signals like lane, ETA proximity, voyage code, route intent, and live movement, then produces a formal confidence score.
