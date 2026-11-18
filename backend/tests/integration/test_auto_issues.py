"""Auto conflict issues on the planted SRS (Abhyudit — US-52, FR-87).

Every planted Conflicting and Duplicate pair whose two requirements have different owners gets
exactly one issue, assigned to both owners; pairs with one owner or none, and every other
category, get none. Analysing again opens nothing new.
"""

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    FindingCategory,
    Issue,
    Project,
    User,
)
from app.services import issues
from app.services.issues import ConflictIssueOpener
from tests.integration.planted import Planted, labels, load, scripted

AUTO = {"Conflicting", "Duplicate"}


@pytest.fixture
def planted(db_session: Session, project: Project, make_user: Callable[..., User]) -> Planted:
    owners: dict[str, User] = {}
    for name in scripted()["owners"]:
        user = make_user(role=DefaultRole.BUSINESS_ANALYST)
        user.full_name = name
        owners[name] = user
    db_session.commit()
    result = load(db_session, project, owners)
    run = AnalysisRun(
        project_id=project.id,
        scope=AnalysisScope.DOCUMENT,
        subject_id=project.id,
        status=AnalysisRunStatus.DONE,
    )
    db_session.add(run)
    db_session.flush()
    for finding in result.findings.values():
        finding.analysis_run_id = run.id
    db_session.commit()
    return result


def expected(planted: Planted) -> dict[frozenset[str], set[str]]:
    """Label pair → owner names, for every auto-issue-worthy planted pair."""
    owner_of = {label: name for name, items in scripted()["owners"].items() for label in items}
    result = {}
    for row in labels():
        if row["category"] not in AUTO:
            continue
        owners = {owner_of.get(row["r1"]), owner_of.get(row["r2"])} - {None}
        if len(owners) >= 2:
            result[frozenset((row["r1"], row["r2"]))] = {o for o in owners if o}
    return result


def run_of(db: Session) -> AnalysisRun:
    run = db.scalar(select(AnalysisRun))
    assert run is not None
    return run


def test_every_two_owner_conflict_gets_one_issue_for_both(
    planted: Planted, db_session: Session
) -> None:
    opened = ConflictIssueOpener(db_session).on_run(run_of(db_session))

    want = expected(planted)
    assert len(want) == 10  # 8 planted conflicts and 2 duplicates span two owners
    got: dict[frozenset[str], set[str]] = {}
    for issue in opened:
        view = issues.view(db_session, issue)
        got[frozenset(r.source_req_id or "" for r in view.requirements)] = {
            u.full_name for u in view.assignees
        }
        assert issue.auto and "auto" in issue.labels
    assert got == want


def test_categories_and_single_owner_pairs_without_issues(
    planted: Planted, db_session: Session
) -> None:
    ConflictIssueOpener(db_session).on_run(run_of(db_session))
    issue_findings = {i.finding_id for i in db_session.scalars(select(Issue))}
    for key, finding in planted.findings.items():
        if finding.id in issue_findings:
            assert finding.category in (FindingCategory.CONFLICTING, FindingCategory.DUPLICATE)
            assert key in expected(planted)
        else:
            assert key not in expected(planted)


def test_analysing_again_opens_nothing_new(planted: Planted, db_session: Session) -> None:
    opener = ConflictIssueOpener(db_session)
    opener.on_run(run_of(db_session))
    opener.on_run(run_of(db_session))
    numbers = list(db_session.scalars(select(Issue.number).order_by(Issue.number)))
    assert numbers == list(range(1, 11))
