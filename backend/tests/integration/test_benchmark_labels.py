"""Validate benchmark label files against eval/benchmark_v2/schema.json.

Locations are searched in this order: $EVAL_DIR, /eval (container mount),
<repo root>/eval. The v1 seed labels are looked up under
<repo root>/sample_docs/planted_conflicts/ (or the hyphenated spelling) or $BENCHMARK_V1_DIR.
Tests skip when the files are not reachable (for example when ./eval is not
mounted into the backend container).
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
PAIRWISE = {"Conflicting", "Duplicate", "Dependent", "None"}
SINGLE = {"Ambiguous", "Incomplete"}
ALL_CATEGORIES = PAIRWISE | SINGLE


def _first_existing(candidates: list[Path], name: str) -> Path | None:
    for base in candidates:
        path = base / name
        if path.is_file():
            return path
    return None


def _eval_dirs() -> list[Path]:
    dirs = []
    if os.environ.get("EVAL_DIR"):
        dirs.append(Path(os.environ["EVAL_DIR"]) / "benchmark_v2")
    dirs += [Path("/eval/benchmark_v2"), REPO_ROOT / "eval" / "benchmark_v2"]
    return dirs


def _v1_dirs() -> list[Path]:
    dirs = []
    if os.environ.get("BENCHMARK_V1_DIR"):
        dirs.append(Path(os.environ["BENCHMARK_V1_DIR"]))
    for folder in ("sample_docs/planted_conflicts", "sample-docs/planted-conflicts"):
        dirs += [Path("/") / folder, REPO_ROOT / folder]
    return dirs


@pytest.fixture(scope="module")
def schema() -> dict:
    path = _first_existing(_eval_dirs(), "schema.json")
    if path is None:
        pytest.skip("eval/benchmark_v2/schema.json not reachable from this environment")
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def v1_labels() -> dict:
    path = _first_existing(_v1_dirs(), "srs_v1_labels.json")
    if path is None:
        pytest.skip("srs_v1_labels.json not reachable from this environment")
    return json.loads(path.read_text())


def test_schema_is_valid_json_schema(schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(schema)


def test_v1_labels_match_schema(schema: dict, v1_labels: dict) -> None:
    jsonschema.Draft202012Validator(schema).validate(v1_labels)


def test_v1_pairs_are_distinct_and_not_self_referential(v1_labels: dict) -> None:
    seen: set[frozenset[str]] = set()
    for entry in v1_labels["labels"]:
        if entry["category"] in PAIRWISE:
            assert entry["r1"] != entry["r2"], entry
            key = frozenset((entry["r1"], entry["r2"]))
            assert key not in seen, f"pair labeled twice: {sorted(key)}"
            seen.add(key)


def test_v1_category_list_matches_schema(schema: dict, v1_labels: dict) -> None:
    allowed = set(schema["$defs"]["category"]["enum"])
    assert allowed == ALL_CATEGORIES
    assert set(v1_labels["categories"]) == allowed


def test_v1_meets_coverage_target(v1_labels: dict) -> None:
    """Labeling guide section 10: at least 3 per category and 4 None hard negatives."""
    counts = Counter(entry["category"] for entry in v1_labels["labels"])
    for category in ALL_CATEGORIES - {"None"}:
        assert counts[category] >= 3, f"{category}: {counts[category]}"
    assert counts["None"] >= 4, f"None: {counts['None']}"
