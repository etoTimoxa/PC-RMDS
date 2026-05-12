"""
Command Delivery Checker (ACK Protocol).
Implements command delivery confirmation with timeout and retry.
Each command has a UUID + lifecycle states + delivery metrics.
"""
import asyncio
import uuid
import time
from enum import Enum, auto
from datetime import datetime
from typing import Dict, Optional, Callable, Any, List
from .state_machine import DiagnosticStateMachine, AgentState
from .diagnostics_logger import DiagnosticsLogger, Severity

MAX_RETRIES: int = 3
ACK_TIMEOUT: float = 10.0
CHECK_INTERVAL: float = 5.0


class CommandState(Enum):
    """Lifecycle states for a command."""
    PENDING = auto()
    SENT = auto()
    RETRYING = auto()
    ACKED = auto()
    FAILED = auto()


class PendingCommand:
    """A command waiting for ACK from the agent, with state machine."""

    def __init__(
        self,
        command_id: str,
        agent_id: str,
        payload: Dict[str, Any],
        max_retries: int = MAX_RETRIES,
        timeout: float = ACK_TIMEOUT,
    ):
        self.command_id = command_id
        self.agent_id = agent_id
        self.payload = payload
        self.max_retries = max_retries
        self.timeout = timeout
        self.state: CommandState = CommandState.PENDING
        self.retry_count: int = 0
        self.sent_at: float = time.time()
        self.last_retry_at: Optional[float] = None
        self.ack_received_at: Optional[float] = None
        self.delivery_time_ms: Optional[float] = None  # time from first send to ACK

    def mark_sent(self):
        self.state = CommandState.SENT

    def mark_retrying(self):
        self.state = CommandState.RETRYING

    def mark_acked(self):
        self.state = CommandState.ACKED
        self.ack_received_at = time.time()
        self.delivery_time_ms = (self.ack_received_at - self.sent_at) * 1000

    def mark_failed(self):
        self.state = CommandState.FAILED

    @property
    def is_expired(self) -> bool:
        if self.state in (CommandState.ACKED, CommandState.FAILED):
            return False
        elapsed = time.time() - (self.last_retry_at or self.sent_at)
        return elapsed > self.timeout

    @property
    def is_exhausted(self) -> bool:
        return self.retry_count >= self.max_retries

    @property
    def is_final(self) -> bool:
        return self.state in (CommandState.ACKED, CommandState.FAILED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'command_id': self.command_id,
            'agent_id': self.agent_id,
            'state': self.state.name,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'timeout': self.timeout,
            'sent_at': datetime.utcfromtimestamp(self.sent_at).isoformat(),
            'last_retry_at': datetime.utcfromtimestamp(self.last_retry_at).isoformat()
            if self.last_retry_at else None,
            'ack_received_at': datetime.utcfromtimestamp(self.ack_received_at).isoformat()
            if self.ack_received_at else None,
            'delivery_time_ms': round(self.delivery_time_ms, 2) if self.delivery_time_ms else None,
        }


class CommandDeliveryChecker:
    """
    Monitors command delivery with ACK protocol.
    States: PENDING → SENT → RETRYING → ACKED | FAILED
    Tracks delivery time metrics and retry counts.
    """

    def __init__(
        self,
        logger: DiagnosticsLogger,
        on_retry: Optional[Callable[[PendingCommand], None]] = None,
        on_failed: Optional[Callable[[PendingCommand], None]] = None,
        on_acked: Optional[Callable[[PendingCommand], None]] = None,
        send_command_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self._logger = logger
        self._on_retry = on_retry
        self._on_failed = on_failed
        self._on_acked = on_acked
        self._send_command = send_command_callback

        self._pending: Dict[str, PendingCommand] = {}
        self._acked_history: List[PendingCommand] = []
        self._max_history: int = 100

        self._machines: Dict[str, DiagnosticStateMachine] = {}
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Delivery metrics
        self._total_sent: int = 0
        self._total_acked: int = 0
        self._total_failed: int = 0
        self._delivery_times: List[float] = []

    def register_agent(self, machine: DiagnosticStateMachine):
        self._machines[machine.agent_id] = machine

    def unregister_agent(self, agent_id: str):
        self._machines.pop(agent_id, None)
        for cmd_id, cmd in list(self._pending.items()):
            if cmd.agent_id == agent_id:
                cmd.mark_failed()
                self._pending.pop(cmd_id, None)
                self._archive_command(cmd)

    # ──────────────────────────── Command Tracking ────────────────────────────

    def send_command(self, agent_id: str, payload: Dict[str, Any]) -> str:
        """Send a command and start tracking. Returns command_id."""
        command_id = str(uuid.uuid4())
        payload_with_id = dict(payload)
        payload_with_id['command_id'] = command_id

        cmd = PendingCommand(
            command_id=command_id,
            agent_id=agent_id,
            payload=payload_with_id,
        )
        cmd.mark_sent()
        self._pending[command_id] = cmd
        self._total_sent += 1

        self._logger.info(
            component='command_checker', event='command_sent',
            agent_id=agent_id,
            message=f'Command {command_id} sent (timeout={cmd.timeout}s)',
            context={'command_id': command_id, 'command_type': payload.get('type', 'unknown')},
        )

        if self._send_command:
            try:
                self._send_command(agent_id, payload_with_id)
            except Exception as e:
                self._logger.error(
                    component='command_checker', event='command_send_failed',
                    agent_id=agent_id, message=f'Failed to send {command_id}: {e}',
                    exception=e,
                )
                raise

        return command_id

    def receive_ack(self, agent_id: str, command_id: str, status: str = 'received', **context):
        """Process ACK from agent."""
        cmd = self._pending.get(command_id)
        if cmd is None:
            self._logger.warning(
                component='command_checker', event='ack_unknown',
                agent_id=agent_id, message=f'ACK for unknown command {command_id}',
            )
            return

        if cmd.agent_id != agent_id:
            self._logger.warning(
                component='command_checker', event='ack_mismatch',
                agent_id=agent_id, message=f'Expected {cmd.agent_id}, got {agent_id}',
            )
            return

        cmd.mark_acked()
        self._delivery_times.append(cmd.delivery_time_ms or 0)
        self._total_acked += 1
        self._pending.pop(command_id, None)
        self._archive_command(cmd)

        machine = self._machines.get(agent_id)
        if machine:
            machine.touch_command_ack()

        self._logger.info(
            component='command_checker', event='ack_received',
            agent_id=agent_id,
            message=f'ACK for {command_id} ({status}, {cmd.retry_count} retries)',
            context={'command_id': command_id, 'status': status,
                     'retries': cmd.retry_count, 'delivery_ms': cmd.delivery_time_ms},
        )

        if self._on_acked:
            try:
                self._on_acked(cmd)
            except Exception as callback_e:
                self._logger.error(
                    component='command_checker', event='on_acked_error',
                    agent_id=agent_id, message=f'ACK callback failed: {callback_e}',
                    exception=callback_e,
                )

    # ──────────────────────────── Background Loop ────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        self._logger.info(
            component='command_checker', event='started',
            message=f'Command checker started (timeout={ACK_TIMEOUT}s, retries={MAX_RETRIES})',
        )

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _check_loop(self):
        while self._running:
            try:
                await self._check_pending()
            except Exception as e:
                self._logger.error(
                    component='command_checker', event='loop_error',
                    message=f'Check loop error: {e}', exception=e,
                )
            await asyncio.sleep(CHECK_INTERVAL)

    async def _check_pending(self):
        now = time.time()
        for command_id, cmd in list(self._pending.items()):
            if cmd.is_final:
                continue

            if cmd.is_expired:
                if cmd.is_exhausted:
                    cmd.mark_failed()
                    self._total_failed += 1
                    self._pending.pop(command_id, None)
                    self._archive_command(cmd)

                    self._logger.error(
                        component='command_checker', event='command_failed',
                        agent_id=cmd.agent_id,
                        message=f'Command {command_id} failed after {cmd.retry_count} retries',
                        context={'command_id': command_id, 'retries': cmd.retry_count},
                    )
                    if self._on_failed:
                        try:
                            self._on_failed(cmd)
                        except Exception as callback_e:
                            self._logger.error(
                                component='command_checker', event='on_failed_error',
                                agent_id=cmd.agent_id, message=f'Failed callback error: {callback_e}',
                                exception=callback_e,
                            )
                else:
                    cmd.retry_count += 1
                    cmd.last_retry_at = now
                    cmd.mark_retrying()

                    self._logger.warning(
                        component='command_checker', event='command_retry',
                        agent_id=cmd.agent_id,
                        message=f'Retry {command_id} ({cmd.retry_count}/{cmd.max_retries})',
                        context={'command_id': command_id, 'retry': cmd.retry_count},
                    )

                    if self._send_command:
                        try:
                            self._send_command(cmd.agent_id, cmd.payload)
                        except Exception as e:
                            self._logger.error(
                                component='command_checker', event='retry_send_failed',
                                agent_id=cmd.agent_id, message=f'Retry send failed: {e}',
                                exception=e,
                            )

                    if self._on_retry:
                        try:
                            self._on_retry(cmd)
                        except Exception as callback_e:
                            self._logger.error(
                                component='command_checker', event='on_retry_error',
                                agent_id=cmd.agent_id, message=f'Retry callback error: {callback_e}',
                                exception=callback_e,
                            )

    # ──────────────────────────── Metrics ────────────────────────────

    def get_metrics(self) -> Dict[str, Any]:
        """Return aggregated delivery metrics."""
        avg_delivery = (sum(self._delivery_times) / len(self._delivery_times)) if self._delivery_times else 0
        success_rate = (self._total_acked / self._total_sent * 100) if self._total_sent > 0 else 100
        return {
            'total_sent': self._total_sent,
            'total_acked': self._total_acked,
            'total_failed': self._total_failed,
            'success_rate': round(success_rate, 1),
            'avg_delivery_time_ms': round(avg_delivery, 2),
            'pending_count': len(self._pending),
        }

    # ──────────────────────────── Status ────────────────────────────

    def get_status(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        if agent_id:
            pending = [cmd.to_dict() for cmd in self._pending.values() if cmd.agent_id == agent_id]
        else:
            pending = [cmd.to_dict() for cmd in self._pending.values()]

        result = {
            'pending_count': len(pending),
            'pending_commands': pending,
            'acked_count': sum(1 for cmd in self._acked_history if cmd.state == CommandState.ACKED),
            'failed_count': sum(1 for cmd in self._acked_history if cmd.state == CommandState.FAILED),
        }
        result['metrics'] = self.get_metrics()
        return result

    # ──────────────────────────── Private ────────────────────────────

    def _archive_command(self, cmd: PendingCommand):
        self._acked_history.append(cmd)
        if len(self._acked_history) > self._max_history:
            self._acked_history = self._acked_history[-self._max_history:]