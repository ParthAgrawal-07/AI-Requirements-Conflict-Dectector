"""The benchmark runner (Abhyudit — US-05 accuracy; CP1: NFR-21, NFR-39, US-09): its scoring and
candidate rule are right, and runs on the planted SRS and on the post-style set work end to end
with scripted model replies, with and without the context pack, including the questions."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

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


def namespace(runner: ModuleType, **overrides: Any) -> argparse.Namespace:
    values: dict[str, Any] = {
        "style": "document",
        "srs": runner.BENCHMARK / "srs_planted.docx",
        "labels": runner.BENCHMARK / "labels.csv",
        "posts": runner.BENCHMARK / "posts.csv",
        "posts_labels": runner.BENCHMARK / "posts_labels.csv",
        "brief": runner.BENCHMARK / "brief.json",
        "context_pack": "off",
        "split": None,
        "embedder": "hashing",
        "llm": "scripted",
        "record": None,
        "clarify": False,
        "k": 3,
        "threshold": 0.2,
        "json": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class Scripted(FakeTransport):
    """Says "no issue" to everything, except Ambiguous for texts containing ``fast``; answers
    clarification prompts with a question naming the requirement."""

    def send(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if '"question"' in system:
            ids = [part.split('"')[0] for part in user.split('<requirement id="')[1:]]
            return json.dumps(
                {
                    "question": f"What does 'fast' mean for {ids[0]}, in seconds?",
                    "addressed_to": "owner",
                    "requirement_ids": ids,
                }
            )
        if "vague_terms" in system:
            vague = "fast" in user.split("<requirement")[-1]
            return json.dumps(
                {"category": "Ambiguous" if vague else "None", "confidence": 0.9,
                 "rationale": "Vague." if vague else "Fine.",
                 "vague_terms": ["fast"] if vague else [], "missing_information": []}
            )  # fmt: skip
        return json.dumps(
            {"category": "None", "confidence": 0.9, "rationale": "Fine.",
             "dependency_direction": None, "evidence": []}
        )  # fmt: skip


@pytest.fixture
def scripted(runner: ModuleType, monkeypatch: pytest.MonkeyPatch) -> Scripted:
    transport = Scripted([])
    monkeypatch.setattr(runner, "make_llm", lambda spec, record: (LLMClient(transport), None))
    return transport


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
    assert set(runner.candidates(ids, vectors, k=5, threshold=0.0, sources={"C"})) == {
        ("A", "C"),
        ("B", "C"),
    }


def test_a_run_on_the_planted_srs_scores_every_category(
    runner: ModuleType, scripted: Scripted
) -> None:
    result = runner.run(namespace(runner))

    assert result["requirements_extracted"] == 60 and result["style"] == "document"
    assert 0 <= result["candidate_recall"] <= 1
    assert set(result["per_category"]) == {
        "Conflicting", "Duplicate", "Dependent", "Ambiguous", "Incomplete"
    }  # fmt: skip
    assert result["per_category"]["Conflicting"]["recall"] == 0  # the script never flags pairs
    assert result["llm_calls"] == result["candidate_pairs"] + 60


def test_the_post_style_set_is_analysed_against_the_baseline(
    runner: ModuleType, scripted: Scripted
) -> None:
    result = runner.run(namespace(runner, style="post"))

    assert (result["requirements_analysed"], result["requirements_extracted"]) == (40, 60)
    # Only the posts are checked on their own; every candidate pair includes a post.
    assert result["llm_calls"] == result["candidate_pairs"] + 40
    single_users = [user for system, user in scripted.calls if "vague_terms" in system]
    assert all('id="P-' in user for user in single_users)
    ambiguous = result["per_category"]["Ambiguous"]
    assert ambiguous["tp"] == 1  # P-20 "The search page shall load fast."


def test_the_context_pack_reaches_every_prompt_only_when_on(
    runner: ModuleType, scripted: Scripted
) -> None:
    runner.run(namespace(runner, style="post", context_pack="on"))
    with_pack = list(scripted.calls)
    scripted.calls.clear()
    runner.run(namespace(runner, style="post", context_pack="off"))

    assert all('<project_context version="1">' in user for _, user in with_pack)
    assert not any("<project_context" in user for _, user in scripted.calls)
    glossary_hits = [u for _, u in with_pack if "- Recycle bin:" in u]
    assert glossary_hits and all("recycle bin" in u.lower().split("</project_context>")[1]
                                 for u in glossary_hits)  # fmt: skip


def test_every_ambiguous_finding_gets_a_specific_question(
    runner: ModuleType, scripted: Scripted
) -> None:
    result = runner.run(namespace(runner, style="post", clarify=True))

    ambiguous = result["clarifications"]["Ambiguous"]
    assert ambiguous["findings"] >= 1
    assert ambiguous["questions"] == ambiguous["findings"] and ambiguous["failed"] == 0


# ── the post-style set itself (component B) ─────────────────────────────────────────────────
def test_the_post_style_set_matches_the_plan(runner: ModuleType) -> None:
    posts = runner.load_posts(runner.BENCHMARK / "posts.csv")
    labels = runner.load_labels(runner.BENCHMARK / "posts_labels.csv", None)
    baseline = {
        line.split(":")[0]
        for line in (runner.BENCHMARK / "srs_planted.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("REQ-")
    } | {
        cell.strip()
        for line in (runner.BENCHMARK / "srs_planted.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| REQ-")
        for cell in [line.split("|")[1]]
    }
    ids = {post.id for post in posts}

    assert len(posts) == 40 and len(ids) == 40
    assert all(post.author and post.group and post.text.endswith(".") for post in posts)
    for label in labels:
        assert label.r1 in ids
        assert label.r2 is None or label.r2 in ids or label.r2 in baseline, label
        assert label.category in {*runner.PAIR_CATEGORIES, *runner.SINGLE_CATEGORIES, "None"}
        assert label.split in {"dev", "heldout"}
    issues = {lb.r1 for lb in labels if lb.category != "None"}
    clean = ids - issues
    assert 0.15 <= len(clean) / len(posts) <= 0.35  # "roughly a quarter clean" (PLAN.md)
    heldout = sum(1 for lb in labels if lb.split == "heldout") / len(labels)
    assert 0.2 <= heldout <= 0.4
