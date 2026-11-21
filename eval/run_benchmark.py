"""Benchmark v2 runner (Abhyudit — US-05 accuracy, Sprint 2; CP1 report, Sprint 3: NFR-21, NFR-39,
US-09).

Runs the detection engine on the benchmark and scores it against the labels:

1. **Requirements** — ``--style document`` (default): ``ingest_document`` on
   ``srs_planted.docx`` (the same code the worker runs). ``--style post``: the 40 post-style
   requirements of ``posts.csv`` (component B), analysed against the planted SRS as their baseline,
   as a posted requirement is (US-31).
2. **Candidates** — the embedder plus top-*k* cosine neighbours above the threshold, the rule of
   ``app.embeddings.candidates`` computed exactly in memory (pgvector's HNSW is approximate, so the
   database can only do as well or slightly worse). Post style pairs each post with the baseline
   and the other posts.
3. **Classification** — ``app.classification.classifier.Classifier`` with the v2 prompts, for every
   candidate pair (Conflicting / Duplicate / Dependent) and every requirement analysed (Ambiguous
   / Incomplete), exactly as ``app.classification.tasks`` does. ``--context-pack on`` sends the
   project context (``brief.json``) rendered as ``ContextPackBuilder`` renders it (NFR-39).
4. **Scores** — candidate recall on labelled pairs, then precision, recall and F1 per category.
   A labelled pair that never became a candidate counts as a miss for its category (recall is the
   headline number, US-05).
5. **Clarifications** (``--clarify``) — a question for every Conflicting, Ambiguous and Incomplete
   finding, through the same generator as the app (``app.clarification.generator``); reports how
   many findings got a specific question (US-09 "done when").

Usage (from the repository root)::

    python eval/run_benchmark.py --embedder minilm --llm none                  # candidates, free
    python eval/run_benchmark.py --style post --embedder minilm --llm none
    python eval/run_benchmark.py --llm live --context-pack on --clarify \\
        --record eval/reports/cp1_doc_pack.json                               # GEMINI_API_KEY set
    python eval/run_benchmark.py --llm replay:eval/reports/cp1_doc_pack.json --context-pack on

``--record`` stores every model reply keyed by a hash of the prompt, so a run can be replayed and
re-scored without spending budget (the context pack changes the prompts: record each setting).
``--json`` writes the full result for the report.
"""

import argparse
import csv
import hashlib
import html
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.clarification import generator as clarify
from app.classification.classifier import Classifier
from app.classification.context_pack import ContextPack
from app.classification.llm_client import LLMClient, LLMError, LLMTransport
from app.classification.prompting import PROMPT_VERSION
from app.classification.schemas import RequirementInput
from app.ingestion import ingest_document
from app.models import FindingCategory

BENCHMARK = ROOT / "eval" / "benchmark_v2"
PAIR_CATEGORIES = ("Conflicting", "Duplicate", "Dependent")
SINGLE_CATEGORIES = ("Ambiguous", "Incomplete")
QUESTION_CATEGORIES = ("Conflicting", "Ambiguous", "Incomplete")


# ── inputs ──────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Label:
    r1: str
    r2: str | None
    category: str
    split: str


@dataclass(frozen=True)
class Post:
    id: str
    author: str
    group: str
    template: str
    text: str


def load_labels(path: Path, split: str | None) -> list[Label]:
    with path.open(encoding="utf-8") as handle:
        rows = [
            Label(row["r1"], row["r2"] or None, row["category"], row["split"])
            for row in csv.DictReader(handle)
        ]
    return [label for label in rows if split in (None, label.split)]


def load_posts(path: Path) -> list[Post]:
    with path.open(encoding="utf-8") as handle:
        return [
            Post(row["id"], row["author"], row["group"], row["template"], row["text"])
            for row in csv.DictReader(handle)
        ]


def key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


# ── the context pack, rendered as ContextPackBuilder renders a confirmed context ─────────────
def render_pack(brief: dict[str, Any], query_text: str) -> ContextPack:
    """Summary, actors and the glossary terms found in the text — what the app sends (US-60). The
    document sections the app adds are left out offline: the SRS *is* the analysed text here."""

    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    parts = [f"Summary: {esc(brief['summary'])}"]
    if brief.get("actors"):
        parts.append("Actors: " + ", ".join(esc(actor) for actor in brief["actors"]))
    terms = [
        entry
        for entry in brief.get("glossary", [])
        if re.search(rf"(?<!\w){re.escape(entry['term'])}(?!\w)", query_text, re.IGNORECASE)
    ]
    if terms:
        parts.append(
            "\n".join(["Glossary:"] + [f"- {esc(t['term'])}: {esc(t['meaning'])}" for t in terms])
        )
    version = int(brief.get("version", 1))
    text = "\n".join([f'<project_context version="{version}">', *parts, "</project_context>"])
    return ContextPack(context_version=version, text=text)


# ── candidates (same rule as app.embeddings.candidates) ──────────────────────────────────────
def cosine(u: list[float], v: list[float]) -> float:
    dot = sum(x * y for x, y in zip(u, v, strict=True))
    norm = math.sqrt(sum(x * x for x in u)) * math.sqrt(sum(y * y for y in v))
    return dot / norm if norm else 0.0


def candidates(
    ids: list[str],
    vectors: list[list[float]],
    *,
    k: int,
    threshold: float,
    sources: set[str] | None = None,
) -> dict[tuple[str, str], float]:
    """Top-*k* neighbours above ``threshold`` of each id in ``sources`` (default: every id)."""
    best: dict[tuple[str, str], float] = {}
    for i, source in enumerate(ids):
        if sources is not None and source not in sources:
            continue
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
    label: str = "recording"

    def send(self, system: str, user: str) -> str:
        reply = self.inner.send(system, user)
        self.replies[prompt_key(system, user)] = reply
        self.label = str(getattr(self.inner, "label", self.label))
        return reply


@dataclass
class ReplayTransport:
    replies: dict[str, str]
    missing: int = 0
    label: str = "replay"

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
    if spec == "live":
        from app.classification.budget import UnlimitedBudget
        from app.classification.llm_client import get_llm_client

        client = get_llm_client()
        if client is None:
            raise SystemExit("--llm live needs GEMINI_API_KEY (or GROQ_API_KEY), see .env.example")
        transport = client._transport  # the benchmark is not a project's budget
        if record is None:
            return LLMClient(transport, UnlimitedBudget()), None
        recorder = RecordingTransport(transport)
        return LLMClient(recorder, UnlimitedBudget()), recorder
    raise SystemExit(f"Unknown --llm {spec!r} (none | live | replay:<file>)")


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


@dataclass
class Corpus:
    text: dict[str, str]  # every requirement in play, by ID
    subjects: list[str]  # the ones being analysed (all of the SRS, or the posts)
    labels: list[Label]


def corpus(args: argparse.Namespace) -> Corpus:
    extracted = [r for r in ingest_document(str(args.srs)).requirements if r.source_req_id]
    text = {r.source_req_id: r.raw_text for r in extracted if r.source_req_id}
    if args.style == "document":
        return Corpus(text, list(text), load_labels(args.labels, args.split))
    posts = load_posts(args.posts)
    text.update({post.id: post.text for post in posts})
    return Corpus(text, [post.id for post in posts], load_labels(args.posts_labels, args.split))


def run(args: argparse.Namespace) -> dict[str, Any]:
    data = corpus(args)
    ids = list(data.text)

    if args.embedder == "minilm":
        from app.embeddings.model import SentenceTransformerEmbedder

        embedder: Any = SentenceTransformerEmbedder()
    else:
        from app.embeddings.model import HashingEmbedder

        embedder = HashingEmbedder()
    vectors = embedder.embed([data.text[i] for i in ids])
    sources = set(data.subjects) if args.style == "post" else None
    pairs = candidates(ids, vectors, k=args.k, threshold=args.threshold, sources=sources)

    pair_labels = {key(lb.r1, lb.r2): lb.category for lb in data.labels if lb.r2}
    issue_pairs = {p: c for p, c in pair_labels.items() if c != "None"}
    found = {p for p in issue_pairs if p in pairs}
    by_category = {
        category: {
            "labelled": sum(1 for c in issue_pairs.values() if c == category),
            "candidates": sum(1 for p, c in issue_pairs.items() if c == category and p in pairs),
        }
        for category in PAIR_CATEGORIES
    }
    brief = (
        json.loads(args.brief.read_text(encoding="utf-8")) if args.context_pack == "on" else None
    )
    result: dict[str, Any] = {
        "style": args.style,
        "context_pack": brief is not None,
        "prompt_version": PROMPT_VERSION,
        "embedder": getattr(embedder, "version", args.embedder),
        "k": args.k,
        "similarity_threshold": args.threshold,
        "split": args.split or "all",
        "requirements_analysed": len(data.subjects),
        "requirements_extracted": len(ids)
        if args.style == "document"
        else len(ids) - len(data.subjects),
        "labels": len(data.labels),
        "candidate_pairs": len(pairs),
        "candidate_recall": len(found) / len(issue_pairs) if issue_pairs else 0.0,
        "candidate_recall_by_category": by_category,
        "missed_by_prefilter": sorted(
            f"{a}–{b} ({c})" for (a, b), c in issue_pairs.items() if (a, b) not in pairs
        ),
    }

    llm, recorder = make_llm(args.llm, args.record)
    if llm is None:
        return result

    def pack_for(*texts: str) -> ContextPack:
        return render_pack(brief, "\n".join(texts)) if brief is not None else ContextPack(None, "")

    classifier = Classifier(llm)
    scores, failures = Scores(), 0
    predicted_pairs: dict[tuple[str, str], tuple[str, Any]] = {}
    for a, b in sorted(pairs):
        try:
            output = classifier.classify_pair(
                RequirementInput(id=a, text=data.text[a]),
                RequirementInput(id=b, text=data.text[b]),
                pack=pack_for(data.text[a], data.text[b]),
            )
            predicted_pairs[(a, b)] = (output.category, output)
        except LLMError:
            failures += 1
            predicted_pairs[(a, b)] = ("None", None)
    for pair, truth in pair_labels.items():
        scores.add(predicted_pairs.get(pair, ("None", None))[0], truth)  # not a candidate: None
    for pair, (predicted, _) in predicted_pairs.items():
        if pair not in pair_labels and predicted != "None":
            scores.fp[predicted] += 1  # flagged an unlabelled pair

    single_labels = {lb.r1: lb.category for lb in data.labels if not lb.r2}
    predicted_singles: dict[str, tuple[str, Any]] = {}
    for requirement_id in data.subjects:
        try:
            output = classifier.classify_single(
                RequirementInput(id=requirement_id, text=data.text[requirement_id]),
                pack=pack_for(data.text[requirement_id]),
            )
            predicted_singles[requirement_id] = (output.category, output)
        except LLMError:
            failures += 1
            predicted_singles[requirement_id] = ("None", None)
        predicted = predicted_singles[requirement_id][0]
        truth = single_labels.get(requirement_id)
        if truth is not None:
            scores.add(predicted, truth)
        elif predicted != "None":
            scores.fp[predicted] += 1

    result["llm_calls"] = llm.calls
    result["failed_items"] = failures
    result["per_category"] = {c: scores.row(c) for c in (*PAIR_CATEGORIES, *SINGLE_CATEGORIES)}
    if args.clarify:
        result["clarifications"] = clarifications(
            llm, data, predicted_pairs, predicted_singles, pack_for
        )
    if recorder is not None and args.record is not None:
        args.record.write_text(json.dumps(recorder.replies, indent=1), encoding="utf-8")
    return result


def clarifications(
    llm: LLMClient,
    data: Corpus,
    pairs: dict[tuple[str, str], tuple[str, Any]],
    singles: dict[str, tuple[str, Any]],
    pack_for: Any,
) -> dict[str, dict[str, int]]:
    """One question per predicted Conflicting / Ambiguous / Incomplete finding, as the app asks
    it: how many got a specific question, per category (US-09)."""
    counts = {c: {"findings": 0, "questions": 0, "failed": 0} for c in QUESTION_CATEGORIES}
    items: list[tuple[str, list[str], Any]] = [
        (category, [a, b], output)
        for (a, b), (category, output) in sorted(pairs.items())
        if category in QUESTION_CATEGORIES
    ] + [
        (category, [rid], output)
        for rid, (category, output) in sorted(singles.items())
        if category in QUESTION_CATEGORIES
    ]
    for category, ids, output in items:
        counts[category]["findings"] += 1
        vague = list(getattr(output, "vague_terms", []) or [])
        system, user = clarify.render_messages(
            FindingCategory(category),
            output.rationale,
            [(i, data.text[i]) for i in ids],
            context_pack=pack_for(*(data.text[i] for i in ids)).text,
            vague_terms=vague,
            missing=list(getattr(output, "missing_information", []) or []),
        )
        try:
            question = clarify.ask(llm, system, user, ids, vague)
        except LLMError:
            question = None
        counts[category]["questions" if question is not None else "failed"] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--style", choices=["document", "post"], default="document")
    parser.add_argument("--srs", type=Path, default=BENCHMARK / "srs_planted.docx")
    parser.add_argument("--labels", type=Path, default=BENCHMARK / "labels.csv")
    parser.add_argument("--posts", type=Path, default=BENCHMARK / "posts.csv")
    parser.add_argument("--posts-labels", type=Path, default=BENCHMARK / "posts_labels.csv")
    parser.add_argument("--brief", type=Path, default=BENCHMARK / "brief.json")
    parser.add_argument("--context-pack", choices=["off", "on"], default="off")
    parser.add_argument("--split", choices=["dev", "heldout"], default=None)
    parser.add_argument("--embedder", choices=["minilm", "hashing"], default="minilm")
    parser.add_argument("--llm", default="none", help="none | live | replay:<file>")
    parser.add_argument("--record", type=Path, default=None, help="save replies (with live)")
    parser.add_argument("--clarify", action="store_true", help="also generate the questions")
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
