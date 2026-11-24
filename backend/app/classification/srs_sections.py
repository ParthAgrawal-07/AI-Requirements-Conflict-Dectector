"""Section prompts of the updated SRS (Keval — US-61, FR-106, FR-107, NFR-38, DR-25; ADR-29).

The updated SRS follows the ISO/IEC/IEEE 29148 outline. The **system** inserts every approved
requirement verbatim (Bansil, ``app.srs``); the LLM writes only the narrative sections listed in
:data:`NARRATIVE_SECTIONS`, about one call each, from:

==========================  ================================================================
Section                     Inputs (design update §12.4)
==========================  ================================================================
1.1 Purpose, 1.2 Scope      the confirmed project brief (purpose, in and out of scope)
1.3 Definitions             the glossary
2.x Overall description     brief fields (actors, environment, constraints, quality goals,
                            regulations) and the requirements' stakeholder groups
4 Changes since …           the written change log between the two baseline revisions (US-55)
Appendix A Decisions        closed issues: chosen option, decision owner, reason
==========================  ================================================================

Requirements reach the model as IDs and titles for cross-references only — never the text it
might restate. Every reply passes :func:`problems` (DR-25) before it is kept:

* no sentence uses "shall" or "must" unless it cites a baseline requirement ID (a narrative never
  states a requirement of its own);
* every ID it names or cites is one it was given.

A reply that breaks a rule is re-asked once with the reasons; then :class:`SectionUnavailable`
is raised and the generator falls back to the template text for that section (US-41), so a
missing model never blocks the SRS.
"""

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.classification.budget import BudgetExceededError
from app.classification.llm_client import LLMClient, LLMError
from app.classification.prompting import _as_data, _pack, _schema_json, load_prompt

PROMPT_VERSION = "srs-section-v1"
ATTEMPTS = 2
MAX_INSTRUCTION = 500
_ID = re.compile(r"\b[A-Z][A-Z0-9]*-\d+(?:\.\d+)*\b")
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
_NORMATIVE = re.compile(r"\b(shall|must)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SectionSpec:
    key: str  # stable, e.g. "1.2_scope"
    title: str
    inputs: tuple[str, ...]  # which section inputs the generator must supply
    guidance: str  # what the section covers, in one sentence for the prompt


NARRATIVE_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec("1.1_purpose", "1.1 Purpose", ("purpose",),
                "why this specification exists and who it is for"),
    SectionSpec("1.2_scope", "1.2 Scope", ("purpose", "scope_in", "scope_out"),
                "what the product covers and, explicitly, what it does not"),
    SectionSpec("1.3_definitions", "1.3 Definitions, acronyms and abbreviations", ("glossary",),
                "the project's terms as a list, each with its meaning from the glossary"),
    SectionSpec("2.1_product_perspective", "2.1 Product perspective",
                ("purpose", "environment", "actors"),
                "where the product sits among the systems and people around it"),
    SectionSpec("2.2_user_classes", "2.2 User classes and characteristics",
                ("actors", "stakeholder_groups"),
                "the kinds of users and stakeholder groups and what they need"),
    SectionSpec("2.3_operating_environment", "2.3 Operating environment", ("environment",),
                "the platforms and conditions the product runs in"),
    SectionSpec("2.4_constraints", "2.4 Design and implementation constraints",
                ("constraints", "regulations"),
                "the constraints and regulations the design must respect, as background"),
    SectionSpec("2.5_assumptions", "2.5 Assumptions and dependencies",
                ("scope_out", "constraints", "quality_goals"),
                "what the specification assumes to be true and depends on"),
    SectionSpec("4_changes", "4 Changes since the previous version", ("change_log",),
                "what changed since the previous published version, from the change log"),
    SectionSpec("A_decisions", "Appendix A — Decisions", ("decisions",),
                "the conflicts and issues resolved, the option chosen, who decided and why"),
)  # fmt: skip
SPECS = {spec.key: spec for spec in NARRATIVE_SECTIONS}


class SectionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=8000, description="The section text, Markdown")
    cited_ids: list[str] = Field(default_factory=list, description="Every ID the text names")


@dataclass(frozen=True)
class SectionDraft:
    key: str
    body: str
    cited_ids: list[str]
    model: str
    prompt_version: str
    llm_calls: int


class SectionUnavailable(Exception):
    """No acceptable text: the model is unavailable, over budget, or kept breaking the rules."""

    def __init__(self, key: str, reason: str, llm_calls: int) -> None:
        super().__init__(f"Section {key}: {reason}")
        self.key, self.reason, self.llm_calls = key, reason, llm_calls


def problems(
    body: str, cited: list[str], *, known_ids: set[str], baseline_ids: set[str]
) -> list[str]:
    """Why ``body`` may not go into the SRS as narrative (empty when it may)."""
    found: list[str] = []
    unknown = sorted({*_ID.findall(body), *cited} - known_ids)
    if unknown:
        found.append(f"names IDs it was not given: {', '.join(unknown)}")
    normative = [
        s.strip()
        for s in _SENTENCE.findall(body)
        if _NORMATIVE.search(s) and not (set(_ID.findall(s)) & baseline_ids)
    ]
    if normative:
        found.append(
            'uses "shall" or "must" without citing a baseline requirement: '
            + " | ".join(n[:80] for n in normative[:3])
        )
    return found


def write_section(
    llm: LLMClient,
    spec: SectionSpec,
    inputs: dict[str, Any],
    *,
    project_name: str,
    project_id: uuid.UUID,
    context_pack: str,
    known_ids: set[str],
    baseline_ids: set[str],
    instruction: str | None = None,
) -> SectionDraft:
    """One checked narrative section, or :class:`SectionUnavailable`."""
    system = load_prompt("srs_section_system", "v1").substitute(
        section_title=spec.title,
        section_guidance=spec.guidance,
        schema=_schema_json(SectionOutput),
    )
    asked = (instruction or "").strip()[:MAX_INSTRUCTION]
    user = load_prompt("srs_section_user", "v1").substitute(
        context_pack=_pack(context_pack),
        inputs=_as_data(json.dumps({k: inputs.get(k) for k in spec.inputs}, indent=2, default=str)),
        instruction=f"<instruction>\n{_as_data(asked)}\n</instruction>\n" if asked else "",
        section_title=spec.title,
        project_name=_as_data(project_name),
    )
    before = llm.calls
    for _ in range(ATTEMPTS):
        try:
            output = llm.complete_json(system, user, SectionOutput, project_id=project_id)
        except BudgetExceededError:
            raise SectionUnavailable(spec.key, "LLM budget used up", llm.calls - before) from None
        except LLMError as error:
            raise SectionUnavailable(spec.key, type(error).__name__, llm.calls - before) from None
        reasons = problems(output.body, output.cited_ids, known_ids=known_ids,
                           baseline_ids=baseline_ids)  # fmt: skip
        if not reasons:
            return SectionDraft(
                key=spec.key,
                body=output.body,
                cited_ids=sorted(set(output.cited_ids) | set(_ID.findall(output.body))),
                model=llm.model,
                prompt_version=PROMPT_VERSION,
                llm_calls=llm.calls - before,
            )
        user += (
            "\n\nYour previous answer was rejected because it "
            + "; it ".join(reasons)
            + ". Answer again, following every rule."
        )
    raise SectionUnavailable(spec.key, "the text kept breaking the rules", llm.calls - before)
