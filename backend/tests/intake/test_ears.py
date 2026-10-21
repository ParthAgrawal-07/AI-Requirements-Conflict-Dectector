"""EARS templates and the composer field schema (Sprint 0 contract, FR-81, FR-55)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.intake import ComposerFields, DraftFields, EarsTemplate, RequirementDraftRead
from app.intake.ears import EARS_TEMPLATES, MissingSlotsError, render_statement, templates_as_json

SLOTS = {"system": "mobile app", "response": "log the user out"}


@pytest.mark.parametrize(
    ("template", "extra", "sentence"),
    [
        (EarsTemplate.UBIQUITOUS, {}, "The mobile app shall log the user out."),
        (
            EarsTemplate.EVENT_DRIVEN,
            {"trigger": "the user is inactive for 5 minutes"},
            "When the user is inactive for 5 minutes, the mobile app shall log the user out.",
        ),
        (
            EarsTemplate.STATE_DRIVEN,
            {"state": "a transfer is pending"},
            "While a transfer is pending, the mobile app shall log the user out.",
        ),
        (
            EarsTemplate.UNWANTED_BEHAVIOUR,
            {"condition": "the OTP is wrong three times"},
            "If the OTP is wrong three times, then the mobile app shall log the user out.",
        ),
        (
            EarsTemplate.OPTIONAL_FEATURE,
            {"feature": "biometric login is enabled"},
            "Where biometric login is enabled, the mobile app shall log the user out.",
        ),
    ],
)
def test_each_template_renders_its_sentence(
    template: EarsTemplate, extra: dict[str, str], sentence: str
) -> None:
    assert render_statement(template, {**SLOTS, **extra}) == sentence


def test_free_text_is_kept_as_written() -> None:
    statement = "  Audit logs shall be kept for 7 years; see RBI 2021.  "
    assert render_statement(EarsTemplate.FREE_TEXT, {"statement": statement}) == statement.strip()


def test_words_the_pattern_already_has_are_not_doubled() -> None:
    sentence = render_statement(
        EarsTemplate.UBIQUITOUS, {"system": "The  mobile\napp", "response": "shall log out."}
    )
    assert sentence == "The mobile app shall log out."


def test_missing_slots_are_named_in_template_order() -> None:
    with pytest.raises(MissingSlotsError) as raised:
        render_statement(EarsTemplate.EVENT_DRIVEN, {"system": "app", "response": "  "})
    assert raised.value.missing == ["trigger", "response"]


def test_every_example_follows_its_own_pattern() -> None:
    for spec in EARS_TEMPLATES.values():
        prefix = spec.pattern.split("{", 1)[0]
        assert spec.example.startswith(prefix), spec.template


def test_the_ui_catalogue_lists_all_six_choices_with_slots() -> None:
    catalogue = templates_as_json()
    assert [t["chip"] for t in catalogue] == [
        "Always",
        "When…",
        "While…",
        "If…then",
        "Where…",
        "Free text",
    ]
    event = catalogue[1]
    assert [s["key"] for s in event["slots"]] == ["trigger", "system", "response"]  # type: ignore[index, union-attr]


def _composer(**overrides: object) -> ComposerFields:
    data: dict[str, object] = {
        "template": "event_driven",
        "slots": {"trigger": "the user is idle", **SLOTS},
        "type": "functional",
        "priority": "must",
    }
    return ComposerFields.model_validate({**data, **overrides})


def test_a_complete_composer_post_renders_its_statement() -> None:
    fields = _composer(
        acceptance_criteria=[{"given": "a user", "when": "idle 5 min", "then": "logged out"}],
        tags=["session", " session ", "security"],
    )
    assert fields.statement == "When the user is idle, the mobile app shall log the user out."
    assert fields.tags == ["session", "security"]


def test_a_composer_post_with_empty_slots_is_rejected() -> None:
    with pytest.raises(ValidationError, match="trigger"):
        _composer(slots=SLOTS)


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "epic"},
        {"priority": "high"},
        {"surprise": 1},
        {"slots": {"trigger": "x" * 501, **SLOTS}},
        {"acceptance_criteria": [{"given": "a", "when": "b"}]},
    ],
)
def test_invalid_composer_fields_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _composer(**overrides)


def test_a_draft_accepts_partial_fields_and_previews_when_it_can() -> None:
    now = datetime.now(UTC)
    empty = RequirementDraftRead.build(
        id=uuid.uuid4(), project_id=uuid.uuid4(), fields=DraftFields(), updated_at=now
    )
    assert empty.preview is None
    partial = DraftFields(template=EarsTemplate.UBIQUITOUS, slots={"system": "app"})
    assert (
        RequirementDraftRead.build(
            id=uuid.uuid4(), project_id=uuid.uuid4(), fields=partial, updated_at=now
        ).preview
        is None
    )
    full = DraftFields(template=EarsTemplate.UBIQUITOUS, slots=SLOTS)
    assert (
        RequirementDraftRead.build(
            id=uuid.uuid4(), project_id=uuid.uuid4(), fields=full, updated_at=now
        ).preview
        == "The mobile app shall log the user out."
    )
