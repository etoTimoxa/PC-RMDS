"""Agent Finite State Machine.

States:
  DISCONNECTED -> CONNECTING -> REGISTERED -> STREAMING
  REGISTERED/STREAMING -> DEGRADED -> RECOVERING -> REGISTERED
  Any -> ERROR -> DISCONNECTED

Thread-safe transitions with validation, timestamps, and logging.
"""

import enum
import time
import traceback
import threading
from typing import Callable, Dict, Optional, Set


class AgentState(enum.Enum):
    """Agent FSM states."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    REGISTERED = "REGISTERED"
    STREAMING = "STREAMING"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    ERROR = "ERROR"

    def __str__(self) -> str:
        return self.value


# Valid transitions: from_state -> set of allowed to_states
_TRANSITIONS: Dict[AgentState, Set[AgentState]] = {
    AgentState.DISCONNECTED: {
        AgentState.CONNECTING,
        AgentState.RECOVERING,
    },
    AgentState.CONNECTING: {
        AgentState.REGISTERED,
        AgentState.DISCONNECTED,
        AgentState.ERROR,
    },
    AgentState.REGISTERED: {
        AgentState.STREAMING,
        AgentState.DEGRADED,
        AgentState.DISCONNECTED,
        AgentState.ERROR,
    },
    AgentState.STREAMING: {
        AgentState.REGISTERED,
        AgentState.DEGRADED,
        AgentState.DISCONNECTED,
        AgentState.ERROR,
    },
    AgentState.DEGRADED: {
        AgentState.RECOVERING,
        AgentState.DISCONNECTED,
        AgentState.ERROR,
    },
    AgentState.RECOVERING: {
        AgentState.REGISTERED,
        AgentState.STREAMING,
        AgentState.DEGRADED,
        AgentState.DISCONNECTED,
        AgentState.ERROR,
    },
    AgentState.ERROR: {
        AgentState.DISCONNECTED,
        AgentState.RECOVERING,
    },
}


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


class AgentFSM:
    """Thread-safe finite state machine for agent lifecycle.

    Usage:
        fsm = AgentFSM()
        fsm.state  # -> AgentState.DISCONNECTED
        fsm.transition(AgentState.CONNECTING)
        fsm.transition(AgentState.REGISTERED)
    """

    def __init__(
        self,
        initial_state: AgentState = AgentState.DISCONNECTED,
        on_transition: Optional[Callable[[AgentState, AgentState], None]] = None,
    ):
        self._state: AgentState = initial_state
        self._lock = threading.Lock()
        self._on_transition: Optional[Callable[[AgentState, AgentState], None]] = on_transition
        self._transition_times: Dict[str, float] = {}
        self._transition_count: int = 0
        self._record_transition(initial_state)

    @property
    def state(self) -> AgentState:
        with self._lock:
            return self._state

    @state.setter
    def state(self, value: AgentState) -> None:
        """Direct setter - raises error. Use transition() instead."""
        raise AttributeError(
            "Cannot set state directly. Use transition() method."
        )

    def transition(self, new_state: AgentState) -> None:
        """Validate and perform state transition. Thread-safe."""
        with self._lock:
            old_state = self._state
            if old_state == new_state:
                # Idempotent - already in target state, no-op
                return

            allowed = _TRANSITIONS.get(old_state, set())
            if new_state not in allowed:
                raise StateTransitionError(
                    f"Invalid transition: {old_state.value} -> {new_state.value}. "
                    f"Allowed from {old_state.value}: "
                    f"{', '.join(s.value for s in allowed)}"
                )

            self._state = new_state
            self._record_transition(new_state)
            self._transition_count += 1

        # Fire callback outside lock to avoid deadlock
        if self._on_transition:
            try:
                self._on_transition(old_state, new_state)
            except Exception:
                # Never let callback break the FSM
                traceback.print_exc()

    def force_transition(self, new_state: AgentState) -> None:
        """Force transition without validation. Only for initialization/reset."""
        with self._lock:
            old_state = self._state
            self._state = new_state
            self._record_transition(new_state)

        if self._on_transition:
            try:
                self._on_transition(old_state, new_state)
            except Exception:
                traceback.print_exc()

    def _record_transition(self, state: AgentState) -> None:
        self._transition_times[state.value] = time.time()

    def time_in_state(self, state: Optional[AgentState] = None) -> float:
        """Seconds since entering given state (or current state)."""
        target = state or self._state
        t = self._transition_times.get(target.value, 0.0)
        return time.time() - t if t > 0 else 0.0

    @property
    def transition_count(self) -> int:
        with self._lock:
            return self._transition_count

    def is_stable(self) -> bool:
        """Check if agent has been in current state > 10 seconds."""
        return self.time_in_state() > 10.0

    def is_connected(self) -> bool:
        s = self.state
        return s in (AgentState.REGISTERED, AgentState.STREAMING)

    def needs_recovery(self) -> bool:
        s = self.state
        return s in (AgentState.ERROR, AgentState.DEGRADED, AgentState.DISCONNECTED)

    def reset(self) -> None:
        """Reset FSM to DISCONNECTED."""
        self.force_transition(AgentState.DISCONNECTED)

    def get_summary(self) -> Dict:
        with self._lock:
            return {
                "state": self._state.value,
                "transition_count": self._transition_count,
                "time_in_state": time.time() - self._transition_times.get(
                    self._state.value, time.time()
                ),
                "timestamps": {
                    k: v for k, v in self._transition_times.items()
                },
            }

    def __repr__(self) -> str:
        return f"AgentFSM(state={self._state.value})"