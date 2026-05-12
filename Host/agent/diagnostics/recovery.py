"""Recovery manager for agent self-healing.

Supports:
- reconnect_websocket
- restart_stream
- restore_session
- restart_tasks

Features:
- async, thread-safe
- cooldown per action
- max attempts tracking
- recovery validation via RecoveryResult
"""

import enum
import time
import asyncio
import traceback
import threading
from typing import Any, Callable, Dict, Optional, Set
from dataclasses import dataclass, field


class RecoveryAction(enum.Enum):
    """Types of recovery actions."""

    RECONNECT_WEBSOCKET = "reconnect_websocket"
    RESTART_STREAM = "restart_stream"
    RESTORE_SESSION = "restore_session"
    RESTART_TASKS = "restart_tasks"
    RESTART_CAPTURE = "restart_capture"


@dataclass
class RecoveryResult:
    """Result of a recovery attempt with validation."""

    action: RecoveryAction
    success: bool
    validation_passed: bool = False
    duration: float = 0.0
    details: str = ""
    attempt: int = 0

    @property
    def fully_successful(self) -> bool:
        return self.success and self.validation_passed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "success": self.success,
            "validation_passed": self.validation_passed,
            "duration": self.duration,
            "details": self.details,
            "attempt": self.attempt,
        }


class RecoveryManager:
    """Lightweight recovery manager with cooldowns and attempt limits.

    Usage:
        manager = RecoveryManager()
        # Register recovery handlers
        manager.register_handler(RecoveryAction.RECONNECT_WEBSOCKET, my_reconnect_fn)
        # Execute recovery
        result = await manager.execute_recovery(RecoveryAction.RECONNECT_WEBSOCKET)
    """

    DEFAULT_COOLDOWN: float = 30.0  # seconds between same action
    DEFAULT_MAX_ATTEMPTS: int = 5
    DEFAULT_BACKOFF_BASE: float = 2.0  # exponential backoff base

    def __init__(
        self,
        global_cooldown: float = 10.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ):
        self._handlers: Dict[RecoveryAction, Callable] = {}
        self._validators: Dict[RecoveryAction, Callable] = {}
        self._lock = threading.Lock()
        self._last_attempt: Dict[str, float] = {}
        self._attempt_counts: Dict[str, int] = {}
        self._global_cooldown = global_cooldown
        self._max_attempts = max_attempts
        self._recovery_history: list = []
        self._max_history = 100

    def register_handler(
        self,
        action: RecoveryAction,
        handler: Callable,
        validator: Optional[Callable] = None,
    ) -> None:
        """Register async handler for recovery action.
        
        handler is an async callable: async def handler() -> bool
        validator is an optional async callable: async def validator() -> bool
        """
        with self._lock:
            self._handlers[action] = handler
            if validator:
                self._validators[action] = validator

    def unregister_handler(self, action: RecoveryAction) -> None:
        with self._lock:
            self._handlers.pop(action, None)
            self._validators.pop(action, None)

    def _can_attempt(self, action: RecoveryAction) -> bool:
        """Check cooldown and attempt limits."""
        key = action.value
        now = time.time()
        last = self._last_attempt.get(key, 0.0)
        count = self._attempt_counts.get(key, 0)

        # Check max attempts (resets on success)
        if count >= self._max_attempts:
            return False

        # Check cooldown
        if now - last < self._global_cooldown:
            return False

        return True

    def _get_backoff(self, action: RecoveryAction) -> float:
        count = self._attempt_counts.get(action.value, 0)
        return self.DEFAULT_BACKOFF_BASE ** count

    def _record_attempt(self, action: RecoveryAction, result: RecoveryResult) -> None:
        key = action.value
        now = time.time()
        with self._lock:
            self._last_attempt[key] = now
            self._recovery_history.append(result.to_dict())
            if len(self._recovery_history) > self._max_history:
                self._recovery_history = self._recovery_history[-self._max_history:]

            if result.fully_successful:
                # Reset attempt count on full success
                self._attempt_counts[key] = 0
            else:
                self._attempt_counts[key] = self._attempt_counts.get(key, 0) + 1

    async def execute_recovery(self, action: RecoveryAction) -> RecoveryResult:
        """Execute a single recovery action. Returns result with validation."""
        start = time.time()
        attempt = self._attempt_counts.get(action.value, 0) + 1

        if not self._can_attempt(action):
            return RecoveryResult(
                action=action,
                success=False,
                validation_passed=False,
                duration=time.time() - start,
                details=f"In cooldown or max attempts reached (attempt {attempt})",
                attempt=attempt,
            )

        handler = self._handlers.get(action)
        if handler is None:
            return RecoveryResult(
                action=action,
                success=False,
                validation_passed=False,
                duration=time.time() - start,
                details=f"No handler registered for {action.value}",
                attempt=attempt,
            )

        # Apply backoff before execution
        backoff = self._get_backoff(action)
        if backoff > 1.0:
            await asyncio.sleep(min(backoff, 30.0))

        # Execute handler
        success = False
        try:
            if asyncio.iscoroutinefunction(handler):
                success = await handler()
            else:
                success = handler()
        except Exception as exc:
            result = RecoveryResult(
                action=action,
                success=False,
                validation_passed=False,
                duration=time.time() - start,
                details=f"Handler raised: {exc}\n{traceback.format_exc()}",
                attempt=attempt,
            )
            self._record_attempt(action, result)
            return result

        # Validate if handler returned True
        validation_passed = False
        if success:
            validator = self._validators.get(action)
            if validator:
                try:
                    if asyncio.iscoroutinefunction(validator):
                        validation_passed = await validator()
                    else:
                        validation_passed = validator()
                except Exception as exc:
                    validation_passed = False
                    # Store in details but don't overwrite success=False
            else:
                # No validator = auto-pass
                validation_passed = True

        result = RecoveryResult(
            action=action,
            success=success,
            validation_passed=validation_passed,
            duration=time.time() - start,
            details=f"Handler {'succeeded' if success else 'failed'}, "
                    f"validation {'passed' if validation_passed else 'failed'}",
            attempt=attempt,
        )
        self._record_attempt(action, result)
        return result

    async def execute_recovery_pipeline(
        self, actions: list
    ) -> Dict[str, RecoveryResult]:
        """Execute multiple recovery actions in sequence. Stops on first failure.

        actions: list of RecoveryAction or (RecoveryAction, callable_overrides)
        Returns dict of action -> result.
        """
        results: Dict[str, RecoveryResult] = {}
        for action in actions:
            if isinstance(action, tuple):
                action, handler_override = action
                # Register temporary handler
                orig = self._handlers.get(action)
                self.register_handler(action, handler_override[0], handler_override[1] if len(handler_override) > 1 else None)
                result = await self.execute_recovery(action)
                if orig:
                    self.register_handler(action, orig)
                else:
                    self.unregister_handler(action)
            else:
                result = await self.execute_recovery(action)

            results[action.value] = result
            if not result.success:
                break

        return results

    def reset_attempts(self, action: Optional[RecoveryAction] = None) -> None:
        """Reset attempt counters for given action or all."""
        with self._lock:
            if action:
                self._attempt_counts[action.value] = 0
            else:
                self._attempt_counts.clear()

    def get_attempt_count(self, action: RecoveryAction) -> int:
        return self._attempt_counts.get(action.value, 0)

    def get_history(self) -> list:
        with self._lock:
            return list(self._recovery_history)

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "attempts": dict(self._attempt_counts),
                "last_attempts": {k: v for k, v in self._last_attempt.items()},
                "history_count": len(self._recovery_history),
                "global_cooldown": self._global_cooldown,
                "max_attempts": self._max_attempts,
            }