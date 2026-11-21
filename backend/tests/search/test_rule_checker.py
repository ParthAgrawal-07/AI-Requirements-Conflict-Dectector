"""Rule-based cross-checks (Heet — US-58, FR-101, NFR-37): conflicts the similarity filter misses."""

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.classification.llm_client import FakeTransport, LLMClient
from app.classification.tasks import classify_candidate_pair
from app.core.permissions import DefaultRole
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    CandidatePair,
    ClassificationStatus,
    Document,
    DocumentFormat,
    Finding,
    Issue,
    Project,
    Requirement,
    RequirementAttribute,
    RequirementState,
    Severity,
    User,
    Workspace,
)
from app.realtime import bus
from app.search import rule_checker
from app.search.rule_checker import RuleChecker, human, index_requirement
from app.services import analysis_orchestrator
from app.services.users import create_user
from tests.analysis_helpers import pair_reply
from tests.conftest import _run_migrations


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    published: list[Any] = []
    monkeypatch.setattr(bus, "publish", published.append)
    return published


@pytest.fixture
def req(make_requirement: Callable[..., Requirement]) -> Callable[..., Requirement]:
    counter = iter(range(1, 100))

    def factory(body: str, **kwargs: object) -> Requirement:
        number = next(counter)
        return make_requirement(body, source_req_id=f"REQ-{number:03d}", order_index=number,
                                **kwargs)  # fmt: skip

    return factory


def rule_findings(db: Session) -> list[Finding]:
    return list(db.scalars(select(Finding).where(Finding.source == "rule")))


def check(db: Session, *requirements: Requirement) -> list[Finding]:
    return RuleChecker(db).check_all(requirements)


def test_different_limits_for_the_same_measure(
    db_session: Session, req: Callable[..., Requirement]
) -> None:
    kept = req("Statements are kept for 7 years.")
    deleted = req("Statements are deleted after 5 years.")

    (finding,) = check(db_session, kept, deleted)

    assert (finding.source, finding.rule_id, finding.category.value) == (
        "rule",
        "numeric_limit",
        "Conflicting",
    )
    assert finding.severity is Severity.MEDIUM
    assert finding.rationale == (
        "REQ-001 sets the retention for statement to 7 years; REQ-002 sets it to 5 years. "
        "Both cannot hold."
    )
    assert finding.explanation and finding.explanation.startswith("Rule check")
    pair = db_session.get(CandidatePair, finding.candidate_pair_id)
    # The embedding filter never proposed this pair: the AI has not classified it.
    assert pair is not None and pair.classification_status is ClassificationStatus.PENDING


@pytest.mark.parametrize(
    ("first", "second", "rule"),
    [
        ("The session shall expire after 30 minutes of inactivity.",
         "The session shall time out after 5 minutes.", "numeric_limit"),
        ("The system shall not store card numbers.",
         "The system shall store card numbers for refunds.", "negation"),
        ("Only administrators shall approve refunds.", "Support agents shall approve refunds.",
         "actor"),
        ("When a payment fails, the system shall retry the payment.",
         "When a payment fails, the system shall cancel the payment.", "condition_overlap"),
    ],
)  # fmt: skip
def test_each_rule(
    db_session: Session, req: Callable[..., Requirement], first: str, second: str, rule: str
) -> None:
    findings = check(db_session, req(first), req(second))
    assert [f.rule_id for f in findings] == [rule]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Passwords shall be at least 12 characters long.",
         "Passwords shall be at most 64 characters long."),  # a range, not a conflict
        ("Support agents shall approve refunds.", "Administrators shall approve refunds."),
        ("The system shall log failed logins.", "The system shall email the security team."),
        ("Sessions shall time out after 30 minutes.", "Sessions shall end after 1800 seconds."),
    ],
)  # fmt: skip
def test_no_finding_without_a_contradiction(
    db_session: Session, req: Callable[..., Requirement], first: str, second: str
) -> None:
    assert check(db_session, req(first), req(second)) == []


def test_checks_are_idempotent_and_see_each_pair_once(
    db_session: Session, req: Callable[..., Requirement]
) -> None:
    kept = req("Statements are kept for 7 years.")
    deleted = req("Statements are deleted after 5 years.")
    check(db_session, kept, deleted)
    check(db_session, deleted, kept)
    RuleChecker(db_session).check(kept)

    assert len(rule_findings(db_session)) == 1
    assert db_session.scalar(select(func.count()).select_from(RequirementAttribute)) == 2


def test_rejected_and_deprecated_requirements_are_not_compared(
    db_session: Session, req: Callable[..., Requirement]
) -> None:
    kept = req("Statements are kept for 7 years.")
    old = req("Statements are deleted after 5 years.", state=RequirementState.DEPRECATED)
    assert check(db_session, kept, old) == []


def test_a_new_version_is_read_again(db_session: Session, req: Callable[..., Requirement]) -> None:
    requirement = req("Statements are kept for 7 years.")
    first = index_requirement(db_session, requirement)
    requirement.body, requirement.current_version = "Statements are kept for 10 years.", 2
    second = index_requirement(db_session, requirement)
    assert (first.version_no, first.value != second.value, second.version_no) == (1, True, 2)


def test_the_ai_never_removes_a_rule_finding(
    db_session: Session, req: Callable[..., Requirement]
) -> None:
    kept = req("Statements are kept for 7 years.")
    deleted = req("Statements are deleted after 5 years.")
    (finding,) = check(db_session, kept, deleted)
    assert finding.candidate_pair_id is not None

    llm = LLMClient(FakeTransport([pair_reply("None")]))
    classify_candidate_pair(db_session, finding.candidate_pair_id, llm)

    db_session.refresh(finding)
    assert not finding.is_stale and finding.source == "rule"
    pair = db_session.get(CandidatePair, finding.candidate_pair_id)
    assert pair is not None and pair.classification_status is ClassificationStatus.DONE


def test_the_ai_may_flag_the_same_pair_beside_the_rule(
    db_session: Session, req: Callable[..., Requirement]
) -> None:
    (rule,) = check(db_session, req("Statements are kept for 7 years."),
                    req("Statements are deleted after 5 years."))  # fmt: skip
    assert rule.candidate_pair_id is not None
    ai = classify_candidate_pair(
        db_session, rule.candidate_pair_id, LLMClient(FakeTransport([pair_reply("Conflicting")]))
    )
    assert ai is not None and ai.source == "ai"


def test_the_llm_reads_only_what_the_patterns_cannot(
    db_session: Session, req: Callable[..., Requirement]
) -> None:
    reply = ('{"entity": "statement", "metric": "retention", "value": null, "unit": null, '
             '"comparison": null, "actor": null, "action": "purge statement", "condition": null, '
             '"modality": "shall", "confidence": 0.6}')  # fmt: skip
    transport = FakeTransport([reply])
    llm = LLMClient(transport)
    parsed = index_requirement(db_session, req("The system shall log every login."), llm=llm)
    fallback = index_requirement(db_session, req("Old statements: gone."), llm=llm)
    assert (parsed.extractor, fallback.extractor, len(transport.calls)) == ("rules", "llm", 1)


def test_values_read_like_people_write_them() -> None:
    assert human(1800, "s") == "30 minutes"
    assert human(2, "s", "<=") == "at most 2 seconds"
    assert human(5e9, "B") == "5 GB"
    assert human(12, "chars", ">=") == "at least 12 characters"


def test_after_a_run_rule_conflicts_between_two_owners_open_an_issue(
    db_session: Session,
    req: Callable[..., Requirement],
    make_user: Callable[..., User],
    events: list[Any],
) -> None:
    asha, ravi = make_user(role=DefaultRole.DEVELOPER), make_user(role=DefaultRole.DEVELOPER)
    kept = req("Statements are kept for 7 years.", owner_id=asha.id)
    req("Statements are deleted after 5 years.", owner_id=ravi.id)
    run = AnalysisRun(
        project_id=kept.project_id,
        scope=AnalysisScope.DOCUMENT,
        subject_id=kept.document_id,
        status=AnalysisRunStatus.DONE,
    )
    db_session.add(run)
    db_session.commit()

    analysis_orchestrator.after_run(db_session, run.id)

    (finding,) = rule_findings(db_session)
    assert finding.analysis_run_id == run.id
    issue = db_session.scalar(select(Issue).where(Issue.finding_id == finding.id))
    assert issue is not None and issue.auto
    edges = [e for ev in events if ev.type == "graph.delta" for e in ev.data["added"]["edges"]]
    assert [e["found_by"] for e in edges] == ["rule"]


def test_on_run_ignores_consequence_runs(
    db_session: Session, req: Callable[..., Requirement]
) -> None:
    requirement = req("Statements are kept for 7 years.")
    run = AnalysisRun(project_id=requirement.project_id, scope=AnalysisScope.CHANGE_REQUEST,
                      subject_id=requirement.id, status=AnalysisRunStatus.DONE)  # fmt: skip
    db_session.add(run)
    db_session.commit()
    assert rule_checker.on_run(db_session, run) == []


def test_two_runs_checking_one_pair_at_once_share_it(scratch_engine: Engine) -> None:
    """Real concurrency (found by the CP2 load test): two posts a moment apart are checked by two
    runs; the first has created their pair but not committed when the second needs it. The second
    waits and reuses the row — before, it failed and lost every finding of its run."""
    _run_migrations(scratch_engine)
    with Session(scratch_engine) as setup:
        workspace = Workspace(name="Race")
        setup.add(workspace)
        setup.commit()
        project = Project(workspace_id=workspace.id, name="Race")
        setup.add(project)
        setup.commit()
        author = create_user(
            setup,
            email="race@example.com",
            password="correct-horse-battery-staple",
            full_name="Race",
        )
        document = Document(
            workspace_id=workspace.id,
            project_id=project.id,
            uploaded_by=author.id,
            filename="srs.docx",
            format=DocumentFormat.DOCX,
            size_bytes=1,
            sha256="0" * 64,
            storage_path="srs.docx",
        )
        setup.add(document)
        setup.commit()
        bodies = (
            "The service shall respond within 1 second.",
            "The service shall respond within 5 seconds.",
        )
        rows = [
            Requirement(document_id=document.id, project_id=project.id, body=body, order_index=i)
            for i, body in enumerate(bodies)
        ]
        setup.add_all(rows)
        setup.commit()
        ids = [row.id for row in rows]

    with Session(scratch_engine) as first, Session(scratch_engine) as second:
        earlier = rule_checker._pair(first, *(first.get_one(Requirement, i) for i in ids))

        def commit_once_the_other_waits() -> None:
            with scratch_engine.connect() as probe:
                for _ in range(200):
                    waiting = probe.scalar(
                        text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'")
                    )
                    if waiting:
                        break
                    time.sleep(0.05)
            first.commit()

        committer = threading.Thread(target=commit_once_the_other_waits)
        committer.start()
        later = rule_checker._pair(second, *(second.get_one(Requirement, i) for i in reversed(ids)))
        committer.join(timeout=30)
        assert later.id == earlier.id


def test_the_existing_rule_finding_is_found_through_its_index(db_session: Session) -> None:
    """Every conflicting pair is looked up twice; a predicate the partial index cannot prove made
    each lookup scan the whole findings table (found profiling a 500-requirement document)."""
    query = rule_checker.live_rule_finding(uuid.uuid4(), "numeric_limit")
    compiled = query.compile(
        dialect=db_session.get_bind().dialect, compile_kwargs={"literal_binds": True}
    )
    db_session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = " ".join(db_session.scalars(text(f"EXPLAIN {compiled}")))
    assert "uq_findings_live_rule" in plan, plan


def test_two_runs_indexing_one_version_at_once_share_its_attributes(
    scratch_engine: Engine,
) -> None:
    """Real concurrency: a re-analysis while an upload is analysed indexes the same version
    twice. The second waits and reuses the row — before, it failed and lost its run's checks."""
    _run_migrations(scratch_engine)
    with Session(scratch_engine) as setup:
        workspace = Workspace(name="Race")
        setup.add(workspace)
        setup.commit()
        project = Project(workspace_id=workspace.id, name="Race")
        setup.add(project)
        setup.commit()
        author = create_user(
            setup,
            email="race@example.com",
            password="correct-horse-battery-staple",
            full_name="Race",
        )
        document = Document(
            workspace_id=workspace.id, project_id=project.id, uploaded_by=author.id,
            filename="srs.docx", format=DocumentFormat.DOCX, size_bytes=1, sha256="0" * 64,
            storage_path="srs.docx",
        )  # fmt: skip
        setup.add(document)
        setup.commit()
        requirement = Requirement(
            document_id=document.id, project_id=project.id, order_index=0,
            body="The service shall respond within 2 seconds.",
        )  # fmt: skip
        setup.add(requirement)
        setup.commit()
        requirement_id = requirement.id

    with Session(scratch_engine) as first, Session(scratch_engine) as second:
        earlier = index_requirement(first, first.get_one(Requirement, requirement_id))

        def commit_once_the_other_waits() -> None:
            with scratch_engine.connect() as probe:
                for _ in range(200):
                    waiting = probe.scalar(
                        text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'")
                    )
                    if waiting:
                        break
                    time.sleep(0.05)
            first.commit()

        committer = threading.Thread(target=commit_once_the_other_waits)
        committer.start()
        later = index_requirement(second, second.get_one(Requirement, requirement_id))
        committer.join(timeout=30)
        assert later.id == earlier.id
