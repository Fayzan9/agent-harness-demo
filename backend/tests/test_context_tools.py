"""Context engineering building blocks, no API key needed.

Run from backend/:  PYTHONPATH=. uv run python tests/test_context_tools.py
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace as NS

from app import llm, sessions, tools, workspace
from app.config import RunConfig, workspace_var
from app.context import Context
from app.controls import Controls
from app.evals import checks
from app.evals.runner import CASES, VARIANTS, run_one
from app.gates import Approvals
from app.loop import run

sessions.SESSIONS_DIR = Path(tempfile.mkdtemp())
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name, extra)


async def main():
    work = Path(tempfile.mkdtemp())
    for name, text in workspace.SEED.items():
        (work / name).write_text(text)
    workspace_var.set(work)

    # optional tool parameters
    schema = tools.schemas(["read_file", "save_note"])
    read = next(s for s in schema if s["function"]["name"] == "read_file")["function"]["parameters"]
    check("optional params are not required", read["required"] == ["path"] and set(read["properties"]) == {"path", "offset", "max_chars"}, read["required"])

    # reading in pieces
    whole = tools.REGISTRY["read_file"].fn("handbook.txt")
    check("read_file returns the whole file by default", whole == workspace.SEED["handbook.txt"] and len(whole) > 8000, len(whole))
    check("read_file reads a piece", tools.REGISTRY["read_file"].fn("handbook.txt", offset=10, max_chars=20) == whole[10:30])
    check("read_file offset alone reads to the end", tools.REGISTRY["read_file"].fn("handbook.txt", offset=len(whole) - 5) == whole[-5:])

    # searching
    found = tools.REGISTRY["search_file"].fn("handbook.txt", "REFUND")
    check("search_file finds the buried line with its number", found.startswith("line 72:") and "30 days" in found and len(found) < 200, found)
    check("search_file says when nothing matches", tools.REGISTRY["search_file"].fn("handbook.txt", "zebra") == "No matches.")
    many = tools.REGISTRY["search_file"].fn("handbook.txt", "Section")
    check("search_file caps its output", many.count("line ") == 10 and "more matches" in many)

    # notes
    check("no notes at first", tools.REGISTRY["read_notes"].fn() == "(no notes yet)")
    tools.REGISTRY["save_note"].fn("Owner is Faizan")
    tools.REGISTRY["save_note"].fn("Ships Friday")
    check("notes accumulate in a file", tools.REGISTRY["read_notes"].fn() == "- Owner is Faizan\n- Ships Friday\n")

    # reset clears the scratchpad but nothing else
    import app.workspace as ws

    ws.WORKSPACE = work
    ws.reset()
    check("reset clears the scratchpad and restores demo files", not (work / "scratchpad.md").exists() and (work / "handbook.txt").exists())

    # the clock-first cache breaker changes the very first message on every call
    ctx = Context("some memory")
    a = ctx.as_messages()
    ctx.clock_first = True
    b = ctx.as_messages()
    time.sleep(0.01)  # real passes are far further apart than this
    c = ctx.as_messages()
    check("normal prompt is stable", a[0] == Context("some memory").as_messages()[0])
    check("clock-first puts the time at the very top and it changes", b[0]["content"].startswith("Current time:") and b[0] != c[0], b[0]["content"][:30])

    # one snapshot per pass: what the event shows is what is sent
    sent, shown = [], []

    async def fake(model, messages, tools_=None):
        sent.append(messages)
        return NS(choices=[NS(message=NS(content="done", tool_calls=None))], usage=None)

    llm.complete = fake
    cfg = RunConfig(model="m", chaos=["clock_in_prompt"])
    session = sessions.create("", "t")
    events = [e async for e in run(cfg, Approvals(), Controls(), "r1", session, "hi")]
    ctx_event = next(e for e in events if e.type == "context_updated")
    check("the chaos event is announced", any(e.type == "chaos" and e.data["kind"] == "clock_in_prompt" for e in events))
    check("event messages equal the messages sent", ctx_event.data["messages"] == sent[0])

    # peak context check and the drop_tools variant
    ev = [{"type": "context_updated", "agent": "main", "step": 1, "data": {"total": 900}}, {"type": "context_updated", "agent": "main", "step": 2, "data": {"total": 1500}}]
    check("peak check fails above the limit", not checks.run_check({"type": "peak_context_at_most", "value": 1200}, checks.RunView(ev, {}))[0])
    check("peak check passes below it", checks.run_check({"type": "peak_context_at_most", "value": 2000}, checks.RunView(ev, {}))[0])

    seen_tools = []

    async def probe(model, messages, tools_=None):
        seen_tools.append([t["function"]["name"] for t in (tools_ or [])])
        return NS(choices=[NS(message=NS(content="30 days", tool_calls=None))], usage=None)

    llm.complete = probe
    await run_one(CASES["find-in-big-file"], "baseline", 0, "m", asyncio.Semaphore(1))
    await run_one(CASES["find-in-big-file"], "no_search", 0, "m", asyncio.Semaphore(1))
    check("no_search variant removes only search_file", "search_file" in seen_tools[0] and "search_file" not in seen_tools[1] and "read_file" in seen_tools[1], seen_tools)

    bad = [n for n, ok in results if not ok]
    print("\nALL PASSED" if not bad else f"\nFAILED: {bad}")


asyncio.run(main())
