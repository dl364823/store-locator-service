"""
Shared pytest fixtures.
All tests use an in-memory SQLite database — no PostgreSQL required.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base, get_db
from app.main import app
from app.middleware.rate_limit import limiter
from app.services.auth import create_access_token


# SQLite needs this pragma to enforce FK constraints (off by default)
def _enable_sqlite_fk(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(autouse=True)
def disable_rate_limiting():
    """Disable rate limiting for all tests to prevent cross-test interference.

    Individual tests that explicitly test the 429 behaviour can re-enable it
    by calling `limiter.enabled = True` inside the test body.
    """
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture(scope="function")
def db_engine():
    # StaticPool forces all connections to share one underlying SQLite connection,
    # so data written by db_session is visible to the client's separate sessions.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_fk)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Session:
    factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="function")
def client(db_engine) -> TestClient:
    """FastAPI test client wired to the in-memory SQLite DB."""
    factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)

    def override_get_db():
        session = factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ---------- Auth helpers ----------

@pytest.fixture()
def seeded_db(db_session):
    """Seed roles, permissions, and the three test users into the in-memory DB."""
    from scripts.seed import seed_roles_and_permissions, seed_users
    role_map = seed_roles_and_permissions(db_session)
    seed_users(db_session, role_map)
    db_session.commit()
    return db_session


def auth_headers(user_id: str, email: str, role: str) -> dict:
    """Return Authorization headers for a given user — no DB needed."""
    token = create_access_token(user_id, email, role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers():
    return auth_headers("U001", "admin@test.com", "admin")


@pytest.fixture()
def marketer_headers():
    return auth_headers("U002", "marketer@test.com", "marketer")


@pytest.fixture()
def viewer_headers():
    return auth_headers("U003", "viewer@test.com", "viewer")
