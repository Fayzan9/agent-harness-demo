# Agent harness playground

A visual playground that shows how an agent harness works: the loop, tools, gates, context and memory.

- `backend/` FastAPI + LiteLLM. The engine emits an event for every step and streams them.
- `frontend/` Next.js. Only renders the events.
- `workspace/` The only folder the agent's file tools can touch.

## Run

1. `cp backend/.env.example backend/.env` and fill in your Azure values. The app checks them at startup and refuses to start if one is missing (see `backend/app/settings.py`).
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
PYTHONPATH=. uv run python tests/test_context_tools.py
PYTHONPATH=. uv run python tests/test_settings.py
```

## Evals

The **Evals** screen (top bar) runs the same tasks several times and checks each run automatically, so you can change one thing and compare the score.

- **Cases and checks are data:** `backend/app/evals/cases.json`. Add a case by adding an entry. Checks are `outcome` (is the result right), `trajectory` (did it get there the right way) or `judge` (a model grades it against a rubric). The check types are in `backend/app/evals/checks.py`.
- **Setups** (top of `backend/app/evals/runner.py`) are overrides applied to every case: without hooks, without the memory file, a step limit of 2, a tiny context, a flaky API.
- Every run gets its own temporary workspace, so runs never interfere and your real `workspace/` is untouched. Evals run without a human, so never use an "ask" gate in a case.
- Runs cost real model calls (about three per run, plus one for each judge check). Above 12 runs the Run button asks for a second click, and one click is capped at 90 runs.
- Click a dot in the grid to see which checks failed, then **Replay this run** to step through it in the Playground.
- Results are also saved to `backend/evals_out/` (gitignored).

## Context engineering and caching

Scenarios in the **Context** group of the dropdown, and Inspect > **Context**, show these ideas live:

- **What changed since the previous pass.** The Context tab compares each pass with the one before it, message by message, and colours every message: same, changed or new. A provider's prompt cache only helps with an exact match from the very start, so the first difference is where the benefit ends. Under it, the provider's own report of how many input tokens it served from cache.
- **Cache: a stable prefix** versus **Cache breaker: clock in the prompt.** The same long instructions, with and without the current time at the top. Stable: nearly everything is cached after the first pass. Clock: nothing is. The switch is `clock_in_prompt` under Break it in Settings.
- **Big file: read it all / search instead / cut at 800 characters.** `handbook.txt` is a 2,600-token file with one useful fact. Reading it whole puts it all in context. With the `search_file` tool the agent loads one line. Blind trimming (the `truncate_result` hook) can make things worse, because the agent pages through the file anyway.
- **Notes outlive compaction.** `save_note` and `read_notes` keep facts in `scratchpad.md`, outside the conversation. The file is cleared when a new chat starts.
- **Largest items** in the Context tab points at what is eating the window.

Two things the numbers taught while building this:

- Whether the agent uses a cheaper tool depends on the tool descriptions. With a plain `read_file` description it never used `search_file`. Adding "a long file is expensive, use search_file first if you only need one fact" changed that every time. The eval case `find-in-big-file` measures it (compare Baseline with **Without search_file**).
- Cache hits are best effort. On this provider the same prompt was sometimes cold and sometimes cached, and caching does not make the context smaller. It only makes re-reading it cheaper.
