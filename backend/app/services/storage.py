"""File storage for uploaded documents (Role 5 — US-01).

``LocalFileStorage`` keeps files on a filesystem path shared by the API and the Celery worker
(the ``uploads`` volume in docker-compose.yml). Everything outside this module talks in
**storage keys** (``"<workspace_id>/<document_id>.pdf"``) rather than absolute paths, so a
different backend (S3-compatible object storage — needed on hosts with ephemeral disks such as
Railway/Render, Sprint 5) can replace this class without touching callers.

Uploads are written in two phases so a failed request never leaves a half-written file where
the worker could find it:

1. ``stage``  — stream the upload into ``<root>/.staging/`` while hashing it and enforcing the
   size limit *as bytes arrive* (never trusting a client-declared size).
2. ``commit`` — atomically ``os.replace`` the staged file onto its final key, only after the
   content has been validated and the database row exists.
"""

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
STAGING_DIR = ".staging"


class UploadTooLargeError(Exception):
    """The stream exceeded ``max_bytes``. Raised while reading, so at most one chunk over."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(f"Upload exceeds {max_bytes} bytes")
        self.max_bytes = max_bytes


class InvalidStorageKeyError(ValueError):
    """A storage key resolved outside the storage root (path traversal attempt or bug)."""


@dataclass(frozen=True)
class StagedFile:
    path: Path
    size_bytes: int
    sha256: str


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # ── write path ───────────────────────────────────────────────────────────
    def stage(self, source: BinaryIO, *, max_bytes: int) -> StagedFile:
        """Copy ``source`` to a staging file, returning its size and SHA-256.

        Raises :class:`UploadTooLargeError` (and removes the partial file) as soon as more than
        ``max_bytes`` have been read.
        """
        staging = self.root / STAGING_DIR
        staging.mkdir(parents=True, exist_ok=True)
        path = staging / f"{uuid.uuid4().hex}.part"
        digest = hashlib.sha256()
        size = 0
        try:
            with path.open("wb") as target:
                while chunk := source.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadTooLargeError(max_bytes)
                    digest.update(chunk)
                    target.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return StagedFile(path=path, size_bytes=size, sha256=digest.hexdigest())

    def commit(self, staged: StagedFile, key: str) -> None:
        """Atomically move a staged file to its final key."""
        destination = self.resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged.path, destination)  # atomic: same filesystem by construction

    def discard(self, staged: StagedFile) -> None:
        staged.path.unlink(missing_ok=True)

    # ── read / delete ────────────────────────────────────────────────────────
    def resolve(self, key: str) -> Path:
        """Absolute path for ``key``, guaranteed to stay inside the storage root."""
        root = self.root.resolve()
        path = (root / key).resolve()
        if not path.is_relative_to(root) or path == root:
            raise InvalidStorageKeyError(f"Storage key escapes the storage root: {key!r}")
        return path

    def exists(self, key: str) -> bool:
        return self.resolve(key).is_file()

    def delete(self, key: str) -> None:
        try:
            self.resolve(key).unlink(missing_ok=True)
        except OSError:
            # Best effort: a leftover file is harmless, a failed cleanup must not mask the
            # original error that made us clean up.
            logger.warning("Could not delete stored file %s", key, exc_info=True)


def get_storage() -> LocalFileStorage:
    """FastAPI dependency (overridable in tests)."""
    return LocalFileStorage(get_settings().upload_dir)
