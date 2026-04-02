# Dockie

Dockie is an AI shipment-tracking copilot for vehicle imports on the US-West Africa ro-ro corridor.

This project started from a simple prompt in the take-home: an agent should answer questions like "Where is my shipment?" That matters, but in real operations that is usually only the first click. The harder problems come right after:

- Is this delay going to affect clearance or trucking?
- Should I be worried about demurrage?
- Has anything changed enough that I need to act?
- Can someone watch this for me instead of me refreshing the app all day?

That is the lens I used to build the project. I tried to model the product around what real importers, freight forwarders, and operations people actually experience: multiple active shipments, uncertain ETAs, stale data, anchorage waits, port congestion, and the need to react before costs stack up.

## Product thinking

The main design choice was to move beyond "chat over tracking data" into something closer to an operational copilot.

- The chat is meant to reason over shipment state, not just repeat fields from a database.
- The UI streams agent status, tool activity, and answer text so you can see how it is working.
- Follow-up questions matter, because real users do not ask one perfect query and leave.
- Tracking is multi-shipment by design, because that is how actual operators work.
- Standby agents exist because watching for change is more useful than manually checking status pages.

In other words, I wanted to build for the questions users really have after the basic "where is it?" question:

- What changed since yesterday?
- Which shipment needs attention first?
- Is this anchorage wait normal?
- Could this become a demurrage problem?
- Tell me when this becomes true, instead of making me monitor it myself.

## What I implemented

### 1. Standby agents

Standby agents are the feature that best captures the product direction.

They follow a simple pattern:

- watch a condition while it is `false`
- fire an action when the condition becomes `true`

That matches how operations teams think. They do not want to sit in front of a screen waiting for a vessel to anchor, an ETA to slip, or a demurrage risk to appear. They want to describe the situation they care about once, then let the system watch it in the background.

Current implementation:

- natural-language standby agent creation in the UI
- shipment-scoped or all-shipment watchers
- selectable actions: notification, email, digest, report, spreadsheet, document
- manual run/check controls in the app
- background worker support
- cooldowns, fired state, next-run scheduling, notifications, and generated outputs

Where it is today versus where I would take it:

- Today, this demo uses scenario commands and simulated refresh commands to flip data into a new state so watching agents can trigger.
- In real usage, those state changes would come from actual carrier, AIS, port, or workflow updates automatically, so the user would not run commands at all.
- Today, the trigger model is intentionally simple and practical for the demo.
- Next, I would make standby agents more semantic, more event-driven, and more deeply connected to external systems through MCP tools.

### 2. Fake websites for simulated web search

Another key product decision was to make the agent more useful for broader operational questions, not just shipment-record lookups.

Some questions need supporting context beyond the shipment row itself:

- Is there anything unusual happening at Lagos right now?
- What does congestion at this port usually imply?
- What external context helps explain this situation?

To support that, I deployed 12 fake websites and wired them into a simulated web-search flow. This lets the agent use web-style supporting context without pretending this project has a production-grade live search integration.

Why I did it:

- it makes the agent more believable on real user questions
- it creates a safer demo surface for external-search behavior
- it shows how I would combine shipment truth with surrounding context

Important boundary:

- shipment status, history, ETA logic, and tracking remain the source of truth
- web search is supporting context, not the authority for vessel state

### 3. Chat as the main control surface

The app is designed so chat is not just a text box. It is where agent behavior becomes visible.

Implemented in the app:

- streaming agent status, tool use, and response writing into the UI
- follow-up question suggestions
- creating a standby agent directly from chat
- standby notifications and outputs flowing back into the relevant shipment thread when an agent fires
- `@` mention support in chat to select a shipment or vessel context
- concise, balanced, and verbose response modes

### 4. Tracking and operational UI

I wanted the app to feel operational, not like a toy chat shell.

Implemented:

- shipment list and detail views
- multi-shipment tracking
- map with segmented route lines and event information on the route
- multiple shipments visible on one tracking map
- rich cards in chat, including graphs, demurrage-related UI, and standby-agent setup UI

### 5. Agent outputs, not just answers

The agent can do more than return text.

Implemented output paths:

- create draft documents
- create reports
- create spreadsheet-style outputs
- send or queue email-style outputs

Future direction:

- MCP integrations for tools like Google Calendar, Google Docs, Notion, and similar systems would make this much more useful in real operations workflows

### 6. Data simulation and refresh flows

The demo includes dedicated ingest and refresh mechanics so the app can show change over time.

- ingest has its own JSON-backed dataset
- refresh applies updated JSON
- scenarios apply business-state changes that are useful for demoing specific agent behaviors

This was important because a standby-agent product is only compelling if the system can visibly move from one state to another.

## How to use standby agents in the app

There are two main ways to use the standby feature.

### From chat

1. Open a shipment and go to chat.
2. Click the `+` button to switch into watcher mode.
3. Type a condition such as:
   - `Alert me when this shipment reaches anchorage`
   - `Notify me if ETA changes materially`
   - `Alert me when demurrage exposure increases`
4. Choose the action and interval.
5. Send the message to create the standby agent.

The UI can also surface an inline standby-agent creator after relevant conversations, so the agent can suggest a watcher when it detects that monitoring would be more useful than a one-time answer.

### From the standby agents workspace

1. Open the standby agents view.
2. Enter a natural-language condition.
3. Pick a shipment scope, action, and check interval.
4. Save the agent.
5. Use `Run check` if you want to force an evaluation immediately during the demo.

What to expect:

- agents stay in a waiting state while the condition is false
- when the condition becomes true, the configured action fires
- fired agents show status, last checked time, next run time, last fired time, and fire count

For this demo:

- scenario commands and simulated refresh commands are what move the system into different states
- that is how you can trigger watchers on demand while testing
- in a real deployment, state changes would come from live operational events automatically

## Features I especially wanted reviewers to notice

- streaming tool use and visible agent status into the chat UI
- follow-up chat questions
- standby-agent creation from chat
- standby alerts and outputs appearing after agents trigger
- `@` mention flow for shipment selection in chat
- segmented map lines with event information
- multiple shipments on one map
- fake-web search support for broader operational questions
- ingest, refresh, and scenario flows as separate concepts
- concise, balanced, and verbose response controls
- rich UI components for graphs, demurrage, tracking, and quick standby setup

## Known rough edges

- Voice currently uses the browser APIs. It works for demo purposes, but the quality is not where I would want it for a polished product.
- Some of the highest-value agentic ideas are present in direction and scaffolding, but not yet fully built out into complete production workflows.

## With Two More Weeks

- Better use of vector embeddings. The backend already has document-chunk vector retrieval; I would push that further so the agent can ground answers across documents, events, shipment notes, and operational context more intelligently.
- Real ETL for ingestion. I would turn more of the current ingest and refresh flow into clearer extraction, transform, load, and reconciliation pipelines.
- Better worker tech and more worker functionality. I would upgrade standby processing and other background work so monitoring, reports, digests, and longer-running actions are more durable and more capable.
- AWS deployment. I would package the system for a cleaner production shape with separate API and worker deployments plus managed data infrastructure.
- Proper web search. I would replace the fake-web demo layer with a real external search and retrieval path.
- Docs in the chat text box. I would add inline help and capability hints while typing so people discover what the agent can do without reading docs first.
- Better voice using live Google ADK. I would replace the current browser speech flow with a much stronger live multimodal experience.
- A stronger likely-vessel discovery engine. I would add a candidate-ranking service that can infer the most likely vessel from sparse shipment facts using lane, ETA proximity, voyage code, route intent, and live movement, then produce a formal confidence score.
- UI animation polish. I would spend time making transitions, reveals, streaming states, and motion feel more intentional across chat, tracking, and agent outputs.

## Repo structure

- `frontend/`: React + Vite app
- `dockie-copilot/`: FastAPI backend, agent runtime, standby worker, ingest/refresh/scenario tooling
- `fake-websites/`: source content used for the simulated web-search experience

## Running the project

### Backend

From `dockie-copilot/`:

```bash
cp .env.example .env
docker compose up --build
```

This compose flow runs migrations and `ingest_if_empty` automatically for the app and standby-worker containers.

Backend API:

- `http://localhost:8000`
- docs at `http://localhost:8000/docs`

### Frontend

From `frontend/`:

```bash
npm install
cp .env.example .env
npm run dev
```

`VITE_API_BASE_URL` defaults to `http://localhost:8000`, so the frontend will talk to the local FastAPI backend unless you point it elsewhere.

Frontend default:

- `http://localhost:5173`

### Helpful backend commands

From `dockie-copilot/`:

```bash
python -m app.cli.commands ingest
python -m app.cli.commands refresh
python -m app.cli.commands simulated_refresh run_001
python -m app.cli.commands apply_scenario scenario_ship_004_anchor_arrival
python -m app.cli.commands standby_worker_once
```

Use `simulated_refresh` when you want to change tracking and freshness state.

Use `apply_scenario` when you want to create visible business-state changes such as ETA slip, anchorage arrival, stale position feeds, or demurrage risk.

## Demos

- Updated demo (includes: Standby agents, web search in chat): https://drive.google.com/file/d/1AqjEcHZE6TnW_NDLSXtZNV1D6hytSci9/view?usp=sharing
- Earlier demo: https://drive.google.com/file/d/1nyMshr1d7rUFHFV4JSNZ5OIQq7EbWHqf/view?usp=sharing

## More detailed docs

- Backend implementation details: `dockie-copilot/README.md`
- Architecture notes: `ARCHITECTURE.md`
