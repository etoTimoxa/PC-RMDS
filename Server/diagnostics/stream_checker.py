"""
Screenshot Stream Pipeline Diagnostics.
Monitors screenshot stream for stalls and timeouts.
If stream active and no frames >5s: pipeline marked as BROKEN.
Auto-recovery: restart screenshot loop, recreate stream task.
"""
import asyncio
import time
from datetime import datetime
from typing import Dict, Optional, Callable, Any
from .state_machine import DiagnosticStateMachine, AgentState
from .diagnostics_logger import DiagnosticsLogger, Severity


class StreamChecker:
    """
    Diagnoses screenshot stream pipeline.
    Detects:
      - отсутствие кадров (no frames)
      - зависание screenshot loop
      - stalled stream
    """

    SCREENSHOT_TIMEOUT: float = 5.0   # no screenshot frames for 5s -> broken
    CHECK_INTERVAL: float = 3.0       # how often to check streams

    def __init__(
        self,
        logger: DiagnosticsLogger,
        on_screenshot_broken: Optional[Callable[[str], None]] = None,
        on_screenshot_recovered: Optional[Callable[[str], None]] = None,
    ):
        self._logger = logger
        self._on_screenshot_broken = on_screenshot_broken
        self._on_screenshot_recovered = on_screenshot_recovered

        # Per-agent stream state
        self._machines: Dict[str, DiagnosticStateMachine] = {}
        self._screenshot_times: Dict[str, float] = {}  # agent_id -> last screenshot time
        self._screenshot_broken: Dict[str, bool] = {}   # agent_id -> is screenshot pipeline broken
        self._stream_active: Dict[str, bool] = {}       # agent_id -> is streaming supposed to be active

        self._task: Optional[asyncio.Task] = None
        self._running = False

    # ──────────────────────────── Registration ────────────────────────────

    def register_agent(self, machine: DiagnosticStateMachine):
        """Register an agent for stream monitoring."""
        self._machines[machine.agent_id] = machine
        self._screenshot_times[machine.agent_id] = time.time()
        self._screenshot_broken[machine.agent_id] = False
        self._stream_active[machine.agent_id] = False

    def unregister_agent(self, agent_id: str):
        """Remove an agent from stream monitoring."""
        self._machines.pop(agent_id, None)
        self._screenshot_times.pop(agent_id, None)
        self._screenshot_broken.pop(agent_id, None)
        self._stream_active.pop(agent_id, None)

    # ──────────────────────────── Stream Recording ────────────────────────────

    def set_stream_active(self, agent_id: str, active: bool):
        """Mark whether streaming is supposed to be active for this agent."""
        old = self._stream_active.get(agent_id, False)
        self._stream_active[agent_id] = active
        if active and not old:
            self._logger.info(
                component='stream_checker',
                event='stream_activated',
                agent_id=agent_id,
                message='Screen streaming activated for agent',
            )
            self._screenshot_broken[agent_id] = False
            self._screenshot_times[agent_id] = time.time()
        elif not active and old:
            self._logger.info(
                component='stream_checker',
                event='stream_deactivated',
                agent_id=agent_id,
                message='Screen streaming deactivated for agent',
            )

    def record_screenshot(self, agent_id: str):
        """Record that a screenshot frame was received."""
        self._screenshot_times[agent_id] = time.time()
        machine = self._machines.get(agent_id)
        if machine:
            machine.touch_screenshot()

        # If it was broken and now recovering
        if self._screenshot_broken.get(agent_id, False):
            self._screenshot_broken[agent_id] = False
            self._logger.recovery(
                component='stream_checker',
                event='screenshot_pipeline_recovered',
                agent_id=agent_id,
                action='screenshot_flow_resumed',
                status='recovered',
                message='Screenshot pipeline recovered — frames are flowing again',
            )
            if self._on_screenshot_recovered:
                try:
                    self._on_screenshot_recovered(agent_id)
                except Exception as e:
                    self._logger.error(
                        component='stream_checker', event='on_recovered_callback_error',
                        agent_id=agent_id, message=f'on_screenshot_recovered callback failed: {e}',
                        exception=e,
                    )

    # ──────────────────────────── Diagnostics ────────────────────────────

    def _check_screenshot_pipeline(self, agent_id: str) -> bool:
        """Check if screenshot pipeline is stalled."""
        if not self._stream_active.get(agent_id, False):
            return False
        if self._screenshot_broken.get(agent_id, False):
            return True  # already broken

        last_time = self._screenshot_times.get(agent_id)
        if last_time is None:
            return False

        elapsed = time.time() - last_time
        if elapsed > self.SCREENSHOT_TIMEOUT:
            self._screenshot_broken[agent_id] = True
            machine = self._machines.get(agent_id)
            state_name = machine.state.name if machine else 'unknown'
            self._logger.error(
                component='stream_checker',
                event='screenshot_pipeline_broken',
                agent_id=agent_id,
                message=f'No screenshot frames for {elapsed:.1f}s (timeout={self.SCREENSHOT_TIMEOUT}s). State={state_name}',
                context={
                    'elapsed_seconds': round(elapsed, 1),
                    'timeout': self.SCREENSHOT_TIMEOUT,
                    'state': state_name,
                },
            )
            if self._on_screenshot_broken:
                try:
                    self._on_screenshot_broken(agent_id)
                except Exception as e:
                    self._logger.error(
                        component='stream_checker', event='on_broken_callback_error',
                        agent_id=agent_id, message=f'on_screenshot_broken callback failed: {e}',
                        exception=e,
                    )
            return True
        return False

    # ──────────────────────────── Background Loop ────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        self._logger.info(
            component='stream_checker',
            event='checker_started',
            message=f'Stream checker started (screenshot_timeout={self.SCREENSHOT_TIMEOUT}s)',
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
                await self._check_all()
            except Exception as e:
                self._logger.error(
                    component='stream_checker',
                    event='check_loop_error',
                    message=f'Error in stream check loop: {e}',
                    exception=e,
                )
            await asyncio.sleep(self.CHECK_INTERVAL)

    async def _check_all(self):
        for agent_id in list(self._machines.keys()):
            self._check_screenshot_pipeline(agent_id)

    # ──────────────────────────── Recovery Helpers ────────────────────────────

    def force_reset_screenshot(self, agent_id: str):
        """Force reset screenshot pipeline state."""
        self._screenshot_broken[agent_id] = False
        self._screenshot_times[agent_id] = time.time()
        self._logger.recovery(
            component='stream_checker',
            event='screenshot_pipeline_reset',
            agent_id=agent_id,
            action='force_reset_screenshot',
            status='completed',
            message='Screenshot pipeline state forcibly reset',
        )

    # ──────────────────────────── Status ────────────────────────────

    def get_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        machine = self._machines.get(agent_id)
        if machine is None:
            return None
        return {
            'agent_id': agent_id,
            'stream_active': self._stream_active.get(agent_id, False),
            'screenshot': {
                'last_frame_ago': round(time.time() - self._screenshot_times.get(agent_id, 0), 1)
                if agent_id in self._screenshot_times else None,
                'is_broken': self._screenshot_broken.get(agent_id, False),
                'timeout': self.SCREENSHOT_TIMEOUT,
            },
        }

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        return {aid: self.get_status(aid) for aid in self._machines}