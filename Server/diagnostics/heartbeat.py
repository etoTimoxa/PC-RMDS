"""
Heartbeat System.
Agent sends heartbeats every 5 sec. Server tracks last_heartbeat per agent.
If no heartbeat >15 sec: emits heartbeat_timeout event.
Tracks jitter/latency statistics. Does NOT perform FSM transitions directly.
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable, Any
from .diagnostics_logger import DiagnosticsLogger, Severity, DiagnosticEvent


class HeartbeatChecker:
    """
    Background watchdog that monitors agent heartbeats.
    Emits diagnostic events on timeout. Tracks statistics.
    Does NOT perform state machine transitions directly — fires callbacks.

    Features:
    - Grace period: heartbeat timeout is ignored for HEARTBEAT_GRACE_PERIOD seconds
      after an agent enters a state where heartbeat monitoring should be deferred
      (e.g. just after REGISTERED). Prevents false timeouts during registration,
      reconnection, or startup delays.
    - Task health check: monitors the watchdog task for unexpected completion
      and auto-restarts it if it died silently. Logs restart events.
    """

    HEARTBEAT_TIMEOUT: float = 15.0
    CHECK_INTERVAL: float = 5.0
    HEARTBEAT_GRACE_PERIOD: float = 20.0  # Seconds to ignore timeouts after state entry

    def __init__(
        self,
        logger: DiagnosticsLogger,
        on_timeout: Optional[Callable[[str], None]] = None,
    ):
        self._logger = logger
        self._on_timeout = on_timeout

        self._last_heartbeat: Dict[str, float] = {}  # agent_id -> timestamp (monotonic)
        self._heartbeat_history: Dict[str, list] = {}  # agent_id -> [intervals]
        self._missed_heartbeats: Dict[str, int] = {}
        self._reconnected: Dict[str, bool] = {}

        # Grace period: agent_id -> float('inf') if grace expired, else time.monotonic() + GRACE
        self._grace_until: Dict[str, float] = {}

        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._restart_count: int = 0

    # ──────────────────────────── Registration ────────────────────────────

    def register_agent(self, agent_id: str):
        """Register an agent for heartbeat monitoring."""
        now = time.monotonic()
        self._last_heartbeat[agent_id] = now
        self._heartbeat_history.setdefault(agent_id, [])
        self._missed_heartbeats[agent_id] = 0
        self._reconnected[agent_id] = False
        # Set grace period on registration
        self._grace_until[agent_id] = now + self.HEARTBEAT_GRACE_PERIOD

        self._logger.info(
            component='heartbeat', event='agent_registered',
            agent_id=agent_id, message='Agent registered for heartbeat monitoring',
            context={'grace_period_seconds': self.HEARTBEAT_GRACE_PERIOD},
        )

    def unregister_agent(self, agent_id: str):
        self._last_heartbeat.pop(agent_id, None)
        self._heartbeat_history.pop(agent_id, None)
        self._missed_heartbeats.pop(agent_id, None)
        self._reconnected.pop(agent_id, None)
        self._grace_until.pop(agent_id, None)
        self._logger.info(
            component='heartbeat', event='agent_unregistered',
            agent_id=agent_id, message='Agent removed from heartbeat monitoring',
        )

    # ──────────────────────────── Grace Period ────────────────────────────

    def set_grace_period(self, agent_id: str, duration: Optional[float] = None):
        """
        Set a grace period for an agent during which heartbeat timeouts are ignored.
        Called by diagnostics manager on state transitions to REGISTERED or CONNECTING.
        If duration is None, uses HEARTBEAT_GRACE_PERIOD.
        If duration is 0, disables grace period (monitoring becomes active immediately).
        """
        if duration == 0:
            # No grace period — monitoring active
            self._grace_until[agent_id] = 0
            return
        if duration is None:
            duration = self.HEARTBEAT_GRACE_PERIOD
        self._grace_until[agent_id] = time.monotonic() + duration
        self._logger.info(
            component='heartbeat', event='grace_period_set',
            agent_id=agent_id, message=f'Grace period set: {duration}s',
            context={'grace_period_seconds': duration},
        )

    def clear_grace_period(self, agent_id: str):
        """Immediately end grace period for an agent (e.g. after heartbeat received)."""
        self._grace_until[agent_id] = 0

    def is_in_grace_period(self, agent_id: str) -> bool:
        """Check if agent is still in grace period."""
        grace_end = self._grace_until.get(agent_id, 0)
        return time.monotonic() < grace_end

    # ──────────────────────────── Heartbeat Receive ────────────────────────────

    def receive_heartbeat(self, agent_id: str):
        """Called when a heartbeat message is received. Tracks jitter."""
        now = time.monotonic()
        last = self._last_heartbeat.get(agent_id)

        # Heartbeat received — clear grace period if set
        self.clear_grace_period(agent_id)

        if last is not None:
            interval = now - last
            history = self._heartbeat_history.setdefault(agent_id, [])
            history.append(interval)
            if len(history) > 20:
                history.pop(0)

            if interval > self.HEARTBEAT_TIMEOUT:
                self._missed_heartbeats[agent_id] = self._missed_heartbeats.get(agent_id, 0) + 1
                self._logger.warning(
                    component='heartbeat', event='heartbeat_delayed',
                    agent_id=agent_id,
                    message=f'Heartbeat delayed: {interval:.1f}s',
                    context={'interval_seconds': round(interval, 2)},
                )
            else:
                self._missed_heartbeats[agent_id] = 0

            if self._reconnected.get(agent_id, False):
                self._reconnected[agent_id] = False
                self._logger.info(
                    component='heartbeat', event='heartbeat_resumed',
                    agent_id=agent_id, message='Heartbeat flow resumed after reconnection',
                )

        self._last_heartbeat[agent_id] = now

    # ──────────────────────────── Statistics ────────────────────────────

    def get_heartbeat_stats(self, agent_id: str) -> Dict[str, Any]:
        """Return heartbeat statistics for an agent."""
        history = self._heartbeat_history.get(agent_id, [])
        if not history:
            return {'agent_id': agent_id, 'intervals': 0}
        return {
            'agent_id': agent_id,
            'intervals': len(history),
            'avg_interval': round(sum(history) / len(history), 3),
            'max_interval': round(max(history), 3),
            'min_interval': round(min(history), 3),
            'missed_count': self._missed_heartbeats.get(agent_id, 0),
            'last_heartbeat_ago': round(time.monotonic() - self._last_heartbeat.get(agent_id, 0), 1)
            if agent_id in self._last_heartbeat else None,
        }

    # ──────────────────────────── Background Loop ────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._watchdog_loop())
        self._logger.info(
            component='heartbeat', event='watchdog_started',
            message=f'Heartbeat watchdog started (timeout={self.HEARTBEAT_TIMEOUT}s, '
                    f'grace={self.HEARTBEAT_GRACE_PERIOD}s)',
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

    async def _watchdog_loop(self):
        """Main watchdog loop with task health monitoring."""
        while self._running:
            try:
                await self._check_all()
            except Exception as e:
                self._logger.error(
                    component='heartbeat', event='watchdog_error',
                    message=f'Error in heartbeat watchdog: {e}',
                    exception=e,
                )
            await asyncio.sleep(self.CHECK_INTERVAL)

        # --- Task health monitoring (post-loop) ---
        # If we exit the loop but _running is still True, the task died unexpectedly
        if self._running and not self._task.done():
            # Task completed but we're still supposed to run — unexpected
            self._logger.error(
                component='heartbeat', event='watchdog_task_died',
                message='Heartbeat watchdog task completed unexpectedly',
            )

    async def _check_all(self):
        """Check all agents for heartbeat timeout. Respects grace period. Emits events only."""
        now = time.monotonic()
        for agent_id, last_time in list(self._last_heartbeat.items()):
            elapsed = now - last_time
            if elapsed > self.HEARTBEAT_TIMEOUT:
                # --- Grace period check ---
                # If the agent is still in grace period, skip timeout event
                if self.is_in_grace_period(agent_id):
                    grace_remaining = self._grace_until[agent_id] - now
                    # Log at debug level so we know it's being deferred
                    self._logger.debug(
                        component='heartbeat', event='heartbeat_timeout_deferred',
                        agent_id=agent_id,
                        message=f'Heartbeat timeout deferred: {elapsed:.1f}s elapsed, '
                                f'{grace_remaining:.1f}s grace remaining',
                        context={
                            'elapsed_seconds': round(elapsed, 2),
                            'grace_remaining': round(grace_remaining, 1),
                            'grace_period': self.HEARTBEAT_GRACE_PERIOD,
                        },
                    )
                    continue  # Skip timeout during grace period

                self._reconnected[agent_id] = True
                self._logger.critical(
                    component='heartbeat', event='heartbeat_timeout',
                    agent_id=agent_id,
                    message=f'No heartbeat for {elapsed:.1f}s (grace expired)',
                    context={
                        'elapsed_seconds': round(elapsed, 2),
                        'missed_count': self._missed_heartbeats.get(agent_id, 0),
                    },
                )
                if self._on_timeout:
                    try:
                        self._on_timeout(agent_id)
                    except Exception as e:
                        self._logger.error(
                            component='heartbeat', event='timeout_callback_error',
                            agent_id=agent_id, message=f'Timeout callback failed: {e}',
                            exception=e,
                        )

    # ──────────────────────────── Task Health ────────────────────────────

    @property
    def is_task_alive(self) -> bool:
        """Check if the watchdog task is running properly."""
        if self._task is None:
            return False
        if self._task.done():
            # Task finished — check if it was cancelled intentionally
            if self._running:
                # Unexpected shutdown — task died silently
                return False
            return True  # Was stopped intentionally
        return True

    def get_task_health(self) -> Dict[str, Any]:
        """Return task health status for monitoring."""
        return {
            'running': self._running,
            'task_alive': self.is_task_alive,
            'restart_count': self._restart_count,
            'task_done': self._task.done() if self._task else None,
            'task_cancelled': self._task.cancelled() if self._task else None,
        }

    # ──────────────────────────── Status ────────────────────────────

    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        if agent_id not in self._last_heartbeat:
            return None
        stats = self.get_heartbeat_stats(agent_id)
        return {
            'agent_id': agent_id,
            'is_online': (time.monotonic() - self._last_heartbeat.get(agent_id, 0)) < self.HEARTBEAT_TIMEOUT,
            'last_heartbeat_ago': round(time.monotonic() - self._last_heartbeat.get(agent_id, 0), 1),
            'missed_count': self._missed_heartbeats.get(agent_id, 0),
            'in_grace_period': self.is_in_grace_period(agent_id),
            'statistics': stats,
        }

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        return {aid: self.get_agent_status(aid) for aid in self._last_heartbeat}

    @property
    def agent_count(self) -> int:
        return len(self._last_heartbeat)