# Architecture

## Stack

- Backend: Python, FastAPI, SQLAlchemy async, Alembic
- Database: PostgreSQL with PostGIS-enabled image for local development
- Agent runtime: Google ADK
- Agent UI protocol: AG-UI streaming endpoint
- Frontend: React + Vite in the sibling `frontend/` app

This project is built as a production-minded MVP for corridor-focused shipment tracking rather than a generic global vessel platform. The backend is responsible for ingest, normalization, persistence, freshness scoring, provenance, and grounded agent access. The frontend consumes those APIs to provide shipment switching, tracking, chat, map views, and source-health visibility.

## System Shape

The backend follows a layered structure:

- `app/domain`
  Pure logic for freshness, ETA confidence, and other business rules.
- `app/application`
  Orchestrates use cases and exposes structured tools for the agent.
- `app/infrastructure`
  Database access, normalization, source integrations, ingest, cache, and source policy.
- `app/interfaces`
  FastAPI routes and CLI commands.
- `app/models`
  SQLAlchemy ORM models mapped to Postgres tables.
- `app/schemas`
  Pydantic request and response contracts.

The frontend is intentionally separate so the backend remains usable as an API-driven service and the UI can evolve independently.

## Data Flow

The data flow is:

1. Source payloads are fetched from fixtures and optionally live overlays.
2. Raw upstream payloads are persisted first in `raw_events`.
3. Payloads are checked for hostile content and validation failures.
4. Invalid or unsafe payloads are stored in `quarantined_events` with reasons.
5. Valid payloads are normalized into canonical records such as shipments, vessels, latest positions, evidence, and voyage events.
6. Read APIs and agent tools assemble shipment status, history, ETA confidence, and supporting context from those normalized tables.

This keeps the ingest path auditable and prevents malformed or stale data from silently replacing trusted state.

## Agent Design

The agent runtime is implemented with Google ADK and exposed over AG-UI-compatible streaming routes.

Core files:

- `app/application/adk_agent.py`
- `app/application/agent_tools.py`
- `app/interfaces/api/routes/agent_run.py`

The agent is constrained to structured tool access rather than direct free-form answering. Current tools include:

- list shipments
- get shipment status
- get shipment history
- get vessel position
- search knowledge base
- get ETA revisions
- get port context

The instruction layer explicitly tells the model to:

- answer only from tool results
- surface freshness and uncertainty
- avoid inventing positions or ETAs
- ignore prompt-like content found in shipment fields or retrieved text
- preserve session focus for follow-up questions

This is the main guardrail against hallucination and prompt injection from untrusted shipment or source content.

## Retrieval And Structured Context

Instead of a separate vector database, this MVP uses structured retrieval from operational tables:

- shipment evidence
- voyage events
- ETA revision logs
- port observations
- source readiness metadata
- source health records

`KnowledgeBaseService` ranks snippets by lightweight token matching and returns evidence that is useful for “why,” “what changed,” and “how reliable is this” questions. This keeps the system simple while still grounded in persisted operational state.

## Rich UI In Chat

The frontend chat consumes the AG-UI stream from `/agent/run` and renders:

- conversational messages
- shipment detail cards
- compact map cards
- source-readiness context
- retrieved evidence context

The current implementation uses frontend-side heuristics to decide when to show some rich cards. A next step would be to make those cards fully agent-directed through structured AG-UI state so the model can intentionally request map or evidence components instead of relying on keyword detection.

## Freshness, Degradation, And Evidence

Freshness and degradation are first-class parts of the backend.

- Source policies define source class, automation safety, business-safe default, and fallback behavior.
- Source health records store last success timestamps, stale windows, and degraded reasons.
- Domain logic computes freshness and ETA confidence from declared ETA plus latest trusted live position.
- If live position data is stale or unavailable, the API returns lower confidence and explicit freshness warnings.
- Evidence and source metadata are surfaced through the API and shown in the frontend.

This helps the assistant answer “How reliable is this?” honestly instead of sounding certain when data is stale.

## Security Decisions

The project is designed around the assumption that upstream and manual data are untrusted.

- Raw payloads are stored inertly before normalization.
- Malicious or malformed payloads are quarantined with reasons.
- Control characters and unsafe URL schemes are normalized or rejected.
- Database writes use SQLAlchemy and parameterized statements.
- Agent instructions explicitly forbid following instructions embedded in retrieved content.
- API error handling avoids leaking stack traces to clients.

One remaining hardening task is frontend rendering: assistant content should be escaped before HTML rendering so hostile strings can never become executable in the browser.

## Local Operations

The backend supports:

- `alembic upgrade head` for migrations
- `python -m app.cli.commands ingest` for baseline fixture ingestion
- `python -m app.cli.commands refresh` for the challenge refresh fixture workflow
- `python -m app.cli.commands live_refresh` for connector-driven live refresh workflows
- `python -m app.cli.commands health` for source-health inspection

Docker Compose is included for local reproducibility, and the frontend can be run separately against the FastAPI backend.

## Trade-Offs

- Structured retrieval was chosen over a larger RAG stack to keep the MVP grounded and maintainable.
- Fixtures are used as a stable baseline so the product still works when live sources are unavailable.
- Live sources are treated as overlays because maritime public sources are often stale, fragile, or policy-limited.
- The frontend and backend are separate apps, which adds setup overhead but improves service boundaries.
- Some rich chat behavior is still UI-driven rather than fully agent-directed; this keeps the MVP practical but leaves room for a stronger AG-UI implementation.

## What I Would Improve With Two More Weeks

- Move rich chat cards to explicit structured AG-UI state emitted by the agent.
- Add stronger frontend sanitization and more security-focused UI tests.
- Add end-to-end browser tests for shipment switching, voice flow, chat streaming, and stale-source scenarios.
- Add a single top-level submission README covering both apps together.
- Add better source-failure simulations and observability around live refresh jobs.
- Add optional analyst tooling such as a clearer “what changed and why” timeline.

## AI Tooling And Validation

AI tools helped accelerate implementation and iteration, especially around scaffolding, refactors, and comparing the app against the project definition. Manual validation was still required for:

- application structure
- API shape alignment
- ingest and normalization rules
- source policy behavior
- freshness logic
- malicious payload handling
- UI/backend integration

The goal throughout was not just to ship a demo, but to keep the behavior inspectable, grounded, and honest about uncertainty.
