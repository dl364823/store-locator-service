"""
Shared pytest fixtures.
All tests use an in-memory SQLite database — no PostgreSQL required.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from app.db.base import Base, get_db
from app.main import app

# SQLite needs this pragma to enforce FK constraints (off by default)
def _enable_sqlite_fk(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
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
