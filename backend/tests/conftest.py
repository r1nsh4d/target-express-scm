"""Test fixtures that run the real app against a real database.

Everything else in this suite tests pure functions, which is where most of the
business rules live. But a pure-function test cannot catch a wrong table name, a
route that was never registered, or a response model that will not serialise
what the ORM hands it — and all three have actually shipped broken on this
project.

So this builds a real FastAPI TestClient over a throwaway SQLite database.

Two things make that work:

  * `app.db.session` builds its engine at import time from DATABASE_URL, so the
    variable is set HERE, at module import, before anything pulls the app in.
    Setting it inside a fixture is too late: the first test binds the engine and
    every later one quietly shares that first database.

  * One database for the whole run, with rows deleted between tests. Rebinding
    the engine per test would mean reloading half the application, and a
    half-reloaded SQLAlchemy registry is its own source of mystery failures.

SQLite rather than Postgres, because the suite has to run on a laptop with no
containers. Tables using Postgres-only column types (JSONB) are simply not
created unless a test asks for them.
"""

from __future__ import annotations

import os
import tempfile
import uuid
import uuid as _uuid
from pathlib import Path

import pytest

# Before any app import. Order matters here, which is why it is not in a fixture.
_DB_PATH = Path(tempfile.gettempdir()) / f"tx-test-{uuid.uuid4().hex}.sqlite"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ.setdefault("SECRET_KEY", "x" * 48)


# Postgres-only column types, taught to SQLite so the real schema can be
# created in a test. JSONB becomes JSON, which SQLite stores as text and
# SQLAlchemy serialises identically — the application never does a jsonb
# operator query, it reads and writes whole documents.
#
# Without this, any test touching a table with an audit or snapshot column
# fails at CREATE TABLE, which quietly pushes people towards testing pure
# functions only. That is how a project ends up with 244 unit tests and two
# endpoints covered.
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.dialects.postgresql import UUID as PGUUID  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - dialect glue
    return "JSON"


# UUID columns, likewise. The application passes string ids straight from the
# URL into `db.get(Model, id)`, which psycopg accepts against a uuid column and
# SQLite does not — it reaches for `.hex` on a str and dies.
#
# This is test glue, not a product change: it teaches SQLite to store UUIDs as
# text and to accept either a str or a UUID on the way in. The alternative was
# to leave every endpoint that takes an id in its path untestable without a
# Postgres container, which is most of them.
@compiles(PGUUID, "sqlite")
def _uuid_on_sqlite(type_, compiler, **kw):  # pragma: no cover - dialect glue
    return "CHAR(36)"


_orig_bind = PGUUID.bind_processor
_orig_result = PGUUID.result_processor


def _bind_processor(self, dialect):  # pragma: no cover - dialect glue
    if dialect.name != "sqlite":
        return _orig_bind(self, dialect)

    def process(value):
        return None if value is None else str(value)

    return process


def _result_processor(self, dialect, coltype):  # pragma: no cover - dialect glue
    if dialect.name != "sqlite":
        return _orig_result(self, dialect, coltype)

    def process(value):
        if value is None:
            return None
        return _uuid.UUID(str(value)) if getattr(self, "as_uuid", True) else str(value)

    return process


PGUUID.bind_processor = _bind_processor
PGUUID.result_processor = _result_processor


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "tables(*names): create these tables before the test runs"
    )


def pytest_unconfigure(config: pytest.Config) -> None:
    # Windows keeps a handle on the sqlite file until the engine is collected,
    # so a failure to delete it is noise, not a problem. It lives in the temp
    # directory either way.
    try:
        _DB_PATH.unlink(missing_ok=True)
    except OSError:
        pass


@pytest.fixture()
def client(request):
    """A TestClient with only the tables the test asks for.

    Tables are named explicitly rather than calling `Base.metadata.create_all`,
    because several use JSONB, which SQLite cannot render:

        pytestmark = pytest.mark.tables("users", "enquiries")
    """
    from fastapi.testclient import TestClient

    from app.db.base import Base
    from app.db.session import engine
    from app.main import app

    marker = request.node.get_closest_marker("tables")
    wanted = marker.args if marker else ()

    for name in wanted:
        Base.metadata.tables[name].create(engine, checkfirst=True)

    # Empty them before the test rather than after, so a failing test leaves its
    # rows behind to be inspected.
    with engine.begin() as conn:
        for name in reversed(wanted):
            conn.exec_driver_sql(f"DELETE FROM {name}")

    # The in-process rate limiter is module state and would otherwise carry
    # counts from one test into the next.
    from app.api.routes.public import _hits

    _hits.clear()

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin_token(client):
    """A signed-in super admin, created directly rather than through the API.

    The user-creation endpoint needs an admin to call it, so bootstrapping
    through HTTP would be circular.
    """
    from app.core.security import create_access_token, hash_password
    from app.db.session import SessionLocal
    from app.models.enums import UserRole
    from app.models.user import User

    db = SessionLocal()
    try:
        user = User(
            full_name="Test Admin",
            phone="9000000099",
            role=UserRole.SUPER_ADMIN,
            hashed_password=hash_password("test-password"),
            is_active=True,
            can_view_earnings=True,
        )
        db.add(user)
        db.commit()
        return create_access_token(str(user.id), user.role)
    finally:
        db.close()


@pytest.fixture()
def auth(admin_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}
