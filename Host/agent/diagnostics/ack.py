"""ACK protocol support for command processing.

Agent MUST send ACK for every received command with command_id.
Async, non-blocking, with duplicate protection.
"""

import asyncio
import json
import threading
from typing import Any, Callable, Dict, Optional, Set

from agent.diagnostics.logger import StructuredLogger


class ACKSender:
    """Sends ACK responses for received commands.

    Deduplicates by command_id.
    Async sending - does NOT block command processing.

    Usage:
        ack = ACKSender()
        ack.set_sender(my_ws_send_func)
        # When command received:
        await ack.send_ack(command_id="uuid-123")
    """

    def __init__(self):
        self._send_func: Optional[Callable] = None
        self._sent_ids: Set[str] = set()
        self._lock = threading.Lock()
        self._ack_count: int = 0
        self._logger = StructuredLogger("ack", agent_id="")

    def set_sender(self, send_func: Callable) -> None:
        """Set async send function."""
        self._send_func = send_func

    def set_agent_id(self, agent_id: str) -> None:
        self._logger = StructuredLogger("ack", agent_id=agent_id)

    async def send_ack(self, command_id: str, status: str = "received") -> bool:
        """Send ACK for command. Returns True if sent, False if duplicate.

        Non-blocking - spawns task if send_func is async.
        """
        # Dedup check
        with self._lock:
            if command_id in self._sent_ids:
                return False
            self._sent_ids.add(command_id)
            # Trim to prevent unbounded growth
            if len(self._sent_ids) > 10000:
                self._sent_ids = set(list(self._sent_ids)[-5000:])

        if not self._send_func:
            self._logger.warning(
                "ack_no_sender",
                f"No send function set, cannot send ACK for {command_id[:8]}...",
            )
            return False

        message = {
            "type": "ack",
            "command_id": command_id,
            "status": status,
        }
        payload = json.dumps(message)

        try:
            if asyncio.iscoroutinefunction(self._send_func):
                await self._send_func(payload)
            else:
                self._send_func(payload)

            with self._lock:
                self._ack_count += 1

            self._logger.info(
                "ack_sent",
                f"ACK sent for command {command_id[:8]}...",
                {"command_id": command_id, "status": status},
            )
            return True

        except Exception as exc:
            self._logger.error(
                "ack_failed",
                f"Failed to send ACK for {command_id[:8]}...: {exc}",
                {"command_id": command_id},
            )
            return False

    def has_acked(self, command_id: str) -> bool:
        """Check if command_id has already been ACKed."""
        with self._lock:
            return command_id in self._sent_ids

    def reset(self) -> None:
        """Reset sent IDs set (e.g., on reconnect)."""
        with self._lock:
            self._sent_ids.clear()
            self._ack_count = 0
        self._logger.info("ack_reset", "ACK sender reset")

    @property
    def ack_count(self) -> int:
        with self._lock:
            return self._ack_count

    @property
    def unique_ids_count(self) -> int:
        with self._lock:
            return len(self._sent_ids)