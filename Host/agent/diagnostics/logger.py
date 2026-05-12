"""Structured logging for diagnostics subsystem.

Each event contains:
- component
- event
- severity
- agent_id
- timestamp
- details
"""

import json
import time
import logging
import threading
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

from agent.diagnostics.events import Severity


@dataclass
class StructuredLogEntry:
    """A single structured log entry."""

    component: str
    event: str
    severity: Severity
    message: str
    agent_id: str = ""
    details: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat(),
            "component": self.component,
            "event": self.event,
            "severity": self.severity.value,
            "message": self.message,
            "agent_id": self.agent_id,
            "details": self.details or {},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class StructuredLogger:
    """Structured logger that wraps Python logging.

    Adds structured fields to every log call.
    Thread-safe.

    Usage:
        logger = StructuredLogger("heartbeat", agent_id="agent-1")
        logger.info("heartbeat_sent", "Heartbeat sent successfully")
        logger.error("connection_lost", "WS connection lost", {"ws_closed": True})
    """

    def __init__(
        self,
        component: str,
        agent_id: str = "",
        log_level: int = logging.INFO,
    ):
        self._component = component
        self._agent_id = agent_id
        self._lock = threading.Lock()

        # Setup Python logger
        self._py_logger = logging.getLogger(f"agent.{component}")
        self._py_logger.setLevel(log_level)

        # Add console handler if none exists
        if not self._py_logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            self._py_logger.addHandler(handler)

    def _log(
        self,
        severity: Severity,
        event: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
    ) -> StructuredLogEntry:
        entry = StructuredLogEntry(
            component=self._component,
            event=event,
            severity=severity,
            message=message,
            agent_id=self._agent_id,
            details=details,
        )

        # Map to python logging level
        py_level = {
            Severity.CRITICAL: logging.CRITICAL,
            Severity.ERROR: logging.ERROR,
            Severity.WARNING: logging.WARNING,
            Severity.INFO: logging.INFO,
        }.get(severity, logging.INFO)

        log_str = json.dumps(entry.to_dict(), ensure_ascii=False, default=str)
        self._py_logger.log(py_level, log_str, exc_info=exc_info)

        return entry

    def info(
        self,
        event: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> StructuredLogEntry:
        return self._log(Severity.INFO, event, message, details)

    def warning(
        self,
        event: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> StructuredLogEntry:
        return self._log(Severity.WARNING, event, message, details)

    def error(
        self,
        event: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        exc_info: bool = True,
    ) -> StructuredLogEntry:
        return self._log(Severity.ERROR, event, message, details, exc_info=exc_info)

    def critical(
        self,
        event: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        exc_info: bool = True,
    ) -> StructuredLogEntry:
        return self._log(Severity.CRITICAL, event, message, details, exc_info=exc_info)

    @property
    def component(self) -> str:
        return self._component