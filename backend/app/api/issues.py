"""Issue routes (Dhavni — US-52, FR-86, FR-87; design update §8).

* ``GET /projects/{p}/issues`` (``view``) — newest first; filter by status, label, assignee,
  requirement, auto.
* ``POST /projects/{p}/issues`` (``issue.open``) — open ISS-n about requirements of the project.
* ``GET /issues/{id}`` (``view``), ``PATCH /issues/{id}`` (``issue.open``; each change checked by
  ``app.services.issues``: labels and assignees need ``issue.manage``).
* ``GET /issues/{id}/comments`` (``view``), ``POST /issues/{id}/comments`` (``issue.open``).

Another workspace's issue is a 404, like everything else (NFR-27).
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import Comment, Issue, Project, RequirementState, User
from app.schemas.common import ErrorResponse, Page
from app.services import issues as issue_service
from app.services.access import AccessContext, Scope, register_scope_resolver

router = APIRouter(tags=["issues"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse, "description": "Not a member, or no such issue"},
}
IssueStatus = Literal["open", "closed"]


class UserRef(BaseModel):
    id: uuid.UUID
    full_name: str


class IssueRequirementRef(BaseModel):
    id: uuid.UUID
    label: str | None
    state: RequirementState
    owner_id: uuid.UUID | None


class IssueRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    number: int
    key: str  # "ISS-3"
    title: str
    body: str
    status: IssueStatus
    close_reason: str | None
    auto: bool
    finding_id: uuid.UUID | None
    author: UserRef | None  # None: opened automatically
    labels: list[str]
    assignees: list[UserRef]
    requirements: list[IssueRequirementRef]
    comment_count: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    closed_by: uuid.UUID | None

    @classmethod
    def from_view(cls, item: issue_service.IssueView) -> "IssueRead":
        issue = item.issue
        return cls(
            id=issue.id,
            project_id=issue.project_id,
            number=issue.number,
            key=issue_service.key(issue),
            title=issue.title,
            body=issue.body,
            status="closed" if issue.status == "closed" else "open",
            close_reason=issue.close_reason,
            auto=issue.auto,
            finding_id=issue.finding_id,
            author=UserRef(id=item.author.id, full_name=item.author.full_name)
            if item.author
            else None,
            labels=list(issue.labels),
            assignees=[UserRef(id=u.id, full_name=u.full_name) for u in item.assignees],
            requirements=[
                IssueRequirementRef(
                    id=r.id, label=r.source_req_id, state=r.state, owner_id=r.owner_id
                )
                for r in item.requirements
            ],
            comment_count=item.comment_count,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
            closed_at=issue.closed_at,
            closed_by=issue.closed_by,
        )


class IssueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200)
    body: str = Field(default="", max_length=10_000)
    labels: list[str] = Field(default_factory=list, max_length=10)
    assignee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    requirement_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class IssueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=200)
    body: str | None = Field(default=None, max_length=10_000)
    labels: list[str] | None = Field(default=None, max_length=10)
    assignee_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    status: IssueStatus | None = None


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=10_000)


class CommentRead(BaseModel):
    id: uuid.UUID
    author: UserRef | None  # None: written by the app (an auto issue's question)
    body: str
    created_at: datetime

    @classmethod
    def from_model(cls, comment: Comment, authors: dict[uuid.UUID, User]) -> "CommentRead":
        author = authors.get(comment.author_id) if comment.author_id else None
        return cls(
            id=comment.id,
            author=UserRef(id=author.id, full_name=author.full_name) if author else None,
            body=comment.body,
            created_at=comment.created_at,
        )


def _issue(db: Session, issue_id: uuid.UUID) -> Issue:
    issue = db.get(Issue, issue_id)
    if issue is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Issue not found")
    return issue


@router.get(
    "/projects/{project_id}/issues",
    response_model=Page[IssueRead],
    summary="The project's issues, newest first",
    responses=_ERRORS,
)
def list_issues(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    status_: Annotated[IssueStatus | None, Query(alias="status")] = None,
    label: Annotated[str | None, Query(max_length=40)] = None,
    assignee: Annotated[uuid.UUID | None, Query()] = None,
    requirement: Annotated[uuid.UUID | None, Query()] = None,
    auto: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[IssueRead]:
    views, total = issue_service.list_issues(
        db,
        project_id,
        status=status_,
        label=label.lower() if label else None,
        assignee=assignee,
        requirement=requirement,
        auto=auto,
        limit=limit,
        offset=offset,
    )
    return Page[IssueRead](
        items=[IssueRead.from_view(v) for v in views], total=total, limit=limit, offset=offset
    )


@router.post(
    "/projects/{project_id}/issues",
    response_model=IssueRead,
    status_code=status.HTTP_201_CREATED,
    summary="Open an issue about requirements of the project",
    responses=_ERRORS,
)
def create_issue(
    project_id: uuid.UUID,
    body: IssueCreate,
    ctx: Annotated[AccessContext, requires("issue.open")],
    db: DbSession,
) -> IssueRead:
    project = db.get(Project, project_id)
    if project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Project not found")
    issue = issue_service.open_issue(
        db,
        project=project,
        author=ctx.user,
        title=body.title,
        body=body.body,
        labels=body.labels,
        assignees=body.assignee_ids,
        requirements=body.requirement_ids,
    )
    return IssueRead.from_view(issue_service.view(db, issue))


@router.get(
    "/issues/{issue_id}",
    response_model=IssueRead,
    summary="One issue",
    responses=_ERRORS,
)
def get_issue(
    issue_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> IssueRead:
    return IssueRead.from_view(issue_service.view(db, _issue(db, issue_id)))


@router.patch(
    "/issues/{issue_id}",
    response_model=IssueRead,
    summary="Edit, label, assign, close or reopen an issue",
    responses=_ERRORS,
)
def update_issue(
    issue_id: uuid.UUID,
    body: IssueUpdate,
    ctx: Annotated[AccessContext, requires("issue.open")],
    db: DbSession,
) -> IssueRead:
    issue = issue_service.update_issue(
        db,
        ctx,
        _issue(db, issue_id),
        title=body.title,
        body=body.body,
        labels=body.labels,
        assignees=body.assignee_ids,
        status=body.status,
    )
    return IssueRead.from_view(issue_service.view(db, issue))


@router.get(
    "/issues/{issue_id}/comments",
    response_model=list[CommentRead],
    summary="An issue's comments, oldest first",
    responses=_ERRORS,
)
def list_comments(
    issue_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> list[CommentRead]:
    rows = issue_service.comments(db, _issue(db, issue_id).id)
    ids = {c.author_id for c in rows if c.author_id}
    authors = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    return [CommentRead.from_model(c, authors) for c in rows]


@router.post(
    "/issues/{issue_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on an issue",
    responses=_ERRORS,
)
def create_comment(
    issue_id: uuid.UUID,
    body: CommentCreate,
    ctx: Annotated[AccessContext, requires("issue.open")],
    db: DbSession,
) -> CommentRead:
    comment = issue_service.add_comment(db, _issue(db, issue_id), ctx.user, body.body)
    return CommentRead.from_model(comment, {ctx.user.id: ctx.user})


def _issue_scope(db: Session, issue_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Project.workspace_id, Project.id)
        .join(Issue, Issue.project_id == Project.id)
        .where(Issue.id == issue_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("issue_id", _issue_scope)
