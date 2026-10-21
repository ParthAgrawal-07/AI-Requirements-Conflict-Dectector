"""EARS sentence templates (Bansil with Keval — FR-81, DR-18, interface design §5).

EARS (Easy Approach to Requirements Syntax) has five patterns. The composer shows each as a chip
with labelled slots and a live preview; *free text* is allowed but the lint flags it (DR-18).

=====================  ========  ==========================================================
Template               Chip      Sentence
=====================  ========  ==========================================================
``ubiquitous``         Always    The <system> shall <response>.
``event_driven``       When…     When <trigger>, the <system> shall <response>.
``state_driven``       While…    While <state>, the <system> shall <response>.
``unwanted_behaviour`` If…then   If <condition>, then the <system> shall <response>.
``optional_feature``   Where…    Where <feature>, the <system> shall <response>.
``free_text``          Free text <statement>
=====================  ========  ==========================================================

The frontend renders the same preview from :data:`EARS_TEMPLATES` (served as JSON), so the
backend's :func:`render_statement` is the single definition of the sentence that is stored.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class EarsTemplate(StrEnum):
    UBIQUITOUS = "ubiquitous"
    EVENT_DRIVEN = "event_driven"
    STATE_DRIVEN = "state_driven"
    UNWANTED_BEHAVIOUR = "unwanted_behaviour"
    OPTIONAL_FEATURE = "optional_feature"
    FREE_TEXT = "free_text"


@dataclass(frozen=True)
class EarsSlot:
    key: str
    label: str
    placeholder: str


@dataclass(frozen=True)
class EarsTemplateSpec:
    template: EarsTemplate
    chip: str  # label on the composer chip
    pattern: str  # sentence with {slot} placeholders
    slots: tuple[EarsSlot, ...]
    example: str


_SYSTEM = EarsSlot("system", "System", "mobile app")
_RESPONSE = EarsSlot("response", "Response", "log the user out")

EARS_TEMPLATES: Mapping[EarsTemplate, EarsTemplateSpec] = MappingProxyType(
    {
        EarsTemplate.UBIQUITOUS: EarsTemplateSpec(
            EarsTemplate.UBIQUITOUS,
            "Always",
            "The {system} shall {response}.",
            (_SYSTEM, _RESPONSE),
            "The mobile app shall encrypt stored card numbers.",
        ),
        EarsTemplate.EVENT_DRIVEN: EarsTemplateSpec(
            EarsTemplate.EVENT_DRIVEN,
            "When…",
            "When {trigger}, the {system} shall {response}.",
            (
                EarsSlot("trigger", "Trigger", "the user is inactive for 5 minutes"),
                _SYSTEM,
                _RESPONSE,
            ),
            "When the user is inactive for 5 minutes, the mobile app shall log the user out.",
        ),
        EarsTemplate.STATE_DRIVEN: EarsTemplateSpec(
            EarsTemplate.STATE_DRIVEN,
            "While…",
            "While {state}, the {system} shall {response}.",
            (EarsSlot("state", "State", "a transfer is pending"), _SYSTEM, _RESPONSE),
            "While a transfer is pending, the mobile app shall show its status.",
        ),
        EarsTemplate.UNWANTED_BEHAVIOUR: EarsTemplateSpec(
            EarsTemplate.UNWANTED_BEHAVIOUR,
            "If…then",
            "If {condition}, then the {system} shall {response}.",
            (
                EarsSlot("condition", "Condition", "the OTP is wrong three times"),
                _SYSTEM,
                _RESPONSE,
            ),
            "If the OTP is wrong three times, then the mobile app shall lock the account.",
        ),
        EarsTemplate.OPTIONAL_FEATURE: EarsTemplateSpec(
            EarsTemplate.OPTIONAL_FEATURE,
            "Where…",
            "Where {feature}, the {system} shall {response}.",
            (EarsSlot("feature", "Feature", "biometric login is enabled"), _SYSTEM, _RESPONSE),
            "Where biometric login is enabled, the mobile app shall accept a fingerprint.",
        ),
        EarsTemplate.FREE_TEXT: EarsTemplateSpec(
            EarsTemplate.FREE_TEXT,
            "Free text",
            "{statement}",
            (EarsSlot("statement", "Statement", "The system shall …"),),
            "The system shall keep audit logs for seven years.",
        ),
    }
)

_SPACES = re.compile(r"\s+")


class MissingSlotsError(ValueError):
    """Some slots of the chosen template are empty; ``missing`` names them in template order."""

    def __init__(self, template: EarsTemplate, missing: list[str]) -> None:
        super().__init__(f"Template '{template.value}' needs: {', '.join(missing)}")
        self.missing = missing


def _clean_slot(key: str, value: str) -> str:
    text = _SPACES.sub(" ", value).strip()
    if key == "system":
        # "the {system}" is in the pattern; accept "The mobile app" or "the mobile app" too.
        text = re.sub(r"^the\s+", "", text, flags=re.IGNORECASE)
    if key == "response":
        # "shall" is in the pattern; "shall log out" must not become "shall shall log out".
        text = re.sub(r"^shall\s+", "", text, flags=re.IGNORECASE)
    if key != "statement":
        text = text.rstrip(" .,;")  # the pattern adds its own punctuation
    return text


def missing_slots(template: EarsTemplate, slots: Mapping[str, str]) -> list[str]:
    spec = EARS_TEMPLATES[template]
    return [s.key for s in spec.slots if not _clean_slot(s.key, slots.get(s.key, ""))]


def render_statement(template: EarsTemplate, slots: Mapping[str, str]) -> str:
    """The requirement sentence for ``template`` filled with ``slots``.

    Whitespace is normalised and doubled words the pattern already supplies ("the", "shall")
    are dropped; otherwise the member's wording is kept. A free-text statement is returned as
    written (trimmed). Raises :class:`MissingSlotsError` if a slot is empty; unknown slot keys
    are ignored.
    """
    missing = missing_slots(template, slots)
    if missing:
        raise MissingSlotsError(template, missing)
    spec = EARS_TEMPLATES[template]
    values = {s.key: _clean_slot(s.key, slots[s.key]) for s in spec.slots}
    return spec.pattern.format(**values)


def templates_as_json() -> list[dict[str, object]]:
    """:data:`EARS_TEMPLATES` in the form the composer UI consumes."""
    return [
        {
            "template": spec.template.value,
            "chip": spec.chip,
            "pattern": spec.pattern,
            "slots": [
                {"key": s.key, "label": s.label, "placeholder": s.placeholder} for s in spec.slots
            ],
            "example": spec.example,
        }
        for spec in EARS_TEMPLATES.values()
    ]
