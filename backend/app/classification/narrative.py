"""The AI narrative of a consequence report (Keval — US-34, FR-99, DR-21; ADR-31).

A short summary of a change request's consequence report for the people who decide on it,
written by the LLM **from the structured report only**: the checks, the risk level and its
reasons, the findings delta and the affected requirements — IDs, labels and template sentences,
never requirement text (``prompts/narrative_v1_*.md``). It is shown labelled *AI*, next to the
report it summarises.

**It never contradicts the checks.** Every reply goes through :func:`contradictions`, a
deterministic guard, before it is kept:

* every ID it names (or cites) is in the report;
* the risk level it states is the report's;
* every failing check is mentioned (by its title or one of the IDs it names);
* it never says "verified", "guaranteed" or "safe to merge", and says "no issues" / "no
  conflicts" / "all checks passed" only when every check passed and the risk is low.

A reply that breaks a rule is re-asked once with the reasons; if it still does, or the model is
unavailable or over budget, there is no narrative — the report stands on its own and the page
says the summary is unavailable. The narrative never changes the report.
"""

import json
import logging
import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.classification.budget import BudgetExceededError
from app.classification.llm_client import LLMClient, LLMError
from app.classification.prompting import _as_data, _schema_json, load_prompt
from app.models import ChangeRequest, ConsequenceReport, Requirement

logger = logging.getLogger(__name__)

NARRATIVE_VERSION = "narrative-v1"
ATTEMPTS = 2
_ID = re.compile(r"\b(?:REQ|RCR|ISS)-\d+\b")
_RISK = re.compile(
    r"\b(low|medium|high)(?:[- ]risk\b|\s+risk\b)|\brisk(?: level)? (?:is |of )?(low|medium|high)\b",
    re.IGNORECASE,
)
_NEVER = ("verified", "guaranteed", "safe to merge", "safe to approve", "risk-free", "risk free")
_REASSURING = (
    "no issues",
    "no issue",
    "no conflicts",
    "no conflict",
    "no problems",
    "no risk",
    "nothing to worry",
    "all checks passed",
    "all checks pass",
)


class NarrativeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=20, max_length=700, description="Two to four sentences")
    points: list[str] = Field(default_factory=list, max_length=5, description="Key points")
    cited_ids: list[str] = Field(default_factory=list, description="Every ID the summary names")


def facts(report: ConsequenceReport) -> dict[str, Any]:
    """The report as the model sees it: ids, statuses and template sentences only."""
    return {
        "risk_level": report.risk_level,
        "risk_reasons": list(report.risk_reasons),
        "checks": [
            {"title": c["title"], "status": c["status"], "message": c["message"]}
            for c in report.checks
        ],
        "findings_delta": {
            part: [
                {"category": e["category"], "ids": e["labels"], "reason": e["reason"]}
                for e in entries
            ]
            for part, entries in report.findings_delta.items()
        },
        "affected": [
            {
                "id": a["label"],
                "relation": a["relation"],
                "depth": a["depth"],
                "reason": a["reason"],
                "status": a["status"],
            }
            for a in report.affected
        ],
    }


def known_ids(report: ConsequenceReport, *extra: str) -> set[str]:
    text = json.dumps(facts(report))
    return {*_ID.findall(text), *extra}


def contradictions(
    output: NarrativeOutput, report: ConsequenceReport, *, known: set[str]
) -> list[str]:
    """Why ``output`` disagrees with ``report`` (empty when it does not)."""
    text = " ".join([output.summary, *output.points])
    lowered = text.lower()
    problems: list[str] = []
    unknown = sorted({*_ID.findall(text), *output.cited_ids} - known)
    if unknown:
        problems.append(f"names IDs that are not in the report: {', '.join(unknown)}")
    for match in _RISK.finditer(text):
        stated = (match.group(1) or match.group(2) or "").lower()
        if stated and stated != report.risk_level:
            problems.append(f"says the risk is {stated}; the report says {report.risk_level}")
            break
    for check in report.checks:
        if check["status"] != "fail":
            continue
        named = _ID.findall(check["message"])
        if check["title"].lower() not in lowered and not any(i in text for i in named):
            problems.append(f"does not mention the failed check {check['title']!r}")
    banned = [p for p in _NEVER if p in lowered]
    if banned:
        problems.append(f"uses words the report cannot support: {', '.join(banned)}")
    all_clear = report.risk_level == "low" and all(c["status"] == "pass" for c in report.checks)
    if not all_clear:
        reassuring = [p for p in _REASSURING if re.search(rf"\b{re.escape(p)}\b", lowered)]
        if reassuring:
            problems.append(f"reassures although checks did not all pass: {', '.join(reassuring)}")
    return problems


def write(
    report: ConsequenceReport,
    *,
    change_request_key: str,
    requirement_label: str,
    llm: LLMClient,
    project_id: uuid.UUID | None,
) -> tuple[dict[str, Any] | None, int]:
    """The narrative for ``report`` (or ``None``) and the LLM calls it took."""
    system = load_prompt("narrative_system", "v1").substitute(schema=_schema_json(NarrativeOutput))
    user = load_prompt("narrative_user", "v1").substitute(
        change_request=change_request_key,
        requirement=requirement_label,
        report=_as_data(json.dumps(facts(report), indent=2)),
    )
    known = known_ids(report, change_request_key, requirement_label)
    calls = 0
    for _ in range(ATTEMPTS):
        before = llm.calls
        try:
            output = llm.complete_json(system, user, NarrativeOutput, project_id=project_id)
        except (BudgetExceededError, LLMError) as error:
            calls += llm.calls - before
            logger.info("No narrative for report %s: %s", report.id, type(error).__name__)
            return None, calls
        calls += llm.calls - before
        problems = contradictions(output, report, known=known)
        if not problems:
            return (
                {
                    "label": "AI",
                    "summary": output.summary,
                    "points": output.points,
                    "cited_ids": sorted(set(output.cited_ids) | set(_ID.findall(output.summary))),
                    "prompt_version": NARRATIVE_VERSION,
                    "model": llm.model,
                },
                calls,
            )
        logger.info("Narrative for report %s rejected: %s", report.id, "; ".join(problems))
        user += (
            "\n\nYour previous answer was rejected because it "
            + "; it ".join(problems)
            + ". Answer again, following every rule."
        )
    return None, calls


def attach(
    db: Session, report: ConsequenceReport, change_request: ChangeRequest, llm: LLMClient
) -> bool:
    """Write the narrative onto ``report`` (best effort). Returns whether one was kept."""
    requirement = db.get(Requirement, change_request.requirement_id)
    label = (requirement.source_req_id if requirement else None) or "the requirement"
    narrative, calls = write(
        report,
        change_request_key=f"RCR-{change_request.number}",
        requirement_label=label,
        llm=llm,
        project_id=change_request.project_id,
    )
    report.narrative = narrative
    report.llm_calls += calls
    db.commit()
    return narrative is not None
