"""Similar-requirement hint latency (Heet — Sprint 0 spike; target under 500 ms server time).

Measures what the composer's "similar requirements" panel will cost per pause in typing:
embed one text with all-MiniLM-L6-v2, then a pgvector top-5 search over one project.

    cd backend
    PYTHONPATH=. python ../eval/latency/hints_bench.py --requirements 500 --queries 50 --projects 5

Needs ``DATABASE_URL`` (a migrated database) and downloads the model on first run. Everything it
writes happens in one transaction that is rolled back, so the database is left as it was.
Copy the printed numbers into ``docs/spikes/hints-latency.md``.
"""

import argparse
import math
import random
import statistics
import sys
import time
import uuid
from pathlib import Path

# Allow running from repository root, backend/, or container without requiring PYTHONPATH=.
for candidate in [
    Path.cwd(),
    Path.cwd() / "backend",
    Path(__file__).resolve().parents[2] / "backend",
    Path("/app"),
]:
    if (candidate / "app").is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
        break

from sqlalchemy.orm import Session

from app.core.database import get_engine
from app.embeddings.model import SentenceTransformerEmbedder
from app.embeddings.store import embed_document, nearest_requirements
from app.models import Document, DocumentFormat, Project, Requirement, User, Workspace

ACTORS = ["user", "admin", "customer", "teller", "auditor", "mobile app", "system"]
ACTIONS = [
    "sign in with a one-time password",
    "end the session after {n} minutes of inactivity",
    "show the account summary within {n} seconds",
    "export statements as PDF",
    "lock the account after {n} failed attempts",
    "retry a failed payment",
    "notify the customer of transfers above {n} rupees",
]


def synthetic_requirements(count: int, seed: int) -> list[str]:
    rng = random.Random(seed)  # noqa: S311 — test data, not security
    return [
        f"REQ-{i:03d}: The {rng.choice(ACTORS)} shall "
        + rng.choice(ACTIONS).format(n=rng.choice([2, 5, 10, 30, 60, 1000]))
        + "."
        for i in range(1, count + 1)
    ]


def _seed_project(db: Session, count: int, seed_offset: int = 0) -> tuple[Project, Document]:
    tag = uuid.uuid4().hex[:6]
    workspace = Workspace(name=f"bench-{tag}")
    user = User(email=f"bench-{tag}@example.com", full_name="Bench", hashed_password="x")
    db.add_all([workspace, user])
    db.flush()
    project = Project(workspace_id=workspace.id, name=f"bench-{tag}")
    db.add(project)
    db.flush()
    document = Document(
        workspace_id=workspace.id,
        project_id=project.id,
        uploaded_by=user.id,
        filename="bench.docx",
        format=DocumentFormat.DOCX,
        size_bytes=0,
        sha256="0" * 64,
        storage_path="bench",
    )
    db.add(document)
    db.flush()
    db.add_all(
        Requirement(document_id=document.id, project_id=project.id, body=body, order_index=i)
        for i, body in enumerate(synthetic_requirements(count, seed=7 + seed_offset))
    )
    db.flush()
    return project, document


def main() -> None:
    parser = argparse.ArgumentParser(description="Similar-requirement hint latency")
    parser.add_argument("--requirements", type=int, default=500, help="Requirements in target project")
    parser.add_argument("--queries", type=int, default=50, help="Number of benchmark queries")
    parser.add_argument(
        "--projects",
        type=int,
        default=1,
        help="Total projects seeded in database to benchmark multi-tenant search (default 1)",
    )
    args = parser.parse_args()

    embedder = SentenceTransformerEmbedder()
    embedder.embed(["warm up"])  # loading the model is once per worker, not per request

    timings: list[float] = []
    with get_engine().connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            # Seed foreign background projects if multiple projects requested
            for p_idx in range(1, args.projects):
                _, bg_doc = _seed_project(db, args.requirements, seed_offset=p_idx * 1000)
                embed_document(db, bg_doc.id, embedder)

            project, document = _seed_project(db, args.requirements)
            started = time.perf_counter()
            embed_document(db, document.id, embedder)
            elapsed = time.perf_counter() - started
            total_reqs = args.requirements * args.projects
            print(
                f"embedded target project ({args.requirements} reqs; "
                f"{total_reqs} total across {args.projects} project(s)) in {elapsed:.1f} s"
            )

            for text in synthetic_requirements(args.queries, seed=99):
                started = time.perf_counter()
                nearest_requirements(db, project.id, embedder.embed([text])[0], k=5)
                timings.append((time.perf_counter() - started) * 1000)
        finally:
            db.close()
            transaction.rollback()

    timings.sort()
    p95 = timings[min(len(timings) - 1, math.ceil(len(timings) * 0.95) - 1)]
    print(
        f"hint latency over {len(timings)} queries ({args.projects} project(s) seeded): "
        f"median {statistics.median(timings):.0f} ms, "
        f"p95 {p95:.0f} ms, max {timings[-1]:.0f} ms (target < 500 ms)"
    )


if __name__ == "__main__":
    main()
