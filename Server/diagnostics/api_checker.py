"""
API Health Checker.
Monitors REST API availability. Agent checks API every 10 seconds.
On API unavailability: agent enters DEGRADED mode, caches events locally, retries.
"""
import asyncio
import time
from datetime import datetime
from typing import Dict, Optional, Callable, Any
from .state_machine import DiagnosticStateMachine, AgentState
from .diagnostics_logger import DiagnosticsLogger, Severity


class APIHealthChecker:
    """
    Checks REST API health from the server side.
    Monitors: connectivity to MySQL, WebSocket server, overall uptime.
    Maintains a global health status exposed via /api/health endpoint.
    """

    CHECK_INTERVAL: float = 10.0  # how often to run health checks
    DEGRADED_AFTER_FAILURES: int = 3  # consecutive failures -> DEGRADED

    def __init__(
        self,
        logger: DiagnosticsLogger,
        check_db: Optional[Callable[[], bool]] = None,
        check_ws: Optional[Callable[[], bool]] = None,
        on_degraded: Optional[Callable[[str], None]] = None,
        on_recovered: Optional[Callable[[str], None]] = None,
    ):
        self._logger = logger
        self._check_db = check_db or (lambda: True)
        self._check_ws = check_ws or (lambda: True)
        self._on_degraded = on_degraded
        self._on_recovered = on_recovered

        # Global health state
        self._start_time: float = time.time()
        self._database_healthy: bool = True
        self._websocket_server_healthy: bool = True
        self._last_db_check: Optional[str] = None
        self._last_ws_check: Optional[str] = None
        self._consecutive_db_failures: int = 0
        self._consecutive_ws_failures: int = 0
        self._last_error: Optional[str] = None

        # Per-agent degradation tracking (for agents that call us)
        self._agent_degraded_states: Dict[str, bool] = {}
        self._agent_failures: Dict[str, int] = {}

        self._task: Optional[asyncio.Task] = None
        self._running = False

    # ──────────────────────────── API Health Endpoint ────────────────────────────

    def get_health(self) -> Dict[str, Any]:
        """Return full health status (used by /api/health endpoint)."""
        uptime = time.time() - self._start_time
        return {
            'status': 'ok' if (self._database_healthy and self._websocket_server_healthy) else 'degraded',
            'database': self._database_healthy,
            'websocket_server': self._websocket_server_healthy,
            'uptime': int(uptime),
            'uptime_formatted': self._format_uptime(uptime),
            'last_db_check': self._last_db_check,
            'last_ws_check': self._last_ws_check,
            'last_error': self._last_error,
            'started_at': datetime.utcfromtimestamp(self._start_time).isoformat(),
        }

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        if days:
            return f'{days}d {hours}h {minutes}m {secs}s'
        if hours:
            return f'{hours}h {minutes}m {secs}s'
        return f'{minutes}m {secs}s'

    # ──────────────────────────── Agent API Check ────────────────────────────

    def report_api_unavailable(self, agent_id: str):
        """
        Called when an agent reports that the API is unreachable.
        Used to track per-agent degradation.
        """
        failures = self._agent_failures.get(agent_id, 0) + 1
        self._agent_failures[agent_id] = failures

        if failures >= self.DEGRADED_AFTER_FAILURES and not self._agent_degraded_states.get(agent_id, False):
            self._agent_degraded_states[agent_id] = True
            self._logger.warning(
                component='api_checker',
                event='agent_api_degraded',
                agent_id=agent_id,
                message=f'Agent reported API unavailable {failures} times -> DEGRADED',
                context={
                    'consecutive_failures': failures,
                    'threshold': self.DEGRADED_AFTER_FAILURES,
                },
            )
            if self._on_degraded:
                try:
                    self._on_degraded(agent_id)
                except Exception as e:
                    self._logger.error(
                        component='api_checker', event='on_degraded_callback_error',
                        agent_id=agent_id, message=f'on_degraded callback failed: {e}',
                        exception=e,
                    )

    def report_api_available(self, agent_id: str):
        """Called when an agent reports that the API is back online."""
        was_degraded = self._agent_degraded_states.get(agent_id, False)
        self._agent_failures[agent_id] = 0
        self._agent_degraded_states[agent_id] = False

        if was_degraded:
            self._logger.info(
                component='api_checker',
                event='agent_api_recovered',
                agent_id=agent_id,
                message='Agent API connectivity restored -> normal',
            )
            if self._on_recovered:
                try:
                    self._on_recovered(agent_id)
                except Exception as e:
                    self._logger.error(
                        component='api_checker', event='on_recovered_callback_error',
                        agent_id=agent_id, message=f'on_recovered callback failed: {e}',
                        exception=e,
                    )

    def is_agent_degraded(self, agent_id: str) -> bool:
        return self._agent_degraded_states.get(agent_id, False)

    # ──────────────────────────── Server-side Health Checks ────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._health_loop())
        self._logger.info(
            component='api_checker',
            event='health_checker_started',
            message=f'API health checker started (interval={self.CHECK_INTERVAL}s)',
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

    async def _health_loop(self):
        while self._running:
            try:
                await self._run_checks()
            except Exception as e:
                self._logger.error(
                    component='api_checker',
                    event='health_check_error',
                    message=f'Error in health check loop: {e}',
                    exception=e,
                )
            await asyncio.sleep(self.CHECK_INTERVAL)

    async def _run_checks(self):
        """Run database and WebSocket server health checks."""
        now = datetime.utcnow().isoformat()

        # Database check
        old_db = self._database_healthy
        try:
            db_ok = self._check_db()
            self._database_healthy = db_ok
            self._last_db_check = now
            if db_ok:
                self._consecutive_db_failures = 0
            else:
                self._consecutive_db_failures += 1
        except Exception as e:
            self._database_healthy = False
            self._consecutive_db_failures += 1
            self._last_db_check = now
            self._last_error = str(e)

        if old_db and not self._database_healthy:
            self._logger.error(
                component='api_checker',
                event='database_unhealthy',
                message=f'Database health check failed ({self._consecutive_db_failures}x)',
                context={'consecutive_failures': self._consecutive_db_failures},
            )

        if not old_db and self._database_healthy:
            self._logger.info(
                component='api_checker',
                event='database_recovered',
                message='Database health check passed again',
            )

        # WebSocket server check
        old_ws = self._websocket_server_healthy
        try:
            ws_ok = self._check_ws()
            self._websocket_server_healthy = ws_ok
            self._last_ws_check = now
            if ws_ok:
                self._consecutive_ws_failures = 0
            else:
                self._consecutive_ws_failures += 1
        except Exception as e:
            self._websocket_server_healthy = False
            self._consecutive_ws_failures += 1
            self._last_ws_check = now
            self._last_error = str(e)

        if old_ws and not self._websocket_server_healthy:
            self._logger.error(
                component='api_checker',
                event='websocket_server_unhealthy',
                message=f'WebSocket server health check failed ({self._consecutive_ws_failures}x)',
                context={'consecutive_failures': self._consecutive_ws_failures},
            )

        if not old_ws and self._websocket_server_healthy:
            self._logger.info(
                component='api_checker',
                event='websocket_server_recovered',
                message='WebSocket server health check passed again',
            )

    # ──────────────────────────── Status ────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        health = self.get_health()
        health['agents_degraded'] = {
            aid: state
            for aid, state in self._agent_degraded_states.items()
        }
        health['agent_degraded_count'] = sum(1 for v in self._agent_degraded_states.values() if v)
        health['agent_failures'] = dict(self._agent_failures)
        return health