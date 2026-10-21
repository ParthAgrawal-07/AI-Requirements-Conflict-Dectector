"""Requirement intake routes (Bansil — FR-81).

Sprint 0–1: only the EARS template catalogue, so the composer UI (Pranshu) builds its chips,
slots and live preview from the same definition the backend renders. Posting and drafts arrive
with US-30 (Sprint 3).
"""

from typing import Any

from fastapi import APIRouter

from app.api.deps import Authenticated
from app.intake.ears import templates_as_json

router = APIRouter(tags=["composer"])


@router.get(
    "/composer/templates",
    summary="The EARS sentence templates, their slots and examples",
)
def list_templates(user: Authenticated) -> list[dict[str, Any]]:
    return templates_as_json()
