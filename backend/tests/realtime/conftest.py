"""An in-process event bus for real-time tests, shared by publishers and the gateway."""

from collections.abc import Iterator

import pytest

from app.realtime import bus, gateway


@pytest.fixture
def event_bus(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    monkeypatch.setattr(gateway, "make_fanout", lambda: gateway.MemoryFanout(test_bus))
    yield test_bus
