import os
import uuid

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


def test_local_documents_are_indexed_searchable_and_used_by_chat(monkeypatch):
    from sqlalchemy import text

    from app.db.repositories import get_engine

    username = os.environ["APP_ADMIN_USERNAME"]
    password = os.environ["APP_ADMIN_PASSWORD"]
    admin = (username, password)
    nik = f"{uuid.uuid4().int % 10**16:016d}"
    padded_nik = f"9{nik}"
    document_ids = []
    viewer_name = None
    monkeypatch.setattr(
        "app.api.routes_documents.answer_from_documents",
        lambda base_url, model, query, matches: "NIK dan nama ditemukan. [1]",
    )
    try:
        with TestClient(app) as client:
            exact = client.post(
                "/documents",
                auth=admin,
                files={
                    "file": (
                        f"identity-{uuid.uuid4().hex}.txt",
                        f"Nama: Siti Contoh\nNIK: {nik}\n".encode(),
                        "text/plain",
                    )
                },
            )
            assert exact.status_code == 201, exact.text
            document_ids.append(exact.json()["document_id"])

            formatted = client.post(
                "/documents",
                auth=admin,
                files={
                    "file": (
                        f"formatted-{uuid.uuid4().hex}.txt",
                        f"Catatan NIK {nik[:4]}-{nik[4:8]}-{nik[8:12]}-{nik[12:]}\n".encode(),
                        "text/plain",
                    )
                },
            )
            assert formatted.status_code == 201, formatted.text
            document_ids.append(formatted.json()["document_id"])

            near = client.post(
                "/documents",
                auth=admin,
                files={
                    "file": (
                        f"near-{uuid.uuid4().hex}.txt",
                        f"Catatan: NIK {padded_nik}\n".encode(),
                        "text/plain",
                    )
                },
            )
            assert near.status_code == 201, near.text
            document_ids.append(near.json()["document_id"])

            search = client.post(
                "/documents/search",
                auth=admin,
                json={"query": nik, "ask_ai": False},
            )
            assert search.status_code == 200, search.text
            assert search.json()["query_type"] == "nik"
            assert search.json()["result_count"] == 2
            assert {
                match["document_id"] for match in search.json()["matches"]
            } == set(document_ids[:2])

            chat = client.post(
                "/chat",
                auth=admin,
                json={
                    "question": (
                        f"Cari NIK {nik[:4]}-{nik[4:8]}-{nik[8:12]}-{nik[12:]} "
                        "dan analisis dokumennya"
                    )
                },
            )
            assert chat.status_code == 200, chat.text
            assert chat.json()["context"] == "local_document_rag"
            assert document_ids[0] in {
                source["document_id"] for source in chat.json()["sources"]
            }

            viewer_name = f"document-viewer-{uuid.uuid4().hex[:8]}"
            viewer_password = f"{uuid.uuid4().hex}Aa9!"
            viewer = client.post(
                "/auth/users",
                auth=admin,
                json={
                    "username": viewer_name,
                    "password": viewer_password,
                    "role": "viewer",
                },
            )
            assert viewer.status_code == 201, viewer.text
            viewer_credentials = (viewer_name, viewer_password)
            assert client.post(
                "/documents/search",
                auth=viewer_credentials,
                json={"query": nik, "ask_ai": False},
            ).status_code == 403
            assert client.post(
                "/chat",
                auth=viewer_credentials,
                json={"question": f"Cari NIK {nik}"},
            ).status_code == 403
    finally:
        if document_ids or viewer_name:
            with get_engine().begin() as connection:
                if document_ids:
                    connection.execute(
                        text(
                            "DELETE FROM local_documents WHERE id::text = ANY(:ids)"
                        ),
                        {"ids": document_ids},
                    )
                if viewer_name:
                    connection.execute(
                        text(
                            """
                            DELETE FROM analysis_audit
                            WHERE user_id = (
                                SELECT id FROM app_users WHERE username = :username
                            )
                            """
                        ),
                        {"username": viewer_name},
                    )
                    connection.execute(
                        text("DELETE FROM app_users WHERE username = :username"),
                        {"username": viewer_name},
                    )
