"""The agreement rules a merge must meet (Parth — US-35, FR-98, FR-65, FR-64, CR-19; §11.3).

``AgreementGuard.unmet(change_request)`` lists every condition that is not met, as
``{code, message}``; empty means the request may be merged. The merge evaluates it inside its
transaction (with the rows locked), and the change request page shows the same list next to a
disabled Merge button, so the two can never disagree.

=========================  =================================================================
``code``                   condition
=========================  =================================================================
``not_open``               the request is open or approved (not a draft, not decided)
``needs_update``           its base version is still the requirement's current version
``checks_pending``         the consequence checks ran on this proposal revision and base
                           version, and their report is not stale
``approvals_missing``      ``projects.required_approvals`` people other than the proposer
                           approved this proposal revision
``reviewer_missing``       every required reviewer (the owner, owners in direct conflict)
                           approved it
``compliance_missing``     a compliance reviewer approved it, when the requirement is protected
``changes_requested``      no reviewer's latest review of this revision asks for changes
``high_finding_open``      no High-severity finding is open on the requirement, unless the
                           merger records an accepted risk with a reason
=========================  =================================================================

Reviews of an earlier proposal revision count for nothing here: they were dismissed by the edit.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.consequences import tasks as consequence_tasks
from app.models import ChangeRequest, Project, Requirement
from app.models.change_request import APPROVED, OPEN
from app.models.change_review import APPROVE, REQUEST_CHANGES
from app.services import lifecycle, reviews


@dataclass(frozen=True)
class Unmet:
    code: str
    message: str

    def as_json(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class AgreementGuard:
    def __init__(self, db: Session) -> None:
        self.db = db

    def approved_by_policy(self, change_request: ChangeRequest) -> bool:
        """The review part only: is the request *approved* (before the merge-time checks)?"""
        return not {
            u.code
            for u in self.unmet(change_request)
            if u.code
            in ("approvals_missing", "reviewer_missing", "compliance_missing", "changes_requested")
        }

    def unmet(self, change_request: ChangeRequest, *, accepted_risk: bool = False) -> list[Unmet]:
        db = self.db
        requirement = db.get(Requirement, change_request.requirement_id)
        project = db.get(Project, change_request.project_id)
        if requirement is None or project is None:  # pragma: no cover
            return [Unmet("not_open", "The requirement is gone")]
        unmet: list[Unmet] = []
        label = requirement.source_req_id or "The requirement"

        if change_request.status not in (OPEN, APPROVED):
            unmet.append(
                Unmet(
                    "not_open", f"The change request is {change_request.status.replace('_', ' ')}"
                )
            )
        if change_request.base_version != requirement.current_version:
            unmet.append(
                Unmet(
                    "needs_update",
                    f"{label} is at v{requirement.current_version}; the proposal was written against "
                    f"v{change_request.base_version}",
                )
            )
        report = consequence_tasks.latest_report(db, change_request.id)
        ran_on_this = (
            change_request.checks_proposal_revision,
            change_request.checks_base_version,
        ) == (
            change_request.proposal_revision,
            change_request.base_version,
        )
        if report is None or not ran_on_this:
            unmet.append(Unmet("checks_pending", "The checks have not run on this revision yet"))
        elif consequence_tasks.refresh_staleness(db, report, change_request):
            unmet.append(Unmet("checks_pending", "The checks are stale: run them again"))

        decisions = reviews.current_decisions(db, change_request)
        approvers = {
            reviewer
            for reviewer, r in decisions.items()
            if r.decision == APPROVE and reviewer != change_request.proposer_id
        }
        if len(approvers) < project.required_approvals:
            unmet.append(
                Unmet(
                    "approvals_missing",
                    f"{len(approvers)} of {project.required_approvals} required approval"
                    f"{'s' * (project.required_approvals != 1)} on revision {change_request.proposal_revision}",
                )
            )
        required = [
            r
            for r in reviews.requests_of(db, change_request.id)
            if r.required and r.reason in ("owner", "direct_conflict")
        ]
        missing = [r for r in required if r.reviewer_id not in approvers]
        if missing:
            unmet.append(
                Unmet(
                    "reviewer_missing",
                    f"{len(missing)} required reviewer{'s' * (len(missing) != 1)} "
                    f"(owner or conflicting owner) still to approve",
                )
            )
        if requirement.is_protected:
            compliance = {u.id for u in reviews.holders(db, project, "protected.signoff")}
            if not approvers & compliance:
                unmet.append(
                    Unmet(
                        "compliance_missing",
                        f"{label} is protected: a compliance reviewer must approve",
                    )
                )
        if any(r.decision == REQUEST_CHANGES for r in decisions.values()):
            unmet.append(
                Unmet("changes_requested", "A reviewer asked for changes to this revision")
            )
        if change_request.kind == "modify" and not accepted_risk:
            high = lifecycle.open_high_findings(db, requirement)
            if high:
                unmet.append(
                    Unmet(
                        "high_finding_open",
                        f"{len(high)} High-severity finding{'s' * (len(high) != 1)} open on {label}: "
                        "resolve it or accept the risk with a reason",
                    )
                )
        return unmet
