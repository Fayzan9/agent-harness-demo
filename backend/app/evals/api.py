import asyncio
import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import llm
from . import checks
from .runner import CASES, VARIANTS, run_one

router = APIRouter(prefix="/evals")
OUT_DIR = Path(__file__).resolve().parents[2] / "evals_out"
MAX_RUNS = 90  # a ceiling so one click cannot spend a surprising amount
PARALLEL = 3


class EvalRequest(BaseModel):
    cases: list[str]
    variants: list[str]
    runs: int = 3


@router.get("/options")
def options():
    return {
        "cases": [
            {
                "id": c["id"],
                "label": c["label"],
                "task": c["task"],
                "checks": [{"kind": checks.KINDS[k["type"]], "label": checks.label(k)} for k in c["checks"]],
            }
            for c in CASES.values()
        ],
        "variants": [{"id": k, "label": v["label"], "description": v["description"]} for k, v in VARIANTS.items()],
    }


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@router.post("/run")
async def run_evals(req: EvalRequest):
    unknown = [c for c in req.cases if c not in CASES] + [v for v in req.variants if v not in VARIANTS]
    if unknown or not req.cases or not req.variants:
        raise HTTPException(400, f"Pick at least one known case and setup. Unknown: {unknown}")
    if not 1 <= req.runs <= 5:
        raise HTTPException(400, "Runs per case must be between 1 and 5.")
    jobs = [(CASES[c], v, i) for c in req.cases for v in req.variants for i in range(req.runs)]
    if len(jobs) > MAX_RUNS:
        raise HTTPException(400, f"That is {len(jobs)} runs. The limit is {MAX_RUNS}.")

    model = llm.default_model()

    async def stream():
        gate = asyncio.Semaphore(PARALLEL)
        tasks = [asyncio.create_task(run_one(case, v, i, model, gate)) for case, v, i in jobs]
        results = []
        try:
            yield _sse({"type": "plan", "total": len(tasks)})
            for finished in asyncio.as_completed(tasks):
                result = await finished
                results.append(result)
                yield _sse({"type": "run_done", **result})
            yield _sse({"type": "done"})
            OUT_DIR.mkdir(exist_ok=True)
            (OUT_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(json.dumps({"request": req.model_dump(), "results": results}))
        finally:
            for t in tasks:
                t.cancel()  # a Stop or a closed tab ends the rest of the suite

    return StreamingResponse(stream(), media_type="text/event-stream")
