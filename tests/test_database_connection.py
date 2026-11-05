import pytest

from app.db.connection import create_database_engine


def test_database_engine_uses_postgresql_and_escapes_password(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test:@/password")
    monkeypatch.setenv("POSTGRES_DB", "test_db")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")

    engine = create_database_engine()
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.username == "test_user"
        assert engine.url.password == "test:@/password"
        assert engine.url.host == "postgres"
        assert engine.url.database == "test_db"
    finally:
        engine.dispose()


def test_database_engine_requires_password(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.setenv("POSTGRES_DB", "test_db")

    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        create_database_engine()
