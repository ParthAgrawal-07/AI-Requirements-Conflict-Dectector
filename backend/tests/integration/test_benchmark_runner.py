"""The benchmark runner (Abhyudit — US-05 accuracy): its scoring and candidate rule are right, and a
run on the planted SRS works end to end with scripted model replies."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.classification.llm_client import FakeTransport, LLMClient

RUNNER = Path(__file__).parents[3] / "eval" / "run_benchmark.py"
pytestmark = pytest.mark.skipif(not RUNNER.exists(), reason="eval/ is not mounted")


@pytest.fixture(scope="module")
def runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_benchmark", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_benchmark"] = module
    spec.loader.exec_module(module)
    return module


def test_scores_count_hits_misses_and_false_alarms(runner: ModuleType) -> None:
    scores = runner.Scores()
    scores.add("Conflicting", "Conflicting")  # hit
    scores.add("None", "Conflicting")  # miss
    scores.add("Conflicting", "None")  # false alarm
    scores.add("Duplicate", "Conflicting")  # wrong category: a miss and a false alarm
    scores.add("None", "None")  # correct rejection, counts nowhere

    row = scores.row("Conflicting")
    assert (row["tp"], row["fp"], row["fn"]) == (1, 1, 2)
    assert row["precision"] == pytest.approx(0.5) and row["recall"] == pytest.approx(1 / 3)
    assert scores.row("Duplicate")["fp"] == 1


def test_candidates_keep_top_k_above_the_threshold(runner: ModuleType) -> None:
    ids = ["A", "B", "C"]
    vectors = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]]

    assert set(runner.candidates(ids, vectors, k=1, threshold=0.5)) == {("A", "B")}
    assert runner.candidates(ids, vectors, k=5, threshold=0.999) == {}


def test_a_run_on_the_planted_srs_scores_every_category(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_none(system: str, user: str) -> str:
        if "vague_terms" in system:
            return json.dumps(
                {"category": "None", "confidence": 0.9, "rationale": "Fine.",
                 "vague_terms": [], "missing_information": []}
            )  # fmt: skip
        return json.dumps(
            {"category": "None", "confidence": 0.9, "rationale": "Fine.",
             "dependency_direction": None, "evidence": []}
        )  # fmt: skip

    class Echo(FakeTransport):
        def send(self, system: str, user: str) -> str:
            self.calls.append((system, user))
            return always_none(system, user)

    monkeypatch.setattr(runner, "make_llm", lambda spec, record: (LLMClient(Echo([])), None))
    args = argparse.Namespace(
        srs=runner.BENCHMARK / "srs_planted.docx",
        labels=runner.BENCHMARK / "labels.csv",
        split=None,
        embedder="hashing",
        llm="scripted",
        record=None,
        k=3,
        threshold=0.2,
        json=None,
    )

    result = runner.run(args)

    assert result["requirements_extracted"] == 60
    assert 0 <= result["candidate_recall"] <= 1
    # A model that never flags anything finds nothing: every category has zero recall.
    assert set(result["per_category"]) == {
        "Conflicting", "Duplicate", "Dependent", "Ambiguous", "Incomplete"
    }  # fmt: skip
    assert all(row["recall"] == 0 for row in result["per_category"].values())
    assert result["llm_calls"] == result["candidate_pairs"] + 60
