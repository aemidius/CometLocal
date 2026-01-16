"""
Run Timeline: Modelo de eventos para runs headful persistentes.

Proporciona conciencia operativa: qué ha pasado, qué está pasando, qué va a pasar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class EventType(str, Enum):
    """Tipos de eventos en el timeline."""
    INFO = "INFO"
    WARNING = "WARNING"
    ACTION = "ACTION"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


@dataclass
class RunEvent:
    """Representa un evento en el timeline de un run."""
    event_id: str
    timestamp: float
    type: EventType
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el evento a diccionario para serialización."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.timestamp)),
            "type": self.type.value,
            "message": self.message,
            "metadata": self.metadata,
        }


class RunTimeline:
    """
    Timeline de eventos para un run headful.
    
    Mantiene eventos en orden cronológico.
    Todos los eventos se añaden automáticamente desde el backend.
    """
    
    def __init__(self, run_id: str):
        self.run_id = run_id
        self._events: List[RunEvent] = []
    
    def add_event(
        self,
        event_type: EventType,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RunEvent:
        """
        Añade un evento al timeline.
        
        Genera automáticamente event_id y timestamp.
        """
        event_id = f"{self.run_id}_{len(self._events)}_{int(time.time() * 1000)}"
        event = RunEvent(
            event_id=event_id,
            timestamp=time.time(),
            type=event_type,
            message=message,
            metadata=metadata or {},
        )
        self._events.append(event)
        return event
    
    def get_events(self, limit: Optional[int] = None) -> List[RunEvent]:
        """
        Obtiene eventos del timeline.
        
        Si limit está especificado, devuelve los últimos N eventos.
        """
        events = self._events
        if limit is not None and limit > 0:
            events = events[-limit:]
        return events
    
    def get_events_dict(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Obtiene eventos como lista de diccionarios."""
        return [event.to_dict() for event in self.get_events(limit)]
    
    def get_last_event(self) -> Optional[RunEvent]:
        """Obtiene el último evento del timeline."""
        if not self._events:
            return None
        return self._events[-1]
    
    def get_event_count(self) -> int:
        """Obtiene el número total de eventos."""
        return len(self._events)
    
    def has_errors(self) -> bool:
        """Verifica si hay eventos de tipo ERROR."""
        return any(event.type == EventType.ERROR for event in self._events)
    
    def get_risk_level(self) -> str:
        """
        Calcula nivel de riesgo basado en eventos.
        
        Retorna: "low" | "medium" | "high"
        """
        error_count = sum(1 for event in self._events if event.type == EventType.ERROR)
        warning_count = sum(1 for event in self._events if event.type == EventType.WARNING)
        action_count = sum(1 for event in self._events if event.type == EventType.ACTION)
        
        if error_count > 0:
            return "high"
        if warning_count > 2 or action_count > 3:
            return "medium"
        return "low"
