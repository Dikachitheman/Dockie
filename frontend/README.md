# Frontend

This frontend now targets the Dockie FastAPI backend instead of local mock data.

## Run locally

1. Start the backend in `dockie-copilot`:
   - `uvicorn app.main:app --reload`
2. Start the frontend in this folder:
   - `npm install`
   - `npm run dev`
3. Open the Vite app and make sure `VITE_API_BASE_URL` points at the backend, by default `http://localhost:8000`.

## What is live

- Shipment list comes from `/shipments`
- Tracking view uses `/shipments/{id}`, `/shipments/{id}/status`, and `/shipments/{id}/history`
- Source health comes from `/source-health`
- Chat streams from `/agent/run`
- Prior conversation state is restored from `/agent/agents/state`
- Standby agents come from `/standby-agents`
- Standby notifications come from `/notifications`

## Supabase email function

For standby-agent email delivery, this repo now includes a Supabase Edge Function scaffold at:

- `supabase/functions/send-standby-email/index.ts`

Deploy it from the `frontend` folder with the Supabase CLI after you log in and link the project:

```bash
supabase link --project-ref tshkzkkwonopbzbxpjoc
supabase functions deploy send-standby-email
```

Set these Supabase function secrets before using email actions:

```bash
supabase secrets set RESEND_API_KEY=your_resend_key
supabase secrets set SENDER_EMAIL=alerts@your-domain
```

The backend worker also needs matching config so it can call the function:

- `SUPABASE_PROJECT_URL`
- `SUPABASE_EDGE_FUNCTION_KEY`
- optional: `SUPABASE_EMAIL_FUNCTION_NAME` default is `send-standby-email`

## Product alignment

The frontend is designed to support the product definition by surfacing:

- Multiple active shipments with shipment switching
- Agent chat grounded in backend data
- Map-based tracking view
- Source-health and degradation visibility
- Browser voice input and spoken playback for agent responses
