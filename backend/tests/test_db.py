"""Database checks: migrations, saving, ownership lookups, and hostile input. Uses SQLite unless TEST_DATABASE_URL is set.

Run from backend/:  PYTHONPATH=. uv run python tests/test_db.py
"""
import tempfile

import fakeenv  # noqa: F401
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text

from app import db, runs, sessions
from app.events import Event
from app.settings import Settings

failed = []


def check(name, ok, extra=""):
    print("PASS" if ok else "FAIL", name, extra)
    if not ok:
        failed.append(name)


# -- migrations -------------------------------------------------------------------------------
check("migration created the tables", {"sessions", "runs", "events"} <= set(inspect(db.get_engine()).get_table_names()))
db.upgrade()
check("running migrations twice is harmless", True)
db.check_schema()
check("startup check passes on a migrated database", True)

real = db.get_engine
empty = create_engine(f"sqlite:///{tempfile.mkdtemp()}/empty.db")
db.get_engine = lambda: empty
try:
    db.check_schema()
    refused = False
except RuntimeError as e:
    refused = "alembic upgrade head" in str(e)
db.get_engine = real
check("startup check refuses an un-migrated database and says how to fix it", refused)

# -- saving and loading -----------------------------------------------------------------------
nasty = "x'); DROP TABLE sessions; --"
s = sessions.create("memory", nasty, "alice")
s.ctx.add({"role": "user", "content": "héllo 👋 'quoted' \"double\""})
s.turns.append({"run_id": "r-1", "task": "t"})
s.save()
back = sessions.load(s.id)
check("a chat round-trips exactly (SQL in the title is just text)", back.title == nasty[:60] and back.ctx.messages == s.ctx.messages and back.owner == "alice")
check("the tables survived the hostile title", "sessions" in inspect(db.get_engine()).get_table_names())
s.title = "renamed"
s.save()
check("saving again updates the same row", sessions.load(s.id).title == "renamed" and len(sessions.list_all("alice")) == 1)

# -- ownership is a query, not a scan ---------------------------------------------------------
check("another owner cannot load it", sessions.load(s.id, "bob") is None and sessions.load(s.id, "alice") is not None)
runs.register("r-1", s.id, "alice")
check("run ownership lookup", sessions.owns_run("alice", "r-1") and not sessions.owns_run("bob", "r-1") and not sessions.owns_run("alice", "nope"))
b = sessions.create("", "bob's", "bob")
b.save()
check("History lists only your own, newest first", [x["id"] for x in sessions.list_all("alice")] == [s.id] and [x["id"] for x in sessions.list_all("bob")] == [b.id])
row = sessions.list_all("alice")[0]
check("History rows are light: no chat contents in them", set(row) == {"id", "title", "created", "updated", "status", "turns", "interrupted_at"} and row["turns"] == 1)

# -- stale "running" chats are reported as interrupted ----------------------------------------
s.status = "running"
s.save()
check("a chat left 'running' with no process is shown as interrupted", sessions.load(s.id).status == "interrupted" and sessions.list_all("alice")[0]["status"] == "interrupted")

# -- events -----------------------------------------------------------------------------------
for i in range(5):
    runs.append("r-1", Event("note", i, {"n": i}))
runs.append("r-2", Event("note", 0, {"n": "other run"}))
got = runs.load("r-1")
check("events come back in order, only for their run", [e["data"]["n"] for e in got] == [0, 1, 2, 3, 4] and runs.load("nope") == [])
check("an event keeps its shape", set(got[0]) >= {"type", "step", "data", "ts", "agent"})

# -- settings guard ----------------------------------------------------------------------------
def refused_cfg(**kw):
    try:
        Settings(_env_file=None, openai_api_base="x", openai_api_key="k", model="m", database_url=kw.pop("database_url", "sqlite:///x.db"), **kw)
    except ValidationError:
        return True
    return False


check("production must use Postgres", refused_cfg(environment="production", auth_mode="jwt", auth_audience="a", allowed_emails=["a@b.c"]))
check("production with Postgres is accepted", not refused_cfg(environment="production", auth_mode="jwt", auth_audience="a", allowed_emails=["a@b.c"], database_url="postgresql+psycopg://u:p@h/db"))
check("the database password never prints", "p@ss" not in repr(Settings(_env_file=None, openai_api_base="x", openai_api_key="k", model="m", database_url="postgresql+psycopg://u:p@ss@h/db")))

print("\nALL PASSED" if not failed else f"\nFAILED: {failed}")
raise SystemExit(1 if failed else 0)
