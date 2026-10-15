# Agent harness playground

A visual playground that shows how an agent harness works: the loop, tools, gates, context and memory.

- `backend/` FastAPI + LiteLLM. The engine emits an event for every step and streams them.
- `frontend/` Next.js. Only renders the events.
- `workspace/` The only folder the agent's file tools can touch.

## Run

1. `cp backend/.env.example backend/.env` and fill in your Azure values.
2. Backend: `cd backend && uv run uvicorn app.main:app --port 8000`
3. Frontend: `cd frontend && npm run dev`, then open http://localhost:3000

## The screen

| Zone | What it is |
|---|---|
| Top bar | Scenario presets (one per lesson), Auto or Step mode, Settings, run status |
| 1 Ask | Chat. Your task, the agent's answer, and Allow or Deny cards |
| 2 Watch | Context bar, then the loop: Agent, before hooks, Gate, Tools, after hooks. A helper lane appears when `delegate` is used. Click any box to configure it |
| 3 Inspect | Events, Trace (timed waterfall, waits, tokens, cache), Context (exactly what the model was sent), Memory (editable), Files |
| 4 Replay | Back, Next, Play and a scrubber. Every event is kept, so you can rewind a run |

Every run first restores the demo files in `workspace/` (it never deletes anything).
