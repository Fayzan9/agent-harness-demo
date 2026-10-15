"""Reliability checks against a scripted fake model, no API key needed.

Run from backend/:  PYTHONPATH=. uv run python tests/test_reliability.py
"""
import asyncio
import json
import time
from types import SimpleNamespace as NS

import litellm

from app import llm, tools
from app.config import RunConfig
from app.controls import Controls
from app.gates import Approvals
from app.loop import run


def resp(content=None, calls=(), usage=None):
    tcs = [NS(id=f"c{i}", function=NS(name=n, arguments=a)) for i, (n, a) in enumerate(calls)] or None
    return NS(choices=[NS(message=NS(content=content, tool_calls=tcs))], usage=usage)


def script(items):
    queue = list(items)

    async def fake(model, messages, tools_=None):
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    llm.complete = fake


async def collect(**kw):
    cfg = RunConfig(task="t", model="m", tools=["read_file", "list_files", "slow"], gates={"read_file": "auto", "list_files": "auto", "slow": "auto"}, **kw)
    out = []
    async for e in run(cfg, Approvals(), Controls(), "test"):
        out.append(e)
    return out


def types(events):
    return [e.type for e in events]


def find(events, t):
    return [e for e in events if e.type == t]


@tools.tool
def slow() -> str:
    """Sleeps."""
    time.sleep(3)
    return "finally"


READ = ("read_file", json.dumps({"path": "notes.txt"}))
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name, extra)


async def main():
    # 1. broken JSON once, then a valid call, then an answer
    script([resp(calls=[("read_file", '{"path": "notes.txt"')]), resp(calls=[READ]), resp("Faizan")])
    ev = await collect()
    check("bad json: one retry event", len(find(ev, "retry")) == 1 and find(ev, "retry")[0].data["attempt"] == 1, types(ev))
    check("bad json: recovered and finished", ev[-1].type == "done" and ev[-1].data["answer"] == "Faizan")
    check("bad json: model told what went wrong", "not valid JSON" in find(ev, "tool_result")[0].data["result"])

    # 2. broken JSON every time: stops after 3 retries
    script([resp(calls=[("read_file", "{nope")])])
    ev = await collect()
    check("bad json forever: 3 retry events then error", len(find(ev, "retry")) == 3 and ev[-1].type == "error", types(ev)[-6:])

    # 3. temporary model failure then success (real litellm exception class)
    t0 = time.time()
    script([litellm.Timeout("slow", model="m", llm_provider="azure"), resp("ok")])
    ev = await collect()
    check("transient error: retried then done", len(find(ev, "retry")) == 1 and ev[-1].type == "done", f"{time.time()-t0:.1f}s")

    # 4. model keeps failing: gives up with a clear error
    script([litellm.Timeout("slow", model="m", llm_provider="azure")])
    ev = await collect()
    check("transient forever: 3 retries then error", len(find(ev, "retry")) == 3 and ev[-1].type == "error" and "kept failing" in ev[-1].data["message"])

    # 5. non transient error is not retried
    script([ValueError("bad request")])
    ev = await collect()
    check("other error: no retry", not find(ev, "retry") and ev[-1].type == "error")

    # 6. loop detection: nudge at 3, stop at 5
    script([resp(calls=[READ])])
    ev = await collect()
    check("loop: nudged twice then stopped", len(find(ev, "loop_detected")) == 2 and ev[-1].type == "error" and "same read_file call" in ev[-1].data["message"], [e.data.get("count") for e in find(ev, "loop_detected")])

    # 7. tool timeout
    script([resp(calls=[("slow", "{}")]), resp("done")])
    ev = await collect(tool_timeout=1)
    r = find(ev, "tool_result")[0].data["result"]
    check("tool timeout: error result for the model", "timed out after 1s" in r, r)

    # 8. step limit message names the last action
    n = {"i": 0}

    async def different(model, messages, tools_=None):
        n["i"] += 1
        return resp(calls=[("read_file", json.dumps({"path": f"f{n['i']}.txt"}))])

    llm.complete = different
    ev = await collect(max_steps=3)
    d = ev[-1].data
    check("step limit: reason and last action", ev[-1].type == "done" and "step limit" in d["reason"] and "f3.txt" in d["last_action"], d)

    # 9. usage and timing recorded
    script([resp("hi", usage=NS(prompt_tokens=100, completion_tokens=20, prompt_tokens_details=NS(cached_tokens=64)))])
    ev = await collect()
    m = find(ev, "model_replied")[0].data
    check("usage + duration recorded", m["usage"] == {"prompt": 100, "completion": 20, "cached": 64} and "duration" in m, m["usage"])
    script([resp("hi", usage=None)])
    ev = await collect()
    check("missing usage tolerated", find(ev, "model_replied")[0].data["usage"]["prompt"] == 0)

    # 10. chaos switches
    script([resp(calls=[READ]), resp("Faizan")])
    ev = await collect(chaos=["rate_limit"])
    check("chaos rate_limit: 2 notes, 2 retries, finished", len(find(ev, "chaos")) == 2 and len(find(ev, "retry")) == 2 and ev[-1].type == "done", types(ev)[:9])
    script([resp(calls=[READ]), resp(calls=[READ]), resp("Faizan")])
    ev = await collect(chaos=["bad_json"])
    check("chaos bad_json: noted, retried, finished", len(find(ev, "chaos")) == 1 and find(ev, "retry") and ev[-1].type == "done")
    script([resp(calls=[READ]), resp("Faizan")])
    ev = await collect(chaos=["slow_tool"], tool_timeout=1)
    check("chaos slow_tool: noted and timed out", find(ev, "chaos") and "timed out" in find(ev, "tool_result")[0].data["result"])
    script([resp(calls=[READ]), resp("Faizan")])
    ev = await collect(chaos=["repeat_call"])
    check("chaos repeat_call: loop detected then stopped", find(ev, "loop_detected") and ev[-1].type == "error", types(ev)[-4:])

    bad = [n for n, ok in results if not ok]
    print("\nALL PASSED" if not bad else f"\nFAILED: {bad}")


asyncio.run(main())
