"""
Diagnostics Manager.
Central orchestrator with event bus. Manages lifecycle of all diagnostic subsystems.
Core: heartbeat, screenshot stream, API health, command ACK.
"""
import asyncio
import time
import logging
from typing import Dict, Optional, Any, Callable, List

from .state_machine import DiagnosticStateMachine, AgentState
from .diagnostics_logger import DiagnosticsLogger, Severity, DiagnosticEvent
from .heartbeat import HeartbeatChecker
from .api_checker import APIHealthChecker
from .stream_checker import StreamChecker
from .command_checker import CommandDeliveryChecker
from .recovery_manager import RecoveryManager, RecoveryAction, RecoveryResult
from .diag_routes import init_routes, diagnostics_bp

log = logging.getLogger('diagnostics_manager')


class DiagnosticsManager:
    """
    Top-level manager.
    - Event bus: all components publish events through manager
    - Manages lifecycle (start/stop)
    - Exposes API blueprint for Flask
    """

    def __init__(
        self,
        log_dir: str = 'logs',
        check_db_callback: Optional[Callable[[], bool]] = None,
        check_ws_callback: Optional[Callable[[], bool]] = None,
    ):
        self.logger = DiagnosticsLogger(log_dir=log_dir)
        self._start_time = time.time()
        self.state_machines: Dict[str, DiagnosticStateMachine] = {}

        # Event bus subscribers: event_type -> [callbacks]
        self._subscribers: Dict[str, List[Callable]] = {}

        # Heartbeat — no FSM dependency, just callbacks
        self.heartbeat = HeartbeatChecker(
            logger=self.logger,
            on_timeout=self._on_heartbeat_timeout,
        )

        # API health checker
        self.api_checker = APIHealthChecker(
            logger=self.logger,
            check_db=check_db_callback,
            check_ws=check_ws_callback,
            on_degraded=lambda aid: self.publish('api_degraded', aid),
            on_recovered=lambda aid: self.publish('api_recovered', aid),
        )

        # Stream checker (screenshot only)
        self.stream_checker = StreamChecker(
            logger=self.logger,
            on_screenshot_broken=lambda aid: self.publish('screenshot_broken', aid),
            on_screenshot_recovered=lambda aid: self.publish('screenshot_recovered', aid),
        )

        # Command checker (ACK protocol)
        self.command_checker = CommandDeliveryChecker(
            logger=self.logger,
            on_retry=lambda cmd: self.publish('command_retry', cmd.agent_id),
            on_failed=lambda cmd: self.publish('command_failed', cmd.agent_id),
            on_acked=lambda cmd: self.publish('command_acked', cmd.agent_id),
            send_command_callback=None,
        )

        # Recovery manager
        self.recovery_manager = RecoveryManager(
            logger=self.logger,
            state_machines=self.state_machines,
        )

        # Wire recovery manager to logger subscription (async)
        self.recovery_manager.subscribe_to_logger(self.logger)

        # Register recovery handlers
        self._register_recovery_handlers()

        # Initialize API routes
        init_routes(
            logger=self.logger,
            heartbeat=self.heartbeat,
            api_checker=self.api_checker,
            stream_checker=self.stream_checker,
            command_checker=self.command_checker,
            recovery_mgr=self.recovery_manager,
        )

    # ──────────────────────────── Event Bus ────────────────────────────

    def publish(self, event_type: str, agent_id: str, **context):
        """Publish an event to all subscribers."""
        for cb in self._subscribers.get(event_type, []):
            try:
                cb(agent_id, **context)
            except Exception as e:
                log.error(f'Event subscriber failed for {event_type}: {e}')
        # Always log
        self.logger.info(
            component='event_bus', event=event_type,
            agent_id=agent_id, message=f'Event: {event_type}',
            context=context,
        )

    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to an event type."""
        self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        if callback in self._subscribers.get(event_type, []):
            self._subscribers[event_type].remove(callback)

    # ──────────────────────────── Agent Lifecycle ────────────────────────────

    def register_agent(self, agent_id: str, initial_state: AgentState = AgentState.DISCONNECTED) -> DiagnosticStateMachine:
        machine = DiagnosticStateMachine(
            agent_id=agent_id,
            initial_state=initial_state,
            on_transition=self._on_state_transition,
            on_invalid_transition=self._on_invalid_transition,
        )
        self.state_machines[agent_id] = machine

        self.heartbeat.register_agent(agent_id)
        self.stream_checker.register_agent(machine)
        self.command_checker.register_agent(machine)
        self.recovery_manager.register_agent(machine)

        self.logger.info(
            component='diagnostics_manager', event='agent_registered',
            agent_id=agent_id, message=f'Agent registered',
            context={'initial_state': initial_state.name},
        )
        return machine

    def unregister_agent(self, agent_id: str):
        if agent_id in self.state_machines:
            self.heartbeat.unregister_agent(agent_id)
            self.stream_checker.unregister_agent(agent_id)
            self.command_checker.unregister_agent(agent_id)
            self.recovery_manager.unregister_agent(agent_id)
            self.state_machines.pop(agent_id, None)
            self.logger.info(
                component='diagnostics_manager', event='agent_unregistered',
                agent_id=agent_id, message='Agent removed',
            )

    def get_agent_machine(self, agent_id: str) -> Optional[DiagnosticStateMachine]:
        return self.state_machines.get(agent_id)

    # ──────────────────────────── WebSocket Message Hooks ────────────────────────────

    def on_agent_connected(self, agent_id: str):
        machine = self.state_machines.get(agent_id)
        if machine:
            try:
                machine.transition_to(AgentState.CONNECTING, reason='ws_connected')
            except Exception as e:
                log.error(f'State transition to CONNECTING failed for {agent_id}: {e}')
            self.heartbeat.receive_heartbeat(agent_id)

    def on_agent_disconnected(self, agent_id: str):
        machine = self.state_machines.get(agent_id)
        if machine:
            try:
                machine.transition_to(AgentState.DISCONNECTED, reason='ws_disconnected')
                machine.increment_error_count()
            except Exception as e:
                log.error(f'State transition to DISCONNECTED failed for {agent_id}: {e}')

    def on_agent_registered(self, agent_id: str, session_id: Optional[str] = None):
        machine = self.state_machines.get(agent_id)
        if machine:
            try:
                machine.transition_to(AgentState.REGISTERED, reason='agent_registered')
            except Exception as e:
                log.error(f'State transition to REGISTERED failed for {agent_id}: {e}')

    def on_any_message(self, agent_id: str, msg_type: str):
        self.heartbeat.receive_heartbeat(agent_id)

    def on_screenshot(self, agent_id: str):
        self.stream_checker.record_screenshot(agent_id)

    def on_stream_start(self, agent_id: str):
        self.stream_checker.set_stream_active(agent_id, True)
        machine = self.state_machines.get(agent_id)
        if machine:
            try:
                machine.transition_to(AgentState.STREAMING, reason='stream_started')
            except Exception as e:
                log.error(f'Stream start transition failed: {e}')

    def on_stream_stop(self, agent_id: str):
        self.stream_checker.set_stream_active(agent_id, False)
        machine = self.state_machines.get(agent_id)
        if machine:
            try:
                machine.transition_to(AgentState.REGISTERED, reason='stream_stopped')
            except Exception as e:
                log.error(f'Stream stop transition failed: {e}')

    def on_ack(self, agent_id: str, command_id: str, status: str = 'received', **context):
        self.command_checker.receive_ack(agent_id, command_id, status, **context)

    def send_command(self, agent_id: str, payload: Dict[str, Any]) -> str:
        return self.command_checker.send_command(agent_id, payload)

    def set_send_command_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        self.command_checker._send_command = callback

    # ──────────────────────────── Lifecycle ────────────────────────────

    async def start(self):
        self.logger.info(component='diagnostics_manager', event='starting', message='Starting diagnostics...')
        await self.heartbeat.start()
        await self.api_checker.start()
        await self.stream_checker.start()
        await self.command_checker.start()
        await self.recovery_manager.start()
        self.logger.info(component='diagnostics_manager', event='started', message='Diagnostics started')

    async def stop(self):
        self.logger.info(component='diagnostics_manager', event='stopping', message='Stopping diagnostics...')
        await self.recovery_manager.stop()
        await self.command_checker.stop()
        await self.stream_checker.stop()
        await self.api_checker.stop()
        await self.heartbeat.stop()
        self.logger.info(component='diagnostics_manager', event='stopped', message='Diagnostics stopped')

    def get_full_status(self) -> Dict[str, Any]:
        return {
            'uptime': time.time() - self._start_time,
            'uptime_formatted': self._format_uptime(time.time() - self._start_time),
            'agent_count': len(self.state_machines),
            'agents': {aid: m.snapshot() for aid, m in self.state_machines.items()},
            'health': self.api_checker.get_health(),
            'heartbeat': self.heartbeat.get_all_status(),
            'streams': self.stream_checker.get_all_status(),
            'commands': self.command_checker.get_status(),
            'recovery': self.recovery_manager.get_status(),
            'log_event_count': self.logger.event_count,
        }

    @property
    def api_blueprint(self):
        return diagnostics_bp

    # ──────────────────────────── Recovery ────────────────────────────

    def _register_recovery_handlers(self):
        """Register async recovery action handlers."""
        async def reconnect_ws(agent_id: str, ctx: Dict) -> RecoveryResult:
            self.logger.recovery(component='recovery', event='reconnect', agent_id=agent_id,
                                 action='reconnect_websocket', status='attempted',
                                 message=f'Reconnecting WebSocket for {agent_id}')
            return RecoveryResult(True, 'reconnect_websocket', 0.0, details='handler registered')

        async def restart_stream(agent_id: str, ctx: Dict) -> RecoveryResult:
            self.stream_checker.force_reset_screenshot(agent_id)
            self.logger.recovery(component='recovery', event='restart_stream', agent_id=agent_id,
                                 action='restart_stream', status='attempted',
                                 message=f'Restarting stream for {agent_id}')
            return RecoveryResult(True, 'restart_stream', 0.0, details='stream reset', validated=True)

        async def restore_session(agent_id: str, ctx: Dict) -> RecoveryResult:
            machine = self.state_machines.get(agent_id)
            if machine and machine.state == AgentState.DISCONNECTED:
                try:
                    machine.transition_to(AgentState.CONNECTING, reason='session_restore')
                except Exception as e:
                    return RecoveryResult(False, 'restore_session', 0.0, details=str(e))
            self.logger.recovery(component='recovery', event='restore_session', agent_id=agent_id,
                                 action='restore_session', status='attempted')
            return RecoveryResult(True, 'restore_session', 0.0, details='session state reset', validated=True)

        async def retry_api(agent_id: str, ctx: Dict) -> RecoveryResult:
            self.api_checker.report_api_available(agent_id)
            return RecoveryResult(True, 'retry_api_sync', 0.0, details='sync reset')

        async def escalate(agent_id: str, ctx: Dict) -> RecoveryResult:
            self.logger.critical(component='recovery', event='escalation', agent_id=agent_id,
                                 message=f'Escalating for {agent_id}', context=ctx)
            return RecoveryResult(True, 'escalate', 0.0, details='escalated')

        self.recovery_manager.set_action_handler(RecoveryAction.RECONNECT_WEBSOCKET, reconnect_ws)
        self.recovery_manager.set_action_handler(RecoveryAction.RESTART_STREAM, restart_stream)
        self.recovery_manager.set_action_handler(RecoveryAction.RESTORE_SESSION, restore_session)
        self.recovery_manager.set_action_handler(RecoveryAction.RETRY_API_SYNC, retry_api)
        self.recovery_manager.set_action_handler(RecoveryAction.ESCALATE, escalate)

    # ──────────────────────────── Callbacks ────────────────────────────

    def _on_heartbeat_timeout(self, agent_id: str):
        self.logger.critical(component='manager', event='heartbeat_timeout', agent_id=agent_id,
                             message='Heartbeat timeout detected')
        self.publish('heartbeat_timeout', agent_id)

    def _on_invalid_transition(self, machine: DiagnosticStateMachine, old: AgentState, new: AgentState, reason: str):
        self.logger.error(component='state_machine', event='invalid_transition',
                          agent_id=machine.agent_id,
                          message=f'Invalid transition: {old.name} -> {new.name} ({reason})',
                          context={'old': old.name, 'new': new.name, 'reason': reason})

    def _on_state_transition(self, machine: DiagnosticStateMachine, old: AgentState, new: AgentState):
        self.logger.info(component='state_machine', event='transition',
                         agent_id=machine.agent_id,
                         message=f'{old.name} -> {new.name}',
                         context={'old': old.name, 'new': new.name})

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        h, r = divmod(int(seconds), 3600)
        m, s = divmod(r, 60)
        d, h = divmod(h, 24)
        return f'{d}d {h}h {m}m {s}s' if d else f'{h}h {m}m {s}s' if h else f'{m}m {s}s'