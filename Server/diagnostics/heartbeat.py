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
    """

    HEARTBEAT_TIMEOUT: float = 15.0
    CHECK_INTERVAL: float = 5.0

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

        self._task: Optional[asyncio.Task] = None
        self._running = False

    # ──────────────────────────── Registration ────────────────────────────

    def register_agent(self, agent_id: str):
        """Register an agent for heartbeat monitoring."""
        now = time.monotonic()
        self._last_heartbeat[agent_id] = now
        self._heartbeat_history.setdefault(agent_id, [])
        self._missed_heartbeats[agent_id] = 0
        self._reconnected[agent_id] = False

        self._logger.info(
            component='heartbeat', event='agent_registered',
            agent_id=agent_id, message='Agent registered for heartbeat monitoring',
        )

    def unregister_agent(self, agent_id: str):
        self._last_heartbeat.pop(agent_id, None)
        self._heartbeat_history.pop(agent_id, None)
        self._missed_heartbeats.pop(agent_id, None)
        self._reconnected.pop(agent_id, None)
        self._logger.info(
            component='heartbeat', event='agent_unregistered',
            agent_id=agent_id, message='Agent removed from heartbeat monitoring',
        )

    # ──────────────────────────── Heartbeat Receive ────────────────────────────

    def receive_heartbeat(self, agent_id: str):
        """Called when a heartbeat message is received. Tracks jitter."""
        now = time.monotonic()
        last = self._last_heartbeat.get(agent_id)

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
            message=f'Heartbeat watchdog started (timeout={self.HEARTBEAT_TIMEOUT}s)',
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

    async def _check_all(self):
        """Check all agents for heartbeat timeout. Emits events only."""
        now = time.monotonic()
        for agent_id, last_time in list(self._last_heartbeat.items()):
            elapsed = now - last_time
            if elapsed > self.HEARTBEAT_TIMEOUT:
                self._reconnected[agent_id] = True
                self._logger.critical(
                    component='heartbeat', event='heartbeat_timeout',
                    agent_id=agent_id,
                    message=f'No heartbeat for {elapsed:.1f}s',
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
            'statistics': stats,
        }

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        return {aid: self.get_agent_status(aid) for aid in self._last_heartbeat}

    @property
    def agent_count(self) -> int:
        return len(self._last_heartbeat)