"""
Diagnostics Logger.
Separate JSON-structured log for all diagnostic events with severity levels,
component tagging, and structured recovery audit trail.
"""
import json
import os
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum, auto


class Severity(Enum):
    DEBUG = 'debug'
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


class DiagnosticEvent:
    """
    Single diagnostic event data class.
    Every event carries component, severity, timestamp, and optional recovery context.
    """

    def __init__(
        self,
        component: str,
        event: str,
        severity: Severity = Severity.INFO,
        agent_id: Optional[str] = None,
        message: str = '',
        recovery_action: Optional[str] = None,
        recovery_status: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        exception: Optional[str] = None,
    ):
        self.timestamp = datetime.utcnow().isoformat()
        self.component = component
        self.event = event
        self.severity = severity
        self.agent_id = agent_id
        self.message = message
        self.recovery_action = recovery_action
        self.recovery_status = recovery_status
        self.context = context or {}
        self.exception = exception

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            'timestamp': self.timestamp,
            'component': self.component,
            'event': self.event,
            'severity': self.severity.value,
        }
        if self.agent_id:
            d['agent_id'] = self.agent_id
        if self.message:
            d['message'] = self.message
        if self.recovery_action:
            d['recovery_action'] = self.recovery_action
        if self.recovery_status:
            d['recovery_status'] = self.recovery_status
        if self.context:
            d['context'] = self.context
        if self.exception:
            d['exception'] = self.exception
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DiagnosticEvent':
        return cls(
            component=data.get('component', 'unknown'),
            event=data.get('event', 'unknown'),
            severity=Severity(data.get('severity', 'info')),
            agent_id=data.get('agent_id'),
            message=data.get('message', ''),
            recovery_action=data.get('recovery_action'),
            recovery_status=data.get('recovery_status'),
            context=data.get('context'),
            exception=data.get('exception'),
        )


class DiagnosticsLogger:
    """
    Structured diagnostic logger.
    Writes JSON events to a dedicated diagnostics log file,
    keeps an in-memory ring buffer of recent events,
    and allows subscribing callbacks to high-severity events.
    """

    def __init__(
        self,
        log_dir: str = 'logs',
        log_filename: str = 'diagnostics.jsonl',
        max_memory_events: int = 1000,
    ):
        self.log_dir = log_dir
        self.log_path = os.path.join(log_dir, log_filename)
        self.max_memory_events = max_memory_events
        self._memory_buffer: List[Dict[str, Any]] = []
        self._subscribers: List[callable] = []

        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)

        # Also mirror critical events to standard logging
        self._std_logger = logging.getLogger('diagnostics')
        self._std_logger.setLevel(logging.DEBUG)

        # File handler for easy reading by humans
        file_handler = logging.FileHandler(
            os.path.join(log_dir, 'diagnostics.log'),
            encoding='utf-8',
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s'
        ))
        self._std_logger.addHandler(file_handler)

    # ──────────────────────────── Event Logging ────────────────────────────

    def log_event(self, event: DiagnosticEvent):
        """Log a single diagnostic event: to JSONL file, memory buffer, and stdout."""
        # 1) JSONL file (structured)
        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(event.to_json() + '\n')
        except OSError as e:
            self._std_logger.error(f'Cannot write to diagnostics log: {e}')

        # 2) Memory buffer (ring)
        self._memory_buffer.append(event.to_dict())
        if len(self._memory_buffer) > self.max_memory_events:
            self._memory_buffer = self._memory_buffer[-self.max_memory_events:]

        # 3) Standard logger (human-readable)
        log_msg = f'[{event.component}] {event.event}'
        if event.message:
            log_msg += f' — {event.message}'
        if event.agent_id:
            log_msg += f' (agent={event.agent_id})'

        severity_map = {
            Severity.DEBUG: logging.DEBUG,
            Severity.INFO: logging.INFO,
            Severity.WARNING: logging.WARNING,
            Severity.ERROR: logging.ERROR,
            Severity.CRITICAL: logging.CRITICAL,
        }
        self._std_logger.log(severity_map.get(event.severity, logging.INFO), log_msg)

        # 4) Notify subscribers for high-severity events
        if event.severity in (Severity.ERROR, Severity.CRITICAL):
            for cb in self._subscribers:
                try:
                    cb(event)
                except Exception as e:
                    self._std_logger.error(
                        f'Subscriber callback failed: {e}',
                        exc_info=True,
                    )

    # ──────────────────────────── Convenience methods ────────────────────────────

    def debug(
        self,
        component: str,
        event: str,
        agent_id: Optional[str] = None,
        message: str = '',
        **kwargs,
    ):
        self.log_event(DiagnosticEvent(
            component=component, event=event, severity=Severity.DEBUG,
            agent_id=agent_id, message=message, **kwargs,
        ))

    def info(
        self,
        component: str,
        event: str,
        agent_id: Optional[str] = None,
        message: str = '',
        **kwargs,
    ):
        self.log_event(DiagnosticEvent(
            component=component, event=event, severity=Severity.INFO,
            agent_id=agent_id, message=message, **kwargs,
        ))

    def warning(
        self,
        component: str,
        event: str,
        agent_id: Optional[str] = None,
        message: str = '',
        **kwargs,
    ):
        self.log_event(DiagnosticEvent(
            component=component, event=event, severity=Severity.WARNING,
            agent_id=agent_id, message=message, **kwargs,
        ))

    def error(
        self,
        component: str,
        event: str,
        agent_id: Optional[str] = None,
        message: str = '',
        exception: Optional[Exception] = None,
        **kwargs,
    ):
        self.log_event(DiagnosticEvent(
            component=component, event=event, severity=Severity.ERROR,
            agent_id=agent_id, message=message,
            exception=''.join(traceback.format_exception_only(type(exception), exception))
            if exception else None,
            **kwargs,
        ))

    def critical(
        self,
        component: str,
        event: str,
        agent_id: Optional[str] = None,
        message: str = '',
        exception: Optional[Exception] = None,
        **kwargs,
    ):
        self.log_event(DiagnosticEvent(
            component=component, event=event, severity=Severity.CRITICAL,
            agent_id=agent_id, message=message,
            exception=''.join(traceback.format_exception_only(type(exception), exception))
            if exception else None,
            **kwargs,
        ))

    def recovery(
        self,
        component: str,
        event: str,
        agent_id: Optional[str] = None,
        action: str = '',
        status: str = 'started',
        message: str = '',
        **kwargs,
    ):
        """Log a recovery-specific event with action and status fields."""
        self.log_event(DiagnosticEvent(
            component=component, event=event, severity=Severity.INFO,
            agent_id=agent_id, message=message,
            recovery_action=action, recovery_status=status,
            **kwargs,
        ))

    # ──────────────────────────── Subscriptions ────────────────────────────

    def subscribe(self, callback: callable):
        """Subscribe to ERROR and CRITICAL events."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: callable):
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    # ──────────────────────────── Query ────────────────────────────

    def recent_events(
        self,
        n: int = 50,
        component: Optional[str] = None,
        severity: Optional[Severity] = None,
        agent_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent events, optionally filtered."""
        events = self._memory_buffer
        if component:
            events = [e for e in events if e.get('component') == component]
        if severity:
            events = [e for e in events if e.get('severity') == severity.value]
        if agent_id:
            events = [e for e in events if e.get('agent_id') == agent_id]
        return events[-n:]

    def events_by_component(self, component: str, n: int = 50) -> List[Dict[str, Any]]:
        return self.recent_events(n=n, component=component)

    def events_by_severity(self, severity: Severity, n: int = 50) -> List[Dict[str, Any]]:
        return self.recent_events(n=n, severity=severity)

    def clear_memory(self):
        self._memory_buffer.clear()

    @property
    def event_count(self) -> int:
        return len(self._memory_buffer)