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

... (content truncated for brevity)
