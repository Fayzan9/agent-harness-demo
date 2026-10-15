import time
import uuid

from sqlalchemy import insert, select, update

from . import db
from .context import Context

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
        """Write the whole chat to the database (a row per chat). Also what the History list reads."""
        self.updated = time.time()
        values = {
            "owner": self.owner,
            "title": self.title,
            "status": self.status,
            "created": self.created,
            "updated": self.updated,
            "turn_count": len(self.turns),
            "resume_point": self.resume_point(),
            "data": self.to_dict(),
        }
        with db.get_engine().begin() as conn:  # one transaction: all of it is saved, or none
            if conn.execute(update(db.sessions).where(db.sessions.c.id == self.id).values(**values)).rowcount == 0:
                conn.execute(insert(db.sessions).values(id=self.id, **values))

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
        return self.resume_point() if self.status == "interrupted" else None

    def resume_point(self) -> dict | None:
        """What was happening to a tool call, if anything. Only meaningful once the chat is interrupted."""
        if not (self.in_flight or self.pending_calls):
            return None
        if self.in_flight:
            return {"tool": self.in_flight["tool"], "state": self.in_flight["state"]}
        return {"tool": self.pending_calls[0]["name"], "state": "not started"}


def create(memory: str, title: str, owner: str = LOCAL_USER) -> Session:
    return Session(uuid.uuid4().hex[:8], memory, title[:60], owner)


def load(session_id: str, owner: str | None = None) -> Session | None:
    """The chat, or None. With an owner, someone else's chat also gives None, so it looks like it does not exist."""
    with db.get_engine().connect() as conn:
        row = conn.execute(select(db.sessions.c.owner, db.sessions.c.data).where(db.sessions.c.id == session_id)).first()
    if not row or (owner is not None and row.owner != owner):
        return None
    s = Session.from_dict(row.data)
    if s.status == "running" and s.id not in ACTIVE:
        s.status = "interrupted"  # it said running, but nothing is running it: the process died
    return s


def list_all(owner: str | None = None) -> list[dict]:
    """Short rows for the History list. Reads columns only, never the big JSON of each chat."""
    q = select(db.sessions).with_only_columns(
        db.sessions.c.id, db.sessions.c.title, db.sessions.c.created, db.sessions.c.updated,
        db.sessions.c.status, db.sessions.c.turn_count, db.sessions.c.resume_point,
    ).order_by(db.sessions.c.updated.desc())
    if owner is not None:
        q = q.where(db.sessions.c.owner == owner)
    with db.get_engine().connect() as conn:
        rows = conn.execute(q).all()
    out = []
    for r in rows:
        status = "interrupted" if r.status == "running" and r.id not in ACTIVE else r.status
        out.append(
            {
                "id": r.id,
                "title": r.title,
                "created": r.created,
                "updated": r.updated,
                "status": status,
                "turns": r.turn_count,
                "interrupted_at": r.resume_point if status == "interrupted" else None,
            }
        )
    return out


def owns_run(owner: str, run_id: str) -> bool:
    """Did this user start this run? One indexed lookup."""
    with db.get_engine().connect() as conn:
        return conn.execute(select(db.runs.c.run_id).where(db.runs.c.run_id == run_id, db.runs.c.owner == owner)).first() is not None
