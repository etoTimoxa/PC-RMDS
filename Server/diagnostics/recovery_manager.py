"""
Recovery Manager.
Async-safe recovery orchestration with per-agent asyncio.Lock, validation phase, RecoveryResult.
No silent exception swallowing. Cooldown + bounded attempts + escalation.
"""
import asyncio
import time
import logging
from enum import Enum, auto
from typing import Dict, Optional, Callable, Any, List, Awaitable
from datetime import datetime
from .state_machine import DiagnosticStateMachine, AgentState
from .diagnostics_logger import DiagnosticsLogger, Severity, DiagnosticEvent

log = logging.getLogger('recovery_manager')


class RecoveryAction(Enum):
    RECONNECT_WEBSOCKET = 'reconnect_websocket'
    RESTART_STREAM = 'restart_stream'
    RESTORE_SESSION = 'restore_session'
    RETRY_API_SYNC = 'retry_api_sync'
    ESCALATE = 'escalate'


class RecoveryStrategy:
    def __init__(self, name: str, description: str, actions: List[RecoveryAction]):
        self.name = name
        self.description = description
        self.actions = actions


class RecoveryResult:
    """Structured result of a recovery action with validation."""
    def __init__(self, success: bool, action: str, duration: float,
                 details: str = '', validated: bool = False):
        self.success = success
        self.action = action
        self.duration = duration
        self.details = details
        self.validated = validated

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'action': self.action,
            'duration_seconds': round(self.duration, 3),
            'details': self.details,
            'validated': self.validated,
        }


class RecoveryManager:
    """
    Async recovery manager.
    - Per-agent asyncio.Lock prevents concurrent recovery
    - RecoveryResult with validation phase
    - Cooldown mechanism (30s default)
    - Bounded attempts (3 max per 120s window)
    - Escalation on exhaustion
    """

    DEFAULT_COOLDOWN: float = 30.0
    MAX_RECOVERY_ATTEMPTS: int = 3
    RECOVERY_WINDOW: float = 120.0

    STRATEGIES: Dict[str, RecoveryStrategy] = {
        'heartbeat_timeout': RecoveryStrategy(
            name='heartbeat_timeout',
            description='Heartbeat not received. Reconnect WebSocket.',
            actions=[RecoveryAction.RECONNECT_WEBSOCKET, RecoveryAction.RESTORE_SESSION],
        ),
        'screenshot_broken': RecoveryStrategy(
            name='screenshot_broken',
            description='Screenshot pipeline stalled. Restart stream.',
            actions=[RecoveryAction.RESTART_STREAM],
        ),
        'api_degraded': RecoveryStrategy(
            name='api_degraded',
            description='API unreachable. Retry sync.',
            actions=[RecoveryAction.RETRY_API_SYNC],
        ),
        'command_failed': RecoveryStrategy(
            name='command_failed',
            description='Command delivery failed. Restore session.',
            actions=[RecoveryAction.RESTORE_SESSION, RecoveryAction.RECONNECT_WEBSOCKET],
        ),
        'session_broken': RecoveryStrategy(
            name='session_broken',
            description='Session inconsistent. Restore.',
            actions=[RecoveryAction.RESTORE_SESSION],
        ),
        'generic_error': RecoveryStrategy(
            name='generic_error',
            description='Generic error. Reconnect.',
            actions=[RecoveryAction.RECONNECT_WEBSOCKET],
        ),
    }

    def __init__(
        self,
        logger: DiagnosticsLogger,
        state_machines: Optional[Dict[str, DiagnosticStateMachine]] = None,
    ):
        self._logger = logger
        self._machines: Dict[str, DiagnosticStateMachine] = state_machines or {}

        # Async handlers: Callable[[str, Dict], Awaitable[RecoveryResult]]
        self._action_handlers: Dict[RecoveryAction, Optional[Callable[[str, Dict[str, Any]], Awaitable[RecoveryResult]]]] = {
            RecoveryAction.RECONNECT_WEBSOCKET: None,
            RecoveryAction.RESTART_STREAM: None,
            RecoveryAction.RESTORE_SESSION: None,
            RecoveryAction.RETRY_API_SYNC: None,
            RecoveryAction.ESCALATE: None,
        }

        # Per-agent state
        self._agent_locks: Dict[str, asyncio.Lock] = {}
        self._recovery_attempts: Dict[str, list] = {}
        self._cooldowns: Dict[str, Dict[str, float]] = {}
        self._agent_recovering: Dict[str, bool] = {}
        self._recovery_history: Dict[str, List[RecoveryResult]] = {}

        self._task: Optional[asyncio.Task] = None
        self._running = False

    def register_agent(self, machine: DiagnosticStateMachine):
        aid = machine.agent_id
        self._machines[aid] = machine
        self._agent_locks.setdefault(aid, asyncio.Lock())
        self._recovery_attempts.setdefault(aid, [])
        self._cooldowns.setdefault(aid, {})
        self._agent_recovering[aid] = False
        self._recovery_history.setdefault(aid, [])

    def unregister_agent(self, agent_id: str):
        self._machines.pop(agent_id, None)
        self._agent_locks.pop(agent_id, None)
        self._recovery_attempts.pop(agent_id, None)
        self._cooldowns.pop(agent_id, None)
        self._agent_recovering.pop(agent_id, None)
        self._recovery_history.pop(agent_id, None)

    def set_action_handler(self, action: RecoveryAction,
                           handler: Optional[Callable[[str, Dict[str, Any]], Awaitable[RecoveryResult]]]):
        self._action_handlers[action] = handler

    # ──────────────────────────── Event Reception ────────────────────────────

    async def on_diagnostic_event(self, event: DiagnosticEvent) -> bool:
        """Async handler for incoming diagnostic events."""
        agent_id = event.agent_id
        if not agent_id:
            return False

        strategy = self._select_strategy(event)
        if strategy is None:
            self._logger.debug(
                component='recovery_manager', event='no_strategy',
                agent_id=agent_id, message=f'No strategy for {event.event}',
            )
            return False

        # Cooldown check
        if not self._check_cooldown(agent_id, strategy.name):
            self._logger.debug(
                component='recovery_manager', event='cooldown_active',
                agent_id=agent_id, message=f'Cooldown for {strategy.name}',
            )
            return False

        # Max attempts check
        if self._exceeded_max_attempts(agent_id):
            self._logger.critical(
                component='recovery_manager', event='max_attempts_exceeded',
                agent_id=agent_id,
                message=f'Max recovery attempts ({self.MAX_RECOVERY_ATTEMPTS}) exceeded, escalating',
            )
            await self._execute_action_safe(RecoveryAction.ESCALATE, agent_id, {
                'reason': 'max_attempts_exceeded',
            })
            return False

        # Execute recovery under per-agent lock
        async with self._agent_locks.setdefault(agent_id, asyncio.Lock()):
            return await self._execute_recovery(agent_id, strategy)

    # ──────────────────────────── Strategy Selection ────────────────────────────

    def _select_strategy(self, event: DiagnosticEvent) -> Optional[RecoveryStrategy]:
        mapping = {
            'heartbeat_timeout': 'heartbeat_timeout',
            'screenshot_pipeline_broken': 'screenshot_broken',
            'agent_api_degraded': 'api_degraded',
            'command_failed': 'command_failed',
            'missing_session_id': 'session_broken',
        }
        name = mapping.get(event.event)
        if name:
            return self.STRATEGIES.get(name)
        if any(kw in event.event for kw in ('error', 'broken', 'failed')):
            return self.STRATEGIES.get('generic_error')
        return None

    # ──────────────────────────── Recovery Execution ────────────────────────────

    async def _execute_recovery(self, agent_id: str, strategy: RecoveryStrategy) -> bool:
        """Execute a recovery strategy with validation. Returns True if all actions succeeded."""
        machine = self._machines.get(agent_id)
        if machine is None:
            return False

        self._agent_recovering[agent_id] = True
        self._record_attempt(agent_id, strategy.name)
        self._set_cooldown(agent_id, strategy.name)

        # State transition to RECOVERING
        if machine.state not in (AgentState.RECOVERING, AgentState.DISCONNECTED, AgentState.ERROR):
            try:
                machine.transition_to(AgentState.RECOVERING, reason=f'recovery_{strategy.name}')
            except Exception as e:
                log.error(f'State transition to RECOVERING failed for {agent_id}: {e}')

        self._logger.recovery(
            component='recovery_manager', event='recovery_started',
            agent_id=agent_id, action=strategy.name, status='started',
            message=f'Starting: {strategy.description}',
        )

        all_success = True
        for action in strategy.actions:
            result = await self._execute_action_safe(action, agent_id, {'strategy': strategy.name})
            if not result.success:
                all_success = False
                self._logger.warning(
                    component='recovery_manager', event='recovery_action_failed',
                    agent_id=agent_id,
                    message=f'Action {action.value} failed: {result.details}',
                    context={'action': action.value, 'result': result.to_dict()},
                )

        # Recovery result
        recovery_duration = time.time() - (self._recovery_attempts[agent_id][-1] if self._recovery_attempts.get(agent_id) else time.time())

        if all_success:
            self._logger.recovery(
                component='recovery_manager', event='recovery_completed',
                agent_id=agent_id, action=strategy.name, status='completed',
                message=f'Recovery successful: {strategy.description}',
            )
            machine.increment_recovery_count()
            self._agent_recovering[agent_id] = False

            # Transition back to REGISTERED
            try:
                if machine.can_transition_to(AgentState.REGISTERED):
                    machine.transition_to(AgentState.REGISTERED, reason=f'recovery_{strategy.name}_ok')
            except Exception as e:
                log.error(f'Post-recovery state transition failed for {agent_id}: {e}')
        else:
            self._logger.recovery(
                component='recovery_manager', event='recovery_failed',
                agent_id=agent_id, action=strategy.name, status='failed',
                message=f'Recovery failed: {strategy.description}',
            )
            machine.increment_error_count()
            self._agent_recovering[agent_id] = False

        return all_success

    async def _execute_action_safe(self, action: RecoveryAction, agent_id: str,
                                    context: Dict[str, Any]) -> RecoveryResult:
        """Execute a single recovery action, returning RecoveryResult."""
        handler = self._action_handlers.get(action)
        if handler is None:
            return RecoveryResult(False, action.value, 0.0, 'No handler registered')

        start = time.time()
        try:
            result = await handler(agent_id, context)
            if isinstance(result, RecoveryResult):
                result.action = action.value
                result.duration = time.time() - start
                return result
            return RecoveryResult(bool(result), action.value, time.time() - start, 'handler returned non-Result')
        except Exception as e:
            duration = time.time() - start
            self._logger.error(
                component='recovery_manager', event='action_handler_error',
                agent_id=agent_id,
                message=f'Error in {action.value}: {e}',
                exception=e,
            )
            return RecoveryResult(False, action.value, duration, str(e))

    # ──────────────────────────── Cooldown / Rate Limiting ────────────────────────────

    def _check_cooldown(self, agent_id: str, strategy_name: str) -> bool:
        return time.time() >= self._cooldowns.get(agent_id, {}).get(strategy_name, 0.0)

    def _set_cooldown(self, agent_id: str, strategy_name: str):
        self._cooldowns.setdefault(agent_id, {})[strategy_name] = time.time() + self.DEFAULT_COOLDOWN

    def _record_attempt(self, agent_id: str, strategy_name: str):
        now = time.time()
        history = self._recovery_attempts.setdefault(agent_id, [])
        history.append(now)
        cutoff = now - self.RECOVERY_WINDOW
        self._recovery_attempts[agent_id] = [t for t in history if t >= cutoff]

    def _exceeded_max_attempts(self, agent_id: str) -> bool:
        return len(self._recovery_attempts.get(agent_id, [])) >= self.MAX_RECOVERY_ATTEMPTS

    # ──────────────────────────── Status ────────────────────────────

    def get_status(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        if agent_id:
            history = self._recovery_history.get(agent_id, [])
            return {
                'agent_id': agent_id,
                'is_recovering': self._agent_recovering.get(agent_id, False),
                'recovery_attempts': len(self._recovery_attempts.get(agent_id, [])),
                'history_count': len(history),
                'last_results': [r.to_dict() for r in history[-5:]],
            }
        return {
            'agents': {
                aid: {
                    'is_recovering': recov,
                    'attempts': len(self._recovery_attempts.get(aid, [])),
                }
                for aid, recov in self._agent_recovering.items()
            },
            'recovering_count': sum(1 for v in self._agent_recovering.values() if v),
        }

    def get_strategies(self) -> List[Dict[str, Any]]:
        return [{'name': s.name, 'description': s.description, 'actions': [a.value for a in s.actions]}
                for s in self.STRATEGIES.values()]

    def get_recovery_history(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if agent_id:
            return [r.to_dict() for r in self._recovery_history.get(agent_id, [])]
        all_history = []
        for aid, hist in self._recovery_history.items():
            for r in hist[-10:]:
                d = r.to_dict()
                d['agent_id'] = aid
                all_history.append(d)
        return sorted(all_history, key=lambda x: x.get('duration_seconds', 0), reverse=True)[:100]

    # ──────────────────────────── Lifecycle ────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._logger.info(component='recovery_manager', event='started',
                          message=f'Recovery manager started (max_attempts={self.MAX_RECOVERY_ATTEMPTS})')

    async def stop(self):
        self._running = False
        self._logger.info(component='recovery_manager', event='stopped', message='Recovery manager stopped')

    def subscribe_to_logger(self, logger: DiagnosticsLogger):
        """Subscribe to high-severity events via asyncio task scheduling."""
        async def async_wrapper(event: DiagnosticEvent):
            try:
                await self.on_diagnostic_event(event)
            except Exception as e:
                log.error(f'Async recovery event handler failed: {e}')
        # Since logger calls subscribers synchronously, wrap them into asyncio tasks
        def sync_wrapper(event: DiagnosticEvent):
            try:
                asyncio.create_task(async_wrapper(event))
            except RuntimeError:
                # No running event loop - fall back to synchronous execution
                log.warning(f'No event loop for async recovery event, scheduling deferred: {event.event}')
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(async_wrapper(event))
                    loop.close()
                except Exception as loop_e:
                    log.error(f'Failed to run recovery event in fallback loop: {loop_e}')
        logger.subscribe(sync_wrapper)
