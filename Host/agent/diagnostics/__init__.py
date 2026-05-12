"""Diagnostics subsystem for Remote Agent.

Provides:
- Agent FSM (finite state machine)
- Diagnostic events with severity
- Recovery manager with cooldowns
- Structured logging
- Heartbeat subsystem
- ACK protocol
- Screenshot watchdog
"""

from agent.diagnostics.state_machine import AgentFSM, AgentState
from agent.diagnostics.events import DiagnosticEvent, Severity, DiagnosticEventStore
from agent.diagnostics.recovery import RecoveryManager, RecoveryResult, RecoveryAction
from agent.diagnostics.logger import StructuredLogger
from agent.diagnostics.heartbeat import HeartbeatSender
from agent.diagnostics.ack import ACKSender
from agent.diagnostics.watchdog import ScreenshotWatchdog

__all__ = [
    "AgentFSM",
    "AgentState",
    "DiagnosticEvent",
    "Severity",
    "DiagnosticEventStore",
    "RecoveryManager",
    "RecoveryResult",
    "RecoveryAction",
    "StructuredLogger",
    "HeartbeatSender",
    "ACKSender",
    "ScreenshotWatchdog",
]