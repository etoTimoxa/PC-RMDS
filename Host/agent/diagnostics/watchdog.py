"""Screenshot watchdog for monitoring and stream validation.

Tracks:
- screenshot task active?
- last screenshot timestamp
- screenshot stalls (> 5 sec = diagnostic event + recovery trigger)

If stalled, generates diagnostic event and triggers recovery.
"""

import asyncio
import time
import threading
from typing import Any, Callable, Dict, Optional

from agent.diagnostics.logger import StructuredLogger
from agent.diagnostics.events import DiagnosticEvent, Severity

SCREENSHOT_STALL_TIMEOUT = 5.0  # seconds


class ScreenshotWatchdog:
    """Monitors screenshot stream health.

    Usage:
        watchdog = ScreenshotWatchdog(agent_id="agent-1")
        watchdog.set_recovery_trigger(my_recovery_fn)
        # Start as task:
        task = asyncio.create_task(watchdog.run())
        # Each screenshot callback:
        watchdog.report_frame()
    """

    def __init__(
        self,
        agent_id: str = "",
        stall_timeout: float = SCREENSHOT_STALL_TIMEOUT,
        check_interval: float = 2.0,
    ):
        self._agent_id = agent_id
        self._stall_timeout = stall_timeout
        self._check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()

        # State
        self._last_frame_time: float = 0.0
        self._frames_received: int = 0
        self._stall_count: int = 0
        self._restart_count: int = 0
        self._is_streaming: bool = False
        self._last_stall_event_time: float = 0.0

        # Callbacks
        self._on_stall: Optional[Callable] = None  # async callable() -> None
        self._logger = StructuredLogger("screenshot_watchdog", agent_id=agent_id)

    def set_on_stall(self, callback: Callable) -> None:
        """Set async callback for when a stall is detected."""
        self._on_stall = callback

    def report_frame(self) -> None:
        """Called by screenshot loop for each frame."""
        with self._lock:
            self._last_frame_time = time.time()
            self._frames_received += 1

    def start_streaming(self) -> None:
        """Mark streaming as active."""
        with self._lock:
            self._is_streaming = True
            self._last_frame_time = time.time()

    def stop_streaming(self) -> None:
        """Mark streaming as inactive."""
        with self._lock:
            self._is_streaming = False

    async def run(self) -> None:
        """Main watchdog loop."""
        self._running = True
        self._logger.info("watchdog_started", "Screenshot watchdog started")

        while self._running:
            await asyncio.sleep(self._check_interval)

            with self._lock:
                if not self._is_streaming:
                    continue
                now = time.time()
                elapsed = now - self._last_frame_time
                if elapsed > self._stall_timeout:
                    self._stall_count += 1
                    should_trigger = (now - self._last_stall_event_time) > self._stall_timeout * 2
                    if should_trigger:
                        self._last_stall_event_time = now
                        stall_details = {
                            "stall_duration": round(elapsed, 2),
                            "frames_received": self._frames_received,
                            "stall_count": self._stall_count,
                            "restart_count": self._restart_count,
                        }
                else:
                    stall_details = None

            if stall_details:
                self._logger.warning(
                    "screenshot_stall_detected",
                    f"Screenshot stall detected: {stall_details['stall_duration']}s since last frame",
                    stall_details,
                )

                if self._on_stall:
                    try:
                        if asyncio.iscoroutinefunction(self._on_stall):
                            await self._on_stall()
                        else:
                            self._on_stall()
                    except Exception as exc:
                        self._logger.error(
                            "watchdog_stall_handler_error",
                            f"Stall handler failed: {exc}",
                        )

    async def stop(self) -> None:
        """Stop watchdog loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._logger.info(
            "watchdog_stopped",
            "Screenshot watchdog stopped",
            {
                "frames_received": self._frames_received,
                "stall_count": self._stall_count,
                "restart_count": self._restart_count,
            },
        )

    def report_restart(self) -> None:
        """Called when screenshot stream is restarted."""
        with self._lock:
            self._restart_count += 1
            self._last_frame_time = time.time()

    def create_task(self) -> asyncio.Task:
        """Create and store watchdog task."""
        self._task = asyncio.create_task(self.run())
        return self._task

    async def cancel(self) -> None:
        await self.stop()

    @property
    def frames_received(self) -> int:
        with self._lock:
            return self._frames_received

    @property
    def stall_count(self) -> int:
        with self._lock:
            return self._stall_count

    @property
    def restart_count(self) -> int:
        with self._lock:
            return self._restart_count

    @property
    def is_healthy(self) -> bool:
        """Check if stream is healthy (no stall in current timeout window)."""
        with self._lock:
            if not self._is_streaming:
                return True
            return (time.time() - self._last_frame_time) <= self._stall_timeout

    def reset_stats(self) -> None:
        with self._lock:
            self._frames_received = 0
            self._stall_count = 0
            self._restart_count = 0
            self._last_frame_time = time.time()

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "frames_received": self._frames_received,
                "stall_count": self._stall_count,
                "restart_count": self._restart_count,
                "last_frame_time": self._last_frame_time,
                "is_streaming": self._is_streaming,
                "healthy": self.is_healthy,
            }