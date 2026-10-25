"""Lint catalogue v1 (Keval, Sprint 0): valid shape, unique ids, patterns compile and catch what
they are meant to catch — and nothing in a well-written requirement."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

CATALOGUE = Path(__file__).resolve().parents[2] / "app" / "lint" / "catalogue.json"
REQUIRED = {"id", "category", "pattern", "message", "hint", "severity"}
SEVERITIES = {"info", "warning", "error"}


@pytest.fixture(scope="module")
def entries() -> list[dict[str, Any]]:
    data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    assert data["version"] == 1
    result: list[dict[str, Any]] = data["entries"]
    return result


def test_every_entry_has_the_agreed_fields(entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        assert set(entry) == REQUIRED, entry["id"]
        assert entry["severity"] in SEVERITIES
        assert entry["message"].strip() and entry["hint"].strip()


def test_ids_are_unique(entries: list[dict[str, Any]]) -> None:
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids))


def test_the_five_agreed_categories_are_covered(entries: list[dict[str, Any]]) -> None:
    assert {"vague", "passive", "actor", "tbd", "unbounded"} <= {e["category"] for e in entries}


def _hits(entries: list[dict[str, Any]], text: str) -> set[str]:
    return {e["id"] for e in entries if re.search(e["pattern"], text, re.IGNORECASE)}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The app shall load the account summary quickly.", "vague.speed"),
        ("The interface shall be user-friendly.", "vague.usability"),
        ("The limit is TBD.", "tbd.placeholder"),
        ("Reports shall be generated nightly.", "passive.shall_be"),
        ("It shall retry three times.", "actor.missing"),
        ("Users can pay by card, UPI, etc.", "unbounded.etc"),
    ],
)
def test_each_rule_catches_its_example(
    entries: list[dict[str, Any]], text: str, expected: str
) -> None:
    assert expected in _hits(entries, text)


def test_a_well_written_requirement_has_no_warnings(entries: list[dict[str, Any]]) -> None:
    text = "When the user is inactive for 10 minutes, the system shall end the session."
    warnings = {
        e["id"] for e in entries if e["severity"] != "info" and e["id"] in _hits(entries, text)
    }
    assert warnings == set()
