"""Discussion, votes, watches and links (Madhav — US-53, FR-80, FR-90, FR-91, DR-17, DR-19).

=======================================================  ==================  ====================
Route                                                    Permission          What
=======================================================  ==================  ====================
``GET /requirements/{r}/social``                         ``view``            drawer summary: comment
                                                                             count, tallies, my vote,
                                                                             watching, links
``GET /requirements/{r}/comments``                       ``view``            the thread, oldest first
``POST /requirements/{r}/comments``                      ``req.comment``     comment (+ @mentions)
``GET /requirements/{r}/votes``                          ``view``            tallies and who voted
``PUT /requirements/{r}/vote``                           ``req.vote``        support / oppose + reason
``DELETE /requirements/{r}/vote``                        ``req.vote``        withdraw my vote
``GET/PUT/DELETE /change-requests/{c}/vote(s)``          as above            the same for a request
``GET/PUT/DELETE /{requirements|issues|change-requests}  ``view``            follow it (own state)
/{id}/watch``
``GET /requirements/{r}/links``                          ``view``            links from and to it
``POST /requirements/{r}/links``                         ``req.link``        depends on / refines /
                                                                             related to
``DELETE /requirements/{r}/links/{link_id}``             ``req.link``        remove a link (a person
                                                                             only, DR-19)
=======================================================  ==================  ====================

Votes are display only (DR-17): nothing reads them to decide. Watching writes only the caller's own
follow list, so every member who may see the subject may watch it.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import Project, Requirement, RequirementLink, User
from app.schemas.common import ErrorResponse
from app.services import social
from app.services.access import AccessContext, Scope, register_scope_resolver

router = APIRouter(tags=["discussion"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}
Stance = Literal["support", "oppose"]
LinkKind = Literal["depends_on", "refines", "related_to"]


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=social.MAX_COMMENT)
    mentions: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class CommentRead(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str | None
    body: str
    created_at: datetime
    edited_at: datetime | None


class VoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stance: Stance
    reason: str | None = Field(default=None, max_length=social.MAX_REASON)


class VoteRead(BaseModel):
    user_id: uuid.UUID
    user_name: str | None
    stance: Stance
    reason: str | None


class TallyRead(BaseModel):
    support: int
    oppose: int
    mine: Stance | None
    votes: list[VoteRead]
    # Votes inform; they never change a state or satisfy a decision rule (DR-17).
    decides: Literal[False] = False


class WatchRead(BaseModel):
    watching: bool
    watchers: int


class LinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: uuid.UUID
    kind: LinkKind
    note: str | None = Field(default=None, max_length=500)


class LinkRead(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_label: str | None
    target_id: uuid.UUID
    target_label: str | None
    kind: LinkKind
    # From the requirement asked about: "outgoing" (it depends on / refines / relates to the
    # other) or "incoming" (the other one does).
    direction: Literal["outgoing", "incoming"]
    note: str | None
    created_by: uuid.UUID | None
    created_by_name: str | None
    created_at: datetime
    found_by: Literal["person"] = "person"


class SocialRead(BaseModel):
    requirement_id: uuid.UUID
    comments: int
    votes: TallyRead
    watching: bool
    links: list[LinkRead]


# ── helpers ─────────────────────────────────────────────────────────────────────────────────
def _requirement(db: Session, requirement_id: uuid.UUID) -> Requirement:
    row = db.get(Requirement, requirement_id)
    if row is None:  # defensive: require_permission resolved it
        raise NotFoundError("Requirement not found")
    return row


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(wanted)))}


def _tally(t: social.Tally) -> TallyRead:
    return TallyRead(
        support=t.support,
        oppose=t.oppose,
        mine=cast(Stance | None, t.mine),
        votes=[VoteRead.model_validate(vars(v)) for v in t.votes],
    )


def _links(db: Session, requirement_id: uuid.UUID) -> list[LinkRead]:
    rows = social.links(db, requirement_id)
    ids = {x for link in rows for x in (link.source_id, link.target_id)}
    labels = {
        r.id: r.source_req_id
        for r in (db.scalars(select(Requirement).where(Requirement.id.in_(ids))) if ids else [])
    }
    names = _names(db, {link.created_by for link in rows})
    return [
        LinkRead(
            id=link.id,
            source_id=link.source_id,
            source_label=labels.get(link.source_id),
            target_id=link.target_id,
            target_label=labels.get(link.target_id),
            kind=cast(LinkKind, link.kind),
            direction="outgoing" if link.source_id == requirement_id else "incoming",
            note=link.note,
            created_by=link.created_by,
            created_by_name=names.get(link.created_by) if link.created_by else None,
            created_at=link.created_at,
        )
        for link in rows
    ]


def _watch(db: Session, subject_type: str, subject_id: uuid.UUID, user_id: uuid.UUID) -> WatchRead:
    return WatchRead(
        watching=social.is_watching(db, subject_type, subject_id, user_id),
        watchers=len(social.watcher_ids(db, subject_type, subject_id)),
    )


# ── drawer summary ──────────────────────────────────────────────────────────────────────────
@router.get(
    "/requirements/{requirement_id}/social",
    response_model=SocialRead,
    summary="Discussion summary for the requirement drawer",
    responses=_ERRORS,
)
def get_social(
    requirement_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> SocialRead:
    requirement = _requirement(db, requirement_id)
    return SocialRead(
        requirement_id=requirement.id,
        comments=social.comment_count(db, requirement.id),
        votes=_tally(social.tally(db, "requirement", requirement.id, ctx.user.id)),
        watching=social.is_watching(db, "requirement", requirement.id, ctx.user.id),
        links=_links(db, requirement.id),
    )


# ── comments ────────────────────────────────────────────────────────────────────────────────
@router.get(
    "/requirements/{requirement_id}/comments",
    response_model=list[CommentRead],
    summary="The requirement's discussion, oldest first",
    responses=_ERRORS,
)
def list_comments(
    requirement_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> list[CommentRead]:
    rows = social.comments(db, _requirement(db, requirement_id).id)
    names = _names(db, {c.author_id for c in rows})
    return [
        CommentRead(
            id=c.id,
            author_id=c.author_id,
            author_name=names.get(c.author_id) if c.author_id else None,
            body=c.body,
            created_at=c.created_at,
            edited_at=c.edited_at,
        )
        for c in rows
    ]


@router.post(
    "/requirements/{requirement_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a requirement",
    responses=_ERRORS,
)
def create_comment(
    requirement_id: uuid.UUID,
    body: CommentCreate,
    ctx: Annotated[AccessContext, requires("req.comment")],
    db: DbSession,
) -> CommentRead:
    comment = social.add_comment(
        db, _requirement(db, requirement_id), ctx.user, body.body, mentions=body.mentions
    )
    return CommentRead(
        id=comment.id,
        author_id=ctx.user.id,
        author_name=ctx.user.full_name,
        body=comment.body,
        created_at=comment.created_at,
        edited_at=None,
    )


# ── votes (display only, DR-17) ─────────────────────────────────────────────────────────────
def _votes(db: Session, subject_type: str, subject_id: uuid.UUID, ctx: AccessContext) -> TallyRead:
    social.project_of(db, subject_type, subject_id)
    return _tally(social.tally(db, subject_type, subject_id, ctx.user.id))


def _vote(
    db: Session, subject_type: str, subject_id: uuid.UUID, ctx: AccessContext, body: VoteCreate
) -> TallyRead:
    project = social.project_of(db, subject_type, subject_id)
    return _tally(
        social.set_vote(db, project, subject_type, subject_id, ctx.user, body.stance, body.reason)
    )


def _unvote(db: Session, subject_type: str, subject_id: uuid.UUID, ctx: AccessContext) -> TallyRead:
    project = social.project_of(db, subject_type, subject_id)
    return _tally(social.clear_vote(db, project, subject_type, subject_id, ctx.user))


@router.get(
    "/requirements/{requirement_id}/votes",
    response_model=TallyRead,
    summary="Support and opposition on a requirement",
    responses=_ERRORS,
)
def list_requirement_votes(
    requirement_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> TallyRead:
    return _votes(db, "requirement", requirement_id, ctx)


@router.put(
    "/requirements/{requirement_id}/vote",
    response_model=TallyRead,
    summary="Support or oppose a requirement (display only)",
    responses=_ERRORS,
)
def put_requirement_vote(
    requirement_id: uuid.UUID,
    body: VoteCreate,
    ctx: Annotated[AccessContext, requires("req.vote")],
    db: DbSession,
) -> TallyRead:
    return _vote(db, "requirement", requirement_id, ctx, body)


@router.delete(
    "/requirements/{requirement_id}/vote",
    response_model=TallyRead,
    summary="Withdraw my vote on a requirement",
    responses=_ERRORS,
)
def delete_requirement_vote(
    requirement_id: uuid.UUID, ctx: Annotated[AccessContext, requires("req.vote")], db: DbSession
) -> TallyRead:
    return _unvote(db, "requirement", requirement_id, ctx)


@router.get(
    "/change-requests/{change_request_id}/votes",
    response_model=TallyRead,
    summary="Support and opposition on a change request",
    responses=_ERRORS,
)
def list_change_request_votes(
    change_request_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> TallyRead:
    return _votes(db, "change_request", change_request_id, ctx)


@router.put(
    "/change-requests/{change_request_id}/vote",
    response_model=TallyRead,
    summary="Support or oppose a change request (display only)",
    responses=_ERRORS,
)
def put_change_request_vote(
    change_request_id: uuid.UUID,
    body: VoteCreate,
    ctx: Annotated[AccessContext, requires("req.vote")],
    db: DbSession,
) -> TallyRead:
    return _vote(db, "change_request", change_request_id, ctx, body)


@router.delete(
    "/change-requests/{change_request_id}/vote",
    response_model=TallyRead,
    summary="Withdraw my vote on a change request",
    responses=_ERRORS,
)
def delete_change_request_vote(
    change_request_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("req.vote")],
    db: DbSession,
) -> TallyRead:
    return _unvote(db, "change_request", change_request_id, ctx)


# ── watches (the caller's own follow list) ──────────────────────────────────────────────────
def _set_watch(
    db: Session, subject_type: str, subject_id: uuid.UUID, ctx: AccessContext, on: bool | None
) -> WatchRead:
    project = social.project_of(db, subject_type, subject_id)
    if on is True:
        social.watch(db, project, subject_type, subject_id, ctx.user)
    elif on is False:
        social.unwatch(db, subject_type, subject_id, ctx.user)
    return _watch(db, subject_type, subject_id, ctx.user.id)


@router.get(
    "/requirements/{requirement_id}/watch",
    response_model=WatchRead,
    summary="Am I watching this requirement?",
    responses=_ERRORS,
)
def get_requirement_watch(
    requirement_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> WatchRead:
    return _set_watch(db, "requirement", requirement_id, ctx, None)


@router.put(
    "/requirements/{requirement_id}/watch",
    response_model=WatchRead,
    summary="Watch a requirement",
    responses=_ERRORS,
)
def put_requirement_watch(
    requirement_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> WatchRead:
    return _set_watch(db, "requirement", requirement_id, ctx, True)


@router.delete(
    "/requirements/{requirement_id}/watch",
    response_model=WatchRead,
    summary="Stop watching a requirement",
    responses=_ERRORS,
)
def delete_requirement_watch(
    requirement_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> WatchRead:
    return _set_watch(db, "requirement", requirement_id, ctx, False)


@router.get(
    "/issues/{issue_id}/watch",
    response_model=WatchRead,
    summary="Am I watching this issue?",
    responses=_ERRORS,
)
def get_issue_watch(
    issue_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> WatchRead:
    return _set_watch(db, "issue", issue_id, ctx, None)


@router.put(
    "/issues/{issue_id}/watch",
    response_model=WatchRead,
    summary="Watch an issue",
    responses=_ERRORS,
)
def put_issue_watch(
    issue_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> WatchRead:
    return _set_watch(db, "issue", issue_id, ctx, True)


@router.delete(
    "/issues/{issue_id}/watch",
    response_model=WatchRead,
    summary="Stop watching an issue",
    responses=_ERRORS,
)
def delete_issue_watch(
    issue_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> WatchRead:
    return _set_watch(db, "issue", issue_id, ctx, False)


@router.get(
    "/change-requests/{change_request_id}/watch",
    response_model=WatchRead,
    summary="Am I watching this change request?",
    responses=_ERRORS,
)
def get_change_request_watch(
    change_request_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> WatchRead:
    return _set_watch(db, "change_request", change_request_id, ctx, None)


@router.put(
    "/change-requests/{change_request_id}/watch",
    response_model=WatchRead,
    summary="Watch a change request",
    responses=_ERRORS,
)
def put_change_request_watch(
    change_request_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> WatchRead:
    return _set_watch(db, "change_request", change_request_id, ctx, True)


@router.delete(
    "/change-requests/{change_request_id}/watch",
    response_model=WatchRead,
    summary="Stop watching a change request",
    responses=_ERRORS,
)
def delete_change_request_watch(
    change_request_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> WatchRead:
    return _set_watch(db, "change_request", change_request_id, ctx, False)


# ── links (DR-19) ───────────────────────────────────────────────────────────────────────────
@router.get(
    "/requirements/{requirement_id}/links",
    response_model=list[LinkRead],
    summary="Links a person made from or to this requirement",
    responses=_ERRORS,
)
def list_links(
    requirement_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> list[LinkRead]:
    return _links(db, _requirement(db, requirement_id).id)


@router.post(
    "/requirements/{requirement_id}/links",
    response_model=LinkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Assert depends on / refines / related to",
    responses=_ERRORS,
)
def create_link(
    requirement_id: uuid.UUID,
    body: LinkCreate,
    ctx: Annotated[AccessContext, requires("req.link")],
    db: DbSession,
) -> LinkRead:
    source = _requirement(db, requirement_id)
    link = social.add_link(db, source, body.target_id, body.kind, ctx.user, note=body.note)
    return next(r for r in _links(db, source.id) if r.id == link.id)


@router.delete(
    "/requirements/{requirement_id}/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a link (people only; nothing automatic ever does, DR-19)",
    responses=_ERRORS,
)
def delete_link(
    requirement_id: uuid.UUID,
    link_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("req.link")],
    db: DbSession,
) -> Response:
    link = db.get(RequirementLink, link_id)
    if link is None or requirement_id not in (link.source_id, link.target_id):
        raise NotFoundError("Link not found")
    social.remove_link(db, link, ctx.user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _link_scope(db: Session, link_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Project.workspace_id, Project.id)
        .join(RequirementLink, RequirementLink.project_id == Project.id)
        .where(RequirementLink.id == link_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("link_id", _link_scope)
