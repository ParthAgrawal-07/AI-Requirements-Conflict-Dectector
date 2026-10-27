from uuid import uuid4

from app.realtime.events import project_channel


def test_project_channel_is_scoped_to_project() -> None:
    project_id = uuid4()
    assert project_channel(project_id) == f"rcd:project:{project_id}:events"
