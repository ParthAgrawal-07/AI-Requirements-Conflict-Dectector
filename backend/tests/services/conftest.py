"""Fixtures for services that work on stored documents."""

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models import (
    Document,
    DocumentFormat,
    DocumentStatus,
    ImportMode,
    Project,
    User,
    Workspace,
)
from app.services.storage import LocalFileStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "uploads")


@pytest.fixture
def make_stored_document(
    db_session: Session,
    workspace: Workspace,
    project: Project,
    user: User,
    storage: LocalFileStorage,
) -> Callable[..., Document]:
    """A queued document whose file really is on disk, as the upload endpoint would leave it."""

    def build(
        data: bytes,
        *,
        extension: str = ".docx",
        status: DocumentStatus = DocumentStatus.QUEUED,
        write_file: bool = True,
        import_mode: ImportMode = ImportMode.PROPOSALS,
        stakeholder_group: str | None = None,
    ) -> Document:
        document = Document(
            workspace_id=workspace.id,
            project_id=project.id,
            uploaded_by=user.id,
            filename=f"srs{extension}",
            format=DocumentFormat(extension.lstrip(".")),
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            storage_path="",
            status=status,
            import_mode=import_mode,
            stakeholder_group=stakeholder_group,
        )
        db_session.add(document)
        db_session.flush()
        document.storage_path = f"{workspace.id}/{document.id}{extension}"
        if write_file:
            path = storage.resolve(document.storage_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        db_session.commit()
        return document

    return build
