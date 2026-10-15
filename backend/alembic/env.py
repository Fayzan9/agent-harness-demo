from alembic import context

from app.db import get_engine, metadata

# Runs a migration against the same database the app uses (DATABASE_URL), so there is one place to set it.
with get_engine().connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
