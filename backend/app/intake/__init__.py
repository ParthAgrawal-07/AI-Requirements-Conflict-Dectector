"""Requirement intake (Bansil): the composer's field schema, EARS templates and drafts.

Sprint 0 contracts, agreed with Pranshu (composer UI) and Keval (EARS wording and lint):

* :mod:`app.intake.ears` — the five EARS templates, their named slots and the sentence renderer
  (FR-81, DR-18);
* :mod:`app.intake.schemas` — the fields a composer post carries (FR-55, FR-81) and the private
  draft that autosaves them.

Posting, drafts persistence (``requirement_drafts``, migration ``0006``) and owners come in
Sprints 2–3 (US-30, US-36).
"""

from app.intake.ears import EARS_TEMPLATES, EarsTemplate, EarsTemplateSpec, render_statement
from app.intake.schemas import (
    AcceptanceCriterion,
    ComposerFields,
    DraftFields,
    Priority,
    RequirementDraftRead,
    RequirementType,
)

__all__ = [
    "EARS_TEMPLATES",
    "AcceptanceCriterion",
    "ComposerFields",
    "DraftFields",
    "EarsTemplate",
    "EarsTemplateSpec",
    "Priority",
    "RequirementDraftRead",
    "RequirementType",
    "render_statement",
]
