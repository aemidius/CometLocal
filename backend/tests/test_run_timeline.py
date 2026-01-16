"""
Tests para RunTimeline.
"""

import pytest
import time
from backend.runs.run_timeline import RunTimeline, EventType, RunEvent


def test_timeline_initialization():
    """Test que RunTimeline se inicializa correctamente."""
    timeline = RunTimeline("test_run_1")
    assert timeline.run_id == "test_run_1"
    assert timeline.get_event_count() == 0
    assert timeline.get_last_event() is None


def test_add_event():
    """Test que se pueden añadir eventos al timeline."""
    timeline = RunTimeline("test_run_2")
    
    event = timeline.add_event(EventType.INFO, "Test message")
    
    assert event.type == EventType.INFO
    assert event.message == "Test message"
    assert timeline.get_event_count() == 1
    assert timeline.get_last_event() == event


def test_add_event_with_metadata():
    """Test que se pueden añadir eventos con metadata."""
    timeline = RunTimeline("test_run_3")
    
    metadata = {"key": "value", "number": 42}
    event = timeline.add_event(EventType.ACTION, "Action message", metadata=metadata)
    
    assert event.metadata == metadata
    assert event.to_dict()["metadata"] == metadata


def test_get_events():
    """Test que get_events retorna eventos en orden cronológico."""
    timeline = RunTimeline("test_run_4")
    
    event1 = timeline.add_event(EventType.INFO, "First")
    time.sleep(0.01)  # Pequeño delay para asegurar timestamps diferentes
    event2 = timeline.add_event(EventType.INFO, "Second")
    
    events = timeline.get_events()
    assert len(events) == 2
    assert events[0] == event1
    assert events[1] == event2


def test_get_events_with_limit():
    """Test que get_events con limit retorna los últimos N eventos."""
    timeline = RunTimeline("test_run_5")
    
    for i in range(5):
        timeline.add_event(EventType.INFO, f"Event {i}")
    
    events = timeline.get_events(limit=3)
    assert len(events) == 3
    assert events[0].message == "Event 2"
    assert events[1].message == "Event 3"
    assert events[2].message == "Event 4"


def test_has_errors():
    """Test que has_errors detecta eventos de error."""
    timeline = RunTimeline("test_run_6")
    
    assert timeline.has_errors() is False
    
    timeline.add_event(EventType.INFO, "Info")
    assert timeline.has_errors() is False
    
    timeline.add_event(EventType.ERROR, "Error")
    assert timeline.has_errors() is True


def test_get_risk_level():
    """Test que get_risk_level calcula correctamente el nivel de riesgo."""
    timeline = RunTimeline("test_run_7")
    
    # Sin eventos -> low
    assert timeline.get_risk_level() == "low"
    
    # Con errores -> high
    timeline.add_event(EventType.ERROR, "Error")
    assert timeline.get_risk_level() == "high"
    
    # Reset
    timeline = RunTimeline("test_run_8")
    
    # Con muchos warnings -> medium
    for _ in range(3):
        timeline.add_event(EventType.WARNING, "Warning")
    assert timeline.get_risk_level() == "medium"
    
    # Reset
    timeline = RunTimeline("test_run_9")
    
    # Con muchas acciones -> medium
    for _ in range(4):
        timeline.add_event(EventType.ACTION, "Action")
    assert timeline.get_risk_level() == "medium"


def test_event_to_dict():
    """Test que event.to_dict() serializa correctamente."""
    timeline = RunTimeline("test_run_10")
    event = timeline.add_event(EventType.SUCCESS, "Success message", metadata={"key": "value"})
    
    event_dict = event.to_dict()
    
    assert event_dict["type"] == "SUCCESS"
    assert event_dict["message"] == "Success message"
    assert event_dict["metadata"] == {"key": "value"}
    assert "timestamp" in event_dict
    assert "timestamp_iso" in event_dict
    assert "event_id" in event_dict
