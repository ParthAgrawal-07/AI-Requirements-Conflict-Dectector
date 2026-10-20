"""MaxBodySizeMiddleware: oversized bodies are refused before they are read or spooled to disk."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import install_exception_handlers
from app.core.middleware import BodyLimit, MaxBodySizeMiddleware, _declared_length
from app.main import create_app
from app.models import Document, Project
from app.services.storage import LocalFileStorage, get_storage
from tests.api.conftest import documents_url, stored_files
from tests.factories import make_pdf

LIMIT = 10_000
BOUNDARY = "testboundary"


def multipart_prefix(filename: str = "a.pdf") -> bytes:
    return (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()


MULTIPART_SUFFIX = f"\r\n--{BOUNDARY}--\r\n".encode()
MULTIPART_HEADERS = {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}


def chunked(payload: bytes, chunk: int = 1000) -> Iterator[bytes]:
    """Yielding from a generator makes the client send Transfer-Encoding: chunked (no Content-Length)."""
    yield multipart_prefix()
    for start in range(0, len(payload), chunk):
        yield payload[start : start + chunk]
    yield MULTIPART_SUFFIX


@pytest.fixture
def reached() -> list[int]:
    return []


@pytest.fixture
def mini_client(reached: list[int]) -> Iterator[TestClient]:
    app = FastAPI()
    install_exception_handlers(app)
    app.add_middleware(
        MaxBodySizeMiddleware,
        limits={
            (("POST", "/upload")): BodyLimit(max_bytes=LIMIT, message="Too big for this test.")
        },
    )

    @app.post("/upload")
    def upload(file: UploadFile = File(...)) -> dict[str, int]:  # noqa: B008
        size = len(file.file.read())
        reached.append(size)
        return {"size": size}

    @app.post("/unguarded")
    def unguarded(file: UploadFile = File(...)) -> dict[str, int]:  # noqa: B008
        return {"size": len(file.file.read())}

    with TestClient(app) as client:
        yield client


@pytest.fixture
def pattern_client() -> Iterator[TestClient]:
    """Limits keyed by a path *pattern*, as needed for /projects/{id}/documents."""
    import re

    app = FastAPI()
    install_exception_handlers(app)
    app.add_middleware(
        MaxBodySizeMiddleware,
        limits={
            ("POST", re.compile(r"/projects/[^/]+/documents")): BodyLimit(
                max_bytes=LIMIT, message="Too big for this test."
            )
        },
    )

    @app.post("/projects/{project_id}/documents")
    def documents(project_id: str, file: UploadFile = File(...)) -> dict[str, int]:  # noqa: B008
        return {"size": len(file.file.read())}

    @app.post("/projects/{project_id}/documents/extra")
    def extra(project_id: str, file: UploadFile = File(...)) -> dict[str, int]:  # noqa: B008
        return {"size": len(file.file.read())}

    @app.get("/projects/{project_id}/documents")
    def listing(project_id: str) -> dict[str, str]:
        return {"project": project_id}

    with TestClient(app) as client:
        yield client


class TestPathPatterns:
    def test_a_matching_path_is_guarded(self, pattern_client: TestClient) -> None:
        response = pattern_client.post(
            f"/projects/{uuid.uuid4()}/documents", files={"file": ("a.bin", b"x" * (LIMIT + 100))}
        )
        assert response.status_code == 413
        assert response.json()["error"]["message"] == "Too big for this test."

    def test_a_matching_path_within_the_limit_passes(self, pattern_client: TestClient) -> None:
        response = pattern_client.post(
            f"/projects/{uuid.uuid4()}/documents", files={"file": ("a.bin", b"x" * 100)}
        )
        assert response.status_code == 200

    def test_the_pattern_must_match_the_whole_path_and_the_method(
        self, pattern_client: TestClient
    ) -> None:
        big = {"file": ("a.bin", b"x" * (LIMIT + 100))}
        assert (
            pattern_client.post(f"/projects/{uuid.uuid4()}/documents/extra", files=big).status_code
            == 200
        )
        assert pattern_client.get(f"/projects/{uuid.uuid4()}/documents").status_code == 200


class TestMiddleware:
    def test_body_within_the_limit_passes_through(
        self, mini_client: TestClient, reached: list[int]
    ) -> None:
        response = mini_client.post("/upload", files={"file": ("a.bin", b"x" * 5000)})
        assert response.status_code == 200
        assert reached == [5000]

    def test_declared_content_length_over_the_limit_is_refused_without_reading_the_body(
        self, mini_client: TestClient, reached: list[int]
    ) -> None:
        response = mini_client.post("/upload", files={"file": ("a.bin", b"x" * (LIMIT + 1))})

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"
        assert response.json()["error"]["message"] == "Too big for this test."
        assert reached == []  # the route never ran

    def test_chunked_body_without_content_length_is_cut_off_while_streaming(
        self, mini_client: TestClient, reached: list[int]
    ) -> None:
        """No Content-Length to check up front: the bytes are counted as they arrive."""
        response = mini_client.post(
            "/upload", content=chunked(b"x" * 50_000), headers=MULTIPART_HEADERS
        )

        assert response.status_code == 413  # not the generic 400 FastAPI uses for body-parse errors
        assert response.json()["error"]["code"] == "payload_too_large"
        assert reached == []

    def test_chunked_body_within_the_limit_passes(
        self, mini_client: TestClient, reached: list[int]
    ) -> None:
        response = mini_client.post(
            "/upload", content=chunked(b"x" * 3000), headers=MULTIPART_HEADERS
        )
        assert response.status_code == 200
        assert reached == [3000]

    def test_only_listed_routes_are_guarded(self, mini_client: TestClient) -> None:
        response = mini_client.post("/unguarded", files={"file": ("a.bin", b"x" * (LIMIT * 5))})
        assert response.status_code == 200

    def test_other_methods_on_a_guarded_path_are_not_limited(self, mini_client: TestClient) -> None:
        assert mini_client.get("/upload").status_code == 405  # reaches the router, not a 413

    @pytest.mark.parametrize(
        ("headers", "expected"),
        [
            ([(b"content-length", b"123")], 123),
            ([(b"content-length", b"abc")], None),
            ([], None),
            ([(b"x-other", b"1"), (b"content-length", b"7")], 7),
        ],
    )
    def test_declared_length_parsing(
        self, headers: list[tuple[bytes, bytes]], expected: int | None
    ) -> None:
        assert _declared_length({"headers": headers}) == expected  # type: ignore[arg-type]


@pytest.fixture
def real_app_client(
    monkeypatch: pytest.MonkeyPatch, db_session: Session, tmp_path: pytest.TempPathFactory
) -> Iterator[tuple[TestClient, LocalFileStorage]]:
    """The real application, built with a 1 MB upload limit."""
    monkeypatch.setattr(get_settings(), "max_upload_size_mb", 1)
    app = create_app()
    storage = LocalFileStorage(tmp_path / "uploads")  # type: ignore[operator]
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as client:
        yield client, storage


class TestOnTheRealApp:
    def test_huge_upload_is_refused_up_front_and_nothing_touches_the_database_or_disk(
        self,
        real_app_client: tuple[TestClient, LocalFileStorage],
        auth_headers: dict[str, str],
        project: Project,
        db_session: Session,
    ) -> None:
        client, storage = real_app_client

        response = client.post(
            documents_url(project),
            files={"file": ("big.pdf", b"%PDF-" + b"x" * (3 * 1024 * 1024))},
            headers=auth_headers,
        )

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"
        assert "1 MB" in response.json()["error"]["message"]
        assert db_session.query(Document).count() == 0
        assert stored_files(storage) == []

    def test_chunked_huge_upload_is_refused_too(
        self,
        real_app_client: tuple[TestClient, LocalFileStorage],
        auth_headers: dict[str, str],
        project: Project,
    ) -> None:
        client, storage = real_app_client
        response = client.post(
            documents_url(project),
            content=chunked(b"x" * (2 * 1024 * 1024), chunk=64 * 1024),
            headers={**MULTIPART_HEADERS, **auth_headers},
        )
        assert response.status_code == 413
        assert stored_files(storage) == []

    def test_the_413_carries_cors_headers_so_the_browser_can_read_it(
        self,
        real_app_client: tuple[TestClient, LocalFileStorage],
        auth_headers: dict[str, str],
        project: Project,
    ) -> None:
        client, _ = real_app_client
        response = client.post(
            documents_url(project),
            files={"file": ("big.pdf", b"x" * (2 * 1024 * 1024))},
            headers={**auth_headers, "Origin": "http://localhost:5173"},
        )
        assert response.status_code == 413
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert response.headers["X-Request-ID"]

    def test_a_normal_upload_still_works_with_the_guard_in_place(
        self,
        real_app_client: tuple[TestClient, LocalFileStorage],
        auth_headers: dict[str, str],
        project: Project,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.services import documents as document_service

        monkeypatch.setattr(document_service, "dispatch_processing", lambda _id: "t")
        client, _ = real_app_client
        response = client.post(
            documents_url(project), files={"file": ("a.pdf", make_pdf())}, headers=auth_headers
        )
        assert response.status_code == 202
        assert uuid.UUID(response.json()["document_id"])
