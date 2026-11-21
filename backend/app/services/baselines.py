"""Baseline snapshots and comparison (Parth — US-40, FR-73, DR-08; design update §5,
``BaselineService``).

``snapshot(project, label)`` freezes every **Approved** and **Implemented** requirement of the
project — its version, printed ID, state and text at that moment — under a label unique in the
project ("v1.0 sign-off"). Members with ``baseline.manage`` (analysts, admins, owners) freeze;
the snapshot is audited and, by a database trigger, immutable.

``compare(a, b)`` lists what changed from snapshot *a* to snapshot *b*:

* **added** — in *b*, not in *a*;
* **changed** — in both, at a different version: both texts are returned for the diff;
* **removed** — in *a*, not in *b* (deprecated, or no longer approved), with the state it has now.

Requirements are matched by id, so a renumbered requirement is "changed", not removed and added.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import AuditAction, AuditLog, Project, Requirement, RequirementState, User
from app.models.baseline import Baseline, BaselineItem

IN_BASELINE = (RequirementState.APPROVED, RequirementState.IMPLEMENTED)


@dataclass(frozen=True)
class Entry:
    requirement_id: uuid.UUID
    label: str | None
    version: int | None  # None on the side where it is absent
    state: str | None
    body: str | None


@dataclass(frozen=True)
class Changed:
    requirement_id: uuid.UUID
    label: str | None
    from_version: int
    to_version: int
    before: str
    after: str


@dataclass
class Comparison:
    base: Baseline
    target: Baseline
    added: list[Entry] = field(default_factory=list)
    changed: list[Changed] = field(default_factory=list)
    removed: list[Entry] = field(default_factory=list)
    unchanged: int = 0


def items_of(db: Session, baseline_id: uuid.UUID) -> list[BaselineItem]:
    return list(
        db.scalars(
            select(BaselineItem)
            .where(BaselineItem.baseline_id == baseline_id)
            .order_by(BaselineItem.label, BaselineItem.requirement_id)
        )
    )


def list_baselines(db: Session, project_id: uuid.UUID) -> list[Baseline]:
    return list(
        db.scalars(
            select(Baseline)
            .where(Baseline.project_id == project_id)
            .order_by(Baseline.created_at.desc(), Baseline.label)
        )
    )


def snapshot(
    db: Session, project: Project, actor: User, *, label: str, note: str | None = None
) -> Baseline:
    """Freeze the project's current baseline under ``label`` (commits; 409 if it exists)."""
    clean = " ".join(label.split())
    requirements = list(
        db.scalars(
            select(Requirement)
            .where(Requirement.project_id == project.id, Requirement.state.in_(IN_BASELINE))
            .order_by(Requirement.order_index, Requirement.source_req_id, Requirement.id)
        )
    )
    baseline = Baseline(
        project_id=project.id,
        label=clean,
        note=(note or "").strip() or None,
        baseline_revision=project.baseline_revision,
        requirement_count=len(requirements),
        created_by=actor.id,
    )
    try:
        with db.begin_nested():
            db.add(baseline)
            db.flush()
    except IntegrityError:
        raise ConflictError(
            f"A baseline labelled {clean!r} already exists", code="label_taken"
        ) from None
    db.add_all(
        BaselineItem(
            baseline_id=baseline.id,
            requirement_id=r.id,
            version_no=r.current_version,
            label=r.source_req_id,
            state=r.state.value,
            body=r.body,
        )
        for r in requirements
    )
    try:
        from app.graph import revisions

        revisions.capture_baseline(db, project, baseline)  # Dhavni (US-50): the time slider
    except (ImportError, AttributeError):
        pass
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=actor.id,
            action=AuditAction.BASELINE_FROZEN,
            details={
                "project_id": str(project.id),
                "baseline_id": str(baseline.id),
                "baseline_revision": project.baseline_revision,
                "requirements": len(requirements),
            },
        )
    )
    db.commit()
    return baseline


def compare(db: Session, base: Baseline, target: Baseline) -> Comparison:
    if base.project_id != target.project_id:  # the access layer already refuses this
        raise ConflictError("Baselines of different projects", code="different_projects")
    before = {i.requirement_id: i for i in items_of(db, base.id)}
    after = {i.requirement_id: i for i in items_of(db, target.id)}
    result = Comparison(base=base, target=target)
    for requirement_id, item in after.items():
        old = before.get(requirement_id)
        if old is None:
            result.added.append(
                Entry(requirement_id, item.label, item.version_no, item.state, item.body)
            )
        elif old.version_no != item.version_no or old.body != item.body:
            result.changed.append(
                Changed(
                    requirement_id,
                    item.label or old.label,
                    old.version_no,
                    item.version_no,
                    old.body,
                    item.body,
                )  # fmt: skip
            )
        else:
            result.unchanged += 1
    gone = [i for rid, i in before.items() if rid not in after]
    now = {
        r.id: r.state.value
        for r in db.scalars(
            select(Requirement).where(Requirement.id.in_([i.requirement_id for i in gone]))
        )
    }
    result.removed = [
        Entry(i.requirement_id, i.label, i.version_no, now.get(i.requirement_id), i.body)
        for i in gone
    ]
    result.added.sort(key=_by_label)
    result.removed.sort(key=_by_label)
    result.changed.sort(key=_by_label)
    return result


def _by_label(entry: Entry | Changed) -> tuple[str, str]:
    return entry.label or "", str(entry.requirement_id)
