import asyncio
import json
import random
import time
from collections import Counter
from dataclasses import dataclass, replace

from . import compaction, hooks, llm, tools
from .chaos import Chaos, SimulatedRateLimit
from .config import RunConfig
from .context import Context
from .controls import Controls
from .events import Event
from .gates import Approvals
from .sessions import Session

SUBAGENT_MAX_STEPS = 6
MAX_MODEL_ATTEMPTS = 4  # the first try plus three retries
MAX_BAD_ARGUMENT_TURNS = 3  # how many times the model gets to fix broken tool arguments
LOOP_NUDGE_AT = 3  # same call this many times: do not run it, tell the model
LOOP_STOP_AT = 5  # same call this many times: end the run


class StuckInLoop(Exception):
    pass


@dataclass
class Reply:
    message: object
    seconds: float
    usage: dict


async def run(
    cfg: RunConfig,
    approvals: Approvals,
    controls: Controls,
    run_id: str,
    session: Session,
    task: str = "",
    resume: bool = False,
    label: str = "",
):
    """One turn of a session. Yields an Event for every step so a UI can draw it."""
    first_turn = not session.turns
    label = label or task
    session.turns.append({"run_id": run_id, "task": label})
    session.setup = cfg.model_dump(exclude={"task", "model"})
    finished = False
    try:
        if task:
            session.close_pending("a new message arrived first")  # keep the history valid for the model
            session.ctx.add({"role": "user", "content": task})
        session.set_status("running")
        yield Event(
            "run_started",
            data={
                "run_id": run_id,
                "session_id": session.id,
                "turn": len(session.turns),
                "task": label,
                "model": cfg.model,
                "tools": cfg.tools,
                "resumed": resume,
            },
        )
        if session.ctx.memory and first_turn:
            yield Event("memory_loaded", data={"text": session.ctx.memory})

        session.ctx.clock_first = "clock_in_prompt" in cfg.chaos
        if session.ctx.clock_first:
            yield Event(
                "chaos",
                data={"kind": "clock_in_prompt", "detail": "Putting the current time at the very top of the instructions, so the start of the prompt changes on every pass"},
            )
        chaos = Chaos(cfg.chaos) if cfg.chaos else None
        pending = _pending_for_resume(session) if resume else None
        async for event in agent_loop(
            cfg, session.ctx, approvals, lambda: controls.take_compact(run_id), chaos, session, pending
        ):
            yield event
        finished = True
    finally:
        if finished:
            session.close_pending("the run ended first")
        session.set_status("idle" if finished else "interrupted")


def _pending_for_resume(session: Session) -> list[dict]:
    """Calls to finish on resume. One that was mid-run may already have taken effect, so flag it."""
    calls = [dict(c) for c in session.pending_calls]
    flight = session.in_flight
    for call in calls:
        if flight and flight["call_id"] == call["id"] and flight["state"] == "running":
            call["maybe_ran"] = True
    return calls


async def agent_loop(
    cfg: RunConfig,
    ctx: Context,
    approvals: Approvals,
    compact_requested,
    chaos: Chaos | None = None,
    session: Session | None = None,
    pending_calls: list[dict] | None = None,
):
    """The loop itself. The main agent and every subagent run this same code."""
    schemas = tools.schemas(cfg.tools)
    seen: Counter = Counter()  # identical tool calls so far, for loop detection
    bad_turns = 0  # consecutive turns where the model sent broken arguments
    last_action = ""
    just_compacted = False  # compacting on two passes in a row only makes the agent redo its work

    if pending_calls:  # finish the step that a crash or a Stop cut short
        try:
            for call in pending_calls:
                async for event in _execute(call, cfg, approvals, ctx, 0, seen, chaos, session):
                    yield event
        except StuckInLoop as e:
            yield Event("error", 0, {"message": str(e)})
            return

    for step in range(1, cfg.max_steps + 1):
        reason = _compact_reason(ctx, cfg, schemas, compact_requested())
        if reason == "auto" and just_compacted:
            reason = None
        just_compacted = False
        if reason and len(ctx.messages) >= 3:  # nothing worth summarizing before that
            just_compacted = True
            try:
                async for event in _compact(ctx, cfg, schemas, reason, step):
                    yield event
            except Exception as e:
                yield Event("error", step, {"message": str(e)})
                return

        messages = ctx.as_messages()  # built once, so what the event shows is exactly what is sent
        yield Event("context_updated", step, {**ctx.usage(schemas, cfg.context_limit), "messages": messages})

        reply = None
        async for item in _call_model(cfg, messages, schemas, step, chaos):
            if isinstance(item, Reply):
                reply = item
            else:
                yield item
        if reply is None:  # _call_model already reported why
            return

        raw_calls = [
            {"id": c.id, "name": c.function.name, "raw": c.function.arguments or "{}"}
            for c in reply.message.tool_calls or []
        ]
        calls = [_parse(c) for c in (chaos.tamper_raw(raw_calls, step) if chaos else raw_calls)]
        if chaos:
            calls = chaos.repeat(calls, step)
            for event in chaos.drain():
                yield event

        ctx.add(_assistant_message(reply.message.content, calls))
        if session:
            session.begin_calls(calls)  # saves the context too, so the calls and their history stay together
        yield Event(
            "model_replied",
            step,
            {
                "text": reply.message.content,
                "tool_calls": [{k: c[k] for k in ("id", "name", "args", "error")} for c in calls],
                "duration": round(reply.seconds, 2),
                "usage": reply.usage,
            },
        )

        if not calls:
            yield Event("done", step, {"answer": reply.message.content})
            return
        last_action = ", ".join(f"{c['name']}({json.dumps(c['args'])})" for c in calls)

        if any(c["error"] for c in calls):
            bad_turns += 1
            if bad_turns > MAX_BAD_ARGUMENT_TURNS:
                yield Event("error", step, {"message": f"The model sent broken tool arguments {bad_turns} times in a row, so the run was stopped."})
                return
            detail = next(c["error"] for c in calls if c["error"])
            yield Event("retry", step, {"kind": "bad_arguments", "attempt": bad_turns, "max": MAX_BAD_ARGUMENT_TURNS, "detail": detail})
        else:
            bad_turns = 0

        try:
            for call in calls:
                async for event in _execute(call, cfg, approvals, ctx, step, seen, chaos, session):
                    yield event
        except StuckInLoop as e:
            yield Event("error", step, {"message": str(e)})
            return

    yield Event(
        "done",
        cfg.max_steps,
        {"answer": None, "reason": f"step limit reached ({cfg.max_steps} steps)", "last_action": last_action},
    )


async def _call_model(cfg: RunConfig, messages: list[dict], schemas: list[dict], step: int, chaos: Chaos | None):
    """One model call. Temporary failures are retried with a growing pause. Yields Events, then a Reply."""
    for attempt in range(1, MAX_MODEL_ATTEMPTS + 1):
        started = time.perf_counter()
        try:
            if chaos:
                chaos.before_model_call(step)
            resp = await llm.complete(cfg.model, messages, schemas or None)
            yield Reply(resp.choices[0].message, time.perf_counter() - started, llm.usage_of(resp))
            return
        except (*llm.TRANSIENT, SimulatedRateLimit) as e:
            if chaos:
                for event in chaos.drain():
                    yield event
            if attempt == MAX_MODEL_ATTEMPTS:
                yield Event("error", step, {"message": f"The model API kept failing after {attempt} tries: {e}"})
                return
            delay = round(2 ** (attempt - 1) + random.random() * 0.5, 1)  # about 1s, 2s, 4s
            yield Event(
                "retry",
                step,
                {"kind": "model_error", "attempt": attempt, "max": MAX_MODEL_ATTEMPTS - 1, "delay": delay, "detail": str(e)[:200]},
            )
            await asyncio.sleep(delay)
        except Exception as e:
            yield Event("error", step, {"message": str(e)})
            return


def _parse(call: dict) -> dict:
    """Turn the model's argument text into a dict. Broken text is kept as an error for the model to fix."""
    try:
        args = json.loads(call["raw"])
        if not isinstance(args, dict):
            raise ValueError("the arguments must be a JSON object")
        return {"id": call["id"], "name": call["name"], "args": args, "error": None}
    except ValueError as e:
        return {"id": call["id"], "name": call["name"], "args": {}, "error": str(e), "raw": call["raw"]}


def _compact_reason(ctx: Context, cfg: RunConfig, schemas: list[dict], requested: bool) -> str | None:
    if requested:
        return "manual"
    if ctx.usage(schemas, cfg.context_limit)["total"] >= cfg.context_limit * cfg.compact_at / 100:
        return "auto"
    return None


async def _compact(ctx: Context, cfg: RunConfig, schemas: list[dict], reason: str, step: int):
    """Replace the chat so far with a model-written summary."""
    before = ctx.usage(schemas, cfg.context_limit)["total"]
    yield Event("compaction_started", step, {"reason": reason, "before": before})
    started = time.perf_counter()
    summary, usage = await compaction.summarize(cfg.model, ctx.summary, ctx.messages)
    ctx.compact(summary)
    after = ctx.usage(schemas, cfg.context_limit)["total"]
    yield Event(
        "compaction_done",
        step,
        {"summary": ctx.summary, "before": before, "after": after, "usage": usage, "duration": round(time.perf_counter() - started, 2)},
    )


async def _execute(
    call: dict,
    cfg: RunConfig,
    approvals: Approvals,
    ctx: Context,
    step: int,
    seen: Counter,
    chaos: Chaos | None,
    session: Session | None = None,
):
    """before hooks, then the gate, then the tool, then after hooks. The result goes into context."""
    name, args = call["name"], call["args"]
    allowed, result, duration = False, None, 0.0

    if call["error"]:
        result = (
            f"Your arguments for {name} were not valid JSON ({call['error']}). "
            f"You sent: {call['raw'][:200]}. Call it again with valid JSON."
        )
    else:
        signature = f"{name}:{json.dumps(args, sort_keys=True)}"
        seen[signature] += 1
        if seen[signature] >= LOOP_STOP_AT:
            raise StuckInLoop(f"The agent made the same {name} call {seen[signature]} times, so the run was stopped.")
        if seen[signature] >= LOOP_NUDGE_AT:
            yield Event("loop_detected", step, {"tool": name, "args": args, "count": seen[signature]})
            result = (
                f"You have made this exact {name} call {seen[signature]} times and it will not give a new answer. "
                "Try something different, or finish and explain what you found."
            )

    if result is None:
        for hook_name, reason in hooks.run_before(cfg.hooks, name, args):
            yield _hook_event(step, "before", hook_name, name, "blocked" if reason else "passed", reason or "")
            if reason:
                result = f"Blocked by hook '{hook_name}': {reason}"

    if result is None and name not in cfg.tools:
        result = f"Error: tool '{name}' is not enabled"

    if result is None:
        maybe_ran = bool(call.get("maybe_ran"))
        mode = "ask" if maybe_ran else cfg.gates.get(name, "ask")  # never repeat a call that may have run without asking
        yield Event("gate_checked", step, {"call_id": call["id"], "tool": name, "mode": mode})
        allowed = mode == "auto"
        if mode == "ask":
            if session:
                session.flight(call["id"], name, "awaiting_approval")
            yield Event(
                "approval_requested",
                step,
                {"call_id": call["id"], "tool": name, "args": args, "maybe_ran": maybe_ran},
            )
            allowed = await approvals.wait(call["id"], session.owner if session else "")

        if not allowed:
            result = "Denied: the gate did not allow this tool call"
        else:
            started = time.perf_counter()
            if session:
                session.flight(call["id"], name, "running")
            if name == "delegate":
                result = "Subagent finished without an answer"
                agent_id = f"sub-{call['id'][-6:]}"
                async for event in _subagent(args.get("task", ""), cfg, approvals, agent_id, step):
                    yield event
                    if event.agent == agent_id and event.type == "done" and event.data.get("answer"):
                        result = event.data["answer"]
                    elif event.agent == agent_id and event.type == "error":
                        result = f"Subagent error: {event.data['message']}"
            else:
                hang = bool(chaos and chaos.hangs(step))
                if chaos:
                    for event in chaos.drain():
                        yield event
                result = await _run_tool(name, args, cfg.tool_timeout, hang)
            duration = time.perf_counter() - started
            for hook_name, new_result in hooks.run_after(cfg.hooks, name, result):
                outcome = "changed" if new_result != result else "passed"
                yield _hook_event(step, "after", hook_name, name, outcome, "")
                result = new_result

    ctx.add({"role": "tool", "tool_call_id": call["id"], "content": result})
    if session:
        session.finish_call(call["id"])
    yield Event(
        "tool_result",
        step,
        {"call_id": call["id"], "tool": name, "allowed": allowed, "result": result, "duration": round(duration, 2)},
    )


async def _run_tool(name: str, args: dict, timeout: int, hang: bool) -> str:
    """Run a tool in a worker thread so a slow one cannot freeze the loop. Errors become text for the model."""
    try:
        # A real thread cannot be killed, so a timed-out tool is abandoned, not stopped.
        work = asyncio.sleep(timeout + 60) if hang else asyncio.to_thread(tools.REGISTRY[name].fn, **args)
        return str(await asyncio.wait_for(work, timeout))
    except asyncio.TimeoutError:
        return f"Error: {name} timed out after {timeout}s. Try another approach."
    except Exception as e:
        return f"Error: {e}"


async def _subagent(task: str, cfg: RunConfig, approvals: Approvals, agent_id: str, step: int):
    """Run the same loop with a fresh context. Only its final answer goes back to the caller."""
    sub_cfg = cfg.model_copy(update={"tools": [t for t in cfg.tools if t != "delegate"], "max_steps": SUBAGENT_MAX_STEPS})
    yield Event("subagent_started", step, {"task": task}, agent=agent_id)
    ctx = Context(cfg.memory)  # fresh: the helper sees none of the main conversation
    ctx.add({"role": "user", "content": task})
    async for event in agent_loop(sub_cfg, ctx, approvals, lambda: False):
        yield replace(event, agent=agent_id)


def _hook_event(step: int, phase: str, hook: str, tool: str, outcome: str, detail: str) -> Event:
    return Event("hook_ran", step, {"phase": phase, "hook": hook, "tool": tool, "outcome": outcome, "detail": detail})


def _assistant_message(content: str | None, calls: list[dict]) -> dict:
    message: dict = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [
            {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
            for c in calls
        ]
    return message
