"""Requirement drafts (Bansil — FR-81): the composer's private autosave.

Account-level routes (``authenticated_only``): a draft belongs to its author, so there is no
workspace permission to check. The service still requires an active membership of the draft's
workspace, so a removed member's drafts are a 404 for them.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from app.api.deps import Authenticated, DbSession
from app.intake import drafts as draft_service
from app.intake.schemas import DraftFields, RequirementDraftRead
from app.models import RequirementDraft
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/me/drafts", tags=["composer"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "No such draft of yours (or no such project)"}
}


class DraftCreate(BaseModel):
    project_id: uuid.UUID
    fields: DraftFields = DraftFields()


class DraftUpdate(BaseModel):
    fields: DraftFields


def _read(draft: RequirementDraft) -> RequirementDraftRead:
    return RequirementDraftRead.build(
        id=draft.id,
        project_id=draft.project_id,
        fields=DraftFields.model_validate(draft.fields),
        updated_at=draft.updated_at,
    )


@router.get("", response_model=list[RequirementDraftRead], summary="Your drafts, newest first")
def list_drafts(
    user: Authenticated,
    db: DbSession,
    project: Annotated[uuid.UUID | None, Query(description="Only this project's")] = None,
) -> list[RequirementDraftRead]:
    return [_read(d) for d in draft_service.list_drafts(db, user, project_id=project)]


@router.post(
    "",
    status_code=201,
    response_model=RequirementDraftRead,
    summary="Start a draft",
    responses={**_NOT_FOUND, 409: {"model": ErrorResponse, "description": "Too many drafts"}},
)
def create_draft(body: DraftCreate, user: Authenticated, db: DbSession) -> RequirementDraftRead:
    return _read(
        draft_service.create_draft(db, user, project_id=body.project_id, fields=body.fields)
    )


@router.get("/{draft_id}", response_model=RequirementDraftRead, responses=_NOT_FOUND)
def get_draft(draft_id: uuid.UUID, user: Authenticated, db: DbSession) -> RequirementDraftRead:
    return _read(draft_service.get_draft(db, user, draft_id))


@router.patch(
    "/{draft_id}",
    response_model=RequirementDraftRead,
    summary="Autosave: replace the draft's fields",
    responses=_NOT_FOUND,
)
def update_draft(
    draft_id: uuid.UUID, body: DraftUpdate, user: Authenticated, db: DbSession
) -> RequirementDraftRead:
    draft = draft_service.get_draft(db, user, draft_id)
    return _read(draft_service.update_draft(db, draft, body.fields))


@router.delete("/{draft_id}", status_code=204, responses=_NOT_FOUND)
def delete_draft(draft_id: uuid.UUID, user: Authenticated, db: DbSession) -> Response:
    draft_service.delete_draft(db, draft_service.get_draft(db, user, draft_id))
    return Response(status_code=204)
