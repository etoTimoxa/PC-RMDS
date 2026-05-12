"""Heartbeat subsystem for agent.

Independent async task that sends periodic heartbeats.
Does NOT depend on screenshot loop or command handling.
"""

import asyncio
import json
import time
from typing import Any, Callable, Dict, Optional

from agent.diagnostics.logger import StructuredLogger

HEARTBEAT_INTERVAL = 5  # seconds


class HeartbeatSender:
    """Sends periodic heartbeats to server via WebSocket.

    Usage:
        heartbeat = HeartbeatSender(agent_id="agent-1")
        heartbeat.set_sender(my_ws_send_func)
        # Start as task:
        task = asyncio.create_task(heartbeat.start())
        # Later:
        await heartbeat.stop()
    """

    def __init__(
        self,
        agent_id: str = "",
        interval: float = HEARTBEAT_INTERVAL,
    ):
        self._agent_id = agent_id
        self._interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._send_func: Optional[Callable] = None  # async callable (str) -> None
        self._heartbeat_count: int = 0
        self._logger = StructuredLogger("heartbeat", agent_id=agent_id)

    def set_sender(self, send_func: Callable) -> None:
        """Set the async send function (e.g., ws.send)."""
        self._send_func = send_func

    async def start(self) -> None:
        """Start heartbeat loop. Runs until stop() is called."""
        if self._running:
            return
        self._running = True
        self._logger.info("heartbeat_started", "Heartbeat sender started")

        while self._running:
            try:
                await self._send_heartbeat()
            except Exception as exc:
                self._logger.error(
                    "heartbeat_error",
                    f"Failed to send heartbeat: {exc}",
                )

            await asyncio.sleep(self._interval)

    async def stop(self) -> None:
        """Stop heartbeat loop gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._logger.info("heartbeat_stopped", "Heartbeat sender stopped")

    async def _send_heartbeat(self) -> None:
        if not self._send_func:
            return

        message = {
            "type": "heartbeat",
            "agent_id": self._agent_id,
            "timestamp": time.time(),
        }
        payload = json.dumps(message)
        await self._send_func(payload)
        self._heartbeat_count += 1

    @property
    def heartbeat_count(self) -> int:
        return self._heartbeat_count

    @property
    def is_running(self) -> bool:
        return self._running

    def create_task(self) -> asyncio.Task:
        """Create and store the heartbeat asyncio task."""
        self._task = asyncio.create_task(self.start())
        return self._task

    async def cancel(self) -> None:
        """Cancel the running task."""
        await self.stop()