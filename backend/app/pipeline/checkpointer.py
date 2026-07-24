"""Shared Postgres-backed LangGraph checkpointer.

The checkpointer owns its own tables (checkpoints, checkpoint_blobs,
checkpoint_writes, checkpoint_migrations) created via PostgresSaver.setup()
-- these are not SQLAlchemy models and Alembic is configured to ignore them
(see alembic/env.py's include_object filter). Checkpointed state is what
powers the pipeline run trace endpoint: every node transition is persisted,
so a run can be inspected step by step after the fact.

A fresh connection is opened per call rather than cached as a long-lived
singleton -- PostgresSaver.from_conn_string() is a generator-based context
manager, and manually calling __enter__() on it without the matching
__exit__() lifecycle leaves the underlying psycopg connection in a state
that closes unexpectedly. Opening one per pipeline run/trace call is simple,
correct, and cheap enough for this prototype's request volume.

Known limitation (see README): this checkpointer preserves state across a
process restart, but is not full durable execution -- see SECURITY.md and
the README for what a production deployment would still need (e.g. the
Temporal LangGraph plugin).
"""

from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver

from app.config import get_settings

_setup_done = False


def _to_psycopg_dsn(sqlalchemy_url: str) -> str:
    # settings.database_url is a SQLAlchemy URL (postgresql+psycopg://...);
    # PostgresSaver wants a plain libpq DSN (postgresql://...).
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://")


@contextmanager
def checkpointer_context():
    global _setup_done
    settings = get_settings()
    dsn = _to_psycopg_dsn(settings.database_url)
    with PostgresSaver.from_conn_string(dsn) as saver:
        if not _setup_done:
            saver.setup()
            _setup_done = True
        yield saver
