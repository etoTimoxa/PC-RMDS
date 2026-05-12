"""
Diagnostic State Machine.
Tracks agent lifecycle: DISCONNECTED → CONNECTING → REGISTERED → STREAMING → ...
Thread-safe via threading.RLock. Logs invalid transitions. Tracks transition timestamps.
"""
import threading
import time
from enum import Enum, auto
from datetime import datetime
from typing import Optional, Dict, Any, Callable


class AgentState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    REGISTERED = auto()
    STREAMING = auto()
    DEGRADED = auto()
    RECOVERING = auto()
    ERROR = auto()


_TRANSITIONS: Dict[tuple[AgentState, AgentState], bool] = {
    (AgentState.DISCONNECTED, AgentState.CONNECTING): True,
    (AgentState.CONNECTING, AgentState.REGISTERED): True,
    (AgentState.REGISTERED, AgentState.STREAMING): True,
    (AgentState.CONNECTING, AgentState.DISCONNECTED): True,
    (AgentState.REGISTERED, AgentState.DISCONNECTED): True,
    (AgentState.STREAMING, AgentState.DISCONNECTED): True,
    (AgentState.DEGRADED, AgentState.DISCONNECTED): True,
    (AgentState.RECOVERING, AgentState.DISCONNECTED): True,
    (AgentState.ERROR, AgentState.DISCONNECTED): True,
    (AgentState.REGISTERED, AgentState.DEGRADED): True,
    (AgentState.STREAMING, AgentState.DEGRADED): True,
    (AgentState.DEGRADED, AgentState.RECOVERING): True,
    (AgentState.ERROR, AgentState.RECOVERING): True,
    (AgentState.RECOVERING, AgentState.REGISTERED): True,
    (AgentState.RECOVERING, AgentState.STREAMING): True,
    (AgentState.RECOVERING, AgentState.DEGRADED): True,
    (AgentState.RECOVERING, AgentState.DISCONNECTED): True,
    (AgentState.CONNECTING, AgentState.ERROR): True,
    (AgentState.REGISTERED, AgentState.ERROR): True,
    (AgentState.STREAMING, AgentState.ERROR): True,
    (AgentState.DEGRADED, AgentState.ERROR): True,
    (AgentState.RECOVERING, AgentState.ERROR): True,
    (AgentState.ERROR, AgentState.CONNECTING): True,
    (AgentState.DISCONNECTED, AgentState.REGISTERED): True,
    (AgentState.DISCONNECTED, AgentState.DEGRADED): True,
    (AgentState.REGISTERED, AgentState.CONNECTING): True,
    (AgentState.DISCONNECTED, AgentState.ERROR): True,
}


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    def __init__(self, agent_id: str, from_state: AgentState, to_state: AgentState, reason: str = ''):
        self.agent_id = agent_id
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(f'agent={agent_id}: invalid transition {from_state.name} -> {to_state.name}'
                         f'{" (" + reason + ")" if reason else ""}')


class TransitionRecord:
    """Single recorded transition with timestamps."""
    def __init__(self, old_state: AgentState, new_state: AgentState, reason: str = '', **context):
        self.timestamp = time.time()
        self.old_state = old_state.name
        self.new_state = new_state.name
        self.reason = reason
        self.context = context

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': datetime.utcfromtimestamp(self.timestamp).isoformat(),
            'old_state': self.old_state,
            'new_state': self.new_state,
            'reason': self.reason,
            'context': self.context,
        }


class DiagnosticStateMachine:
    """
    Thread-safe state machine for tracking agent diagnostic state.
    Uses threading.RLock for cross-thread safety.
    Maintains per-agent state with timed transition history and callbacks.
    """

    def __init__(
        self,
        agent_id: str,
        initial_state: AgentState = AgentState.DISCONNECTED,
        on_transition: Optional[Callable[['DiagnosticStateMachine', AgentState, AgentState], None]] = None,
        on_invalid_transition: Optional[Callable[['DiagnosticStateMachine', AgentState, AgentState, str], None]] = None,
    ):
        self.agent_id = agent_id
        self._lock = threading.RLock()
        self._state = initial_state
        self._on_transition = on_transition
        self._on_invalid_transition = on_invalid_transition

        self._history: list[TransitionRecord] = []
        self._last_transition_time: Optional[float] = None
        self._state_entry_time: float = time.time()

        self._metadata: Dict[str, Any] = {
            'last_heartbeat': None,
            'last_screenshot': None,
            'last_command_ack': None,
            'last_error': None,
            'error_count': 0,
            'recovery_count': 0,
            'uptime_start': None,
            'streaming_since': None,
        }
        self._append_record(initial_state, initial_state, 'initial_state')

    # ──────────────────────────── Properties ────────────────────────────

    @property
    def state(self) -> AgentState:
        with self._lock:
            return self._state

    @property
    def history(self) -> list[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._history]

    @property
    def metadata(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._metadata)

    @property
    def is_online(self) -> bool:
        return self._state not in (AgentState.DISCONNECTED, AgentState.ERROR)

    @property
    def is_streaming(self) -> bool:
        return self._state == AgentState.STREAMING

    @property
    def is_degraded(self) -> bool:
        return self._state == AgentState.DEGRADED

    @property
    def is_recovering(self) -> bool:
        return self._state == AgentState.RECOVERING

    @property
    def last_transition_time(self) -> Optional[float]:
        return self._last_transition_time

    @property
    def time_in_current_state(self) -> float:
        """Seconds elapsed since entering the current state."""
        return time.time() - self._state_entry_time

    # ──────────────────────────── State Transition ────────────────────────────

    def can_transition_to(self, new_state: AgentState) -> bool:
        """Check if a transition is allowed without executing it."""
        key = (self._state, new_state)
        return _TRANSITIONS.get(key, False)

    def transition_to(self, new_state: AgentState, reason: str = '', **context) -> bool:
        """
        Attempt a state transition. Returns True if transition occurred.
        Raises StateTransitionError if transition is not allowed.
        Thread-safe via RLock.
        """
        with self._lock:
            if self._state == new_state:
                return False

            key = (self._state, new_state)
            allowed = _TRANSITIONS.get(key, False)

            if not allowed:
                err = StateTransitionError(self.agent_id, self._state, new_state, reason)
                # Notify invalid transition callback
                if self._on_invalid_transition:
                    try:
                        self._on_invalid_transition(self, self._state, new_state, reason)
                    except Exception as e:
                        import logging
                        logging.getLogger('state_machine').error(
                            f'on_invalid_transition callback failed for {self.agent_id}: {e}'
                        )
                raise err

            old_state = self._state
            self._state = new_state
            self._last_transition_time = time.time()
            self._state_entry_time = time.time()

            self._append_record(old_state, new_state, reason, **context)

            if new_state == AgentState.DISCONNECTED:
                self._metadata['last_error'] = reason or 'disconnected'
            if new_state == AgentState.STREAMING:
                self._metadata['streaming_since'] = datetime.utcnow().isoformat()
            if old_state == AgentState.STREAMING:
                self._metadata['streaming_since'] = None

            if self._on_transition:
                try:
                    self._on_transition(self, old_state, new_state)
                except Exception as e:
                    # Log but don't suppress — propagate to caller
                    import logging
                    logging.getLogger('state_machine').error(
                        f'on_transition callback failed for {self.agent_id}: {e}'
                    )

            return True

    # ──────────────────────────── Metadata ────────────────────────────

    def update_metadata(self, key: str, value: Any):
        with self._lock:
            if key in self._metadata:
                self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._metadata.get(key, default)

    def touch_heartbeat(self):
        with self._lock:
            self._metadata['last_heartbeat'] = datetime.utcnow().isoformat()
            if self._metadata.get('uptime_start') is None:
                self._metadata['uptime_start'] = datetime.utcnow().isoformat()

    def touch_screenshot(self):
        with self._lock:
            self._metadata['last_screenshot'] = datetime.utcnow().isoformat()

    def touch_command_ack(self):
        with self._lock:
            self._metadata['last_command_ack'] = datetime.utcnow().isoformat()

    def increment_error_count(self):
        with self._lock:
            self._metadata['error_count'] = self._metadata.get('error_count', 0) + 1

    def increment_recovery_count(self):
        with self._lock:
            self._metadata['recovery_count'] = self._metadata.get('recovery_count', 0) + 1

    # ──────────────────────────── Snapshot ────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'agent_id': self.agent_id,
                'state': self._state.name,
                'is_online': self.is_online,
                'is_streaming': self.is_streaming,
                'is_degraded': self.is_degraded,
                'is_recovering': self.is_recovering,
                'time_in_state_seconds': round(self.time_in_current_state, 2),
                'metadata': dict(self._metadata),
                'history_count': len(self._history),
                'last_events': [r.to_dict() for r in self._history[-10:]],
            }

    # ──────────────────────────── Private ────────────────────────────

    def _append_record(self, old_state: AgentState, new_state: AgentState, reason: str = '', **context):
        """Append a transition record (caller must hold _lock)."""
        record = TransitionRecord(old_state, new_state, reason, **context)
        self._history.append(record)
        if len(self._history) > 1000:
            self._history = self._history[-500:]