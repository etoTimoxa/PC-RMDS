"""
Diagnostics Subsystem Package.
Provides self-healing, fault-tolerant monitoring for the PC-RMDS distributed system.
Core: heartbeat, screenshot stream, API health, command ACK protocol.
"""
__version__ = '1.0.0'

from .state_machine import AgentState, DiagnosticStateMachine, StateTransitionError
from .diagnostics_logger import DiagnosticsLogger, DiagnosticEvent, Severity
from .heartbeat import HeartbeatChecker
from .api_checker import APIHealthChecker
from .stream_checker import StreamChecker
from .command_checker import CommandDeliveryChecker, PendingCommand, CommandState
from .recovery_manager import RecoveryManager, RecoveryAction, RecoveryStrategy, RecoveryResult
from .diagnostics_manager import DiagnosticsManager
from .diag_routes import DiagnosticsContext, diagnostics_bp, init_routes

__all__ = [
    'AgentState',
    'DiagnosticStateMachine',
    'StateTransitionError',
    'DiagnosticsLogger',
    'DiagnosticEvent',
    'Severity',
    'HeartbeatChecker',
    'APIHealthChecker',
    'StreamChecker',
    'CommandDeliveryChecker',
    'PendingCommand',
    'CommandState',
    'RecoveryManager',
    'RecoveryAction',
    'RecoveryStrategy',
    'RecoveryResult',
    'DiagnosticsManager',
    'DiagnosticsContext',
    'diagnostics_bp',
    'init_routes',
]