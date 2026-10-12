"""process_document: the worker-side glue between upload, extraction and the requirements table.

These run the *real* ingestion pipeline on real PDF/DOCX bytes against a real PostgreSQL.
"""

import uuid
from collections.abc import Callable

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion import Requirement as Extracted
from app.models import Document, DocumentStatus, Requirement, RequirementVersion
from app.services.processing import ProcessingOutcome, process_document
from app.services.storage import LocalFileStorage
from tests.factories import make_docx, make_pdf

MakeDoc = Callable[..., Document]


def requirements_of(db: Session, document: Document) -> list[Requirement]:
    return list(
        db.scalars(
            select(Requirement)
            .where(Requirement.document_id == document.id)
            .order_by(Requirement.order_index)
        )
    )


def refreshed(db: Session, document: Document) -> Document:
    db.refresh(document)
    return document


class TestHappyPath:
    def test_docx_requirements_are_persisted_in_order_with_versions(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        document = make_stored_document(
            make_docx(
                "REQ-001: The system shall allow user login.",
                "Some background text.",
                "FR-1.2: The system shall lock accounts after 5 failed attempts.",
            )
        )

        outcome = process_document(db_session, document.id, storage=storage)

        assert outcome is ProcessingOutcome.DONE
        document = refreshed(db_session, document)
        assert document.status is DocumentStatus.DONE
        assert document.progress_percent == 100
        assert document.error_message is None

        rows = requirements_of(db_session, document)
        assert [r.body for r in rows] == [
            "REQ-001: The system shall allow user login.",
            "Some background text.",
            "FR-1.2: The system shall lock accounts after 5 failed attempts.",
        ]
        assert [r.order_index for r in rows] == [0, 1, 2]
        assert [r.location for r in rows] == ["page/para 1", "page/para 2", "page/para 3"]
        assert all(r.current_version == 1 for r in rows)

        versions = db_session.scalars(select(RequirementVersion)).all()
        assert {(v.requirement_id, v.version_no, v.body_snapshot) for v in versions} == {
            (r.id, 1, r.body) for r in rows
        }
        assert all(v.changed_by is None for v in versions)  # extracted by the system, not a person

    def test_ids_printed_in_the_document_are_kept_and_invented_ones_are_not(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        """The segmenter labels id-less lines 'UNKNOWN-<page>-<line>'; that must never look real (FR-04)."""
        document = make_stored_document(
            make_docx("REQ-001: first", "no identifier here", "NFR-02: third", "FR-1.2: fourth")
        )
        process_document(db_session, document.id, storage=storage)

        assert [r.source_req_id for r in requirements_of(db_session, document)] == [
            "REQ-001",
            None,
            "NFR-02",
            "FR-1.2",
        ]

    def test_pdf_documents_work_too(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        document = make_stored_document(
            make_pdf("REQ-010: The API shall respond within 2 seconds."), extension=".pdf"
        )
        assert process_document(db_session, document.id, storage=storage) is ProcessingOutcome.DONE
        assert requirements_of(db_session, document)[0].source_req_id == "REQ-010"

    def test_the_claim_is_committed_before_extraction_so_pollers_see_processing(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        document = make_stored_document(make_docx("REQ-1: x"))
        observed: list[tuple[DocumentStatus, int]] = []

        def spy(path: str) -> list[Extracted]:
            db_session.refresh(document)
            observed.append((document.status, document.progress_percent))
            return [Extracted(id="REQ-1", raw_text="REQ-1: x", source_document="s", location="p 1")]

        process_document(db_session, document.id, storage=storage, extract=spy)
        assert observed == [(DocumentStatus.PROCESSING, 10)]


class TestFailuresAreNeverSilent:
    def test_unreadable_document_fails_with_a_readable_reason_and_no_internals(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        # Passes upload validation (a ZIP) but python-docx can't open it as a Word document.
        document = make_stored_document(b"PK\x03\x04" + b"\x00" * 100)

        outcome = process_document(db_session, document.id, storage=storage)

        assert outcome is ProcessingOutcome.FAILED
        document = refreshed(db_session, document)
        assert document.status is DocumentStatus.FAILED
        assert document.progress_percent == 0
        assert document.error_message is not None
        assert document.error_message.startswith("[extraction] The document could not be read")
        assert (
            "PackageNotFoundError" not in document.error_message
        )  # exception text stays in the logs
        assert "/" not in document.error_message.split("] ", 1)[1]  # ...and so do file paths
        assert requirements_of(db_session, document) == []

    def test_a_document_with_nothing_to_extract_fails_instead_of_looking_successful(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        document = make_stored_document(make_docx("", "   ", ""))
        assert (
            process_document(db_session, document.id, storage=storage) is ProcessingOutcome.FAILED
        )
        document = refreshed(db_session, document)
        assert document.status is DocumentStatus.FAILED
        assert document.error_message is not None
        assert "No requirement statements were found" in document.error_message

    def test_a_missing_file_names_the_storage_stage(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        document = make_stored_document(make_docx("REQ-1: x"), write_file=False)
        assert (
            process_document(db_session, document.id, storage=storage) is ProcessingOutcome.FAILED
        )
        assert refreshed(db_session, document).error_message.startswith("[storage]")  # type: ignore[union-attr]

    def test_a_timeout_is_reported_as_one(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        def too_slow(_: str) -> list[Extracted]:
            raise SoftTimeLimitExceeded()

        document = make_stored_document(make_docx("REQ-1: x"))
        process_document(db_session, document.id, storage=storage, extract=too_slow)
        assert "took too long" in refreshed(db_session, document).error_message  # type: ignore[operator]

    def test_a_database_error_while_saving_fails_the_document_and_saves_nothing(
        self,
        db_session: Session,
        storage: LocalFileStorage,
        make_stored_document: MakeDoc,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        document = make_stored_document(make_docx("REQ-1: x"))
        real_extract = lambda path: [  # noqa: E731
            Extracted(id="REQ-1", raw_text="REQ-1: x", source_document="s", location="p 1")
        ]
        original_flush = db_session.flush
        armed = {"fail": True}

        def flaky_flush(*args: object, **kwargs: object) -> None:
            if armed.pop("fail", False):
                raise RuntimeError("connection reset by peer")
            original_flush(*args, **kwargs)  # type: ignore[arg-type]

        def extract_then_break_the_next_flush(path: str) -> list[Extracted]:
            monkeypatch.setattr(db_session, "flush", flaky_flush)
            return real_extract(path)

        outcome = process_document(
            db_session, document.id, storage=storage, extract=extract_then_break_the_next_flush
        )

        assert outcome is ProcessingOutcome.FAILED
        document = refreshed(db_session, document)
        assert document.status is DocumentStatus.FAILED
        assert document.error_message is not None
        assert document.error_message.startswith("[persistence]")
        assert "connection reset" not in document.error_message
        assert requirements_of(db_session, document) == []


class TestIdempotence:
    """Celery may deliver a task more than once (acks_late); that must never duplicate data."""

    def test_a_finished_document_is_not_processed_again(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        document = make_stored_document(make_docx("REQ-1: a", "REQ-2: b"))
        assert process_document(db_session, document.id, storage=storage) is ProcessingOutcome.DONE
        assert (
            process_document(db_session, document.id, storage=storage) is ProcessingOutcome.SKIPPED
        )
        assert len(requirements_of(db_session, document)) == 2

    def test_a_failed_document_is_not_retried_automatically(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        document = make_stored_document(make_docx("", ""))
        assert (
            process_document(db_session, document.id, storage=storage) is ProcessingOutcome.FAILED
        )
        assert (
            process_document(db_session, document.id, storage=storage) is ProcessingOutcome.SKIPPED
        )

    def test_a_crashed_run_is_redone_from_scratch_without_duplicates(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        """Worker died mid-run: status stuck on 'processing', maybe with partial rows."""
        document = make_stored_document(make_docx("REQ-1: real one", "REQ-2: real two"))
        document.status = DocumentStatus.PROCESSING
        db_session.add(
            Requirement(document_id=document.id, body="stale partial row", order_index=0)
        )
        db_session.commit()

        assert process_document(db_session, document.id, storage=storage) is ProcessingOutcome.DONE

        assert [r.body for r in requirements_of(db_session, document)] == [
            "REQ-1: real one",
            "REQ-2: real two",
        ]

    def test_a_deleted_document_is_skipped(
        self, db_session: Session, storage: LocalFileStorage
    ) -> None:
        assert (
            process_document(db_session, uuid.uuid4(), storage=storage) is ProcessingOutcome.SKIPPED
        )


class TestTextHygiene:
    @staticmethod
    def run_with(
        db: Session, storage: LocalFileStorage, make: MakeDoc, items: list[Extracted]
    ) -> tuple[Document, ProcessingOutcome]:
        document = make(make_docx("placeholder"))
        return document, process_document(db, document.id, storage=storage, extract=lambda _: items)

    def test_nul_bytes_are_stripped_because_postgres_cannot_store_them(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        item = Extracted(
            id="REQ-1",
            raw_text="The system\x00 shall\x00 work.",
            source_document="s",
            location="p 1",
        )
        document, outcome = self.run_with(db_session, storage, make_stored_document, [item])
        assert outcome is ProcessingOutcome.DONE
        assert requirements_of(db_session, document)[0].body == "The system shall work."

    def test_text_is_otherwise_stored_verbatim(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        raw = "  REQ-1: The  system\tshall keep   spacing — and “quotes”.  "
        item = Extracted(id="REQ-1", raw_text=raw, source_document="s", location="p 1")
        document, _ = self.run_with(db_session, storage, make_stored_document, [item])
        assert requirements_of(db_session, document)[0].body == raw

    def test_blank_items_are_dropped_but_order_follows_the_source(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        items = [
            Extracted(id="REQ-1", raw_text="first", source_document="s", location="p 1"),
            Extracted(id="UNKNOWN-2-0", raw_text="   \x00 ", source_document="s", location="p 2"),
            Extracted(id="REQ-3", raw_text="third", source_document="s", location="p 3"),
        ]
        document, _ = self.run_with(db_session, storage, make_stored_document, items)
        rows = requirements_of(db_session, document)
        assert [r.body for r in rows] == ["first", "third"]
        assert [r.source_req_id for r in rows] == ["REQ-1", "REQ-3"]

    def test_only_blank_items_fail_the_document(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        items = [Extracted(id="UNKNOWN-1-0", raw_text=" ", source_document="s", location="p 1")]
        document, outcome = self.run_with(db_session, storage, make_stored_document, items)
        assert outcome is ProcessingOutcome.FAILED
        assert "No readable requirement text" in refreshed(db_session, document).error_message  # type: ignore[operator]
        assert db_session.scalar(select(func.count(Requirement.id))) == 0

    def test_overlong_location_is_truncated_to_the_column_size(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        item = Extracted(id="REQ-1", raw_text="x", source_document="s", location="L" * 200)
        document, _ = self.run_with(db_session, storage, make_stored_document, [item])
        assert requirements_of(db_session, document)[0].location == "L" * 64

    def test_empty_location_becomes_null(
        self, db_session: Session, storage: LocalFileStorage, make_stored_document: MakeDoc
    ) -> None:
        item = Extracted(id="REQ-1", raw_text="x", source_document="s", location="")
        document, _ = self.run_with(db_session, storage, make_stored_document, [item])
        assert requirements_of(db_session, document)[0].location is None
