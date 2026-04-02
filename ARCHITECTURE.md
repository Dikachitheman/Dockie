# System Architecture

This document describes the architecture of the whole repository.

- Product and demo framing: [README.md](README.md)
- Backend-only architecture: [dockie-copilot/ARCHITECTURE.md](dockie-copilot/ARCHITECTURE.md)

## System Boundary

Dockie is split into five practical pieces:

1. `frontend/`
   React + Vite application for chat, tracking, analytics, standby agents, notifications, and generated outputs.
2. `dockie-copilot/`
   FastAPI backend, Google ADK agent runtime, shipment services, ingest flows, standby-agent logic, and geospatial endpoints.
3. Data stores used by `dockie-copilot/`
   PostgreSQL is the primary store, with PostGIS enabled for geospatial work. Redis is optional for cache and session coordination. `pgvector` is available when installed and is already used for document-chunk retrieval.
4. `fake-websites/`
   A controlled fake-web corpus used by the simulated web-search flow.
5. `notes/` and `2weeks/`
   Working notes, review notes, and short-horizon roadmap thinking.

## Repo Shape

```text
frontend/           React app
dockie-copilot/     FastAPI backend + worker + migrations
fake-websites/      fake search sources and routing registry
notes/              project notes and review notes
2weeks/             short-horizon roadmap notes
```

## Runtime Shape

### Frontend

The frontend is the primary user surface.

- It boots from `frontend/src/pages/Index.tsx`.
- It loads initial application state through `/app-bootstrap`.
- It opens chat threads per shipment.
- It sends agent requests to `/agent/run`.
- It manages standby agents through `/standby-agents`, `/notifications`, and `/agent-outputs`.

The UI is intentionally multi-view rather than chat-only. It has dedicated views for shipments, tracking, agents, analytics, notifications, outputs, and settings.

### Backend

The backend owns the operational state and the agent runtime.

- FastAPI app factory: `dockie-copilot/app/interfaces/api/app.py`
- App entrypoint: `dockie-copilot/app/main.py`
- Agent runtime: `dockie-copilot/app/application/adk_agent.py`
- Tool implementations: `dockie-copilot/app/application/agent_tools.py`
- Core orchestration/services: `dockie-copilot/app/application/services.py`
- Standby agent logic: `dockie-copilot/app/application/standby_services.py`

### Background worker

Standby-agent evaluation runs in two grounded ways today:

- a dedicated `standby-worker` container in Docker Compose
- a dev-only in-process HTTP-started worker exposed by standby routes

The production-like path in this repo is the separate `standby-worker` container, but the implementation is still a polling loop rather than a more durable job system.

### Data stores

- PostgreSQL stores shipments, vessels, positions, events, source health, document chunks, notifications, and outputs.
- PostGIS powers proximity and nearby-vessel queries.
- `pgvector` is used when available for document-chunk similarity search.
- Redis is optional and improves cache behavior and multi-worker session consistency.

### Fake web search

The app does not call a real internet search provider.

- `fake-websites/sources.json` defines the fake-web source registry and routing.
- The backend searches each source through its `search-index.json`.
- The result is supporting context, not the source of truth for shipment state.

## Main Flows

### 1. App bootstrap

When the app loads, the frontend requests `/app-bootstrap`.

That payload combines:

- shipment summaries
- source health
- standby agents
- notifications
- generated outputs

This reduces first-load request fan-out and gives the UI enough state to render the main workspace quickly.

### 2. Shipment exploration

After bootstrap, the frontend loads shipment-specific details as needed:

- shipment bundle
- thread history
- tracking view and map context

This supports the two core user modes:

- ask questions in chat
- inspect operations state visually

### 3. Agent chat

The chat flow is:

1. frontend sends a request to `/agent/run`
2. request includes a persistent `X-Session-ID`
3. frontend also forwards Supabase auth headers when present
4. backend runs the ADK agent against structured tools
5. frontend streams back text plus visible tool and status events

Important grounded detail:

- the chat UI is not just a text stream
- it also renders follow-up prompts, maps, evidence cards, timeline cards, standby setup prompts, and generated-output previews
- some of that rendering is still triggered by frontend heuristics rather than fully agent-directed UI state

### 4. Standby agents

Standby agents follow a false-to-true monitoring pattern:

- watch a condition while it is false
- fire an action when it becomes true

Today, the system supports:

- creating standby agents in the UI or over the API
- manual run/check
- polling evaluation in the worker
- notifications, digests, emails, and generated outputs

For the demo, scenario commands and simulated refresh commands are what change the world state. In real deployment, carrier updates, live vessel movement, port updates, and workflow events would drive those transitions automatically.

### 5. Ingest, refresh, and scenarios

The backend currently supports three different state-changing paths:

- `ingest`: load the baseline dataset
- `refresh` and `live_refresh`: refresh connector-style data
- `simulated_refresh` and `apply_scenario`: push the system into specific demo states

That split matters. It lets the product demo both stable baseline tracking and operational change over time.

## Identity And Session Model

The current auth and session model is practical and grounded:

- the frontend stores a generated session id in local storage
- it sends that as `X-Session-ID`
- if Supabase auth is present, the frontend also sends bearer auth plus `X-User-ID` and `X-User-Email`
- the backend verifies JWTs when JWKS is configured
- otherwise it falls back to the explicit headers or session id

This is enough for the demo and multi-thread continuity, but it is still a lightweight app-level identity model rather than a fully hardened multi-tenant architecture.

## What Is Grounded Today

- The system is really split into separate frontend and backend apps.
- The backend really owns the agent runtime and standby-agent logic.
- The frontend really does stream chat status and tool activity from `/agent/run`.
- The fake-web search really is a controlled corpus of deployed source apps, not the open web.
- The standby agent really does create notifications and generated outputs that flow back into the frontend.
- Vector retrieval is already present for document chunks when embeddings and `pgvector` are available, but it is not yet the main retrieval strategy for the whole product.

## Honest Limits

- Docker Compose is still demo and dev shaped and runs the backend with `--reload`.
- Voice currently uses browser APIs in the frontend rather than a live multimodal ADK flow.
- Some rich chat components are still selected by frontend heuristics.
- The standby worker uses a straightforward polling loop rather than a dedicated workflow system.
- Simulated web search is useful for the demo, but it is not a proper production web-search stack.

## Two More Weeks

If I had two more weeks, the best next improvements would be:

- Better use of vector embeddings. The backend already has document-chunk vector retrieval; I would expand that into hybrid retrieval across documents, shipment notes, event explanations, and source context so the agent can answer broader questions more reliably.
- Real ETL for ingestion. I would move from a mostly CLI-and-fixture-driven ingest model to scheduled ETL jobs with clearer extraction, normalization, reconciliation, and observability.
- Better worker tech and more worker functionality. I would move standby processing and other async jobs onto a stronger worker and scheduler model so monitoring, digests, reports, and long-running tasks are more durable and easier to operate.
- AWS deployment. I would package the system for a real environment with managed Postgres, Redis, object storage, logs, secrets, and separate API and worker deployments.
- Proper web search. I would replace the fake-web demo layer with a real external search and retrieval path plus trust rules, source controls, and stronger citation handling.
- Docs in the chat text box. I would add inline capability hints and context-aware docs while typing so users can discover prompts, tools, shipment mentions, and standby patterns more easily.
- Better voice using live Google ADK. I would replace the current browser speech flow with a higher-quality live multimodal voice path.
- A stronger likely-vessel discovery engine. I would build a candidate-ranking service that scores vessels from sparse shipment facts using multiple weak signals like lane, ETA proximity, voyage code, route intent, and live movement, then outputs a formal confidence score with reasons.
- UI animation polish. I would make the interface feel more intentional by improving reveal timing, transitions, loading states, and map/chat motion design.
