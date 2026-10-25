"""Similar-requirement hint latency (Heet — Sprint 0 spike; target under 500 ms server time).

Measures what the composer's "similar requirements" panel will cost per pause in typing:
embed one text with all-MiniLM-L6-v2, then a pgvector top-5 search over one project.

    cd backend
    python ../eval/latency/hints_bench.py --requirements 500 --queries 50

Needs ``DATABASE_URL`` (a migrated database) and downloads the model on first run. Everything it
writes happens in one transaction that is rolled back, so the database is left as it was.
Copy the printed numbers into ``docs/spikes/hints-latency.md``.
"""

import argparse
import random
import statistics
import time
import uuid

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


def _seed_project(db: Session, count: int) -> tuple[Project, Document]:
    tag = uuid.uuid4().hex[:6]
    workspace = Workspace(name=f"bench-{tag}")
    user = User(email=f"bench-{tag}@example.com", full_name="Bench", hashed_password="x")
    db.add_all([workspace, user])
    db.flush()
    project = Project(workspace_id=workspace.id, name="bench")
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
        for i, body in enumerate(synthetic_requirements(count, seed=7))
    )
    db.flush()
    return project, document


def main() -> None:
    parser = argparse.ArgumentParser(description="Similar-requirement hint latency")
    parser.add_argument("--requirements", type=int, default=500)
    parser.add_argument("--queries", type=int, default=50)
    args = parser.parse_args()

    embedder = SentenceTransformerEmbedder()
    embedder.embed(["warm up"])  # loading the model is once per worker, not per request

    timings: list[float] = []
    with get_engine().connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            project, document = _seed_project(db, args.requirements)
            started = time.perf_counter()
            embed_document(db, document.id, embedder)
            elapsed = time.perf_counter() - started
            print(f"embedded {args.requirements} requirements in {elapsed:.1f} s")

            for text in synthetic_requirements(args.queries, seed=99):
                started = time.perf_counter()
                nearest_requirements(db, project.id, embedder.embed([text])[0], k=5)
                timings.append((time.perf_counter() - started) * 1000)
        finally:
            db.close()
            transaction.rollback()

    timings.sort()
    p95 = timings[max(0, int(len(timings) * 0.95) - 1)]
    print(
        f"hint latency over {len(timings)} queries: median {statistics.median(timings):.0f} ms, "
        f"p95 {p95:.0f} ms, max {timings[-1]:.0f} ms (target < 500 ms)"
    )


if __name__ == "__main__":
    main()
