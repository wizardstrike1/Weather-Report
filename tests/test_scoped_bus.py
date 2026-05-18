"""ScopedBus stamps each solver's events with its project id so the GUI can
keep simultaneous challenges' conversations separate."""
from ctf_copilot.core.events import EventBus, EventType, ScopedBus


def test_scoped_bus_injects_project():
    bus = EventBus()
    seen = []
    bus.subscribe(EventType.LOG, lambda e: seen.append(e.payload))
    bus.subscribe(EventType.SOLVER_STATE, lambda e: seen.append(e.payload))

    a = ScopedBus(bus, "/proj/A")
    b = ScopedBus(bus, "/proj/B")
    a.log("hello")
    b.publish(EventType.SOLVER_STATE, state="thinking", step=1)
    a.publish(EventType.SOLVER_STATE, state="solved")

    assert seen[0]["project"] == "/proj/A" and seen[0]["message"] == "hello"
    assert seen[1]["project"] == "/proj/B" and seen[1]["state"] == "thinking"
    assert seen[2]["project"] == "/proj/A" and seen[2]["state"] == "solved"


def test_scoped_bus_respects_explicit_project():
    bus = EventBus()
    got = []
    bus.subscribe(EventType.NOTE, lambda e: got.append(e.payload["project"]))
    ScopedBus(bus, "/A").publish(EventType.NOTE, project="/override")
    assert got == ["/override"]  # setdefault: don't clobber an explicit id
