import json
from dataclasses import replace

from . import compaction, hooks, llm, tools
from .config import RunConfig
from .context import Context
from .controls import Controls
from .events import Event
from .gates import Approvals


SUBAGENT_MAX_STEPS = 6


async def run(cfg: RunConfig, approvals: Approvals, controls: Controls, run_id: str):
    """One run. Yields an Event for every step so a UI can draw it."""
    yield Event("run_started", data={"run_id": run_id, "task": cfg.task, "model": cfg.model, "tools": cfg.tools})
    if cfg.memory:
        yield Event("memory_loaded", data={"text": cfg.memory})
    async for event in agent_loop(cfg, cfg.task, approvals, lambda: controls.take_compact(run_id)):
        yield event


async def agent_loop(cfg: RunConfig, task: str, approvals: Approvals, compact_requested):
    """The loop itself. The main agent and every subagent run this same code."""
    ctx = Context(cfg.memory)
    schemas = tools.schemas(cfg.tools)
    ctx.add({"role": "user", "content": task})

    for step in range(1, cfg.max_steps + 1):
        reason = _compact_reason(ctx, cfg, schemas, compact_requested())
        if reason and len(ctx.messages) >= 3:  # nothing worth summarizing before that
            try:
                async for event in _compact(ctx, cfg, schemas, reason, step):
                    yield event
            except Exception as e:
                yield Event("error", step, {"message": str(e)})
                return

        yield Event("context_updated", step, {**ctx.usage(schemas, cfg.context_limit), "messages": ctx.as_messages()})

        try:
            resp = await llm.complete(cfg.model, ctx.as_messages(), schemas or None)
        except Exception as e:
            yield Event("error", step, {"message": str(e)})
            return

        msg = resp.choices[0].message
        calls = [
            {"id": c.id, "name": c.function.name, "args": json.loads(c.function.arguments or "{}")}
            for c in msg.tool_calls or []
        ]
        ctx.add(_assistant_message(msg.content, calls))
        yield Event("model_replied", step, {"text": msg.content, "tool_calls": calls})

        if not calls:
            yield Event("done", step, {"answer": msg.content})
            return

        for call in calls:
            async for event in _execute(call, cfg, approvals, ctx, step):
                yield event

    yield Event("done", cfg.max_steps, {"answer": None, "reason": "max_steps reached"})


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
    ctx.compact(await compaction.summarize(cfg.model, ctx.summary, ctx.messages))
    after = ctx.usage(schemas, cfg.context_limit)["total"]
    yield Event("compaction_done", step, {"summary": ctx.summary, "before": before, "after": after})


async def _execute(call: dict, cfg: RunConfig, approvals: Approvals, ctx: Context, step: int):
    """before hooks, then the gate, then the tool, then after hooks. The result goes into context."""
    name, args = call["name"], call["args"]
    allowed, result = False, None

    for hook_name, reason in hooks.run_before(cfg.hooks, name, args):
        yield _hook_event(step, "before", hook_name, name, "blocked" if reason else "passed", reason or "")
        if reason:
            result = f"Blocked by hook '{hook_name}': {reason}"

    if result is None and name not in cfg.tools:
        result = f"Error: tool '{name}' is not enabled"

    if result is None:
        mode = cfg.gates.get(name, "ask")
        yield Event("gate_checked", step, {"call_id": call["id"], "tool": name, "mode": mode})
        allowed = mode == "auto"
        if mode == "ask":
            yield Event("approval_requested", step, {"call_id": call["id"], "tool": name, "args": args})
            allowed = await approvals.wait(call["id"])

        if not allowed:
            result = "Denied: the gate did not allow this tool call"
        else:
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
                try:
                    result = str(tools.REGISTRY[name].fn(**args))
                except Exception as e:
                    result = f"Error: {e}"
            for hook_name, new_result in hooks.run_after(cfg.hooks, name, result):
                outcome = "changed" if new_result != result else "passed"
                yield _hook_event(step, "after", hook_name, name, outcome, "")
                result = new_result

    ctx.add({"role": "tool", "tool_call_id": call["id"], "content": result})
    yield Event("tool_result", step, {"call_id": call["id"], "tool": name, "allowed": allowed, "result": result})


async def _subagent(task: str, cfg: RunConfig, approvals: Approvals, agent_id: str, step: int):
    """Run the same loop with a fresh context. Only its final answer goes back to the caller."""
    sub_cfg = cfg.model_copy(update={"tools": [t for t in cfg.tools if t != "delegate"], "max_steps": SUBAGENT_MAX_STEPS})
    yield Event("subagent_started", step, {"task": task}, agent=agent_id)
    async for event in agent_loop(sub_cfg, task, approvals, lambda: False):
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
