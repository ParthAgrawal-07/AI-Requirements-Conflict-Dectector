"""LocalFileStorage: streaming with a hard size cap, atomic commit, traversal-proof keys."""

import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import storage as storage_module
from app.services.storage import (
    InvalidStorageKeyError,
    LocalFileStorage,
    UploadTooLargeError,
    get_storage,
)


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "uploads")


def staged_files(storage: LocalFileStorage) -> list[Path]:
    staging = storage.root / ".staging"
    return list(staging.iterdir()) if staging.exists() else []


class TestStage:
    def test_records_size_and_sha256(self, storage: LocalFileStorage) -> None:
        data = b"hello world" * 1000
        staged = storage.stage(io.BytesIO(data), max_bytes=10_000_000)
        assert staged.size_bytes == len(data)
        assert staged.sha256 == hashlib.sha256(data).hexdigest()
        assert staged.path.read_bytes() == data

    def test_reads_in_chunks(
        self, storage: LocalFileStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(storage_module, "CHUNK_SIZE", 4)
        data = b"0123456789abcdef!"
        staged = storage.stage(io.BytesIO(data), max_bytes=100)
        assert staged.path.read_bytes() == data

    def test_exactly_the_limit_is_accepted(self, storage: LocalFileStorage) -> None:
        assert storage.stage(io.BytesIO(b"x" * 100), max_bytes=100).size_bytes == 100

    def test_one_byte_over_is_rejected_and_leaves_nothing(self, storage: LocalFileStorage) -> None:
        with pytest.raises(UploadTooLargeError):
            storage.stage(io.BytesIO(b"x" * 101), max_bytes=100)
        assert staged_files(storage) == []

    def test_limit_is_enforced_while_streaming_not_after(
        self, storage: LocalFileStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 1 GB upload must be cut off after ~limit bytes, not read to the end first."""
        monkeypatch.setattr(storage_module, "CHUNK_SIZE", 10)
        consumed = 0

        class Endless(io.RawIOBase):
            def readable(self) -> bool:
                return True

            def readinto(self, buffer: bytearray) -> int:  # type: ignore[override]
                nonlocal consumed
                consumed += len(buffer)
                buffer[:] = b"x" * len(buffer)
                return len(buffer)

        with pytest.raises(UploadTooLargeError):
            storage.stage(io.BufferedReader(Endless(), buffer_size=10), max_bytes=50)
        assert consumed <= 100

    def test_empty_stream_stages_an_empty_file(self, storage: LocalFileStorage) -> None:
        staged = storage.stage(io.BytesIO(b""), max_bytes=10)
        assert staged.size_bytes == 0


class TestCommit:
    def test_moves_the_file_to_its_key_atomically(self, storage: LocalFileStorage) -> None:
        staged = storage.stage(io.BytesIO(b"payload"), max_bytes=100)
        storage.commit(staged, "ws-1/doc-1.pdf")

        assert storage.resolve("ws-1/doc-1.pdf").read_bytes() == b"payload"
        assert storage.exists("ws-1/doc-1.pdf")
        assert not staged.path.exists()
        assert staged_files(storage) == []

    def test_discard_removes_the_staged_file(self, storage: LocalFileStorage) -> None:
        staged = storage.stage(io.BytesIO(b"payload"), max_bytes=100)
        storage.discard(staged)
        assert staged_files(storage) == []
        storage.discard(staged)  # idempotent

    def test_delete_is_idempotent(self, storage: LocalFileStorage) -> None:
        staged = storage.stage(io.BytesIO(b"payload"), max_bytes=100)
        storage.commit(staged, "a/b.pdf")
        storage.delete("a/b.pdf")
        assert not storage.exists("a/b.pdf")
        storage.delete("a/b.pdf")
        storage.delete("never/existed.pdf")


class TestKeysCannotEscapeTheRoot:
    @pytest.mark.parametrize(
        "key",
        ["../outside.pdf", "a/../../outside.pdf", "/etc/passwd", "", ".", "a/../.."],
    )
    def test_rejected(self, storage: LocalFileStorage, key: str) -> None:
        with pytest.raises(InvalidStorageKeyError):
            storage.resolve(key)

    def test_commit_refuses_an_escaping_key(
        self, storage: LocalFileStorage, tmp_path: Path
    ) -> None:
        staged = storage.stage(io.BytesIO(b"x"), max_bytes=10)
        with pytest.raises(InvalidStorageKeyError):
            storage.commit(staged, "../escaped.pdf")
        assert not (tmp_path / "escaped.pdf").exists()

    def test_normal_nested_key_is_fine(self, storage: LocalFileStorage) -> None:
        assert storage.resolve("ws/doc.pdf").is_relative_to(storage.root.resolve())


def test_get_storage_uses_the_configured_upload_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        storage_module, "get_settings", lambda: SimpleNamespace(upload_dir=tmp_path)
    )
    assert get_storage().root == tmp_path
