# Dockie Copilot Backend

This README is for the backend in `dockie-copilot/`.

- Product-facing overview: [../README.md](../README.md)
- Backend architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

## What This Service Owns

The backend owns:

- shipment APIs
- ingest, refresh, simulated refresh, and scenario flows
- source health and source readiness
- Google ADK agent runtime
- AG-UI streaming chat endpoint
- standby agents, notifications, digests, and generated outputs
- geospatial APIs
- fake-web supporting search

The frontend is a separate React app in `../frontend`.

## Quick Start

### Prerequisites

- Docker + Docker Compose for the easiest local run
- Python 3.11+ for local development without Docker
- Postgres with PostGIS if you are not using Docker

### Run with Docker

Run these commands from `dockie-copilot/`:

```bash
cp .env.example .env
docker compose up --build
```

What Docker Compose actually does:

- starts Postgres
- enables `postgis` and `vector`
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

### Run locally without Docker

```bash
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python -m app.cli.commands ingest
uvicorn app.main:app --reload
```

For this path you will need a local Postgres with PostGIS. `pgvector` is optional, but required if you want vector-backed similarity search instead of the default non-`pgvector` fallback.

### Frontend

The backend does not serve the frontend bundle. Run the sibling app separately from `../frontend` and point `VITE_API_BASE_URL` at `http://localhost:8000`.

## Useful CLI Commands

Run these from `dockie-copilot/`:

```bash
python -m app.cli.commands ingest
python -m app.cli.commands ingest_if_empty
python -m app.cli.commands refresh
python -m app.cli.commands live_refresh
python -m app.cli.commands simulated_refresh run_001
python -m app.cli.commands apply_scenario scenario_ship_004_anchor_arrival
python -m app.cli.commands import_live_carriers
python -m app.cli.commands health
python -m app.cli.commands aisdiag
python -m app.cli.commands create_standby_agent "<condition_text>" email ship-004 30 test-user test@example.com
python -m app.cli.commands list_standby_agents
python -m app.cli.commands run_standby_agent <agent_id> test-user
python -m app.cli.commands list_standby_runs <agent_id>
python -m app.cli.commands list_notifications test-user
python -m app.cli.commands embed_backfill 100
python -m app.cli.commands embed_rebuild 100 --all
python -m app.cli.commands standby_worker
python -m app.cli.commands standby_worker_once
```

When to use which:

- `ingest` loads the baseline dataset.
- `ingest_if_empty` is the bootstrap-safe version used by Docker Compose.
- `refresh` applies the refresh fixture pack.
- `live_refresh` refreshes configured connector-style sources.
- `simulated_refresh` changes tracking and freshness state.
- `apply_scenario` pushes the system into a named demo business state.
- `import_live_carriers` creates stable shipments from parsed live carrier rows.
- `create_standby_agent`, `list_standby_agents`, `run_standby_agent`, `list_standby_runs`, and `list_notifications` are the fastest way to exercise watcher behavior from the CLI.
- `embed_backfill` and `embed_rebuild` manage document-chunk embeddings.
- `standby_worker` runs the long-lived polling worker.
- `standby_worker_once` runs one evaluation cycle, which is useful for smoke tests.

## Fixture + Live Source Model

- Fixtures remain the stable baseline dataset.
- Live sources can refresh on top of that baseline when they are enabled and reachable.
- Simulated refreshes and scenarios are separate from live refresh and exist to drive the demo into known states.
- AISStream is integrated as a bounded live overlay and diagnostic capture path, but the main testing loop shifted toward fixture JSONs, simulated refreshes, and scenario files because live AIS updates were not predictable enough for repeatable demos or load testing.
- That fixture-first flow lets us force known state transitions on demand, which matters for standby agents, ETA-change scenarios, stale-data checks, and frontend verification.
- Source readiness is visible at `GET /sources/readiness`.
- Shipment-critical answers should still come from backend shipment state, not from fake-web narrative context.

## Main HTTP Surface

The most important routes today are:

### Core app routes

- `GET /health`
- `GET /app-bootstrap`
- `GET /source-health`
- `GET /sources/readiness`
- `GET /sources/aisstream/diagnostic`

### Shipment routes

- `GET /shipments`
- `POST /shipments/manual`
- `GET /shipments/carrier-performance`
- `GET /shipments/{id}`
- `GET /shipments/{id}/bundle`
- `GET /shipments/{id}/status`
- `GET /shipments/{id}/history`
- `GET /shipments/{id}/eta-revisions`
- `GET /shipments/{id}/port-context`
- `GET /shipments/{id}/demurrage-exposure`
- `GET /shipments/{id}/port-congestion`
- `GET /shipments/{id}/vessel-anomaly`
- `GET /shipments/compare`

### Agent routes

- `POST /agent/run`
- `POST /agent/agents/state`
- `GET /agent/shipments`
- `GET /agent/shipments/{shipment_id}/status`
- `GET /agent/shipments/{shipment_id}/history`
- `GET /agent/shipments/{shipment_id}/eta-revisions`
- `GET /agent/shipments/{shipment_id}/port-context`
- `GET /agent/vessel/position`

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

### Supporting-context routes

- `GET /knowledge/search`
- `GET /web-search`
- `GET /web-search/plan`

### Geospatial routes

- `GET /geo/nearby-vessels`
- `GET /geo/nearest-port`
- `GET /geo/vessel-proximity/{mmsi}`
- `GET /geo/shipment-proximity/{shipment_id}`
- `GET /geo/reference-ports`

### Dev-only worker control routes

- `POST /standby-worker/start`
- `POST /standby-worker/stop`
- `GET /standby-worker/status`

## Running Tests

Run these from `dockie-copilot/`:

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing
```

## Project Structure

```text
app/
  application/     use-case orchestration, agent tools, standby services
  cli/             CLI entry points
  core/            config, logging, security
  domain/          business rules and domain logic
  infrastructure/  database, cache, ingest, fake-web, embeddings, source adapters
  interfaces/      FastAPI routes and request handling
  models/          SQLAlchemy ORM models
  schemas/         Pydantic request and response contracts
  main.py          ASGI entrypoint

alembic/           database migrations
tests/             pytest suite and challenge fixtures
```

## Key Environment Variables

These are the most useful variables to know about:

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | Async database URL | `postgresql+asyncpg://dockie:dockie_secret@localhost:5432/dockie_copilot` |
| `SYNC_DATABASE_URL` | Sync database URL for CLI and Alembic | `postgresql://dockie:dockie_secret@localhost:5432/dockie_copilot` |
| `APP_ENV` | Environment name | `development` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `ADK_MODEL` | Google ADK model name | `gemini-3-flash-preview` |
| `ADK_SESSION_BACKEND` | ADK session backend (`database` or `redis` recommended for shared state) | `memory` |
| `REDIS_URL` | Redis cache/session URL for shared cache and optional Redis-backed ADK sessions | unset |
| `CACHE_PREFIX` | Cache namespace prefix | `dockie` |
| `OPENAI_API_KEY` | Enables embeddings generation | unset |
| `GOOGLE_API_KEY` | Enables the ADK model runtime | unset |
| `AISSTREAM_API_KEY` | Enables AISStream diagnostic/live capture | unset |
| `KNOWLEDGE_VECTOR_ENABLED` | Toggles embedding-backed knowledge features | `true` |
| `KNOWLEDGE_VECTOR_BACKEND` | Retrieval backend mode | `array` |
| `SUPABASE_PROJECT_URL` | Supabase project URL for standby email delivery | unset |
| `SUPABASE_EDGE_FUNCTION_KEY` | Supabase Edge Function auth key | unset |
| `SUPABASE_JWKS_URL` | JWKS URL for Supabase JWT verification | unset |

## Cache, Sessions, and Retrieval

- If `CACHE_ENABLED=true` but `REDIS_URL` is missing, caching falls back to the null backend.
- If `REDIS_URL` is set, shipment lists, shipment status, shipment history, and source health can use Redis-backed JSON caching.
- Cache-miss rebuilds use a single-flight lock so multiple workers do not stampede the same expensive status calculation.
- `ADK_SESSION_BACKEND` supports `memory`, `database`, and `redis`.
- The checked-in `.env.example` uses `database` so agent thread state survives across backend processes without depending on per-process memory.
- The repo also includes a Redis-backed ADK session service for deployments that want shared cache and shared sessions in the same tier.
- `memory` is still available as a lightweight fallback for single-process local work, but it is not the recommended mode for multi-worker deployment.
- `search_supporting_context` runs knowledge search and fake-web search together in parallel for mixed questions.
- `web_search` is supporting context, not the source of truth for shipment state.
- Embeddings already exist for document chunks. Vector similarity search is used when embeddings are available and `KNOWLEDGE_VECTOR_BACKEND=pgvector`.

## What Changed After The Load Review

Several issues from the earlier load-review pass are now handled differently in code:

- Session continuity: the ADK runtime no longer has to rely on in-memory sessions. `build_session_service()` supports `database` and `redis`, and the local example environment is configured to use `database` so `/agent/run` and `/agent/agents/state` can share persistent thread state.
- First-load request fan-out: `GET /app-bootstrap` collapses the initial shell data into one request for shipments, source health, standby agents, notifications, and outputs. `GET /shipments/{id}/bundle` also collapses shipment detail, status, and history into one request per selected shipment.
- Duplicate shipment loads: `ShipmentService.get_shipment_bundle()` loads the shipment once, then passes the same ORM object into the status and history builders so those paths do not each re-fetch the shipment row.
- Shipment list over-fetching: the list endpoint now uses `ShipmentRepository.get_all_summary()` instead of the full eager-loaded path, so shipment summaries do not pull every evidence row into memory.
- Cache coordination: shipment status/history and source health are cacheable, and shipment-status rebuilds use a single-flight coordinator so only one worker should do the expensive rebuild when Redis is available.
- Knowledge-search churn: the frontend now only performs the post-answer `searchKnowledgeBase()` fallback when the agent did not already use `search_knowledge_base` or `search_supporting_context` during that turn.
- Streaming and map pressure: the frontend reveal loop now buffers assistant text instead of rewriting the transcript on every tiny delta, and `ShipmentMap` reuses one Leaflet instance with layer updates instead of destroying and rebuilding the map for each render.
- Position-history scale: the `positions` and `latest_positions` tables now include indexes for the MMSI/IMO lookup patterns used by shipment history and live-position lookups.

These changes reduce the most obvious failure modes from the original review, but the backend is still demo-oriented in a few places. For real horizontal scale, pair shared sessions with Redis caching and run production workers without `--reload`.

## Key Design Decisions

- Raw payloads are persisted into `raw_events` before normalization.
- The JSONB `payload` column stores a PostgreSQL-safe copy of the source payload after control characters such as null bytes are stripped.
- The `raw_payload_text` text column stores the serialized original payload so escaped sequences such as `\\u0000` are preserved for provenance, debugging, and security review.
- Hostile or invalid payloads are quarantined instead of being silently trusted.
- Older position updates do not overwrite fresher latest-position rows.
- Text input is sanitized and URLs are checked so unsafe content does not flow straight through the system.
- Source policy metadata affects trust, fallback behavior, and how degraded sources are surfaced.

## Key Features

- Standby agents for background monitoring, notifications, digests, documents, spreadsheets, reports, and email-style outputs.
- Simulated web search over the fake-web corpus for narrative context without depending on live internet search.
- Google ADK agent runtime with AG-UI-compatible streaming.
- Structured agent tools for shipments, history, ETA revisions, port context, knowledge search, web search, demurrage reasoning, and geospatial lookups.
- PostGIS-powered proximity and port-geofence APIs.
- Supabase Edge Function-based standby email delivery when the Supabase email settings are configured.
- Document-chunk embeddings and optional vector retrieval support.

## Grounded Notes About The Current Backend

- Docker Compose is still local and demo oriented. The API container runs `uvicorn ... --reload`.
- The fake-web layer is simulated supporting context, not real internet search.
- Voice is not handled by this backend today. The current voice flow lives in the frontend with browser APIs.
- The standby worker is real and persisted, but it is still a polling loop rather than a dedicated workflow engine.
- The default ADK session backend is still `memory` unless you configure Redis-backed sessions.

## Scenario And Standby-Agent Testing

Use this grounded Tema anchorage example from `dockie-copilot/`. This corrects the shipment/scenario pairing so the demo flow actually matches the fixtures: `ship-004` is the Tema shipment that matches `scenario_ship_004_anchor_arrival`.

```bash
python -m app.cli.commands create_standby_agent \
  "Alert me when the vessel reaches anchorage at Tema. send me an email." \
  email \
  ship-004 \
  30 \
  test-user \
  test@example.com

python -m app.cli.commands run_standby_agent <agent_id> test-user
python -m app.cli.commands apply_scenario scenario_ship_004_anchor_arrival
python -m app.cli.commands run_standby_agent <agent_id> test-user
python -m app.cli.commands list_standby_runs <agent_id>
python -m app.cli.commands list_notifications test-user
```

The create command prints the new `<agent_id>`. In this flow:

- the first `run_standby_agent` checks the agent before the trigger condition is true
- `apply_scenario` moves the system into the anchorage-arrival state
- the second `run_standby_agent` re-evaluates the condition after the state change

For a worker-driven check instead of a manual forced run, use the background worker commands below.

## Run The Standby Worker Container

`docker compose up --build` already starts `standby-worker` with the API.

Useful commands:

```bash
docker compose up --build
docker compose logs -f standby-worker
docker compose stop standby-worker
docker compose exec app python -m app.cli.commands standby_worker_once
```

Use `standby_worker_once` when you want one deterministic evaluation pass during testing. Use the long-running container when you want the normal polling behavior.

## Where To Look

- App factory: `app/interfaces/api/app.py`
- Agent runtime: `app/application/adk_agent.py`
- Agent tools: `app/application/agent_tools.py`
- Core services: `app/application/services.py`
- Standby agents: `app/application/standby_services.py`
- CLI commands: `app/cli/commands.py`
- Fake web client: `app/infrastructure/fake_web.py`
- Cache backend: `app/infrastructure/cache.py`
- Email delivery: `app/infrastructure/email.py`
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
