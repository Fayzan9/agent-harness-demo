"""Checks are data: a dict with a "type". Each one looks at what a run did and says pass or fail."""

from dataclasses import dataclass

# outcome: is the end result right. trajectory: did it get there the right way. judge: a model grades it.
KINDS = {
    "answer_contains": "outcome",
    "answer_not_contains": "outcome",
    "file_exists": "outcome",
    "file_contains": "outcome",
    "tool_called": "trajectory",
    "tool_not_called": "trajectory",
    "hook_blocked": "trajectory",
    "event_seen": "trajectory",
    "max_steps": "trajectory",
    "no_error": "trajectory",
    "no_leak": "trajectory",
    "peak_context_at_most": "trajectory",
    "judge": "judge",
}


@dataclass
class RunView:
    events: list[dict]
    files: dict[str, str]

    @property
    def answer(self) -> str:
        done = [e for e in self.events if e["type"] == "done" and e["agent"] == "main"]
        return (done[-1]["data"].get("answer") or "") if done else ""

    def tools_called(self) -> list[str]:
        return [c["name"] for e in self.events if e["type"] == "model_replied" for c in e["data"]["tool_calls"]]

    def tool_results(self) -> list[str]:
        return [str(e["data"]["result"]) for e in self.events if e["type"] == "tool_result"]


def label(c: dict) -> str:
    t = c["type"]
    return {
        "answer_contains": f'Answer mentions "{c.get("value")}"',
        "answer_not_contains": f'Answer does not mention "{c.get("value")}"',
        "file_exists": f'{c.get("path")} was created',
        "file_contains": f'{c.get("path")} contains "{c.get("value")}"',
        "tool_called": f'Used the {c.get("tool")} tool',
        "tool_not_called": f'Never used {c.get("tool")}',
        "hook_blocked": f'Hook {c.get("hook")} blocked a call',
        "event_seen": f'A "{c.get("event")}" step happened',
        "max_steps": f'Finished within {c.get("value")} steps',
        "no_error": "Ran without errors",
        "no_leak": f'"{c.get("value")}" never showed up in the answer or a tool result',
        "peak_context_at_most": f'Context never above {c.get("value")} tokens',
        "judge": f'Judge: {c.get("rubric")}',
    }[t]


def run_check(c: dict, run: RunView) -> tuple[bool, str]:
    """Returns (passed, detail). The judge check is handled by the runner because it calls a model."""
    t = c["type"]
    if t == "answer_contains":
        ok = c["value"].lower() in run.answer.lower()
        return ok, "" if ok else f"The answer was: {run.answer[:140]!r}"
    if t == "answer_not_contains":
        ok = c["value"].lower() not in run.answer.lower()
        return ok, "" if ok else "The answer contained it."
    if t == "file_exists":
        ok = c["path"] in run.files
        return ok, "" if ok else f"Files at the end: {sorted(run.files)}"
    if t == "file_contains":
        text = run.files.get(c["path"])
        ok = text is not None and c["value"].lower() in text.lower()
        return ok, "" if ok else (f"{c['path']} does not exist." if text is None else f"{c['path']} said: {text[:140]!r}")
    if t == "tool_called":
        ok = c["tool"] in run.tools_called()
        return ok, "" if ok else f"Tools used: {run.tools_called() or 'none'}"
    if t == "tool_not_called":
        ok = c["tool"] not in run.tools_called()
        return ok, "" if ok else f"{c['tool']} was used."
    if t == "hook_blocked":
        ok = any(e["type"] == "hook_ran" and e["data"]["outcome"] == "blocked" and e["data"]["hook"] == c["hook"] for e in run.events)
        return ok, "" if ok else "That hook never blocked anything."
    if t == "event_seen":
        ok = any(e["type"] == c["event"] for e in run.events)
        return ok, "" if ok else "It never happened."
    if t == "max_steps":
        steps = max((e["step"] for e in run.events if e["type"] == "model_replied" and e["agent"] == "main"), default=0)
        return steps <= c["value"], f"Took {steps} steps."
    if t == "no_error":
        errors = [e["data"].get("message", "") for e in run.events if e["type"] == "error" and e["agent"] == "main"]
        return not errors, errors[0][:160] if errors else ""
    if t == "peak_context_at_most":
        peak = max((e["data"]["total"] for e in run.events if e["type"] == "context_updated" and e["agent"] == "main"), default=0)
        return peak <= c["value"], f"Peak context was {peak} tokens."
    if t == "no_leak":
        value = c["value"].lower()
        where = "the answer" if value in run.answer.lower() else "a tool result" if any(value in r.lower() for r in run.tool_results()) else ""
        return not where, f"It appeared in {where}." if where else ""
    raise ValueError(f"Unknown check type: {t}")
