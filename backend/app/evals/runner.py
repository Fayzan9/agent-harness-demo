import asyncio
import json
import shutil
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from .. import llm, workspace
from ..config import RunConfig, workspace_var
from ..controls import Controls
from ..gates import Approvals
from ..loop import run
from ..sessions import Session
from . import checks

CASES: dict[str, dict] = {c["id"]: c for c in json.loads((Path(__file__).parent / "cases.json").read_text())}

# "Change one thing": each variant is a set of overrides applied on top of every case's own setup.
VARIANTS: dict[str, dict] = {
    "baseline": {"label": "Baseline", "description": "Every case exactly as written", "overrides": {}},
    "no_hooks": {"label": "Without hooks", "description": "Turn every hook off", "overrides": {"hooks": []}},
    "no_memory": {"label": "Without the memory file", "description": "Start with no standing instructions", "overrides": {"memory": ""}},
    "tight_steps": {"label": "Step limit of 2", "description": "Barely enough room to finish", "overrides": {"max_steps": 2}},
    "tiny_context": {
        "label": "Tiny context (350 tokens)",
        "description": "Forces compaction almost immediately",
        "overrides": {"context_limit": 350, "compact_at": 30},
    },
    "flaky_api": {"label": "Flaky API", "description": "The first two model calls fail with a 429", "overrides": {"chaos": ["rate_limit"]}},
}

JUDGE_PROMPT = (
    "You are a strict grader. Decide whether the output meets the rubric. "
    "Reply with PASS or FAIL on the first line, then one short reason."
)


class EphemeralSession(Session):
    """Eval runs are not saved anywhere, so they never show up in History."""

    def save(self):
        pass


async def judge(model: str, task: str, text: str, rubric: str) -> tuple[bool, str, int]:
    prompt = [
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": f"Task given to the agent:\n{task}\n\nOutput to grade:\n{text}\n\nRubric: {rubric}"},
    ]
    resp = await llm.complete(model, prompt, None)
    reply = (resp.choices[0].message.content or "").strip()
    usage = llm.usage_of(resp)
    return reply.upper().startswith("PASS"), reply[:200], usage["prompt"] + usage["completion"]


async def grade(case: dict, view: checks.RunView, model: str) -> tuple[list[dict], int]:
    out, judge_tokens = [], 0
    for c in case["checks"]:
        if c["type"] == "judge":
            target = c.get("target", "answer")
            text = view.answer if target == "answer" else view.files.get(target, "")
            if not text.strip():
                ok, detail, tokens = False, f"Nothing to grade: {target} is empty or missing.", 0
            else:
                try:
                    ok, detail, tokens = await judge(model, case["task"], text, c["rubric"])
                except Exception as e:
                    ok, detail, tokens = False, f"The judge failed: {e}", 0
            judge_tokens += tokens
        else:
            ok, detail = checks.run_check(c, view)
        out.append({"kind": checks.KINDS[c["type"]], "label": checks.label(c), "passed": ok, "detail": detail})
    return out, judge_tokens


def _tokens(events: list[dict]) -> int:
    total = 0
    for e in events:
        usage = e["data"].get("usage") if e["type"] in ("model_replied", "compaction_done") else None
        if usage:
            total += usage["prompt"] + usage["completion"]
    return total


async def run_one(case: dict, variant_id: str, index: int, model: str, gate: asyncio.Semaphore) -> dict:
    """One run of one case under one variant, in its own temporary workspace so runs cannot interfere."""
    async with gate:
        started = time.perf_counter()
        workdir = Path(tempfile.mkdtemp(prefix="eval-"))
        events: list[dict] = []
        answer, results, judge_tokens = "", [], 0
        try:
            for name, text in {**workspace.SEED, **case.get("fixtures", {})}.items():
                (workdir / name).write_text(text)
            workspace_var.set(workdir)  # this task has its own copy of the context, so this stays local

            setup = {**case["setup"], **VARIANTS[variant_id]["overrides"]}
            cfg = RunConfig(**setup, task=case["task"], model=model)
            run_id = f"eval-{case['id']}-{variant_id}-{index}"
            session = EphemeralSession(run_id, cfg.memory)
            # No human is watching an eval, so a stray "ask" gate is refused after two seconds instead of waiting.
            async for event in run(cfg, Approvals(timeout=2), Controls(), run_id, session, case["task"]):
                events.append(asdict(event))

            files = {p.name: p.read_text(errors="replace") for p in workdir.iterdir() if p.is_file()}
            view = checks.RunView(events, files)
            answer = view.answer
            results, judge_tokens = await grade(case, view, model)
        except Exception as e:
            results = [{"kind": "trajectory", "label": "The run completed", "passed": False, "detail": f"The run crashed: {e}"}]
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        return {
            "case": case["id"],
            "variant": variant_id,
            "index": index,
            "passed": all(r["passed"] for r in results),
            "checks": results,
            "seconds": round(time.perf_counter() - started, 1),
            "tokens": _tokens(events) + judge_tokens,
            "answer": answer,
            "events": events,
        }
