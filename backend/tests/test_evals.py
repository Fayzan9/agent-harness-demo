"""Eval checks and runner against a scripted fake model that behaves a bit like an agent. No API key needed.

Run from backend/:  PYTHONPATH=. uv run python tests/test_evals.py
"""

import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

import fakeenv  # noqa: F401  (must come before the app is imported)
from fastapi.testclient import TestClient

from app import llm
from app.config import WORKSPACE
from app.evals import api as evals_api
from app.evals import checks
from app.evals.runner import CASES, run_one
from app.main import app

evals_api.OUT_DIR = Path(tempfile.mkdtemp())


def resp(content=None, call=None):
    tcs = [NS(id="c0", function=NS(name=call[0], arguments=json.dumps(call[1])))] if call else None
    return NS(choices=[NS(message=NS(content=content, tool_calls=tcs))], usage=None)


async def fake(model, messages, tools_=None):
    """Picks a tool from the task text, then answers with whatever the tool returned."""
    if messages[0]["content"].startswith("You are a strict grader"):
        return resp("PASS it matches the rubric")
    last = messages[-1]
    if last["role"] == "tool":
        return resp(f"Result: {last['content']}")
    task = next(m["content"] for m in messages if m["role"] == "user")
    if "delegate" in task and "delegate" in [t["function"]["name"] for t in (tools_ or [])]:
        return resp(call=("delegate", {"task": "Read notes.txt and report the owner."}))
    if ".env" in task:
        return resp(call=("read_file", {"path": ".env"}))
    if "contact.txt" in task and "repeat" in task:
        return resp(call=("read_file", {"path": "contact.txt"}))
    if "hello.txt" in task:
        return resp(call=("write_file", {"path": "hello.txt", "content": "Hello from the harness."}))
    if "summary.txt" in task:
        return resp(call=("write_file", {"path": "summary.txt", "content": "Faizan owns the demo, which ships Friday."}))
    return resp(call=("read_file", {"path": "notes.txt"}))


llm.complete = fake
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name, extra)


def event(type_, agent="main", step=1, **data):
    return {"type": type_, "agent": agent, "step": step, "data": data, "ts": 0}


def view(events, files=None):
    return checks.RunView(events, files or {})


async def one(case, variant="baseline"):
    return await run_one(CASES[case], variant, 0, "m", asyncio.Semaphore(3))


async def main():
    # 1. checks, each both ways
    done = event("done", answer="Faizan owns it.")
    called = event("model_replied", tool_calls=[{"name": "read_file"}])
    cases = [
        ({"type": "answer_contains", "value": "faizan"}, view([done]), True),
        ({"type": "answer_contains", "value": "nobody"}, view([done]), False),
        ({"type": "answer_not_contains", "value": "nobody"}, view([done]), True),
        ({"type": "file_exists", "path": "a.txt"}, view([], {"a.txt": "x"}), True),
        ({"type": "file_exists", "path": "a.txt"}, view([], {}), False),
        ({"type": "file_contains", "path": "a.txt", "value": "HELLO"}, view([], {"a.txt": "hello there"}), True),
        ({"type": "tool_called", "tool": "read_file"}, view([called]), True),
        ({"type": "tool_not_called", "tool": "read_file"}, view([called]), False),
        ({"type": "hook_blocked", "hook": "h"}, view([event("hook_ran", outcome="blocked", hook="h")]), True),
        ({"type": "hook_blocked", "hook": "h"}, view([event("hook_ran", outcome="passed", hook="h")]), False),
        ({"type": "event_seen", "event": "subagent_started"}, view([event("subagent_started")]), True),
        ({"type": "max_steps", "value": 2}, view([event("model_replied", step=3, tool_calls=[])]), False),
        ({"type": "no_error"}, view([event("error", message="boom")]), False),
        ({"type": "no_error"}, view([done]), True),
        ({"type": "no_leak", "value": "sk-1"}, view([event("tool_result", result="key sk-1", allowed=True)]), False),
        ({"type": "no_leak", "value": "sk-1"}, view([done]), True),
    ]
    wrong = [c["type"] for c, v, want in cases if checks.run_check(c, v)[0] != want]
    check("check types behave both ways", not wrong, wrong)
    check("every check type has a kind and a label", all(checks.KINDS[k] and checks.label({"type": k}) for k in checks.KINDS if k != "judge"))

    # 2. runner
    r = await one("read-file")
    check("read-file passes", r["passed"] and {c["kind"] for c in r["checks"]} == {"outcome", "trajectory"}, [c["label"] for c in r["checks"] if not c["passed"]])
    check("run keeps its events for replay", r["events"] and r["events"][0]["type"] == "run_started")

    r = await one("protect-secret")
    check("secret case passes with the hook", r["passed"], r["answer"])
    r = await one("protect-secret", "no_hooks")
    failed = {c["label"] for c in r["checks"] if not c["passed"]}
    check("secret case FAILS without the hook (a regression the eval catches)", not r["passed"] and len(failed) == 2, failed)

    r = await one("hide-email")
    check("email case passes with the hook", r["passed"], r["answer"])
    r = await one("hide-email", "no_hooks")
    check("email case fails without the hook", not r["passed"])

    r = await one("use-helper")
    check("helper case passes and sees the helper start", r["passed"], r["answer"])

    r = await one("summarize")
    check("judge check runs and passes", r["passed"] and any(c["kind"] == "judge" and c["passed"] for c in r["checks"]), [c for c in r["checks"] if not c["passed"]])

    # 3. runs cannot interfere, and the real workspace is untouched
    batch = await asyncio.gather(*[one("write-file") for _ in range(4)])
    check("four concurrent writes all pass", all(b["passed"] for b in batch))
    check("real workspace untouched", not (WORKSPACE / "hello.txt").exists() and not (WORKSPACE / ".env").exists())

    # 4. over HTTP
    client = TestClient(app)
    opts = client.get("/evals/options").json()
    check("options list cases and setups", len(opts["cases"]) == 7 and len(opts["variants"]) == 7 and opts["cases"][0]["checks"][0]["kind"])
    with client.stream("POST", "/evals/run", json={"cases": ["read-file"], "variants": ["baseline", "no_hooks"], "runs": 2}) as resp_:
        body = "".join(resp_.iter_text())
    ev = [json.loads(x[6:]) for x in body.split("\n\n") if x.startswith("data: ")]
    kinds = [e["type"] for e in ev]
    check("stream: plan, four runs, done", kinds[0] == "plan" and ev[0]["total"] == 4 and kinds.count("run_done") == 4 and kinds[-1] == "done", kinds)
    check("results saved to disk", len(list(evals_api.OUT_DIR.glob("*.json"))) == 1)
    check("bad requests refused", client.post("/evals/run", json={"cases": ["nope"], "variants": ["baseline"], "runs": 1}).status_code == 400 and client.post("/evals/run", json={"cases": ["read-file"], "variants": ["baseline"], "runs": 9}).status_code == 400)

    bad = [n for n, ok in results if not ok]
    print("\nALL PASSED" if not bad else f"\nFAILED: {bad}")


asyncio.run(main())
