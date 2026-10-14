import uuid

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import hooks, llm, tools, workspace
from .config import GATE_MODES, RunConfig
from .controls import Controls
from .gates import Approvals
from .loop import run

app = FastAPI(title="Agent harness playground")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])
approvals = Approvals()
controls = Controls()


class CompactRequest(BaseModel):
    run_id: str


class Decision(BaseModel):
    call_id: str
    allow: bool


@app.get("/options")
def options():
    """What the setup panel can offer."""
    return {
        "models": [llm.default_model()],
        "gate_modes": GATE_MODES,
        "tools": [{"name": t.name, "description": t.description} for t in tools.REGISTRY.values()],
        "hooks": [
            {
                "name": h.name,
                "phase": h.phase,
                "description": h.description,
                "param_label": h.param_label,
                "param_default": h.param_default,
            }
            for h in hooks.HOOKS.values()
        ],
    }


@app.post("/run")
async def start_run(cfg: RunConfig):
    cfg.model = cfg.model or llm.default_model()
    run_id = uuid.uuid4().hex[:8]

    async def stream():
        try:
            async for event in run(cfg, approvals, controls, run_id):
                yield event.sse()
        finally:
            controls.take_compact(run_id)  # drop any request the loop never got to

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/compact")
def compact(r: CompactRequest):
    controls.request_compact(r.run_id)
    return {"queued": True}


@app.get("/workspace")
def get_workspace():
    return workspace.snapshot()


@app.post("/workspace/reset")
def reset_workspace():
    workspace.reset()
    return {"ok": True}


@app.post("/approve")
def approve(d: Decision):
    return {"resolved": approvals.resolve(d.call_id, d.allow)}
