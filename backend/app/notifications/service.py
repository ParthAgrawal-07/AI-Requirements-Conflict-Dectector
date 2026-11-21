"""Notification service (Madhav — US-38, FR-69, FR-70, CR-04; contract
``NotificationService.notify(users, kind, payload)``, design update §6).

Producers call :meth:`NotificationService.notify` **after** the change they announce is committed;
it stores one row per recipient and pushes ``notification.created`` to that person's sockets
only. Rules:

* nobody is notified of their own action, and only current members of the workspace are;
* the payload is ``{title, key, url}`` plus ids — a title like "RCR-3 on REQ-014", never
  requirement or message text (CR-04). :func:`notify` refuses a payload key it does not know;
* an **unread** notification of the same kind about the same subject is refreshed (moved to the
  top, its title and actor updated) instead of repeated.

The inbox groups kinds GitHub-style (interface design §8):

==================  =========================================================
``review``          review requested
``assigned``        assigned to an issue, or named decision owner
``mentioned``       @mentioned in a message or comment
``watching``        merges and changes to what you own or watch
``results``         analysis results on your requirements
``join_requests``   join requests to decide (managers)
==================  =========================================================
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Membership
from app.models.notification import (
    ASSIGNED,
    DECISION,
    JOIN_REQUEST,
    KINDS,
    MENTIONED,
    MERGED,
    RESULTS,
    REVIEW_REQUESTED,
    WATCHING,
    Notification,
)
from app.realtime import bus
from app.realtime.events import notification_created

GROUPS: dict[str, tuple[str, ...]] = {
    "review": (REVIEW_REQUESTED,),
    "assigned": (ASSIGNED, DECISION),
    "mentioned": (MENTIONED,),
    "watching": (WATCHING, MERGED),
    "results": (RESULTS,),
    "join_requests": (JOIN_REQUEST,),
}
GROUP_OF = {kind: group for group, kinds in GROUPS.items() for kind in kinds}
# What a payload may carry: ids, printed keys and short titles (CR-04).
PAYLOAD_KEYS = frozenset(
    {
        "title",
        "key",
        "url",
        "requirement_id",
        "requirement_ids",
        "finding_id",
        "issue_id",
        "change_request_id",
        "channel_id",
        "message_id",
        "suggestion_id",
        "join_request_id",
        "reason",
    }
)
MAX_TITLE = 140


@dataclass(frozen=True)
class Subject:
    """What a notification is about, and where the client opens it."""

    type: str  # change_request, issue, finding, requirement, message, join_request
    id: uuid.UUID
    key: str  # "RCR-3", "ISS-4", "REQ-014"…
    title: str  # "Review requested: RCR-3 on REQ-014"
    url: str  # client route, e.g. "/projects/<p>/change-requests/<id>"


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _members(self, workspace_id: uuid.UUID, users: set[uuid.UUID]) -> set[uuid.UUID]:
        if not users:
            return set()
        return set(
            self.db.scalars(
                select(Membership.user_id).where(
                    Membership.workspace_id == workspace_id,
                    Membership.user_id.in_(users),
                    Membership.ended_at.is_(None),
                )
            )
        )

    def notify(
        self,
        users: Iterable[uuid.UUID | None],
        kind: str,
        *,
        workspace_id: uuid.UUID,
        subject: Subject,
        project_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        **ids: Any,
    ) -> list[Notification]:
        """Notify ``users`` (commits; publishes after the commit). Returns the rows touched."""
        if kind not in KINDS:
            raise ValueError(f"Unknown notification kind {kind!r}")
        unknown = set(ids) - PAYLOAD_KEYS
        if unknown:
            raise ValueError(f"Payload keys {sorted(unknown)} are not ids or titles (CR-04)")
        db = self.db
        wanted = {u for u in users if u is not None and u != actor_id}
        recipients = self._members(workspace_id, wanted)
        payload = {
            "title": subject.title[:MAX_TITLE],
            "key": subject.key,
            "url": subject.url,
            **{k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in ids.items()},
        }
        now = datetime.now(UTC)
        touched: list[Notification] = []
        for user_id in sorted(recipients):
            row = db.scalar(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.kind == kind,
                    Notification.subject_id == subject.id,
                    Notification.read_at.is_(None),
                )
            )
            if row is None:
                row = Notification(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    kind=kind,
                    subject_type=subject.type,
                    subject_id=subject.id,
                )
                db.add(row)
            row.actor_id = actor_id
            row.payload = payload
            row.updated_at = now
            touched.append(row)
        db.commit()
        for row in touched:
            bus.publish(
                notification_created(
                    workspace_id=workspace_id,
                    project_id=project_id,
                    notification_id=row.id,
                    recipient_id=row.user_id,
                    kind=kind,
                    group=GROUP_OF[kind],
                )
            )
        return touched

    def _mine(self, user_id: uuid.UUID) -> Any:
        """The caller's notifications in workspaces they still belong to."""
        active = select(Membership.workspace_id).where(
            Membership.user_id == user_id, Membership.ended_at.is_(None)
        )
        return select(Notification).where(
            Notification.user_id == user_id, Notification.workspace_id.in_(active)
        )

    def inbox(
        self,
        user_id: uuid.UUID,
        *,
        group: str | None = None,
        unread_only: bool = False,
        workspace_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        query = self._mine(user_id)
        if group is not None:
            query = query.where(Notification.kind.in_(GROUPS[group]))
        if unread_only:
            query = query.where(Notification.read_at.is_(None))
        if workspace_id is not None:
            query = query.where(Notification.workspace_id == workspace_id)
        query = query.order_by(Notification.updated_at.desc(), Notification.id).limit(limit)
        return list(self.db.scalars(query))

    def unread_counts(self, user_id: uuid.UUID) -> dict[str, int]:
        mine = self._mine(user_id).where(Notification.read_at.is_(None)).subquery()
        rows = self.db.execute(select(mine.c.kind, func.count()).group_by(mine.c.kind)).tuples()
        counts = dict.fromkeys(GROUPS, 0)
        for kind, count in rows:
            counts[GROUP_OF[kind]] += count
        return {**counts, "total": sum(counts.values())}

    def mark_read(self, user_id: uuid.UUID, ids: Iterable[uuid.UUID] | None = None) -> int:
        """Mark some (or, with ``ids=None``, all) of the caller's notifications read."""
        statement = update(Notification).where(
            Notification.user_id == user_id, Notification.read_at.is_(None)
        )
        if ids is not None:
            statement = statement.where(Notification.id.in_(list(ids)))
        result = self.db.execute(statement.values(read_at=datetime.now(UTC)))
        self.db.commit()
        return int(getattr(result, "rowcount", 0) or 0)
