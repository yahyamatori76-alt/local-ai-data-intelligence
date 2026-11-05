import os

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoints_are_public_and_database_is_postgresql():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/health/db").json() == {
            "status": "ok",
            "database": "postgresql",
        }
        assert client.get("/health/ollama").status_code == 200


def test_protected_endpoints_require_authentication():
    with TestClient(app) as client:
        response = client.get("/sources")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_admin_can_authenticate_and_read_sources():
    username = os.environ["APP_ADMIN_USERNAME"]
    password = os.environ["APP_ADMIN_PASSWORD"]
    with TestClient(app) as client:
        response = client.get("/sources", auth=(username, password))

    assert response.status_code == 200
    assert {"population", "marketplace", "system_log"}.issubset(
        {source["source_code"] for source in response.json()}
    )
    with TestClient(app) as client:
        assert (
            client.get("/analysis/results", auth=(username, password)).status_code
            == 200
        )
        assert client.get(
            "/analysis/results?review_status=unreviewed",
            auth=(username, password),
        ).status_code == 200
