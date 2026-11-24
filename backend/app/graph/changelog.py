"""The written change log and its summaries (Dhavni — US-55, FR-95, FR-96; design update §3.8,
``ChangeNarrator``).

Every map delta that carries sentences (``app.graph.deltas.publish``) is stored here as
``graph_events`` rows — one per sentence, with the map revision, the kind of change, the nodes and
edges it is about and the counts a summary adds up. The Changes panel lists them newest first,
the time slider (US-50) filters them by revision, and hovering a node lists its own.

:func:`summary` answers "what changed since…" (a date, a labelled baseline, or the member's last
visit) **from these rows with SQL**: counts (requirements added, changed and deprecated, conflicts
opened and resolved, change requests merged), the important changes as a bullet list, and the
same as Markdown to copy. No sentence and no count comes from an LLM; Keval's optional AI
paragraph (``app.classification.change_summary``) is written from this result and labelled.

Sentences name requirements by printed ID and people by name; requirement text never appears
(CR-04).
"""

import re
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, cast, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from app.models import ChangeLogVisit, GraphEvent, User
from app.models.graph import EVENT_KINDS, SUMMARY_COUNTS

MAX_PAGE = 200
MAX_HIGHLIGHTS = 12
_KEY = re.compile(r"\b[A-Z][A-Z0-9]*-\d+(?:\.\d+)*\b")
# What a summary lists as "important", in this order of preference when there are many.
IMPORTANT = ("merged", "conflict_found", "conflict_resolved", "concern", "state", "added", "issue")
COUNT_WORDS = {
    "requirements_added": ("requirement added", "requirements added"),
    "requirements_changed": ("requirement changed", "requirements changed"),
    "requirements_deprecated": ("requirement deprecated", "requirements deprecated"),
    "conflicts_opened": ("conflict found", "conflicts found"),
    "conflicts_resolved": ("conflict resolved", "conflicts resolved"),
    "change_requests_merged": ("change request merged", "change requests merged"),
}


@dataclass(frozen=True)
class Event:
    id: uuid.UUID
    at: datetime
    revision: int | None
    kind: str
    sentence: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    node_ids: list[str]
    edge_ids: list[str]
    backfilled: bool


@dataclass
class Summary:
    since: datetime | None
    until: datetime
    since_label: str  # "v1.0", "3 Jan 2027 10:00", "your last visit", "the beginning"
    counts: dict[str, int]
    highlights: list[Event]
    total_events: int
    markdown: str = ""
    keys: list[str] = field(default_factory=list)  # REQ-/ISS-/RCR- keys the summary mentions


# ── writing (called by deltas.publish) ──────────────────────────────────────────────────────
def record(
    db: Session,
    project_id: uuid.UUID,
    *,
    revision: int | None,
    baseline_revision: int,
    actor_id: uuid.UUID | None,
    kind: str,
    sentences: Sequence[str],
    node_ids: Collection[uuid.UUID],
    edge_ids: Collection[uuid.UUID],
    counts: dict[str, int],
) -> None:
    """Store one row per sentence (the counts go on the first). Does not commit."""
    if kind not in EVENT_KINDS:
        raise ValueError(f"Unknown change-log kind {kind!r}")
    unknown = set(counts) - set(SUMMARY_COUNTS)
    if unknown:
        raise ValueError(f"Unknown summary counts {sorted(unknown)}")
    nodes = sorted(str(n) for n in node_ids)
    edges = sorted(str(e) for e in edge_ids)
    # The wall clock, not the transaction's start: sentences written in one transaction (and a
    # "last visit" taken just before) must still come out in the order they happened.
    now = datetime.now(UTC)
    for index, sentence in enumerate(sentences):
        db.add(
            GraphEvent(
                project_id=project_id,
                revision=revision,
                baseline_revision=baseline_revision,
                actor_id=actor_id,
                kind=kind,
                sentence=sentence,
                node_ids=nodes,
                edge_ids=edges,
                counts={k: v for k, v in counts.items() if v} if index == 0 else {},
                created_at=now + timedelta(microseconds=index),
            )
        )


# ── reading ─────────────────────────────────────────────────────────────────────────────────
def events(
    db: Session,
    project_id: uuid.UUID,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    before: datetime | None = None,
    actor_id: uuid.UUID | None = None,
    kinds: Collection[str] = (),
    requirement_id: uuid.UUID | None = None,
    until_revision: int | None = None,
    limit: int = 50,
) -> list[Event]:
    """The project's change log, newest first, filtered (every filter optional).

    ``before`` pages backwards (pass the ``at`` of the last row seen); ``until_revision`` keeps
    the panel in step with the time slider (backfilled rows, which have no revision, are older
    than every revision and stay in).
    """
    query = (
        select(GraphEvent, User.full_name)
        .outerjoin(User, User.id == GraphEvent.actor_id)
        .where(GraphEvent.project_id == project_id)
    )
    if since is not None:
        query = query.where(GraphEvent.created_at >= since)
    if until is not None:
        query = query.where(GraphEvent.created_at <= until)
    if before is not None:
        query = query.where(GraphEvent.created_at < before)
    if actor_id is not None:
        query = query.where(GraphEvent.actor_id == actor_id)
    if kinds:
        query = query.where(GraphEvent.kind.in_(list(kinds)))
    if requirement_id is not None:
        query = query.where(
            GraphEvent.node_ids.contains(cast(literal(f'["{requirement_id}"]'), JSONB))
        )
    if until_revision is not None:
        query = query.where((GraphEvent.revision <= until_revision) | GraphEvent.revision.is_(None))
    query = query.order_by(
        GraphEvent.created_at.desc(), GraphEvent.revision.desc().nulls_last(), GraphEvent.id.desc()
    ).limit(max(1, min(limit, MAX_PAGE)))
    return [_event(row, name) for row, name in db.execute(query)]


def _event(row: GraphEvent, actor_name: str | None) -> Event:
    return Event(
        id=row.id,
        at=row.created_at,
        revision=row.revision,
        kind=row.kind,
        sentence=row.sentence,
        actor_id=row.actor_id,
        actor_name=actor_name,
        node_ids=list(row.node_ids or []),
        edge_ids=list(row.edge_ids or []),
        backfilled=row.backfilled,
    )


# ── last visit ──────────────────────────────────────────────────────────────────────────────
def last_visit(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> datetime | None:
    row = db.get(ChangeLogVisit, (user_id, project_id))
    return row.seen_at if row else None


def mark_seen(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> datetime:
    now = datetime.now(UTC)
    db.execute(
        insert(ChangeLogVisit)
        .values(user_id=user_id, project_id=project_id, seen_at=now)
        .on_conflict_do_update(index_elements=["user_id", "project_id"], set_={"seen_at": now})
    )
    db.commit()
    return now


# ── summaries ───────────────────────────────────────────────────────────────────────────────
def summary(
    db: Session,
    project_id: uuid.UUID,
    *,
    since: datetime | None,
    since_label: str,
    until: datetime | None = None,
    after_revision: int | None = None,
) -> Summary:
    """Counts and important changes between ``since`` (None: the beginning) and ``until``.

    ``after_revision`` starts the window at a map revision instead (a labelled baseline knows the
    revision it was frozen at), which is exact even when clocks or transactions overlap.
    """
    end = until or datetime.now(UTC)
    window = [GraphEvent.project_id == project_id, GraphEvent.created_at <= end]
    if after_revision is not None:
        window.append(GraphEvent.revision > after_revision)
    elif since is not None:
        window.append(GraphEvent.created_at > since)
    counts = dict.fromkeys(SUMMARY_COUNTS, 0)
    totals = db.execute(
        select(
            *(
                func.coalesce(func.sum(cast(GraphEvent.counts[key].astext, Integer)), 0)
                for key in SUMMARY_COUNTS
            ),
            func.count(),
        ).where(*window)
    ).one()
    for key, value in zip(SUMMARY_COUNTS, totals[:-1], strict=True):
        counts[key] = int(value)
    total = int(totals[-1])
    rows = db.execute(
        select(GraphEvent, User.full_name)
        .outerjoin(User, User.id == GraphEvent.actor_id)
        .where(*window, GraphEvent.kind.in_(IMPORTANT))
        .order_by(
            GraphEvent.created_at.desc(),
            GraphEvent.revision.desc().nulls_last(),
            GraphEvent.id.desc(),
        )
        .limit(MAX_HIGHLIGHTS * 4)
    )
    candidates = [_event(row, name) for row, name in rows]
    rank = {kind: i for i, kind in enumerate(IMPORTANT)}
    chosen = sorted(candidates, key=lambda e: rank[e.kind])[:MAX_HIGHLIGHTS]
    highlights = sorted(chosen, key=lambda e: e.at, reverse=True)
    result = Summary(
        since=since,
        until=end,
        since_label=since_label,
        counts=counts,
        highlights=highlights,
        total_events=total,
    )
    result.markdown = markdown(result)
    result.keys = sorted({key for e in highlights for key in keys_in(e.sentence)})
    return result


def count_lines(counts: dict[str, int]) -> list[str]:
    """ "3 requirements added", … — only the non-zero counts, in a fixed order."""
    lines = []
    for key in SUMMARY_COUNTS:
        n = counts.get(key, 0)
        if n:
            one, many = COUNT_WORDS[key]
            lines.append(f"{n} {one if n == 1 else many}")
    return lines


def markdown(result: Summary) -> str:
    """The summary as Markdown to copy into a message or a report (US-55)."""
    head = f"## Changes since {result.since_label}"
    span = f"_{_when(result.since) if result.since else 'Start'} – {_when(result.until)}_"
    lines = [head, "", span, ""]
    numbers = count_lines(result.counts)
    if not numbers and not result.highlights:
        lines.append("No changes in this period.")
        return "\n".join(lines) + "\n"
    lines += [f"- {line}" for line in numbers] or ["- No counted changes"]
    if result.highlights:
        lines += ["", "### Important changes", ""]
        lines += [f"- {_when(e.at)} · {e.sentence}" for e in result.highlights]
    return "\n".join(lines) + "\n"


def _when(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%d %b %Y %H:%M UTC")


def keys_in(sentence: str) -> set[str]:
    """The REQ-/ISS-/RCR- style keys a sentence mentions (what an AI narrative may cite)."""
    return set(_KEY.findall(sentence))
