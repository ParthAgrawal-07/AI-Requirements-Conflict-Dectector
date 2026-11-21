"""Baseline exports and the open-items report (Bansil — US-41, US-59, FR-74, FR-102, DR-22).

=====================================================  ========  ================================
``GET /baselines/{b}/export?format=docx|pdf|md``        ``view``  the template SRS of a labelled
                                                                  baseline
``GET /projects/{p}/export?format=docx|pdf|md``         ``view``  the template SRS of the current
                                                                  baseline
``GET /baselines/{b}/open-items?format=md|pdf|json``    ``view``  what that export leaves out
``GET /projects/{p}/open-items?format=md|pdf|json``     ``view``  … for the current baseline
=====================================================  ========  ================================

The **template export** is the fallback when there is no published updated SRS or the LLM budget
is used up (FR-74): the IEEE 830 / 29148 outline with the confirmed brief, and only Approved and
Implemented requirements, verbatim, grouped by type and stakeholder group. Its first page states
what was excluded; the open-items report for the same baseline revision lists it (US-59). The
JSON form of the report carries the excluded counts the Baselines screen shows before export.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.api.srs import MEDIA, file_response, render
from app.context import service as context_service
from app.context.brief import BriefValues
from app.core.errors import NotFoundError
from app.export import open_items, template
from app.models import Baseline, Project
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext
from app.srs.generator import freeze

router = APIRouter(tags=["exports"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}
_FILES: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    200: {"content": {MEDIA["md"]: {}, MEDIA["docx"]: {}, MEDIA["pdf"]: {}, MEDIA["json"]: {}}},
}


def _baseline(db: Session, baseline_id: uuid.UUID) -> tuple[Baseline, Project]:
    baseline = db.get(Baseline, baseline_id)
    project = db.get(Project, baseline.project_id) if baseline else None
    if baseline is None or project is None:  # defensive: the access layer resolved it
        raise NotFoundError("Baseline not found")
    return baseline, project


def _project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:  # defensive
        raise NotFoundError("Project not found")
    return project


def _template(db: Session, project: Project, baseline: Baseline | None, fmt: str) -> Response:
    context = context_service.confirmed_context(db, project)
    brief = context_service.confirmed_values(context) if context else BriefValues()
    revision = baseline.baseline_revision if baseline else project.baseline_revision
    markdown = template.template_markdown(
        project_name=project.name,
        items=freeze(db, project, baseline),
        brief=brief,
        baseline_revision=revision,
        baseline_label=baseline.label if baseline else None,
        generated_at=datetime.now(UTC),
        excluded=open_items.excluded_counts(db, project.id),
    )
    return render(markdown, fmt, title=f"{project.name} — SRS (template)",
                  filename=f"srs-template-rev{revision}")  # fmt: skip


def _open_items(db: Session, project: Project, baseline: Baseline | None, fmt: str) -> Response:
    revision = baseline.baseline_revision if baseline else project.baseline_revision
    report = open_items.build(
        db,
        project,
        baseline_revision=revision,
        baseline_label=baseline.label if baseline else None,
        generated_at=datetime.now(UTC),
    )
    if fmt == "json":
        return file_response(json.dumps(report.as_json(), default=str), "json", "open-items")
    return render(open_items.to_markdown(report), fmt, title=f"{project.name} — open items",
                  filename=f"open-items-rev{revision}")  # fmt: skip


@router.get(
    "/baselines/{baseline_id}/export",
    summary="Template SRS of a labelled baseline (DOCX, PDF or Markdown)",
    responses=_FILES,
)
def export_baseline(
    baseline_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    format: Annotated[Literal["md", "docx", "pdf"], Query()] = "docx",
) -> Response:
    baseline, project = _baseline(db, baseline_id)
    return _template(db, project, baseline, format)


@router.get(
    "/projects/{project_id}/export",
    summary="Template SRS of the current baseline (DOCX, PDF or Markdown)",
    responses=_FILES,
)
def export_current(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    format: Annotated[Literal["md", "docx", "pdf"], Query()] = "docx",
) -> Response:
    return _template(db, _project(db, project_id), None, format)


@router.get(
    "/baselines/{baseline_id}/open-items",
    summary="Open-items report beside a labelled baseline (Markdown, PDF or JSON)",
    responses=_FILES,
)
def baseline_open_items(
    baseline_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    format: Annotated[Literal["md", "pdf", "json"], Query()] = "pdf",
) -> Response:
    baseline, project = _baseline(db, baseline_id)
    return _open_items(db, project, baseline, format)


@router.get(
    "/projects/{project_id}/open-items",
    summary="Open-items report beside the current baseline (Markdown, PDF or JSON)",
    responses=_FILES,
)
def project_open_items(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    format: Annotated[Literal["md", "pdf", "json"], Query()] = "pdf",
) -> Response:
    return _open_items(db, _project(db, project_id), None, format)
