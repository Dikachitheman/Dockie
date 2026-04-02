# Backend Architecture

This document covers the backend in `dockie-copilot/` only.

- Whole-system architecture: [../ARCHITECTURE.md](../ARCHITECTURE.md)
- Product framing and feature walkthrough: [../README.md](../README.md)

## Scope

The backend owns:

- shipment APIs
- ingest, refresh, and scenario flows
- source health and source readiness
- Google ADK agent runtime
- AG-UI streaming endpoint
- standby-agent persistence, evaluation, notifications, and outputs
- geospatial APIs
- fake-web supporting search

It does not serve the frontend bundle. The React app lives in the sibling `frontend/` directory.

## Stack

- Python
- FastAPI
- SQLAlchemy async
- Alembic
- PostgreSQL
- PostGIS
- `pgvector` when available
- Redis when configured
- Google ADK for the agent runtime

## Runtime Processes

### API process

The main app is created in `app/interfaces/api/app.py` and started through `app/main.py`.

At startup it:

- configures logging
- checks database connectivity
- checks cache connectivity
- diagnoses ADK schema state
- builds the ADK agent once and stores it on `app.state`

### Standby-worker process

The repo includes a separate `standby-worker` container. In Docker Compose it runs:

1. `alembic upgrade head`
2. `python -m app.cli.commands ingest_if_empty`
3. `python -m app.cli.commands standby_worker`

That worker:

- polls for due standby agents
- evaluates them
- dispatches actions
- processes queued digests

There is also a dev-only HTTP-started worker path, but the separate worker container is the main intended runtime shape in this repo.

### Docker Compose shape

Compose currently starts three services:

- `db`
- `app`
- `standby-worker`

Important grounded note:

- the `app` container still runs `uvicorn ... --reload`
- this is convenient for local and demo use, not the final production deployment shape

## Backend Layers

The backend is intentionally layered.

### `app/domain`

Pure logic and domain models.

- freshness scoring
- ETA confidence logic
- core business rules

### `app/application`

Use-case orchestration.

- shipment services
- source health services
- app bootstrap assembly
- agent tool wrappers
- standby-agent orchestration

### `app/infrastructure`

I/O and persistence.

- database engine and session
- repositories
- cache
- fake-web search client
- email integration
- ingest and simulated ingest
- source adapters and policies
- embeddings service

### `app/interfaces`

External entry points.

- FastAPI routes
- CLI commands

### `app/models` and `app/schemas`

- SQLAlchemy ORM models
- Pydantic request and response contracts

## Core Backend Flows

### 1. Shipment data flow

The backend follows a raw-first ingest model:

1. source payloads are fetched
2. raw payloads are persisted first
3. validation and hostile-content checks run
4. invalid data is quarantined
5. valid data is normalized into shipments, vessels, positions, evidence, revisions, and events

This keeps the ingest path inspectable and prevents malformed or stale upstream data from silently becoming trusted state.

### 2. App bootstrap flow

`AppBootstrapService` assembles the first-load payload used by the frontend. It gathers, in parallel:

- shipment summaries
- source health
- standby agents
- notifications
- agent outputs

This exists to reduce frontend first-load fan-out.

### 3. Shipment read flow

The read model is centered around:

- shipment summaries
- shipment detail
- shipment status
- shipment history
- shipment bundle

`ShipmentService` handles these compositions and uses cache where configured.

### 4. Agent flow

The ADK agent is exposed through `/agent/run`.

The backend agent is tool-constrained. It does not answer from free text alone. Current tool surface includes:

- list shipments
- get shipment status
- get shipment history
- get vessel position
- search knowledge base
- search supporting context
- web search
- ETA revisions
- port context
- clearance checklist
- realistic ETA
- demurrage exposure
- shipment comparison
- vessel anomaly detection
- vessel swap check
- PostGIS proximity helpers

That tool boundary is one of the main grounding mechanisms in the backend.

### 5. Standby-agent flow

Standby agents are persisted records with:

- user scope
- shipment scope
- condition text
- trigger classification
- interval and cooldown
- last-check and last-fire state

The backend supports:

- CRUD over `/standby-agents`
- manual execution over `/standby-agents/{id}/run`
- notification listing
- agent-output listing
- digest processing

The current evaluation model is still a pragmatic polling loop, not a full workflow engine.

### 6. Search and retrieval flow

There are two supporting-context paths today:

- structured knowledge search over operational tables and document chunks
- fake-web search over a deployed, controlled fake-web corpus

Important grounded nuance:

- vector embeddings already exist in the backend and are used for document chunks when available
- retrieval is still mixed: operational tables are largely structured and lexical, while document chunks can use vector ranking
- this is better than pure keyword matching alone, but it is still not the final retrieval architecture

## Data Categories

The main backend data categories are:

- raw events and quarantined events
- normalized shipments, vessels, latest positions, and voyage events
- ETA revisions and port observations
- source health and source readiness metadata
- clearance, congestion, demurrage, carrier performance, and other decision-support tables
- document chunks and embeddings
- standby agents, runs, digest queue items, notifications, and generated outputs

## Identity And Session Handling

The backend accepts user and session context through:

- bearer auth when Supabase JWT verification is configured
- `X-User-ID`
- `X-User-Email`
- `X-Session-ID`

In practice, this means:

- authenticated flows can be verified through JWKS
- local and demo flows can still work through explicit headers and session ids

This is grounded and useful for the demo, but it is still lighter than a fully hardened production auth model.

## What Is Grounded Today

- The backend really is separate from the frontend.
- The agent really is built once at startup and reused.
- The standby worker really runs as a separate container in compose.
- The backend really does support cached shipment status and history reads.
- The fake-web search really is simulated and routed through a controlled registry.
- Vector retrieval really does exist already for document chunks.

## Current Trade-Offs

- Compose is still tuned for local and demo use, not production process management.
- The standby worker is a polling worker, not a workflow engine.
- Retrieval is grounded, but not yet a full hybrid RAG system across all entity types.
- Fake-web search is useful for demoing external context, but it is not proper production web search.
- Some user-facing behavior still depends on frontend heuristics rather than explicit agent-driven UI state.

## Two More Weeks

If I had two more weeks focused on the backend, I would prioritize:

- Better use of vector embeddings. Expand from document chunks into hybrid retrieval and richer cross-source grounding so the agent can connect shipment state, notes, documents, and operational context more effectively.
- Real ETL for ingestion. Replace more of the current CLI-oriented ingest path with clearer extraction, transform, load, reconciliation, and monitoring workflows.
- Better worker tech and more worker functionality. Move standby processing, digests, long-running report generation, and other async work onto a more durable worker and scheduler model.
- AWS deployment. Package API, worker, Postgres, Redis, logs, secrets, and object storage into a cleaner deploy target.
- Proper web search. Replace the fake-web demo flow with a real search and source-ingestion strategy, while preserving trust and provenance controls.
- Better voice using live Google ADK. Add live multimodal sessions instead of relying on browser-only speech features.
- A stronger likely-vessel discovery engine. Build a candidate-ranking service that can infer the most likely vessel from sparse shipment facts using lane, ETA proximity, voyage code, route intent, and live movement, then return a formal confidence score and explanation.
