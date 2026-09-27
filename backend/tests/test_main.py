"""Tests for health, auth stubs, and document upload endpoint."""


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── Auth Tests ─────────────────────────────────────────────


def test_register_success(client):
    response = client.post(
        "/auth/register",
        json={"username": "alice", "password": "secret123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "alice"
    assert "msg" in data


def test_login_returns_token(client):
    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_me_returns_user(client):
    response = client.get("/auth/me")
    assert response.status_code == 200
    assert "username" in response.json()


# ── Upload Tests ───────────────────────────────────────────


def test_upload_rejects_invalid_extension(client):
    files = {"file": ("report.txt", b"some content", "text/plain")}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 400
    assert "Invalid file type" in response.json()["detail"]


def test_upload_accepts_pdf(client):
    files = {"file": ("spec.pdf", b"fake pdf content", "application/pdf")}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert data["doc_id"] is not None
    assert "Document uploaded successfully" in data["msg"]


def test_upload_accepts_docx(client):
    files = {
        "file": (
            "spec.docx",
            b"fake docx content",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 201


def test_upload_rejects_missing_filename(client):
    files = {"file": ("", b"some content", "application/pdf")}
    response = client.post("/documents/upload", files=files)
    assert response.status_code == 400
