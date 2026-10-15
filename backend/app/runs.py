import json

from sqlalchemy import insert, select

from . import db
from .events import Event


def register(run_id: str, session_id: str, owner: str):
    """Record which chat (and user) a run belongs to. The chat must already be saved."""
    with db.get_engine().begin() as conn:
        conn.execute(insert(db.runs).values(run_id=run_id, session_id=session_id, owner=owner))


def append(run_id: str, event: Event):
    """Keep every event of a run, one row each."""
    with db.get_engine().begin() as conn:
        conn.execute(insert(db.events).values(run_id=run_id, body=json.loads(event.to_json())))


def load(run_id: str) -> list[dict]:
    """Read back every event of a saved run, in the order they happened."""
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.events.c.body).where(db.events.c.run_id == run_id).order_by(db.events.c.id)).all()
    return [r.body for r in rows]
