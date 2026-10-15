"""Import this first in a test: gives the app harmless settings and a fresh database, so no real key or server is needed.

Real environment variables beat the .env file, so these always win, and tests never reach a real model.
Set TEST_DATABASE_URL to run the same tests against Postgres. Otherwise each run gets its own SQLite file.
"""
import os
import tempfile

os.environ["OPENAI_API_BASE"] = "https://fake.example.test"
os.environ["OPENAI_API_KEY"] = "fake-key-for-tests"
os.environ["MODEL"] = "fake-model"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp()}/test.db"

from app import db  # noqa: E402

if os.environ.get("TEST_DATABASE_URL"):
    # Start every test file from an empty database. Refuse anything that is not clearly a throwaway one.
    assert os.environ["TEST_DATABASE_URL"].rsplit("/", 1)[-1].endswith("_test"), "TEST_DATABASE_URL must name a database ending in _test"
    from sqlalchemy import text

    with db.get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

db.upgrade()  # build the tables the way production does: by running the migrations
