"""Migrations 0003 (severity) and 0004 (tenancy) on a database that already holds data.

An empty database proves little: the risk in 0004 is the *backfill* — existing users, documents
and requirements must survive the move from "one workspace and one role per user" to projects,
memberships and permission-based roles (the plan's risk "tenancy and permission refactor breaks Sprint 0-1 code").
"""

import time
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from tests.conftest import BACKEND_DIR


def _config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False
    return config


def _upgrade(engine: Engine, revision: str) -> None:
    config = _config()
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, revision)


def _downgrade(engine: Engine, revision: str) -> None:
    config = _config()
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        command.downgrade(config, revision)


def _new_id() -> uuid.UUID:
    return uuid.uuid4()


def _insert_user(conn, workspace_id, email, role, created_at, *, active=True):  # type: ignore[no-untyped-def]
    user_id = _new_id()
    conn.execute(
        text(
            "INSERT INTO users (id, email, full_name, hashed_password, role, workspace_id,"
            " is_active, created_at) VALUES (:id, :email, :name, 'h', :role, :ws, :active, :created)"
        ),
        {
            "id": user_id,
            "email": email,
            "name": email.split("@")[0],
            "role": role,
            "ws": workspace_id,
            "active": active,
            "created": created_at,
        },
    )
    return user_id


def _insert_document(conn, workspace_id, uploaded_by, name):  # type: ignore[no-untyped-def]
    document_id = _new_id()
    conn.execute(
        text(
            "INSERT INTO documents (id, workspace_id, uploaded_by, filename, format, size_bytes,"
            " sha256, storage_path) VALUES (:id, :ws, :by, :name, 'pdf', 10, :sha, :path)"
        ),
        {
            "id": document_id,
            "ws": workspace_id,
            "by": uploaded_by,
            "name": name,
            "sha": uuid.uuid4().hex * 2,
            "path": f"{workspace_id}/{document_id}.pdf",
        },
    )
    return document_id


def _insert_requirement(conn, document_id, body):  # type: ignore[no-untyped-def]
    requirement_id = _new_id()
    conn.execute(
        text("INSERT INTO requirements (id, document_id, body) VALUES (:id, :doc, :body)"),
        {"id": requirement_id, "doc": document_id, "body": body},
    )
    return requirement_id


def test_0003_turns_critical_findings_into_high_and_narrows_the_constraint(
    scratch_engine: Engine,
) -> None:
    _upgrade(scratch_engine, "0002")
    with scratch_engine.begin() as conn:
        workspace = _new_id()
        conn.execute(text("INSERT INTO workspaces (id, name) VALUES (:id, 'W')"), {"id": workspace})
        user = _insert_user(conn, workspace, "a@example.com", "analyst", "2026-01-01")
        document = _insert_document(conn, workspace, user, "srs.pdf")
        requirement = _insert_requirement(conn, document, "The system shall X.")
        for severity in ("critical", "low"):
            conn.execute(
                text(
                    "INSERT INTO findings (id, document_id, requirement_id, category, confidence,"
                    " rationale, severity, original_ai_output) VALUES (:id, :doc, :req,"
                    " 'Conflicting', 0.9, 'r', :sev, '{}'::jsonb)"
                ),
                {"id": _new_id(), "doc": document, "req": requirement, "sev": severity},
            )

    _upgrade(scratch_engine, "0003")

    with scratch_engine.connect() as conn:
        severities = sorted(conn.scalars(text("SELECT severity FROM findings")).all())
    assert severities == ["high", "low"]  # critical became high, low untouched

    with scratch_engine.begin() as conn:
        try:
            conn.execute(text("UPDATE findings SET severity = 'critical'"))
        except Exception as exc:  # noqa: BLE001 — any DB error proves the constraint
            assert "ck_findings_finding_severity" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("'critical' must be rejected after 0003")

    _downgrade(scratch_engine, "0002")
    with scratch_engine.begin() as conn:  # the old constraint accepts it again
        conn.execute(text("UPDATE findings SET severity = 'critical' WHERE severity = 'high'"))


def test_0004_backfills_projects_memberships_and_requirement_columns(
    scratch_engine: Engine,
) -> None:
    _upgrade(scratch_engine, "0003")
    with scratch_engine.begin() as conn:
        acme, solo, empty = _new_id(), _new_id(), _new_id()
        conn.execute(
            text(
                "INSERT INTO workspaces (id, name, similarity_threshold) VALUES"
                " (:a, 'Acme', 0.6), (:b, 'Solo', 0.75), (:c, 'Empty', 0.75)"
            ),
            {"a": acme, "b": solo, "c": empty},
        )
        # Acme: two admins (the *earlier* one must become Owner), an analyst, a compliance
        # reviewer, a read-only user, a deactivated analyst and a service account.
        late_admin = _insert_user(conn, acme, "late-admin@x.io", "admin", "2026-03-01")
        first_admin = _insert_user(conn, acme, "first-admin@x.io", "admin", "2026-01-01")
        analyst = _insert_user(conn, acme, "analyst@x.io", "analyst", "2026-02-01")
        reviewer = _insert_user(conn, acme, "reviewer@x.io", "compliance_reviewer", "2026-02-02")
        reader = _insert_user(conn, acme, "reader@x.io", "read_only", "2026-02-03")
        gone = _insert_user(conn, acme, "gone@x.io", "analyst", "2026-02-04", active=False)
        service = _insert_user(conn, acme, "svc@x.io", "service", "2026-02-05")
        # Solo: no admin at all — the earliest user must still end up as Owner.
        only_analyst = _insert_user(conn, solo, "only@x.io", "analyst", "2026-01-05")

        document = _insert_document(conn, acme, analyst, "srs.pdf")
        other_document = _insert_document(conn, solo, only_analyst, "solo.pdf")
        r1 = _insert_requirement(conn, document, "The system shall A.")
        r2 = _insert_requirement(conn, other_document, "The system shall B.")

    _upgrade(scratch_engine, "0004")

    with scratch_engine.connect() as conn:
        # one project per workspace, active, carrying the workspace's threshold
        projects = {
            row.name: row
            for row in conn.execute(
                text("SELECT name, status, similarity_threshold, workspace_id FROM projects")
            )
        }
        assert set(projects) == {"Acme", "Solo", "Empty"}
        assert {p.status for p in projects.values()} == {"active"}
        assert projects["Acme"].similarity_threshold == 0.6

        roles = dict(
            conn.execute(
                text(
                    "SELECT m.user_id, r.name FROM memberships m JOIN roles r ON r.id = m.role_id"
                    " WHERE m.ended_at IS NULL"
                )
            ).all()
        )
        assert roles[first_admin] == "Owner"  # first admin by creation time
        assert roles[late_admin] == "Admin"
        assert roles[analyst] == "Business Analyst"
        assert roles[reviewer] == "Compliance Reviewer"
        assert roles[reader] == "Viewer"
        assert roles[gone] == "Business Analyst"  # deactivated users keep their (inactive) seat
        assert roles[only_analyst] == "Owner"  # no admin -> the earliest user owns the workspace
        assert service not in roles  # service accounts are platform-level, not members

        assert (
            conn.scalar(text("SELECT platform_role FROM users WHERE id = :id"), {"id": service})
            == "service"
        )
        assert conn.scalar(text("SELECT count(*) FROM users WHERE platform_role IS NOT NULL")) == 1
        owners = conn.scalar(
            text(
                "SELECT count(*) FROM memberships m JOIN roles r ON r.id = m.role_id"
                " WHERE r.name = 'Owner'"
            )
        )
        assert owners == 2  # exactly one per workspace that has people

        # documents and requirements point at their workspace's project; legacy = baseline
        doc_row = conn.execute(
            text(
                "SELECT d.project_id, p.name, d.import_mode FROM documents d"
                " JOIN projects p ON p.id = d.project_id WHERE d.id = :id"
            ),
            {"id": document},
        ).one()
        assert (doc_row.name, doc_row.import_mode) == ("Acme", "baseline")
        req_rows = {
            row.id: row
            for row in conn.execute(
                text(
                    "SELECT r.id, r.project_id, r.state, r.origin, p.name FROM requirements r"
                    " JOIN projects p ON p.id = r.project_id"
                )
            )
        }
        assert req_rows[r1].name == "Acme" and req_rows[r2].name == "Solo"
        assert {row.state for row in req_rows.values()} == {"Approved"}
        assert {row.origin for row in req_rows.values()} == {"document"}

        columns = set(
            conn.scalars(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
            ).all()
        )
        assert "role" not in columns and "workspace_id" not in columns


def test_0004_downgrade_restores_roles_and_workspaces_for_existing_users(
    scratch_engine: Engine,
) -> None:
    _upgrade(scratch_engine, "0003")
    with scratch_engine.begin() as conn:
        workspace = _new_id()
        conn.execute(text("INSERT INTO workspaces (id, name) VALUES (:id, 'W')"), {"id": workspace})
        admin = _insert_user(conn, workspace, "admin@x.io", "admin", "2026-01-01")
        analyst = _insert_user(conn, workspace, "analyst@x.io", "analyst", "2026-01-02")
        reviewer = _insert_user(conn, workspace, "rev@x.io", "compliance_reviewer", "2026-01-03")
        reader = _insert_user(conn, workspace, "read@x.io", "read_only", "2026-01-04")
        service = _insert_user(conn, workspace, "svc@x.io", "service", "2026-01-05")
    _upgrade(scratch_engine, "0004")

    # A platform admin created after the upgrade has no workspace to go back to.
    with scratch_engine.begin() as conn:
        platform_admin = _new_id()
        conn.execute(
            text(
                "INSERT INTO users (id, email, full_name, hashed_password, platform_role)"
                " VALUES (:id, 'root@x.io', 'Root', 'h', 'platform_admin')"
            ),
            {"id": platform_admin},
        )

    _downgrade(scratch_engine, "0003")

    with scratch_engine.connect() as conn:
        rows = {
            row.id: row
            for row in conn.execute(
                text(
                    "SELECT u.id, u.role, w.name AS workspace FROM users u JOIN workspaces w ON w.id = u.workspace_id"
                )
            )
        }
    assert rows[admin].role == "admin"  # Owner maps back to admin
    assert rows[analyst].role == "analyst"
    assert rows[reviewer].role == "compliance_reviewer"
    assert rows[reader].role == "read_only"
    assert rows[service].role == "service"
    assert {rows[u].workspace for u in (admin, analyst, reviewer, reader)} == {"W"}
    assert rows[service].workspace == "Recovered users"  # no membership to say where it was
    assert rows[platform_admin].role == "admin"
    assert rows[platform_admin].workspace == "Recovered users"  # NOT NULL needs *some* workspace


def test_0004_can_be_reapplied_after_a_downgrade(scratch_engine: Engine) -> None:
    _upgrade(scratch_engine, "head")
    _downgrade(scratch_engine, "0003")
    _upgrade(scratch_engine, "head")
    with scratch_engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM roles WHERE is_default")) == 9


# ── 0004a: the PR-review follow-up migration ─────────────────────────────────────────────────
def test_0004a_drops_the_unique_workspace_name_and_fixes_the_owner_wording(
    scratch_engine: Engine,
) -> None:
    _upgrade(scratch_engine, "0004")
    with scratch_engine.begin() as conn:
        old = conn.scalar(text("SELECT description FROM roles WHERE is_default AND name = 'Owner'"))
        conn.execute(text("INSERT INTO workspaces (id, name) VALUES (gen_random_uuid(), 'Dup')"))
        try:
            with conn.begin_nested():
                conn.execute(
                    text("INSERT INTO workspaces (id, name) VALUES (gen_random_uuid(), 'Dup')")
                )
        except Exception as exc:  # noqa: BLE001 — the unique constraint of 0001
            assert "uq_workspaces_name" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("names were unique before 0004a")
    assert old is not None and "everything" in old

    _upgrade(scratch_engine, "0004a")

    with scratch_engine.begin() as conn:
        conn.execute(text("INSERT INTO workspaces (id, name) VALUES (gen_random_uuid(), 'Dup')"))
        assert conn.scalar(text("SELECT count(*) FROM workspaces WHERE name = 'Dup'")) == 2
        new = conn.scalar(text("SELECT description FROM roles WHERE is_default AND name = 'Owner'"))
    assert new is not None and "everything" not in new and "compliance sign-off" in new


def test_0004a_applies_on_a_database_where_0004_already_ran_with_data(
    scratch_engine: Engine,
) -> None:
    """The Render case: 0004 may already be applied; the review fixes must apply on top of it."""
    _upgrade(scratch_engine, "0003")
    with scratch_engine.begin() as conn:
        workspace = _new_id()
        conn.execute(text("INSERT INTO workspaces (id, name) VALUES (:id, 'W')"), {"id": workspace})
        _insert_user(conn, workspace, "a@x.io", "admin", "2026-01-01")
    _upgrade(scratch_engine, "0004")
    _upgrade(scratch_engine, "head")  # 0004a and anything after it
    with scratch_engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM memberships")) == 1


def test_0004a_downgrade_renames_duplicates_so_the_constraint_can_return(
    scratch_engine: Engine,
) -> None:
    _upgrade(scratch_engine, "0004a")
    with scratch_engine.begin() as conn:
        for _ in range(3):
            conn.execute(
                text("INSERT INTO workspaces (id, name) VALUES (gen_random_uuid(), 'Same')")
            )

    _downgrade(scratch_engine, "0004")

    with scratch_engine.connect() as conn:
        names = sorted(conn.scalars(text("SELECT name FROM workspaces")).all())
    assert len(names) == len(set(names)) == 3  # all distinct again
    assert names.count("Same") == 1  # the oldest keeps its name
    assert all(n.startswith("Same") for n in names)


# ── 0004 on a realistic volume, checked with the runbook's verification script ───────────────
VERIFY_SQL = Path(__file__).resolve().parents[2] / "scripts" / "verify_tenancy_backfill.sql"


def _problems(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {row[0]: row[1] for row in conn.execute(text(VERIFY_SQL.read_text()))}


def test_0004_backfills_a_realistic_volume_correctly_and_quickly(scratch_engine: Engine) -> None:
    """300 workspaces, 3,000 users, 900 documents, 18,000 requirements — the shape of real data,
    including workspaces with no users, only inactive users, only a service account, and no admin."""
    _upgrade(scratch_engine, "0003")
    with scratch_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces (id, name, similarity_threshold) "
                "SELECT gen_random_uuid(), 'WS ' || g, 0.5 + (g % 5) / 10.0 "
                "FROM generate_series(1, 300) g"
            )
        )
        # 10 users per workspace for most; roles rotate; ties in created_at on purpose.
        conn.execute(
            text(
                """
                INSERT INTO users (id, email, full_name, hashed_password, role, workspace_id,
                                   is_active, created_at)
                SELECT gen_random_uuid(), 'u' || w.n || '-' || u || '@x.io', 'User', 'h',
                       (ARRAY['analyst','admin','compliance_reviewer','read_only','analyst'])[1 + (u % 5)],
                       w.id,
                       NOT (w.n % 17 = 0),                 -- every 17th workspace: all inactive
                       TIMESTAMPTZ '2026-01-01'            -- identical timestamps: ties
                FROM (SELECT id, row_number() OVER (ORDER BY name) AS n FROM workspaces) w,
                     generate_series(1, 10) u
                WHERE w.n % 23 <> 0                          -- every 23rd workspace: no users at all
                """
            )
        )
        conn.execute(  # every 29th workspace: only a service account
            text(
                """
                DELETE FROM users WHERE workspace_id IN (
                    SELECT id FROM (SELECT id, row_number() OVER (ORDER BY name) AS n FROM workspaces) w
                    WHERE w.n % 29 = 0)
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO users (id, email, full_name, hashed_password, role, workspace_id)
                SELECT gen_random_uuid(), 'svc' || n || '@x.io', 'Svc', 'h', 'service', id
                FROM (SELECT id, row_number() OVER (ORDER BY name) AS n FROM workspaces) w
                WHERE n % 29 = 0 OR n % 7 = 0
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO documents (id, workspace_id, uploaded_by, filename, format, size_bytes,
                                       sha256, storage_path)
                SELECT gen_random_uuid(), u.workspace_id, u.id, 'srs-' || g || '.pdf', 'pdf', 10,
                       md5(u.id::text || g) || md5(g::text || u.id::text), 'p/' || u.id || '/' || g
                FROM (SELECT DISTINCT ON (workspace_id) id, workspace_id FROM users
                      WHERE role <> 'service' ORDER BY workspace_id, email) u,
                     generate_series(1, 3) g
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO requirements (id, document_id, body, order_index) "
                "SELECT gen_random_uuid(), d.id, 'The system shall do item ' || g, g "
                "FROM documents d, generate_series(1, 20) g"
            )
        )
        counts_before = {
            name: conn.scalar(text(f"SELECT count(*) FROM {name}"))
            for name in ("workspaces", "users", "documents", "requirements")
        }
        humans_before = conn.scalar(text("SELECT count(*) FROM users WHERE role <> 'service'"))

    started = time.monotonic()
    _upgrade(scratch_engine, "0004")
    elapsed = time.monotonic() - started

    with scratch_engine.connect() as conn:
        after = {
            name: conn.scalar(text(f"SELECT count(*) FROM {name}"))
            for name in ("workspaces", "users", "documents", "requirements")
        }
        assert after == counts_before  # nothing was lost or duplicated
        assert conn.scalar(text("SELECT count(*) FROM projects")) == counts_before["workspaces"]
        assert conn.scalar(text("SELECT count(*) FROM memberships")) == humans_before
        assert (
            conn.scalar(text("SELECT count(*) FROM requirements WHERE state = 'Approved'"))
            == (counts_before["requirements"])
        )
    problems = _problems(scratch_engine)
    assert len(problems) == 10  # every check in the script ran
    assert set(problems.values()) == {0}, problems
    assert elapsed < 30, f"backfill took {elapsed:.1f}s — set-based SQL should be much faster"


def test_the_verification_script_really_detects_problems(scratch_engine: Engine) -> None:
    """A check that cannot fail proves nothing: break the data and watch it notice."""
    _upgrade(scratch_engine, "0003")
    with scratch_engine.begin() as conn:
        workspace = _new_id()
        conn.execute(text("INSERT INTO workspaces (id, name) VALUES (:id, 'W')"), {"id": workspace})
        admin = _insert_user(conn, workspace, "a@x.io", "admin", "2026-01-01")
        _insert_user(conn, workspace, "b@x.io", "analyst", "2026-01-02")
        document = _insert_document(conn, workspace, admin, "s.pdf")
        _insert_requirement(conn, document, "The system shall X.")
    _upgrade(scratch_engine, "0004")
    assert set(_problems(scratch_engine).values()) == {0}

    with scratch_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE memberships SET role_id = (SELECT id FROM roles WHERE name = 'Viewer' AND is_default)"
            )
        )
        conn.execute(text("DELETE FROM project_members"))
        conn.execute(
            text(
                "INSERT INTO users (id, email, full_name, hashed_password) VALUES (gen_random_uuid(), 'orphan@x.io', 'O', 'h')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO findings (id, document_id, requirement_id, category, confidence, rationale, severity, original_ai_output) SELECT gen_random_uuid(), document_id, id, 'Ambiguous', 0.5, 'r', 'low', '{}'::jsonb FROM requirements"
            )
        )

    found = _problems(scratch_engine)
    assert found["workspace with members but no Owner"] == 1
    assert found["person without any membership (neither service nor platform admin)"] == 1
