import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import db, hooks, llm, runs, sessions, tools, workspace
from .auth import CurrentUser, User
from .chaos import KINDS as CHAOS_KINDS
from .config import GATE_MODES, RunConfig
from .controls import Controls
from .evals.api import router as evals_router
from .gates import Approvals
from .loop import run
from .settings import get_settings

settings = get_settings()  # fail fast: a missing or wrong setting stops the app here, not in the middle of a run
db.check_schema()  # fail fast: refuse to run on a database that has not been migrated

app = FastAPI(title="Agent harness playground")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(evals_router, dependencies=[CurrentUser])  # every eval route needs a signed-in user
approvals = Approvals()
controls = Controls()
run_owner: dict[str, str] = {}  # run id -> user id, for runs in progress, so one user cannot steer another's run


class CompactRequest(BaseModel):
    run_id: str


class Decision(BaseModel):
    call_id: str
    allow: bool


@app.get("/health")
def health():
    """For the load balancer. Public, and says nothing about the app."""
    return {"ok": True}


@app.get("/auth/config")
def auth_config():
    """Public: what the sign-in screen needs. The client id is not a secret (it is in every Google button)."""
    return {"mode": settings.auth_mode, "client_id": settings.auth_audience}


@app.get("/auth/me")
def me(user: User = CurrentUser):
    return user


@app.get("/options", dependencies=[CurrentUser])
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
    run_owner[run_id] = session.owner
    session.save()  # the chat must exist before a run can point at it
    runs.register(run_id, session.id, session.owner)

    async def stream():
        try:
            async for event in run(cfg, approvals, controls, run_id, session, task, resume, label):
                runs.append(run_id, event)
                yield event.sse()
        finally:
            sessions.ACTIVE.discard(session.id)
            controls.take_compact(run_id)  # drop any request the loop never got to
            run_owner.pop(run_id, None)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/run")
async def start_run(cfg: SessionRun, user: User = CurrentUser):
    """A new chat, or the next message of an existing one."""
    session = sessions.load(cfg.session_id, user.id) if cfg.session_id else None
    if cfg.session_id and not session:
        raise HTTPException(404, "No such chat.")
    session = session or sessions.create(cfg.memory, cfg.task, user.id)
    return _stream(cfg, session, cfg.task)


@app.post("/sessions/{session_id}/resume")
async def resume_session(session_id: str, cfg: RunConfig, user: User = CurrentUser):
    """Pick up a chat that stopped part-way, from its last checkpoint."""
    session = sessions.load(session_id, user.id)
    if not session:
        raise HTTPException(404, "No such chat.")
    if session.status != "interrupted":
        raise HTTPException(409, "That chat did not stop part-way.")
    return _stream(cfg, session, resume=True, label="Resumed after an interruption")


@app.post("/branch")
async def branch(req: BranchRun, user: User = CurrentUser):
    """Start a new chat from what the model saw at one point of an earlier run, with the current settings."""
    if not sessions.owns_run(user.id, req.run_id):
        raise HTTPException(404, "No such run.")
    events = runs.load(req.run_id)
    marks = [e for e in events[: req.event_index + 1] if e["type"] == "context_updated" and e["agent"] == "main"]
    if not marks:
        raise HTTPException(400, "Nothing to branch from at that point.")
    mark = marks[-1]
    session = sessions.create(req.memory, f"Re-run from step {mark['step']}", user.id)
    session.ctx.messages = [m for m in mark["data"]["messages"] if m["role"] != "system"]
    return _stream(req, session, label=f"Re-run from step {mark['step']}")


@app.get("/sessions")
def list_sessions(user: User = CurrentUser):
    return sessions.list_all(user.id)


@app.get("/sessions/{session_id}")
def get_session(session_id: str, user: User = CurrentUser):
    session = sessions.load(session_id, user.id)
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
def compact(r: CompactRequest, user: User = CurrentUser):
    if run_owner.get(r.run_id) != user.id:
        raise HTTPException(404, "No such run.")
    controls.request_compact(r.run_id)
    return {"queued": True}


@app.get("/workspace", dependencies=[CurrentUser])
def get_workspace():
    return workspace.snapshot()


@app.post("/workspace/reset", dependencies=[CurrentUser])
def reset_workspace():
    workspace.reset()
    return {"ok": True}


@app.post("/approve")
def approve(d: Decision, user: User = CurrentUser):
    return {"resolved": approvals.resolve(d.call_id, d.allow, owner=user.id)}
