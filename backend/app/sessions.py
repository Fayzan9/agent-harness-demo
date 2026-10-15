import json
import os
import time
import uuid
from pathlib import Path

from .context import Context

SESSIONS_DIR = Path(__file__).resolve().parents[1] / "sessions"
LOCAL_USER = "local-user"  # the one user when login is off
ACTIVE: set[str] = set()  # sessions with a run in progress right now, in this process


class Session:
    """A conversation: the context plus enough bookkeeping to resume it after a crash."""

    def __init__(self, id: str, memory: str = "", title: str = "", owner: str = LOCAL_USER):
        self.id = id
        self.owner = owner  # the user id this chat belongs to; nobody else may see it
        self.title = title
        self.created = time.time()
        self.updated = self.created
        self.status = "idle"  # idle | running | interrupted
        self.ctx = Context(memory)
        self.turns: list[dict] = []  # {run_id, task}, one per user turn
        self.pending_calls: list[dict] = []  # tool calls the model asked for that have no result yet
        self.in_flight: dict | None = None  # {call_id, tool, state}: what was happening to one call
        self.setup: dict = {}  # tools, gates and hooks of the latest turn, so a reopened chat can use the same ones

    # -- saving -----------------------------------------------------------------
    def save(self):
        self.updated = time.time()
        SESSIONS_DIR.mkdir(exist_ok=True)
        path = SESSIONS_DIR / f"{self.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict()))
        os.replace(tmp, path)  # all or nothing, so a crash mid-write cannot leave half a file

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner": self.owner,
            "title": self.title,
            "created": self.created,
            "updated": self.updated,
            "status": self.status,
            "ctx": self.ctx.to_dict(),
            "turns": self.turns,
            "pending_calls": self.pending_calls,
            "in_flight": self.in_flight,
            "setup": self.setup,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        s = cls(data["id"], title=data.get("title", ""), owner=data.get("owner", LOCAL_USER))
        s.created = data.get("created", s.created)
        s.updated = data.get("updated", s.updated)
        s.status = data.get("status", "idle")
        s.ctx = Context.from_dict(data.get("ctx", {}))
        s.turns = data.get("turns", [])
        s.pending_calls = data.get("pending_calls", [])
        s.in_flight = data.get("in_flight")
        s.setup = data.get("setup", {})
        return s

    # -- checkpoints the loop takes -----------------------------------------------
    def set_status(self, status: str):
        self.status = status
        self.save()

    def begin_calls(self, calls: list[dict]):
        """The model just asked for these tools. Remember them until each has a result."""
        self.pending_calls = [dict(c) for c in calls]
        self.save()

    def flight(self, call_id: str, tool: str, state: str):
        self.in_flight = {"call_id": call_id, "tool": tool, "state": state}
        self.save()

    def finish_call(self, call_id: str):
        self.pending_calls = [c for c in self.pending_calls if c["id"] != call_id]
        self.in_flight = None
        self.save()

    def close_pending(self, reason: str):
        """Give every unanswered tool call a result, so the history stays valid for the model."""
        for call in self.pending_calls:
            self.ctx.add({"role": "tool", "tool_call_id": call["id"], "content": f"Not run: {reason}"})
        self.pending_calls = []
        self.in_flight = None
        self.save()

    def interrupted_at(self) -> dict | None:
        if self.status != "interrupted" or not (self.in_flight or self.pending_calls):
            return None
        if self.in_flight:
            return {"tool": self.in_flight["tool"], "state": self.in_flight["state"]}
        return {"tool": self.pending_calls[0]["name"], "state": "not started"}


def create(memory: str, title: str, owner: str = LOCAL_USER) -> Session:
    return Session(uuid.uuid4().hex[:8], memory, title[:60], owner)


def load(session_id: str, owner: str | None = None) -> Session | None:
    """The chat, or None. With an owner, someone else's chat also gives None, so it looks like it does not exist."""
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    s = Session.from_dict(json.loads(path.read_text()))
    if owner is not None and s.owner != owner:
        return None
    if s.status == "running" and s.id not in ACTIVE:
        s.status = "interrupted"  # it said running, but nothing is running it: the process died
    return s


def list_all(owner: str | None = None) -> list[dict]:
    if not SESSIONS_DIR.exists():
        return []
    out = []
    for path in SESSIONS_DIR.glob("*.json"):
        s = load(path.stem, owner)
        if s:
            out.append(
                {
                    "id": s.id,
                    "title": s.title,
                    "created": s.created,
                    "updated": s.updated,
                    "status": s.status,
                    "turns": len(s.turns),
                    "interrupted_at": s.interrupted_at(),
                }
            )
    return sorted(out, key=lambda x: x["updated"], reverse=True)


def owns_run(owner: str, run_id: str) -> bool:
    """Did this user start this run? A run is listed in the turns of the chat it belongs to."""
    if not SESSIONS_DIR.exists():
        return False
    for path in SESSIONS_DIR.glob("*.json"):
        s = load(path.stem, owner)
        if s and any(t.get("run_id") == run_id for t in s.turns):
            return True
    return False
