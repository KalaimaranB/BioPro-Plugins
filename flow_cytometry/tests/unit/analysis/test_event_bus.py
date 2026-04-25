import pytest
from unittest.mock import MagicMock
from flow_cytometry.analysis.event_bus import Event, EventType

def test_event_bus_publish_subscribe(event_bus):
    callback = MagicMock()
    event_bus.subscribe(EventType.GATE_CREATED, callback)
    
    event = Event(EventType.GATE_CREATED, {"id": "gate1"})
    event_bus.publish(event)
    
    assert callback.call_count == 1
    assert callback.call_args[0][0].data["id"] == "gate1"

def test_event_bus_pausing_queues_events(event_bus):
    """Verify that events are queued while paused and flushed on resume."""
    callback = MagicMock()
    event_bus.subscribe(EventType.GATE_CREATED, callback)
    
    event_bus.pause()
    event_bus.publish(Event(EventType.GATE_CREATED, {"id": "gate1"}))
    
    assert callback.call_count == 0
    
    event_bus.resume()
    assert callback.call_count == 1
    assert callback.call_args[0][0].data["id"] == "gate1"

def test_event_bus_unsubscribe(event_bus):
    callback = MagicMock()
    unsub = event_bus.subscribe(EventType.GATE_CREATED, callback)
    unsub()
    
    event_bus.publish(Event(EventType.GATE_CREATED, {}))
    assert callback.call_count == 0
