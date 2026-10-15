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
| 1 Ask | A real conversation. Follow-ups remember earlier turns. Click a turn to replay it. Allow or Deny cards, and a Resume card if a chat stopped part-way. New chat starts fresh |
| 2 Watch | Context bar, then the loop: Agent, before hooks, Gate, Tools, after hooks. A helper lane appears when `delegate` is used. Click any box to configure it |
| 3 Inspect | Events, Trace (timed waterfall, waits, tokens, cache), Context (exactly what the model was sent), Memory (editable), Files |
| 4 Replay | Back, Next, Play and a scrubber. Every event is kept, so you can rewind a run |

Every run first restores the demo files in `workspace/` (it never deletes anything).

## Sessions, History and re-running

- Every chat is saved to `backend/sessions/` after each step, and every run's events to `backend/runs/` (both gitignored).
- **History** (top bar) lists saved chats. Open one to replay it or carry on.
- **Resume**: if the backend dies or you press Stop mid-step, the chat is marked as stopped part-way. Resume continues from the last checkpoint. A call that was already running when it stopped always asks you again, even if its gate is on auto.
- **Re-run from here** (Inspect > Events): starts a new chat from what the model saw at that event, with your current settings. Change a gate or hook first to try a "what if".

## Tests

Neither needs an API key. Run from `backend/`:

```bash
PYTHONPATH=. uv run python tests/test_reliability.py
PYTHONPATH=. uv run python tests/test_sessions.py
PYTHONPATH=. uv run python tests/test_evals.py
```

## Evals

The **Evals** screen (top bar) runs the same tasks several times and checks each run automatically, so you can change one thing and compare the score.

- **Cases and checks are data:** `backend/app/evals/cases.json`. Add a case by adding an entry. Checks are `outcome` (is the result right), `trajectory` (did it get there the right way) or `judge` (a model grades it against a rubric). The check types are in `backend/app/evals/checks.py`.
- **Setups** (top of `backend/app/evals/runner.py`) are overrides applied to every case: without hooks, without the memory file, a step limit of 2, a tiny context, a flaky API.
- Every run gets its own temporary workspace, so runs never interfere and your real `workspace/` is untouched. Evals run without a human, so never use an "ask" gate in a case.
- Runs cost real model calls (about three per run, plus one for each judge check). Above 12 runs the Run button asks for a second click, and one click is capped at 90 runs.
- Click a dot in the grid to see which checks failed, then **Replay this run** to step through it in the Playground.
- Results are also saved to `backend/evals_out/` (gitignored).
