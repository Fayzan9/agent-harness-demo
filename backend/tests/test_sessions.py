"""Session checks against a scripted fake model, no API key needed.

Run from backend/:  PYTHONPATH=. uv run python tests/test_sessions.py
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace as NS

import fakeenv  # noqa: F401  (must come before the app is imported)
from fastapi.testclient import TestClient

from app import llm, runs, sessions, tools
from app.config import RunConfig
from app.controls import Controls
from app.gates import Approvals
from app.loop import run
from app.main import app


seen_messages: list[list[dict]] = []


def resp(content=None, calls=()):
    tcs = [NS(id=f"c{i}", function=NS(name=n, arguments=a)) for i, (n, a) in enumerate(calls)] or None
    return NS(choices=[NS(message=NS(content=content, tool_calls=tcs))], usage=None)


def script(items):
    queue = list(items)
    seen_messages.clear()

    async def fake(model, messages, tools_=None):
        seen_messages.append(messages)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    llm.complete = fake


@tools.tool
def note(text: str) -> str:
    """Pretends to record a note."""
    return "noted"


@tools.tool
def slow_note(text: str) -> str:
    """Takes a while."""
    time.sleep(5)
    return "noted slowly"


results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name, extra)


def cfg(**kw):
    gates = kw.pop("gates", {"note": "auto", "slow_note": "auto"})
    return RunConfig(model="m", tools=["note", "slow_note"], gates=gates, **kw)


def valid_history(messages) -> bool:
    """Every tool call the model made has a matching tool result, and the other way round."""
    asked = {c["id"] for m in messages for c in m.get("tool_calls", [])}
    answered = {m["tool_call_id"] for m in messages if m["role"] == "tool"}
    return asked == answered


async def drain(gen):
    return [e async for e in gen]


NOTE = ("note", json.dumps({"text": "hi"}))


async def main():
    # 1. two turns in one session: the second turn remembers the first
    script([resp("first answer"), resp("second answer")])
    s = sessions.create("", "chat")
    await drain(run(cfg(), Approvals(), Controls(), "r1", s, "hello"))
    await drain(run(cfg(), Approvals(), Controls(), "r2", s, "and now?"))
    second_call = seen_messages[1]
    texts = [m["content"] for m in second_call if m["role"] != "system"]
    check("multi-turn: second call sees the first turn", texts == ["hello", "first answer", "and now?"], texts)
    reloaded = sessions.load(s.id)
    check("saved: status idle, two turns, messages kept", reloaded.status == "idle" and len(reloaded.turns) == 2 and len(reloaded.ctx.messages) == 4)

    # 2. stop while waiting for approval, then restart and resume
    script([resp(calls=[NOTE]), resp("done after resume")])
    s = sessions.create("", "approval chat")
    approvals = Approvals()
    gen = run(cfg(gates={"note": "ask"}), approvals, Controls(), "r3", s, "take a note")
    task_events = []

    async def consume():
        async for e in gen:
            task_events.append(e)

    t = asyncio.create_task(consume())
    for _ in range(100):
        await asyncio.sleep(0.05)
        if any(e.type == "approval_requested" for e in task_events):
            break
    t.cancel()
    await asyncio.gather(t, return_exceptions=True)
    disk = sessions.load(s.id)
    check("stopped at approval: marked interrupted with the call remembered", disk.status == "interrupted" and len(disk.pending_calls) == 1 and disk.in_flight["state"] == "awaiting_approval", (disk.status, disk.in_flight))
    check("summary says where it stopped", disk.interrupted_at() == {"tool": "note", "state": "awaiting_approval"})

    sessions.ACTIVE.clear()  # pretend the whole process restarted
    disk = sessions.load(s.id)
    ev = await drain(run(cfg(gates={"note": "auto"}), Approvals(), Controls(), "r4", disk, resume=True))
    types = [e.type for e in ev]
    check("resume: the pending call runs and the chat finishes", "tool_result" in types and ev[-1].type == "done" and ev[-1].data["answer"] == "done after resume", types)
    check("resume: history valid and status idle", valid_history(sessions.load(s.id).ctx.messages) and sessions.load(s.id).status == "idle")

    # 3. a call that was running when it stopped must be asked about again, even with an auto gate
    script([resp(calls=[("slow_note", json.dumps({"text": "x"}))]), resp("ok")])
    s = sessions.create("", "running chat")
    gen = run(cfg(tool_timeout=30), Approvals(), Controls(), "r5", s, "slow one")
    evs = []

    async def consume2():
        async for e in gen:
            evs.append(e)

    t = asyncio.create_task(consume2())
    for _ in range(100):
        await asyncio.sleep(0.05)
        if any(e.type == "gate_checked" for e in evs):
            await asyncio.sleep(0.3)
            break
    t.cancel()
    await asyncio.gather(t, return_exceptions=True)
    disk = sessions.load(s.id)
    check("cancelled mid-tool: in flight is running", disk.in_flight and disk.in_flight["state"] == "running", disk.in_flight)
    sessions.ACTIVE.clear()
    disk = sessions.load(s.id)
    ap = Approvals()
    out = []

    async def resumed():
        async for e in run(cfg(gates={"slow_note": "auto"}), ap, Controls(), "r6", disk, resume=True):
            out.append(e)

    t = asyncio.create_task(resumed())
    for _ in range(100):
        await asyncio.sleep(0.05)
        asks = [e for e in out if e.type == "approval_requested"]
        if asks:
            break
    check("resume of a running call asks first and warns", asks and asks[0].data["maybe_ran"] is True, [e.type for e in out])
    ap.resolve(asks[0].data["call_id"], False)
    await t
    check("denied resume finishes cleanly", out[-1].type == "done" and valid_history(sessions.load(s.id).ctx.messages))

    # 4. a brand new message in an interrupted chat repairs the history instead of breaking it
    script([resp(calls=[NOTE]), resp("fresh answer")])
    s = sessions.create("", "repair chat")
    gen = run(cfg(gates={"note": "ask"}), Approvals(), Controls(), "r7", s, "first")
    evs = []

    async def consume3():
        async for e in gen:
            evs.append(e)

    t = asyncio.create_task(consume3())
    for _ in range(100):
        await asyncio.sleep(0.05)
        if any(e.type == "approval_requested" for e in evs):
            break
    t.cancel()
    await asyncio.gather(t, return_exceptions=True)
    sessions.ACTIVE.clear()
    disk = sessions.load(s.id)
    await drain(run(cfg(), Approvals(), Controls(), "r8", disk, "never mind, new question"))
    final = sessions.load(s.id).ctx.messages
    check("new message after interruption: history stays valid", valid_history(final) and any("Not run" in str(m.get("content")) for m in final if m["role"] == "tool"))

    # 4b. compaction keeps the latest user request verbatim, whatever the summary says
    from app.context import Context

    ctx = Context("")
    for m in [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "write the summary to summary.txt"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "x", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "x", "content": "data"},
    ]:
        ctx.add(m)
    ctx.compact("a summary that forgot the task")
    kept = [m["content"] for m in ctx.as_messages() if m["role"] == "user"]
    check("compaction keeps the latest request verbatim, before the notes", ctx.anchor["content"] == "write the summary to summary.txt" and kept[0] == "write the summary to summary.txt" and kept[1].startswith("Progress notes"), kept)
    check("compaction leaves no dangling tool calls", valid_history(ctx.as_messages()))

    # 5. over HTTP: list, detail, branch
    script([resp(calls=[NOTE]), resp("http answer"), resp("branched answer")])
    client = TestClient(app)
    with client.stream("POST", "/run", json={"task": "http task", "tools": ["note"], "gates": {"note": "auto"}, "model": "m"}) as r:
        body = "".join(r.iter_text())
    events = [json.loads(x[6:]) for x in body.split("\n\n") if x.startswith("data: ")]
    started = events[0]["data"]
    check("http run: run_started carries session id and turn", started["session_id"] and started["turn"] == 1)
    listing = client.get("/sessions").json()
    check("http list: session present and idle", any(x["id"] == started["session_id"] and x["status"] == "idle" for x in listing))
    detail = client.get(f"/sessions/{started['session_id']}").json()
    check("http detail: events come back with the turn", len(detail["turns"]) == 1 and len(detail["turns"][0]["events"]) == len(events))
    first_ctx = next(i for i, e in enumerate(events) if e["type"] == "context_updated")
    with client.stream("POST", "/branch", json={"run_id": started["run_id"], "event_index": first_ctx, "tools": ["note"], "gates": {"note": "auto"}, "model": "m"}) as r:
        bbody = "".join(r.iter_text())
    bevents = [json.loads(x[6:]) for x in bbody.split("\n\n") if x.startswith("data: ")]
    first_msgs = next(e for e in bevents if e["type"] == "context_updated")["data"]["messages"]
    check("branch: starts from only the original task", [m["content"] for m in first_msgs if m["role"] == "user"] == ["http task"] and len(first_msgs) == 2, len(first_msgs))
    check("branch: new session, labelled", bevents[0]["data"]["session_id"] != started["session_id"] and "Re-run" in bevents[0]["data"]["task"])
    check("404 for unknown chat", client.get("/sessions/nope").status_code == 404)

    bad = [n for n, ok in results if not ok]
    print("\nALL PASSED" if not bad else f"\nFAILED: {bad}")


asyncio.run(main())
