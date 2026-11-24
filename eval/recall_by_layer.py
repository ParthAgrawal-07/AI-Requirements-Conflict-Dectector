"""Recall by layer for Checkpoint 2 (Abhyudit — US-58, NFR-37, FR-101; CP2 report).

Which layer catches each labelled conflict — the similarity filter plus the AI, the rule checks,
or neither — so "no issue detected" can be told apart from "the similarity filter never looked":

* **similarity + AI** — the pair passes the embedding filter (top-*k* above the threshold, exactly
  as ``app.embeddings.candidates``) **and** the classifier calls it Conflicting. Without a model
  (``--llm none``) this layer is reported as *not run*: only the filter's share is known.
* **rules** — ``app.search.rule_checker.compare`` on Keval's attributes, over **every** pair,
  whatever its similarity: the same functions the worker runs after each analysis.
* **missed** — neither.

Two sets:

1. ``below_threshold.csv`` — 18 reworded pairs written to share little vocabulary: 12 conflicts a
   rule should catch (the expected rule is labelled), 3 conflicts only the AI or a person can
   catch, 3 look-alike non-conflicts (a rule firing on them is a false positive);
2. the planted SRS (``srs_planted.docx`` + ``labels.csv``): every Conflicting label, and every
   rule hit on a pair that is **not** labelled (to review: an unlabelled true conflict, or a false
   positive).

Usage (from the repository root)::

    python eval/recall_by_layer.py --embedder minilm --llm none --json eval/reports/cp2_layers.json
    python eval/recall_by_layer.py --llm replay:eval/reports/cp2_ai.json   # with recorded replies
"""

import argparse
import csv
import json
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

from run_benchmark import BENCHMARK, candidates, cosine, key, load_labels, make_llm  # noqa: E402

from app.classification.classifier import Classifier  # noqa: E402
from app.classification.llm_client import LLMClient, LLMError  # noqa: E402
from app.classification.schemas import RequirementInput  # noqa: E402
from app.ingestion import ingest_document  # noqa: E402
from app.models import Requirement, RequirementAttribute  # noqa: E402
from app.search.rule_checker import compare, read_attributes  # noqa: E402


@dataclass(frozen=True)
class Pair:
    id: str
    a: str  # requirement ids within the set
    b: str
    category: str
    expected_rule: str | None
    split: str


def _row(label: str, text: str) -> tuple[Requirement, RequirementAttribute]:
    """A transient requirement and its attributes, as the checker reads them from the database."""
    attributes = read_attributes(text)  # exactly as the checker indexes it
    requirement = Requirement(id=uuid.uuid4(), source_req_id=label, body=text)
    row = RequirementAttribute(**attributes.as_json(), requirement_id=requirement.id, version_no=1)
    return requirement, row


def rule_hits(texts: dict[str, str], pairs: list[tuple[str, str]] | None = None) -> dict[tuple[str, str], list[str]]:
    """The rules that fire on each pair (all pairs when ``pairs`` is None)."""
    rows = {label: _row(label, text) for label, text in texts.items()}
    labels = sorted(rows)
    todo = pairs or [(a, b) for i, a in enumerate(labels) for b in labels[i + 1 :]]
    found: dict[tuple[str, str], list[str]] = {}
    for a, b in todo:
        (ra, aa), (rb, ab) = rows[a], rows[b]
        hits = sorted({h.rule_id for h in compare(aa, ab, a_req=ra, b_req=rb)})
        if hits:
            found[key(a, b)] = hits
    return found


def classify(llm: LLMClient | None, texts: dict[str, str], pairs: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    if llm is None:
        return {}
    classifier = Classifier(llm)
    result: dict[tuple[str, str], str] = {}
    for a, b in sorted(pairs):
        try:
            output = classifier.classify_pair(RequirementInput(id=a, text=texts[a]),
                                              RequirementInput(id=b, text=texts[b]))  # fmt: skip
            result[(a, b)] = output.category
        except LLMError:
            result[(a, b)] = "failed"
    return result


def layer(pair: tuple[str, str], *, candidate: bool, ai: dict[tuple[str, str], str] | None,
          rules: dict[tuple[str, str], list[str]]) -> str:  # fmt: skip
    by_ai = ai is not None and candidate and ai.get(pair) == "Conflicting"
    by_rules = pair in rules
    if by_ai and by_rules:
        return "both"
    if by_ai:
        return "ai"
    if by_rules:
        return "rules"
    return "missed" if ai is not None or not candidate else "candidate_not_classified"


def below_threshold(args: argparse.Namespace, embedder: Any, llm: LLMClient | None) -> dict[str, Any]:
    with (BENCHMARK / "below_threshold.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    texts: dict[str, str] = {}
    pairs: list[Pair] = []
    for row in rows:
        a, b = f"{row['id']}a", f"{row['id']}b"
        texts[a], texts[b] = row["a_text"], row["b_text"]
        pairs.append(Pair(row["id"], a, b, row["category"],
                          None if row["expected_rule"] == "none" else row["expected_rule"],
                          row["split"]))  # fmt: skip
    vectors = dict(zip(texts, embedder.embed(list(texts.values())), strict=True))
    similarity = {key(p.a, p.b): cosine(vectors[p.a], vectors[p.b]) for p in pairs}
    passing = {k for k, s in similarity.items() if s >= args.threshold}
    rules = rule_hits(texts, [(p.a, p.b) for p in pairs])
    ai = classify(llm, texts, passing) if llm else None
    detail = []
    for p in pairs:
        pk = key(p.a, p.b)
        fired = rules.get(pk, [])
        detail.append({
            "id": p.id, "category": p.category, "expected_rule": p.expected_rule,
            "similarity": round(similarity[pk], 3), "passes_filter": pk in passing,
            "rules_fired": fired, "ai": (ai or {}).get(pk),
            "layer": layer(pk, candidate=pk in passing, ai=ai, rules=rules)
            if p.category == "Conflicting" else ("false_positive" if fired else "correctly_quiet"),
            "rule_as_expected": (p.expected_rule in fired) if p.expected_rule else not fired,
        })  # fmt: skip
    conflicts = [d for d in detail if d["category"] == "Conflicting"]
    return {
        "pairs": len(detail),
        "conflicts": len(conflicts),
        "below_threshold": sum(1 for d in conflicts if not d["passes_filter"]),
        "by_layer": dict(Counter(d["layer"] for d in conflicts)),
        "rule_subset": sum(1 for d in conflicts if d["expected_rule"]),
        "rule_subset_caught": sum(1 for d in conflicts if d["expected_rule"] and d["rule_as_expected"]),
        "false_positives": sum(1 for d in detail if d["layer"] == "false_positive"),
        "detail": detail,
    }


def planted(args: argparse.Namespace, embedder: Any, llm: LLMClient | None) -> dict[str, Any]:
    extracted = [r for r in ingest_document(str(args.srs)).requirements if r.source_req_id]
    texts = {r.source_req_id: r.raw_text for r in extracted if r.source_req_id}
    ids = list(texts)
    passing = set(candidates(ids, embedder.embed([texts[i] for i in ids]), k=args.k,
                             threshold=args.threshold))  # fmt: skip
    labels = [lb for lb in load_labels(args.labels, None) if lb.r2]
    conflicts = {key(lb.r1, lb.r2) for lb in labels if lb.category == "Conflicting"}
    labelled = {key(lb.r1, lb.r2) for lb in labels}
    rules = rule_hits(texts)
    ai = classify(llm, texts, passing & conflicts) if llm else None
    layers = Counter(layer(p, candidate=p in passing, ai=ai, rules=rules) for p in conflicts)
    return {
        "requirements": len(ids),
        "conflicts": len(conflicts),
        "below_threshold": len(conflicts - passing),
        "by_layer": dict(layers),
        "rules_on_conflicts": sorted(f"{a}/{b}: {', '.join(rules[(a, b)])}" for a, b in conflicts & set(rules)),
        "rules_on_unlabelled_pairs": sorted(
            f"{a}/{b}: {', '.join(r)}" for (a, b), r in rules.items() if (a, b) not in labelled
        ),
        "rules_on_labelled_non_conflicts": sorted(
            f"{a}/{b}: {', '.join(r)}" for (a, b), r in rules.items() if (a, b) in labelled - conflicts
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--srs", type=Path, default=BENCHMARK / "srs_planted.docx")
    parser.add_argument("--labels", type=Path, default=BENCHMARK / "labels.csv")
    parser.add_argument("--embedder", choices=["minilm", "hashing"], default="minilm")
    parser.add_argument("--llm", default="none", help="none | live | replay:<file>")
    parser.add_argument("--record", type=Path, default=None)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    if args.embedder == "minilm":
        from app.embeddings.model import SentenceTransformerEmbedder

        embedder: Any = SentenceTransformerEmbedder()
    else:
        from app.embeddings.model import HashingEmbedder

        embedder = HashingEmbedder()
    llm, recorder = make_llm(args.llm, args.record)
    result = {
        "embedder": getattr(embedder, "version", args.embedder),
        "similarity_threshold": args.threshold,
        "k": args.k,
        "ai_layer": "run" if llm else "not run (no model)",
        "below_threshold_set": below_threshold(args, embedder, llm),
        "planted_srs": planted(args, embedder, llm),
    }
    if recorder is not None and args.record is not None:
        args.record.write_text(json.dumps(recorder.replies, indent=1), encoding="utf-8")
    text = json.dumps(result, indent=2)
    if args.json:
        args.json.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
