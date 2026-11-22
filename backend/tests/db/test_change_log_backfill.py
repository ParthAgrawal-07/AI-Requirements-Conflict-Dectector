"""Migration 0009 backfills the change log from the audit log (Dhavni — US-55).

Changes made before Sprint 6 have no ``graph_events`` rows of their own; the migration writes one
per audited post, state change, change request, issue, concern, owner change and finding review,
with the same template wording as ``app.graph.narrator`` and no requirement text.
"""

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


SEED = """
INSERT INTO workspaces (id, name) VALUES ('00000000-0000-0000-0000-00000000000a', 'W');
INSERT INTO users (id, email, full_name, hashed_password)
    VALUES ('00000000-0000-0000-0000-0000000000a1', 'arjun@example.com', 'Arjun', 'x'),
           ('00000000-0000-0000-0000-0000000000a2', 'riya@example.com', 'Riya', 'x');
INSERT INTO projects (id, workspace_id, name)
    VALUES ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-00000000000a', 'P');
INSERT INTO requirements (id, project_id, body, origin, source_req_id)
    VALUES ('00000000-0000-0000-0000-0000000000c1', '00000000-0000-0000-0000-0000000000b1',
            'The vault code is 4711.', 'post', 'REQ-031');
INSERT INTO audit_log (workspace_id, actor_id, requirement_id, action, details, at) VALUES
    ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
     '00000000-0000-0000-0000-0000000000c1', 'requirement_posted', '{}', now() - interval '3 day'),
    ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
     '00000000-0000-0000-0000-0000000000c1', 'state_changed',
     '{"from": "Proposed", "to": "Approved", "version": 1}', now() - interval '2 day'),
    ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
     '00000000-0000-0000-0000-0000000000c1', 'owner_changed',
     '{"before": null, "after": "00000000-0000-0000-0000-0000000000a2"}', now() - interval '1 day'),
    ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1', NULL,
     'member_added', '{}', now());
"""


def test_audited_changes_become_written_change_log_rows(scratch_engine: Engine) -> None:
    _upgrade(scratch_engine, "0010c")
    with scratch_engine.begin() as conn:
        for statement in SEED.split(";"):
            if statement.strip():
                conn.execute(text(statement))

    _upgrade(scratch_engine, "0009")

    with scratch_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT kind, sentence, revision, backfilled, counts, node_ids "
                "FROM graph_events ORDER BY created_at"
            )
        ).all()
    assert [(r.kind, r.sentence) for r in rows] == [
        ("added", "Arjun added REQ-031 (Proposed)."),
        ("state", "Arjun approved REQ-031."),
        ("owner", "Arjun made Riya the owner of REQ-031."),
    ]  # the member_added row is not a change to the map
    assert all(r.revision is None and r.backfilled for r in rows)
    assert rows[0].counts == {"requirements_added": 1}
    assert rows[0].node_ids == ["00000000-0000-0000-0000-0000000000c1"]
    assert all("4711" not in r.sentence for r in rows)
