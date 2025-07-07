
"""
loop_engine
-----------------

It has not been confirmed to work yet.


This package provides a wrapper to augment a user-defined loop ("circuit")
with a lifecycle and standard event hooks.

It offers:
- `make_loop_engine_handle()`: factory to create a loop engine handle
  that wraps the user circuit with event processing and state control.
- Optional code generation for the circuit, allowing experimental
  or quick-access execution without a user-supplied loop.

Detailed usage and examples are available in loop_engine_manual.py.

"""

__version__ = "0.2.0"

from .loop_engine_manual import (
    LoopEngineHandle,
    StateObserver,
    LoopInterruptObserver,
    LoopResultReader,
    LoopLog,
    EventHandler,
    Action,
    Context,
    Reactor,
    ReactorFactory,
)

from .loop_engine import make_loop_engine_handle

__all__ = [
    "make_loop_engine_handle",
    "LoopEngineHandle",
    "StateObserver",
    "LoopInterruptObserver",
    "LoopResultReader",
    "LoopLog",
    "EventHandler",
    "Action",
    "Context",
    "Reactor",
    "ReactorFactory",
]