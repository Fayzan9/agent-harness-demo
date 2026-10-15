"""The database: the tables, the connection, and a startup check that the schema is current.

Tables are created by migrations (alembic/versions), never by the app itself.
"""
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import JSON, BigInteger, Column, Float, ForeignKey, Index, Integer, MetaData, String, Table, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from .settings import get_settings

ROOT = Path(__file__).resolve().parents[1]  # backend/
JSONType = JSON().with_variant(JSONB(), "postgresql")

metadata = MetaData()

# One row per chat. The big nested part (context, turns, ...) is one JSON column; what we FILTER by is a real column.
sessions = Table(
    "sessions",
    metadata,
    Column("id", String(16), primary_key=True),
    Column("owner", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("status", String(16), nullable=False),
    Column("created", Float, nullable=False),  # unix seconds
    Column("updated", Float, nullable=False),
    Column("turn_count", Integer, nullable=False),  # so the History list does not have to open every chat
    Column("resume_point", JSONType),
    Column("data", JSONType, nullable=False),
    Index("ix_sessions_owner_updated", "owner", "updated"),
)
# Which chat (and so which user) a run belongs to. "Who owns this run?" is one indexed lookup.
runs = Table(
    "runs",
    metadata,
    Column("run_id", String(16), primary_key=True),
    Column("session_id", String(16), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("owner", Text, nullable=False),
)
# Every event of every run, in the order they happened (id only goes up).
events = Table(
    "events",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("run_id", String(16), nullable=False),
    Column("body", JSONType, nullable=False),
    Index("ix_events_run", "run_id", "id"),
)


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url.get_secret_value()
    if url.startswith("sqlite"):
        path = url.removeprefix("sqlite:///")
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)  # pre_ping: quietly replace a connection the server dropped


def _config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def upgrade() -> None:
    """Apply every migration not yet applied. Same as `alembic upgrade head`."""
    command.upgrade(_config(), "head")


def check_schema() -> None:
    """Startup check: refuse to run against a database that has not been migrated to what this code expects."""
    head = ScriptDirectory.from_config(_config()).get_current_head()
    with get_engine().connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current != head:
        raise RuntimeError(f"The database is at revision {current}, this code needs {head}. Run: uv run alembic upgrade head")
