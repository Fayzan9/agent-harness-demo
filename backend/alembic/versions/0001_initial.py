"""sessions, runs and events

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None

# JSONB on Postgres (indexable, compact), plain JSON elsewhere (SQLite, used for local runs and tests).
JSONType = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("owner", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created", sa.Float, nullable=False),
        sa.Column("updated", sa.Float, nullable=False),
        sa.Column("turn_count", sa.Integer, nullable=False),
        sa.Column("resume_point", JSONType),
        sa.Column("data", JSONType, nullable=False),
    )
    op.create_index("ix_sessions_owner_updated", "sessions", ["owner", "updated"])
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(16), primary_key=True),
        sa.Column("session_id", sa.String(16), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner", sa.Text, nullable=False),
    )
    op.create_index("ix_runs_session", "runs", ["session_id"])
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(16), nullable=False),
        sa.Column("body", JSONType, nullable=False),
    )
    op.create_index("ix_events_run", "events", ["run_id", "id"])


def downgrade():
    op.drop_table("events")
    op.drop_table("runs")
    op.drop_table("sessions")
