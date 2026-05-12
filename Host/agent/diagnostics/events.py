"""Diagnostic events subsystem.

Agent generates local diagnostic events with severity levels,
stores them, and can send them to server or cache locally.
"""

import enum
import json
import time
import threading
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict


class Severity(enum.Enum):
    """Event severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def __str__(self) -> str:
        return self.value


@dataclass
class DiagnosticEvent:
    """Single diagnostic event from agent component."""

    component: str
    event: str
    severity: Severity
    details: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)
    agent_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "component": self.component,
            "event": self.event,
            "severity": self.severity.value,
            "details": self.details or {},
            "agent_id": self.agent_id,
        }

    def to_ws_message(self) -> Dict[str, Any]:
        """Format as WebSocket message for server."""
        return {
            "type": "diagnostic_event",
            "event": self.to_dict(),
        }

    @classmethod
    def info(cls, component: str, event: str, details: Optional[Dict] = None) -> "DiagnosticEvent":
        return cls(component=component, event=event, severity=Severity.INFO, details=details)

    @classmethod
    def warning(cls, component: str, event: str, details: Optional[Dict] = None) -> "DiagnosticEvent":
        return cls(component=component, event=event, severity=Severity.WARNING, details=details)

    @classmethod
    def error(cls, component: str, event: str, details: Optional[Dict] = None) -> "DiagnosticEvent":
        return cls(component=component, event=event, severity=Severity.ERROR, details=details)

    @classmethod
    def critical(cls, component: str, event: str, details: Optional[Dict] = None) -> "DiagnosticEvent":
        return cls(component=component, event=event, severity=Severity.CRITICAL, details=details)


class DiagnosticEventStore:
    """Thread-safe event store with local caching.

    Events are stored with max capacity.
    If server is unreachable, events are cached and sent on reconnect.
    """

    def __init__(self, max_events: int = 1000):
        self._events: List[DiagnosticEvent] = []
        self._lock = threading.Lock()
        self._max_events = max_events

    def add(self, event: DiagnosticEvent) -> None:
        """Add a diagnostic event. Thread-safe."""
        with self._lock:
            self._events.append(event)
            # Trim to max
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]

    def add_event(
        self,
        component: str,
        event: str,
        severity: Severity,
        details: Optional[Dict[str, Any]] = None,
        agent_id: str = "",
    ) -> DiagnosticEvent:
        """Create and add event in one call."""
        ev = DiagnosticEvent(
            component=component,
            event=event,
            severity=severity,
            details=details,
            agent_id=agent_id,
        )
        self.add(ev)
        return ev

    def get_all(self) -> List[DiagnosticEvent]:
        """Get all stored events. Thread-safe."""
        with self._lock:
            return list(self._events)

    def get_pending(self, since: float = 0.0) -> List[DiagnosticEvent]:
        """Get events since given timestamp. Thread-safe."""
        with self._lock:
            return [e for e in self._events if e.timestamp >= since]

    def get_by_severity(self, severity: Severity) -> List[DiagnosticEvent]:
        """Filter events by severity. Thread-safe."""
        with self._lock:
            return [e for e in self._events if e.severity == severity]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._events)

    def get_latest(self, n: int = 10) -> List[DiagnosticEvent]:
        with self._lock:
            return list(self._events[-n:])

    def to_dict_list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self._events]