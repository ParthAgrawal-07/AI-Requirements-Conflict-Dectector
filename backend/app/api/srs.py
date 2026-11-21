"""Updated SRS routes (Bansil — US-61, US-41; FR-106, FR-107, DR-25; design update §12.5).

=====================================================  ================  ==========================
Route                                                  Permission        What
=====================================================  ================  ==========================
``GET /projects/{p}/srs/readiness?baseline_id=``       ``view``          the checklist
``POST /projects/{p}/srs``                             ``srs.generate``  start a draft (override:
                                                                         ``srs.publish``)
``GET /projects/{p}/srs``                              ``view``          drafts and versions
``GET /srs/{id}``                                      ``view``          one, with its sections
``PATCH /srs/{id}/sections/{key}``                     ``srs.generate``  accept, edit, regenerate
``POST /srs/{id}/fidelity``                            ``srs.generate``  run the fidelity check
``POST /srs/{id}/publish``                             ``srs.publish``   publish the next version
``POST /srs/{id}/discard``                             ``srs.generate``  drop a draft
``GET /srs/{id}/compare/{other_srs_id}``               ``view``          two versions side by side
``GET /srs/{id}/export?format=md|docx|pdf``            ``view``          the document (a draft:
                                                                         Markdown preview only)
``GET /srs/{id}/open-items?format=md|pdf|json``        ``view``          what it leaves out
=====================================================  ================  ==========================
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.core.errors import ConflictError, NotFoundError
from app.export import open_items, srs_docx, srs_pdf, template
from app.models import Baseline, Project, User
from app.models.srs import SrsDocument, SrsSection
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext, Scope, register_scope_resolver
from app.srs import generator, service

router = APIRouter(tags=["srs"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}
Format = Literal["md", "docx", "pdf"]
SectionKind = Literal["narrative", "requirements", "appendix"]
SectionSource = Literal["llm", "template", "system", "edited"]
SectionStatus = Literal["pending", "generating", "accepted"]
SrsStatus = Literal["generating", "draft", "published", "discarded"]
MEDIA = {
    "md": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "json": "application/json",
}


class CheckRead(BaseModel):
    key: str
    label: str
    ok: bool
    count: int
    links: list[dict[str, Any]]


class ReadinessRead(BaseModel):
    baseline_id: uuid.UUID | None
    baseline_revision: int
    requirements: int
    ready: bool
    checks: list[CheckRead]


class SrsCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_id: uuid.UUID | None = None
    override_reason: str | None = Field(default=None, max_length=2000)


class SectionRead(BaseModel):
    key: str
    order: int
    title: str
    kind: SectionKind
    body: str
    source: SectionSource
    status: SectionStatus
    # AI text stays labelled until a person accepts it (FR-107, NFR-17).
    ai_pending: bool
    locked: bool  # requirement and system sections: changed only through change requests
    regenerations: int
    instruction: str | None
    note: str | None
    llm_model: str | None
    accepted_by: uuid.UUID | None
    accepted_at: datetime | None


class SrsRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    baseline_id: uuid.UUID | None
    baseline_revision: int
    version_label: str | None
    status: SrsStatus
    requirements: int
    sections_total: int
    sections_accepted: int
    override_reason: str | None
    fidelity: dict[str, Any] | None
    llm_calls: int
    created_by: uuid.UUID | None
    created_at: datetime
    published_by: uuid.UUID | None
    published_by_name: str | None
    published_at: datetime | None


class SrsDetail(SrsRead):
    readiness: list[dict[str, Any]]
    sections: list[SectionRead]


class SectionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "edit", "regenerate"]
    body: str | None = Field(default=None, max_length=service.MAX_BODY)
    instruction: str | None = Field(default=None, max_length=service.MAX_INSTRUCTION)


class FailureRead(BaseModel):
    code: str
    message: str
    section_key: str | None
    label: str | None


class FidelityRead(BaseModel):
    passed: bool
    checked_at: str
    requirements_checked: int
    failures: list[FailureRead]


class SectionDiff(BaseModel):
    key: str
    title: str
    change: Literal["added", "removed", "changed", "unchanged"]
    before: str | None
    after: str | None


class SrsComparison(BaseModel):
    base: SrsRead
    target: SrsRead
    sections: list[SectionDiff]
    requirements: dict[str, list[dict[str, Any]]]


# ── helpers ─────────────────────────────────────────────────────────────────────────────────
def _document(db: Session, srs_id: uuid.UUID) -> SrsDocument:
    row = db.get(SrsDocument, srs_id)
    if row is None:  # defensive
        raise NotFoundError("SRS not found")
    return row


def _project(db: Session, project_id: uuid.UUID) -> Project:
    row = db.get(Project, project_id)
    if row is None:  # defensive
        raise NotFoundError("Project not found")
    return row


def _section(section: SrsSection) -> SectionRead:
    return SectionRead(
        key=section.key,
        order=section.order,
        title=section.title,
        kind=cast(SectionKind, section.kind),
        body=section.body,
        source=cast(SectionSource, section.source),
        status=cast(SectionStatus, section.status),
        ai_pending=section.source == "llm" and section.status != "accepted",
        locked=section.kind == "requirements" or section.source == "system",
        regenerations=section.regenerations,
        instruction=section.instruction,
        note=section.note,
        llm_model=section.llm_model,
        accepted_by=section.accepted_by,
        accepted_at=section.accepted_at,
    )


def _read(db: Session, document: SrsDocument, sections: list[SrsSection] | None = None) -> SrsRead:
    rows = sections if sections is not None else service.sections_of(db, document.id)
    publisher = db.get(User, document.published_by) if document.published_by else None
    return SrsRead(
        id=document.id,
        project_id=document.project_id,
        baseline_id=document.baseline_id,
        baseline_revision=document.baseline_revision,
        version_label=document.version_label,
        status=cast(SrsStatus, document.status),
        requirements=len(document.requirements or []),
        sections_total=len(rows),
        sections_accepted=sum(1 for s in rows if s.status == "accepted"),
        override_reason=document.override_reason,
        fidelity=document.fidelity_report,
        llm_calls=document.llm_calls,
        created_by=document.created_by,
        created_at=document.created_at,
        published_by=document.published_by,
        published_by_name=publisher.full_name if publisher else None,
        published_at=document.published_at,
    )


def _detail(db: Session, document: SrsDocument) -> SrsDetail:
    rows = service.sections_of(db, document.id)
    return SrsDetail(
        **_read(db, document, rows).model_dump(),
        readiness=list(document.readiness or []),
        sections=[_section(s) for s in rows],
    )


def file_response(content: str | bytes, fmt: str, filename: str) -> Response:
    body = content.encode("utf-8") if isinstance(content, str) else content
    return Response(
        content=body,
        media_type=MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}.{fmt}"'},
    )


def render(markdown: str, fmt: str, *, title: str, filename: str) -> Response:
    if fmt == "docx":
        return file_response(srs_docx.render(markdown, title=title), fmt, filename)
    if fmt == "pdf":
        return file_response(srs_pdf.render(markdown, title=title), fmt, filename)
    return file_response(markdown, "md", filename)


# ── routes ──────────────────────────────────────────────────────────────────────────────────
@router.get(
    "/projects/{project_id}/srs/readiness",
    response_model=ReadinessRead,
    summary="The readiness checklist before generating an updated SRS",
    responses=_ERRORS,
)
def get_readiness(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    baseline_id: uuid.UUID | None = None,
) -> ReadinessRead:
    project = _project(db, project_id)
    baseline = None
    if baseline_id is not None:
        baseline = db.get(Baseline, baseline_id)
        if baseline is None or baseline.project_id != project.id:
            raise NotFoundError("Baseline not found")
    items, checks = generator.readiness_for(db, project, baseline)
    return ReadinessRead(
        baseline_id=baseline_id,
        baseline_revision=baseline.baseline_revision if baseline else project.baseline_revision,
        requirements=len(items),
        ready=all(c.ok for c in checks),
        checks=[CheckRead.model_validate(c.as_json()) for c in checks],
    )


@router.post(
    "/projects/{project_id}/srs",
    response_model=SrsDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Start an updated SRS draft (sections are written in the background)",
    responses=_ERRORS,
)
def create_srs(
    project_id: uuid.UUID,
    body: SrsCreate,
    ctx: Annotated[AccessContext, requires("srs.generate")],
    db: DbSession,
) -> SrsDetail:
    document = generator.create_draft(
        db,
        ctx,
        _project(db, project_id),
        baseline_id=body.baseline_id,
        override_reason=body.override_reason,
    )
    generator.enqueue(generator.GENERATE, [str(document.id)])
    return _detail(db, document)


@router.get(
    "/projects/{project_id}/srs",
    response_model=list[SrsRead],
    summary="The project's SRS drafts and published versions, newest first",
    responses=_ERRORS,
)
def list_srs(
    project_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> list[SrsRead]:
    return [_read(db, d) for d in service.versions(db, project_id)]


@router.get(
    "/srs/{srs_id}",
    response_model=SrsDetail,
    summary="One updated SRS with its sections",
    responses=_ERRORS,
)
def get_srs(
    srs_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> SrsDetail:
    return _detail(db, _document(db, srs_id))


@router.patch(
    "/srs/{srs_id}/sections/{key}",
    response_model=SrsDetail,
    summary="Accept, edit or regenerate one section (requirement sections are locked)",
    responses=_ERRORS,
)
def review_section(
    srs_id: uuid.UUID,
    key: str,
    body: SectionAction,
    ctx: Annotated[AccessContext, requires("srs.generate")],
    db: DbSession,
) -> SrsDetail:
    document = _document(db, srs_id)
    service.review(
        db, ctx, document, key, body.action, body=body.body, instruction=body.instruction
    )
    return _detail(db, document)


@router.post(
    "/srs/{srs_id}/fidelity",
    response_model=FidelityRead,
    summary="Check that every baseline requirement appears once, verbatim, and nothing else",
    responses=_ERRORS,
)
def check_fidelity(
    srs_id: uuid.UUID, ctx: Annotated[AccessContext, requires("srs.generate")], db: DbSession
) -> FidelityRead:
    report = service.run_fidelity(db, _document(db, srs_id))
    return FidelityRead.model_validate(report.as_json())


@router.post(
    "/srs/{srs_id}/publish",
    response_model=SrsDetail,
    summary="Publish the draft as the next immutable SRS version",
    responses=_ERRORS,
)
def publish_srs(
    srs_id: uuid.UUID, ctx: Annotated[AccessContext, requires("srs.publish")], db: DbSession
) -> SrsDetail:
    return _detail(db, service.publish(db, ctx, _document(db, srs_id)))


@router.post(
    "/srs/{srs_id}/discard",
    response_model=SrsRead,
    summary="Discard a draft",
    responses=_ERRORS,
)
def discard_srs(
    srs_id: uuid.UUID, ctx: Annotated[AccessContext, requires("srs.generate")], db: DbSession
) -> SrsRead:
    return _read(db, service.discard(db, ctx, _document(db, srs_id)))


@router.get(
    "/srs/{srs_id}/compare/{other_srs_id}",
    response_model=SrsComparison,
    summary="Compare two SRS versions section by section and requirement by requirement",
    responses=_ERRORS,
)
def compare_srs(
    srs_id: uuid.UUID,
    other_srs_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> SrsComparison:
    result = service.compare(db, _document(db, srs_id), _document(db, other_srs_id))
    return SrsComparison(
        base=_read(db, result.base),
        target=_read(db, result.target),
        sections=[SectionDiff.model_validate(s) for s in result.sections],
        requirements=result.requirements,
    )


def _markdown(db: Session, document: SrsDocument) -> str:
    project = _project(db, document.project_id)
    baseline = db.get(Baseline, document.baseline_id) if document.baseline_id else None
    publisher = db.get(User, document.published_by) if document.published_by else None
    excluded = (document.fidelity_report or {}).get("excluded") or open_items.excluded_counts(
        db, project.id
    )
    return template.srs_markdown(
        document,
        service.sections_of(db, document.id),
        project_name=project.name,
        baseline_label=baseline.label if baseline else None,
        published_by=publisher.full_name if publisher else None,
        excluded=excluded,
    )


@router.get(
    "/srs/{srs_id}/export",
    summary="Download the SRS as Markdown, DOCX or PDF",
    responses={**_ERRORS, 200: {"content": {MEDIA["md"]: {}, MEDIA["docx"]: {}, MEDIA["pdf"]: {}}}},
)
def export_srs(
    srs_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    format: Annotated[Format, Query()] = "md",
) -> Response:
    document = _document(db, srs_id)
    if document.status != "published" and format != "md":
        raise ConflictError(
            "Only a published SRS is exported as DOCX or PDF; a draft can be previewed as Markdown",
            code="not_published",
        )
    project = _project(db, document.project_id)
    label = document.version_label or "draft"
    return render(
        _markdown(db, document),
        format,
        title=f"{project.name} — SRS {label}",
        filename=f"srs-{label}",
    )


@router.get(
    "/srs/{srs_id}/open-items",
    summary="The open-items report beside this SRS (Markdown, PDF or JSON)",
    responses=_ERRORS,
)
def srs_open_items(
    srs_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    format: Annotated[Literal["md", "pdf", "json"], Query()] = "md",
) -> Response:
    document = _document(db, srs_id)
    project = _project(db, document.project_id)
    baseline = db.get(Baseline, document.baseline_id) if document.baseline_id else None
    report = open_items.build(
        db,
        project,
        baseline_revision=document.baseline_revision,
        baseline_label=baseline.label if baseline else None,
        generated_at=datetime.now(UTC),
    )
    if format == "json":
        return file_response(json.dumps(report.as_json(), default=str), "json", "open-items")
    return render(
        open_items.to_markdown(report),
        format,
        title=f"{project.name} — open items",
        filename=f"open-items-rev{document.baseline_revision}",
    )


def _srs_scope(db: Session, srs_id: uuid.UUID) -> Scope | None:
    row = db.get(SrsDocument, srs_id)
    project = db.get(Project, row.project_id) if row else None
    return None if project is None else Scope(project.workspace_id, project.id)


register_scope_resolver("srs_id", _srs_scope)
register_scope_resolver("other_srs_id", _srs_scope)
