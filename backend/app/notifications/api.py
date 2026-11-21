"""Inbox API (Madhav — US-38, FR-69, FR-70).

=================================  ==========================================================
``GET /notifications``             the caller's inbox, newest first; ``?group=`` one of the
                                   inbox groups, ``?unread=true``, ``?workspace_id=``
``GET /notifications/counts``      unread counts per group, for the bell
``POST /notifications/read``       mark some (``ids``) or all (``all: true``) as read
=================================  ==========================================================

A person's notifications are theirs alone: these routes are ``authenticated_only`` and only ever
read or change the caller's own rows, in workspaces they still belong to.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.deps import Authenticated, DbSession
from app.notifications.service import GROUP_OF, NotificationService

router = APIRouter(tags=["notifications"])

Group = Literal["review", "assigned", "mentioned", "watching", "results", "join_requests"]


class NotificationRead(BaseModel):
    id: uuid.UUID
    kind: str
    group: str
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    subject_type: str
    subject_id: uuid.UUID
    actor_id: uuid.UUID | None
    payload: dict[str, Any]
    read: bool
    updated_at: datetime


class Counts(BaseModel):
    review: int
    assigned: int
    mentioned: int
    watching: int
    results: int
    join_requests: int
    total: int


class ReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    all: bool = False

    @model_validator(mode="after")
    def _one_of(self) -> "ReadRequest":
        if self.all == bool(self.ids):
            raise ValueError("Send either ids or all: true")
        return self


class ReadResult(BaseModel):
    marked: int


@router.get("/notifications", response_model=list[NotificationRead], summary="My inbox")
def list_notifications(
    user: Authenticated,
    db: DbSession,
    group: Annotated[Group | None, Query()] = None,
    unread: bool = False,
    workspace_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[NotificationRead]:
    rows = NotificationService(db).inbox(
        user.id, group=group, unread_only=unread, workspace_id=workspace_id, limit=limit
    )
    return [
        NotificationRead(
            id=r.id,
            kind=r.kind,
            group=GROUP_OF[r.kind],
            workspace_id=r.workspace_id,
            project_id=r.project_id,
            subject_type=r.subject_type,
            subject_id=r.subject_id,
            actor_id=r.actor_id,
            payload=r.payload,
            read=r.read_at is not None,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get("/notifications/counts", response_model=Counts, summary="Unread counts per group")
def notification_counts(user: Authenticated, db: DbSession) -> Counts:
    return Counts(**NotificationService(db).unread_counts(user.id))


@router.post("/notifications/read", response_model=ReadResult, summary="Mark notifications as read")
def mark_read(body: ReadRequest, user: Authenticated, db: DbSession) -> ReadResult:
    marked = NotificationService(db).mark_read(user.id, None if body.all else body.ids)
    return ReadResult(marked=marked)
