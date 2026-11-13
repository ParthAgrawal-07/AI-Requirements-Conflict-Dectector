"""Benchmark v2 runner (Abhyudit — US-05 accuracy, Sprint 2).

Runs the detection engine on the planted-conflict SRS and scores it against ``labels.csv``:

1. **Extraction** — ``ingest_document`` on ``srs_planted.docx`` (the same code the worker runs);
2. **Candidates** — the embedder plus top-*k* cosine neighbours above the threshold, the rule of
   ``app.embeddings.candidates`` computed exactly in memory (pgvector's HNSW is approximate, so the
   database can only do as well or slightly worse);
3. **Classification** — ``app.classification.classifier.Classifier`` with the v2 prompts, for every
   candidate pair (Conflicting / Duplicate / Dependent) and every requirement (Ambiguous /
   Incomplete), exactly as ``app.classification.tasks`` does;
4. **Scores** — candidate recall on labelled pairs, then precision, recall and F1 per category.
   A labelled pair that never became a candidate counts as a miss for its category (recall is the
   headline number, US-05).

Usage (from the repository root)::

    python eval/run_benchmark.py --embedder minilm --llm none           # candidates only, free
    python eval/run_benchmark.py --embedder minilm --llm live \\
        --record eval/reports/s2_replies.json             # real run: GEMINI_API_KEY (Groq backup)
    python eval/run_benchmark.py --embedder minilm --llm replay:eval/reports/s2_replies.json

``--record`` stores every model reply keyed by a hash of the prompt, so a run can be replayed and
re-scored without spending budget. ``--json`` writes the full result for the report.
"""

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.classification.classifier import Classifier
from app.classification.llm_client import LLMClient, LLMError, LLMTransport
from app.classification.prompting import PROMPT_VERSION
from app.classification.schemas import RequirementInput
from app.ingestion import ingest_document

BENCHMARK = ROOT / "eval" / "benchmark_v2"
PAIR_CATEGORIES = ("Conflicting", "Duplicate", "Dependent")
SINGLE_CATEGORIES = ("Ambiguous", "Incomplete")


# ── inputs ──────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Label:
    r1: str
    r2: str | None
    category: str
    split: str


def load_labels(path: Path, split: str | None) -> list[Label]:
    with path.open(encoding="utf-8") as handle:
        rows = [
            Label(row["r1"], row["r2"] or None, row["category"], row["split"])
            for row in csv.DictReader(handle)
        ]
    return [label for label in rows if split in (None, label.split)]


def key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


# ── candidates (same rule as app.embeddings.candidates) ──────────────────────────────────────
def cosine(u: list[float], v: list[float]) -> float:
    dot = sum(x * y for x, y in zip(u, v, strict=True))
    norm = math.sqrt(sum(x * x for x in u)) * math.sqrt(sum(y * y for y in v))
    return dot / norm if norm else 0.0


def candidates(
    ids: list[str], vectors: list[list[float]], *, k: int, threshold: float
) -> dict[tuple[str, str], float]:
    best: dict[tuple[str, str], float] = {}
    for i, source in enumerate(ids):
        scored = sorted(
            ((cosine(vectors[i], vectors[j]), ids[j]) for j in range(len(ids)) if j != i),
            reverse=True,
        )
        for similarity, other in scored[:k]:
            if similarity < threshold or other == source:
                continue
            pair = key(source, other)
            best[pair] = max(best.get(pair, -1.0), similarity)
    return best


# ── LLM transports for reproducible runs ────────────────────────────────────────────────────
def prompt_key(system: str, user: str) -> str:
    return hashlib.sha256(f"{system}\x00{user}".encode()).hexdigest()


@dataclass
class RecordingTransport:
    inner: LLMTransport
    replies: dict[str, str] = field(default_factory=dict)

    def send(self, system: str, user: str) -> str:
        reply = self.inner.send(system, user)
        self.replies[prompt_key(system, user)] = reply
        return reply


@dataclass
class ReplayTransport:
    replies: dict[str, str]
    missing: int = 0

    def send(self, system: str, user: str) -> str:
        reply = self.replies.get(prompt_key(system, user))
        if reply is None:
            self.missing += 1
            raise LLMError("No recorded reply for this prompt (prompts changed since recording?)")
        return reply


def make_llm(spec: str, record: Path | None) -> tuple[LLMClient | None, RecordingTransport | None]:
    if spec == "none":
        return None, None
    if spec.startswith("replay:"):
        replies = json.loads(Path(spec.removeprefix("replay:")).read_text(encoding="utf-8"))
        return LLMClient(ReplayTransport(replies)), None
    if spec == "live":  # the configured provider: Gemini, Groq as backup (ADR-31)
        from app.classification.llm_client import get_llm_client

        client = get_llm_client()
        if client is None:
            raise SystemExit("--llm live needs GEMINI_API_KEY or GROQ_API_KEY")
        if record is None:
            return client, None
        recorder = RecordingTransport(client._transport)
        return LLMClient(recorder), recorder
    raise SystemExit(f"Unknown --llm {spec!r}")


# ── scoring ─────────────────────────────────────────────────────────────────────────────────
@dataclass
class Scores:
    tp: Counter[str] = field(default_factory=Counter)
    fp: Counter[str] = field(default_factory=Counter)
    fn: Counter[str] = field(default_factory=Counter)

    def add(self, predicted: str, truth: str) -> None:
        if predicted == truth:
            if truth != "None":
                self.tp[truth] += 1
            return
        if predicted != "None":
            self.fp[predicted] += 1
        if truth != "None":
            self.fn[truth] += 1

    def row(self, category: str) -> dict[str, float | int]:
        tp, fp, fn = self.tp[category], self.fp[category], self.fn[category]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def run(args: argparse.Namespace) -> dict[str, Any]:
    labels = load_labels(args.labels, args.split)
    extracted = [r for r in ingest_document(str(args.srs)).requirements if r.source_req_id]
    text = {r.source_req_id: r.raw_text for r in extracted if r.source_req_id}
    ids = list(text)

    if args.embedder == "minilm":
        from app.embeddings.model import SentenceTransformerEmbedder

        embedder: Any = SentenceTransformerEmbedder()
    else:
        from app.embeddings.model import HashingEmbedder

        embedder = HashingEmbedder()
    vectors = embedder.embed([text[i] for i in ids])
    pairs = candidates(ids, vectors, k=args.k, threshold=args.threshold)

    pair_labels = {key(lb.r1, lb.r2): lb.category for lb in labels if lb.r2}
    issue_pairs = {p: c for p, c in pair_labels.items() if c != "None"}
    found = {p for p in issue_pairs if p in pairs}
    candidate_recall = len(found) / len(issue_pairs) if issue_pairs else 0.0
    by_category = {
        category: {
            "labelled": sum(1 for c in issue_pairs.values() if c == category),
            "candidates": sum(1 for p, c in issue_pairs.items() if c == category and p in pairs),
        }
        for category in PAIR_CATEGORIES
    }
    result: dict[str, Any] = {
        "prompt_version": PROMPT_VERSION,
        "embedder": getattr(embedder, "version", args.embedder),
        "k": args.k,
        "similarity_threshold": args.threshold,
        "split": args.split or "all",
        "requirements_extracted": len(ids),
        "labels": len(labels),
        "candidate_pairs": len(pairs),
        "candidate_recall": candidate_recall,
        "candidate_recall_by_category": by_category,
        "missed_by_prefilter": sorted(
            f"{a}–{b} ({c})" for (a, b), c in issue_pairs.items() if (a, b) not in pairs
        ),
    }

    llm, recorder = make_llm(args.llm, args.record)
    if llm is None:
        return result

    classifier = Classifier(llm)
    scores, failures, predicted_pairs = Scores(), 0, {}
    for a, b in sorted(pairs):
        try:
            output = classifier.classify_pair(
                RequirementInput(id=a, text=text[a]), RequirementInput(id=b, text=text[b])
            )
            predicted_pairs[(a, b)] = output.category
        except LLMError:
            failures += 1
            predicted_pairs[(a, b)] = "None"
    for pair, truth in pair_labels.items():
        scores.add(predicted_pairs.get(pair, "None"), truth)  # not a candidate: predicted None
    for pair, predicted in predicted_pairs.items():
        if pair not in pair_labels and predicted != "None":
            scores.fp[predicted] += 1  # flagged an unlabelled pair

    single_labels = {lb.r1: lb.category for lb in labels if not lb.r2}
    for requirement_id in ids:
        try:
            predicted = classifier.classify_single(
                RequirementInput(id=requirement_id, text=text[requirement_id])
            ).category
        except LLMError:
            failures += 1
            predicted = "None"
        truth = single_labels.get(requirement_id)
        if truth is not None:
            scores.add(predicted, truth)
        elif predicted != "None":
            scores.fp[predicted] += 1

    result["llm_calls"] = llm.calls
    result["failed_items"] = failures
    result["per_category"] = {c: scores.row(c) for c in (*PAIR_CATEGORIES, *SINGLE_CATEGORIES)}
    if recorder is not None and args.record is not None:
        args.record.write_text(json.dumps(recorder.replies, indent=1), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--srs", type=Path, default=BENCHMARK / "srs_planted.docx")
    parser.add_argument("--labels", type=Path, default=BENCHMARK / "labels.csv")
    parser.add_argument("--split", choices=["dev", "heldout"], default=None)
    parser.add_argument("--embedder", choices=["minilm", "hashing"], default="minilm")
    parser.add_argument("--llm", default="none", help="none | live | replay:<file>")
    parser.add_argument("--record", type=Path, default=None, help="save replies (with live)")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--json", type=Path, default=None, help="write the result here")
    args = parser.parse_args()

    result = run(args)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
