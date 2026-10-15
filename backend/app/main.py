import uuid

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import hooks, llm, runs, sessions, tools, workspace
from .chaos import KINDS as CHAOS_KINDS
from .config import GATE_MODES, RunConfig
from .controls import Controls
from .evals.api import router as evals_router
from .gates import Approvals
from .loop import run

app = FastAPI(title="Agent harness playground")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])
app.include_router(evals_router)
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
        "chaos": [{"name": k, "description": d} for k, d in CHAOS_KINDS.items()],
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


class SessionRun(RunConfig):
    session_id: str | None = None  # continue this chat, or start a new one when empty


class BranchRun(RunConfig):
    run_id: str  # the run to branch from
    event_index: int  # where in that run's events


def _stream(cfg: RunConfig, session: sessions.Session, task: str = "", *, resume: bool = False, label: str = ""):
    if session.id in sessions.ACTIVE:
        raise HTTPException(409, "This chat already has a run in progress.")
    sessions.ACTIVE.add(session.id)
    cfg.model = cfg.model or llm.default_model()
    run_id = uuid.uuid4().hex[:8]

    async def stream():
        try:
            async for event in run(cfg, approvals, controls, run_id, session, task, resume, label):
                runs.append(run_id, event)
                yield event.sse()
        finally:
            sessions.ACTIVE.discard(session.id)
            controls.take_compact(run_id)  # drop any request the loop never got to

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/run")
async def start_run(cfg: SessionRun):
    """A new chat, or the next message of an existing one."""
    session = sessions.load(cfg.session_id) if cfg.session_id else None
    if cfg.session_id and not session:
        raise HTTPException(404, "No such chat.")
    session = session or sessions.create(cfg.memory, cfg.task)
    return _stream(cfg, session, cfg.task)


@app.post("/sessions/{session_id}/resume")
async def resume_session(session_id: str, cfg: RunConfig):
    """Pick up a chat that stopped part-way, from its last checkpoint."""
    session = sessions.load(session_id)
    if not session:
        raise HTTPException(404, "No such chat.")
    if session.status != "interrupted":
        raise HTTPException(409, "That chat did not stop part-way.")
    return _stream(cfg, session, resume=True, label="Resumed after an interruption")


@app.post("/branch")
async def branch(req: BranchRun):
    """Start a new chat from what the model saw at one point of an earlier run, with the current settings."""
    events = runs.load(req.run_id)
    marks = [e for e in events[: req.event_index + 1] if e["type"] == "context_updated" and e["agent"] == "main"]
    if not marks:
        raise HTTPException(400, "Nothing to branch from at that point.")
    mark = marks[-1]
    session = sessions.create(req.memory, f"Re-run from step {mark['step']}")
    session.ctx.messages = [m for m in mark["data"]["messages"] if m["role"] != "system"]
    return _stream(req, session, label=f"Re-run from step {mark['step']}")


@app.get("/sessions")
def list_sessions():
    return sessions.list_all()


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    session = sessions.load(session_id)
    if not session:
        raise HTTPException(404, "No such chat.")
    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "interrupted_at": session.interrupted_at(),
        "setup": session.setup or None,
        "turns": [{**t, "events": runs.load(t["run_id"])} for t in session.turns],
    }


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
