"""Impact, checks, findings delta and risk of a change request (Madhav — US-11, US-34).

The fixture graph, seen from REQ-014 (the requirement being changed)::

    REQ-031 ──conflict── REQ-014 ◀──depends on── REQ-040 (confirmed)
       │                   ?  (ambiguous wording)
    conflict
       │
    REQ-050   (two steps away)

The probe classifies the proposed text against REQ-031, then REQ-040 (the direct relations in
order), then on its own; scripted replies follow that order.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.classification.budget import CountingBudget
from app.classification.llm_client import FakeTransport, LLMClient
from app.consequences import tasks
from app.consequences.impact import ImpactAnalyzer
from app.core.permissions import DefaultRole
from app.models import (
    CandidatePair,
    ChangeRequest,
    ConsequenceReport,
    Finding,
    FindingCategory,
    FindingStatus,
    Project,
    Requirement,
    RequirementState,
    User,
)
from tests.analysis_helpers import pair_reply, single_reply
from tests.api.conftest import headers_for

PROPOSED = "Sessions shall end after 5 minutes of inactivity."


class Graph:
    def __init__(
        self,
        db: Session,
        project: Project,
        make_user: Callable[..., User],
        make: Callable[..., Requirement],
    ) -> None:
        self.db, self.project = db, project
        self.asha = make_user(role=DefaultRole.BUSINESS_ANALYST)
        self.ravi = make_user(role=DefaultRole.DEVELOPER)
        approved = RequirementState.APPROVED

        def req(n: int, owner: User, group: str) -> Requirement:
            return make(
                f"Requirement {n}.",
                source_req_id=f"REQ-{n:03d}",
                state=approved,
                owner_id=owner.id,
                stakeholder_group=group,
            )

        self.r14 = req(14, self.asha, "Security")
        self.r31 = req(31, self.ravi, "Mobile")
        self.r40 = req(40, self.ravi, "Mobile")
        self.r50 = req(50, self.asha, "Security")
        self.conflict = self.pair_finding(self.r14, self.r31, FindingCategory.CONFLICTING)
        self.dependency = self.pair_finding(
            self.r40, self.r14, FindingCategory.DEPENDENT, depends=True
        )
        self.dependency.status = FindingStatus.CONFIRMED
        self.far = self.pair_finding(self.r31, self.r50, FindingCategory.CONFLICTING)
        self.vague = Finding(
            project_id=project.id,
            requirement_id=self.r14.id,
            category=FindingCategory.AMBIGUOUS,
            confidence=0.8,
            rationale="vague",
            original_ai_output={},
        )
        db.add(self.vague)
        db.commit()

    def pair_finding(
        self, a: Requirement, b: Requirement, category: FindingCategory, *, depends: bool = False
    ) -> Finding:
        first, second = CandidatePair.ordered(a.id, b.id)
        pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
        self.db.add(pair)
        self.db.flush()
        direction = None
        if depends:  # ``a`` depends on ``b``, stated in the pair's own order
            direction = "A_depends_on_B" if first == a.id else "B_depends_on_A"
        finding = Finding(
            project_id=self.project.id,
            candidate_pair_id=pair.id,
            category=category,
            confidence=0.9,
            rationale="r",
            original_ai_output={"dependency_direction": direction},
        )
        self.db.add(finding)
        self.db.commit()
        return finding

    def request(self, *, kind: str = "modify") -> ChangeRequest:
        cr = ChangeRequest(
            project_id=self.project.id,
            requirement_id=self.r14.id,
            number=1,
            proposer_id=self.ravi.id,
            kind=kind,
            base_version=1,
            proposed_body=PROPOSED if kind == "modify" else None,
            reason="The bank asks for 5 minutes",
        )
        self.db.add(cr)
        self.db.commit()
        return cr

    def build(self, cr: ChangeRequest, llm: LLMClient | None) -> ConsequenceReport:
        report = tasks.build_report(self.db, cr.id, llm, None)
        assert report is not None
        return report


@pytest.fixture
def g(
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
    make_requirement: Callable[..., Requirement],
) -> Graph:
    return Graph(db_session, project, make_user, make_requirement)


def llm(*replies: str, allowance: int | None = None) -> LLMClient:
    budget = CountingBudget(allowance) if allowance is not None else None
    return LLMClient(FakeTransport(list(replies)), budget)


def checks_of(report: ConsequenceReport) -> dict[str, tuple[str, str]]:
    return {c["key"]: (c["status"], c["message"]) for c in report.checks}


def delta_of(report: ConsequenceReport) -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    return {
        part: sorted((e["category"], tuple(e["labels"])) for e in entries)
        for part, entries in report.findings_delta.items()
    }


# ── impact (US-11) ──────────────────────────────────────────────────────────────────────────
def test_impact_lists_affected_requirements_owners_and_reasons(g: Graph) -> None:
    impact = ImpactAnalyzer(g.db).analyse(g.r14)

    by_label = {a.label: a for a in impact.affected}
    assert [(a.label, a.depth) for a in impact.affected] == [
        ("REQ-031", 1),
        ("REQ-040", 1),
        ("REQ-050", 2),
    ]
    assert (
        by_label["REQ-031"].reason
        == "REQ-031 conflicts with REQ-014 today; the new text may resolve or change that"
    )
    assert by_label["REQ-040"].reason == "REQ-040 depends on REQ-014: it relies on what changes"
    assert by_label["REQ-050"].reason == "Two steps away: REQ-031 conflicts with REQ-050"
    assert (by_label["REQ-040"].status, by_label["REQ-031"].status) == ("confirmed", "potential")
    assert impact.owners == [g.asha.id, g.ravi.id]
    assert impact.stakeholder_groups == ["Mobile", "Security"]
    assert impact.work_items == []


def test_impact_of_a_deprecation_names_the_broken_dependency(g: Graph) -> None:
    impact = ImpactAnalyzer(g.db).analyse(g.r14, kind="deprecate")
    reasons = {a.label: a.reason for a in impact.affected}
    assert reasons["REQ-040"] == "REQ-040 depends on REQ-014, which this request deprecates"


# ── checks, delta, risk (US-34) ─────────────────────────────────────────────────────────────
def test_a_change_that_resolves_one_conflict_and_creates_another(g: Graph) -> None:
    cr = g.request()
    report = g.build(cr, llm(pair_reply("None"), pair_reply("Conflicting"), single_reply("None")))

    checks = checks_of(report)
    assert checks["stale"][0] == "pass"
    assert checks["protected"][0] == "pass"
    assert checks["dependency"] == ("warning", "REQ-040 depends on REQ-014: check they still hold")
    assert checks["new_conflicts"] == ("fail", "The new text conflicts with REQ-040")
    assert checks["duplicates"][0] == checks["wording"][0] == "pass"
    assert delta_of(report) == {
        "resolved": sorted(
            [
                ("Ambiguous", ("REQ-014",)),
                ("Conflicting", _order(g.r14, g.r31)),
                ("Dependent", _order(g.r40, g.r14)),
            ]
        ),
        "new": [("Conflicting", ("REQ-014", "REQ-040"))],
        "still_open": [("Conflicting", _order(g.r31, g.r50))],
        "must_rerun": [("conflict", ("REQ-014", "REQ-050"))],
    }
    assert report.risk_level == "high"
    assert "The new text conflicts with REQ-040" in report.risk_reasons
    assert report.llm_calls == 3
    g.db.refresh(cr)
    assert (cr.checks_proposal_revision, cr.checks_base_version) == (1, 1)


def _order(a: Requirement, b: Requirement) -> tuple[str, ...]:
    """Labels in the stored pair's order (the canonical id order)."""
    first, _ = CandidatePair.ordered(a.id, b.id)
    pair = (a, b) if first == a.id else (b, a)
    return (pair[0].source_req_id or "", pair[1].source_req_id or "")


def test_without_a_model_nothing_pretends_to_have_run(g: Graph) -> None:
    report = g.build(g.request(), None)

    checks = checks_of(report)
    assert checks["new_conflicts"] == (
        "info",
        "No analysis model is configured, so this was not checked",
    )
    assert checks["wording"][0] == "info"
    delta = delta_of(report)
    assert delta["resolved"] == [] and delta["new"] == []
    assert len(delta["must_rerun"]) == 4  # the three open findings on REQ-014 and REQ-050
    assert (
        report.risk_level == "medium"
    )  # the dependency warning; checks that did not run are no risk
    assert report.llm_calls == 0


def test_a_deprecation_resolves_its_findings_and_breaks_its_dependants(g: Graph) -> None:
    report = g.build(g.request(kind="deprecate"), llm())

    checks = checks_of(report)
    assert checks["dependency"] == (
        "fail",
        "REQ-040 depends on REQ-014: deprecating it breaks them",
    )
    assert checks["new_conflicts"][0] == checks["wording"][0] == "info"
    delta = delta_of(report)
    assert len(delta["resolved"]) == 3 and delta["new"] == []
    assert report.risk_level == "high" and report.llm_calls == 0


def test_out_of_budget_the_checks_wait(g: Graph) -> None:
    report = g.build(g.request(), llm(pair_reply("None"), allowance=1))

    checks = checks_of(report)
    assert checks["new_conflicts"][0] == "pending"
    assert checks["wording"][0] == "pending"
    delta = delta_of(report)
    assert delta["resolved"] == [("Conflicting", _order(g.r14, g.r31))]
    assert {c for c, _ in delta["must_rerun"]} == {"Ambiguous", "Dependent", "conflict"}


def test_a_protected_requirement_is_high_risk(g: Graph) -> None:
    g.r40.is_protected = True
    g.db.commit()
    report = g.build(g.request(), None)
    assert checks_of(report)["protected"][0] == "warning"
    assert report.risk_level == "high"


def test_a_request_behind_the_requirement_fails_the_stale_check(g: Graph) -> None:
    cr = g.request()
    g.r14.current_version = 2
    g.db.commit()
    report = g.build(cr, None)
    assert checks_of(report)["stale"] == (
        "fail",
        "REQ-014 is at v2 now; this request was written against v1: update it",
    )


def test_a_report_goes_stale_when_the_baseline_or_proposal_moves(g: Graph) -> None:
    cr = g.request()
    report = g.build(cr, None)
    assert tasks.refresh_staleness(g.db, report, cr) is False

    g.project.baseline_revision += 1
    g.db.commit()
    assert tasks.mark_stale(g.db, g.project.id) == 1
    g.db.refresh(report)
    assert report.is_stale

    fresh = g.build(cr, None)
    cr.proposal_revision = 2
    g.db.commit()
    assert tasks.stale_reasons(fresh, cr, g.r14, g.project) == [
        "the proposal was edited since the checks ran"
    ]
    assert tasks.refresh_staleness(g.db, fresh, cr) is True


def test_a_decided_request_is_not_checked(g: Graph) -> None:
    cr = g.request()
    cr.status = "merged"
    g.db.commit()
    assert tasks.build_report(g.db, cr.id, None, None) is None


# ── routes ──────────────────────────────────────────────────────────────────────────────────
def test_opening_queues_the_checks_and_the_page_reads_them(
    g: Graph, client: TestClient, followups: list[tuple[str, list[str]]]
) -> None:
    opened = client.post(
        f"/api/v1/requirements/{g.r14.id}/change-requests",
        json={"proposed_body": PROPOSED, "reason": "The bank asks for 5 minutes"},
        headers=headers_for(g.ravi),
    ).json()
    draft = client.post(
        f"/api/v1/requirements/{g.r31.id}/change-requests",
        json={"proposed_body": "Changed.", "reason": "Later", "draft": True},
        headers=headers_for(g.ravi),
    ).json()
    url = f"/api/v1/change-requests/{opened['id']}/checks"

    pending = client.get(url, headers=headers_for(g.ravi)).json()
    tasks.build_report(g.db, opened["id"], None, None)
    done = client.get(url, headers=headers_for(g.ravi)).json()
    rerun = client.post(f"{url}/rerun", headers=headers_for(g.ravi))

    assert followups.count(("consequence.build", [opened["id"]])) == 2  # opened, then re-run
    assert ("consequence.build", [draft["id"]]) not in followups
    assert pending == {"state": "pending", "stale_reasons": [], "report": None}
    assert done["state"] == "done" and done["report"]["risk_level"] == "medium"
    assert {c["key"] for c in done["report"]["checks"]} == {
        "stale", "protected", "dependency", "new_conflicts", "duplicates", "wording"
    }  # fmt: skip
    assert rerun.status_code == 202


def test_impact_route(g: Graph, client: TestClient) -> None:
    body = client.get(f"/api/v1/requirements/{g.r14.id}/impact", headers=headers_for(g.ravi)).json()
    assert [a["label"] for a in body["affected"]] == ["REQ-031", "REQ-040", "REQ-050"]
    assert body["owners"] == [str(g.asha.id), str(g.ravi.id)]
