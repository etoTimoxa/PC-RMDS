import atexit
import signal
import sys
from typing import Optional, Callable


_cleanup_done = False
_cleanup_callback: Optional[Callable] = None


def register_cleanup(callback: Callable) -> None:
    global _cleanup_callback
    _cleanup_callback = callback


def cleanup_on_exit() -> None:
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    
    if _cleanup_callback:
        try:
            _cleanup_callback()
        except:
            pass


def signal_handler(signum, frame) -> None:
    cleanup_on_exit()
    sys.exit(0)


def setup_cleanup() -> None:
    atexit.register(cleanup_on_exit)
    signal.signal(signal.SIGTERM, signal_handler)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, signal_handler)