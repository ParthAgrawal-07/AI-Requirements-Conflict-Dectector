"""Suggestion correctness study for Checkpoint 2 (Abhyudit — US-45, NFR-36).

Acceptance is not proof that a suggestion was right, so analysts rate a sample of suggestions for
correctness and the CP2 report puts the two side by side. This tool:

1. ``sample`` — picks ``--n`` ready suggestions of a project (30 by default), stratified by
   category, and writes a rating sheet (CSV) with the requirements, the finding and each option;
2. ``submit`` — sends the sheet's ratings (1 = wrong or harmful … 5 = correct, adopt as is) to
   ``POST /suggestions/{id}/rating``, stored append-only as ``expert_rating`` feedback;
3. ``report`` — prints ``GET /projects/{p}/suggestions/stats``: outcomes per category next to the
   expert ratings.

Ratings are per option; an analyst may leave an option blank. Analysts need ``finding.review``.

Usage (from the repository root)::

    python eval/suggestion_rating.py sample --api http://localhost:8000 --project <id> \\
        --email analyst@example.com --out eval/reports/cp2_rating_sheet.csv
    python eval/suggestion_rating.py submit --api … --email … --sheet eval/reports/cp2_rating_sheet.csv
    python eval/suggestion_rating.py report --api … --email … --project <id>
"""

import argparse
import csv
import getpass
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

COLUMNS = ["suggestion_id", "category", "requirements", "finding", "option_index", "option",
           "trade_off", "ai_confidence", "rating", "note"]  # fmt: skip


def login(api: str, email: str) -> httpx.Client:
    password = getpass.getpass(f"Password for {email}: ")
    client = httpx.Client(base_url=f"{api.rstrip('/')}/api/v1", timeout=30)
    response = client.post("/auth/login", data={"username": email, "password": password})
    response.raise_for_status()
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


def findings(client: httpx.Client, project: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = client.get(f"/projects/{project}/findings", params={"limit": 200, "offset": offset})
        page.raise_for_status()
        body = page.json()
        found.extend(body["items"])
        offset += len(body["items"])
        if not body["items"] or offset >= body["total"]:
            return found


def sample(args: argparse.Namespace) -> None:
    client = login(args.api, args.email)
    by_category: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for finding in findings(client, args.project):
        response = client.get(f"/findings/{finding['id']}/suggestions")
        if response.status_code == 200 and response.json()["status"] == "ready":
            by_category[finding["category"]].append((finding, response.json()))
    rng = random.Random(args.seed)
    for items in by_category.values():
        rng.shuffle(items)
    chosen: list[tuple[dict[str, Any], dict[str, Any]]] = []
    while len(chosen) < args.n and any(by_category.values()):
        for category in sorted(by_category):  # round-robin: every category is represented
            if by_category[category] and len(chosen) < args.n:
                chosen.append(by_category[category].pop())
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for finding, suggestion in chosen:
            texts = " || ".join(f"{r.get('label')}: {r.get('body', '')}" for r in finding.get("requirements", []))
            for index, option in enumerate(suggestion["options"]):
                writer.writerow({
                    "suggestion_id": suggestion["id"], "category": suggestion["category"],
                    "requirements": texts, "finding": finding.get("explanation", ""),
                    "option_index": index, "option": option["text"], "trade_off": option["trade_off"],
                    "ai_confidence": option["confidence"], "rating": "", "note": "",
                })  # fmt: skip
    print(f"{len(chosen)} suggestions written to {args.out}; fill the rating column (1-5).")


def submit(args: argparse.Namespace) -> None:
    client = login(args.api, args.email)
    sent = skipped = 0
    with args.sheet.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not row["rating"].strip():
                skipped += 1
                continue
            response = client.post(
                f"/suggestions/{row['suggestion_id']}/rating",
                json={"option_index": int(row["option_index"]), "rating": int(row["rating"]),
                      "note": row["note"] or None},
            )  # fmt: skip
            response.raise_for_status()
            sent += 1
    print(f"{sent} ratings stored, {skipped} options left unrated.")


def report(args: argparse.Namespace) -> None:
    client = login(args.api, args.email)
    response = client.get(f"/projects/{args.project}/suggestions/stats")
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("sample", "submit", "report"):
        command = commands.add_parser(name)
        command.add_argument("--api", default="http://localhost:8000")
        command.add_argument("--email", required=True)
        if name in ("sample", "report"):
            command.add_argument("--project", required=True)
    commands.choices["sample"].add_argument("--n", type=int, default=30)
    commands.choices["sample"].add_argument("--seed", type=int, default=314)
    commands.choices["sample"].add_argument("--out", type=Path, default=Path("eval/reports/cp2_rating_sheet.csv"))
    commands.choices["submit"].add_argument("--sheet", type=Path, required=True)
    args = parser.parse_args()
    {"sample": sample, "submit": submit, "report": report}[args.command](args)


if __name__ == "__main__":
    main()
