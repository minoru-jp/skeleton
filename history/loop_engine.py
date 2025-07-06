"""
This code defines isolated, self-contained implementations via `_setup_*()` functions,  
each conforming to a Protocol interface.  

- Each implementation has its own internal state and constants, with no global or shared definitions.  
- Reusability is ensured only through Protocols; implementations remain independent.  
- Lifecycle is explicitly controlled by the caller.  

The design emphasizes locality, predictability, and safety over reuse or readability.

Implementation Closure Design Pattern

Core Principles:
1. Each _setup_*() function returns an instance implementing a Protocol
2. Dependencies are explicitly passed as arguments
3. Internal implementation is encapsulated within closures

## Design Notes

This module deliberately avoids traditional Python classes and instances
for internal components. Instead, it uses closures to encapsulate all 
state and constants within each `_setup_*()` function.

### Rationale:
- Classes expose unnecessary mutability (e.g., instance `__dict__`).
- Classes inherit and expose attributes/methods beyond the intended interface.
- Instances allow access to internals by mistake or convention-breaking.
- Closures ensure true immutability and locality, enforcing the Protocol contract
  as the only visible surface.

This pattern prioritizes:
- Explicitness
- Safety from misuse
- Locality of state
- Minimal and predictable surface

All components are initialized and configured explicitly and return a 
Protocol-compliant implementation with no shared or global state.

Design Notes: Property-based constants & static exceptions

- Constants (like event names, state tokens) are exposed via `@property` + `__slots__`
  to prevent accidental overwrite or deletion, and to enforce immutability.

- Exception classes are defined as static, named classes (not closures)
  so they can be explicitly referenced in `except` clauses.

This ensures explicit, immutable, and predictable interfaces, minimizing misuse.

Method naming and decorator convention for API design.

- Setter methods:
    - Decorator: @staticmethod
    - Name: set_*
    - Description: Modifies internal state. Has side effects.

- Simple getter properties:
    - Decorator: @property
    - Name: plain attribute name (e.g., foo)
    - Description: Retrieves internal state. No side effects. Lightweight.

- Complex or expensive getters:
    - Decorator: @staticmethod
    - Name: get_*
    - Description: Retrieves derived or computed result. May involve calculation or side effects.

This convention ensures:
- Clear distinction between mutating and non-mutating operations.
- Readability and predictability of the API.
- Consistency with common Python practices.

Use `get_*` only when the retrieval is not a trivial state access.


This module defines closures that return concrete implementations of protocol interfaces.
Each closure encapsulates state and logic locally and returns an implementation that
conforms to the specified protocol.

The internal implementation classes are defined inside the closures and intentionally
named generically (e.g., '_Interface') to avoid coupling to the protocol’s specific name.
This ensures the implementation remains correct and comprehensible even if the protocol
name changes later.

### Design Notes: Access Pattern

- All operations must be performed through the interface instance returned by the `_setup_*()` function.
- Accessing methods or properties directly on the class (without instantiating via the setup closure) is not supported or intended.
- This ensures that the internal state remains properly encapsulated within the closure and that no global or shared state leaks through class-level access.
- Always hold and use the instance returned by the setup function for any interaction.

This design eliminates unnecessary choices and enforces a minimal surface.
Its primary benefit is to reduce the cognitive load during implementation — not just future maintenance.

Additional Note: I avoid using Enum because it contradicts Python’s philosophy that “readability counts.” To deny this principle is to deny Python itself.

"""

import asyncio
import inspect
import logging

import string
from types import MappingProxyType

from typing import Awaitable, Optional, Protocol, Callable, Mapping, Tuple, Any, runtime_checkable, FrozenSet, Type
from types import MappingProxyType
from typing_extensions import TypeAlias


@runtime_checkable
class _LoopEvent(Protocol):
    """
    Protocol for standard loop lifecycle events and validation.
    """

    @property
    def START(_) -> str: 
        """Event name for loop start."""
    @property
    def PAUSE(_) -> str: 
        """Event name for loop pause."""
    @property
    def RESUME(_) -> str: 
        """Event name for loop resume."""
    @property
    def STOP_NORMALLY(_) -> str: 
        """Event name for normal loop stop."""
    @property
    def STOP_CANCELED(_) -> str: 
        """Event name for canceled loop stop."""
    @property
    def STOP_HANDLER_ERROR(_) -> str: 
        """Event name when a event handler raises an error."""
    @property
    def STOP_CIRCUIT_ERROR(_) -> str: 
        """Event name when a circuit raises an error."""
    @property
    def CLEANUP(_) -> str: 
        """Event name for loop cleanup."""
    @property
    def LOOP_RESULT(_) -> str: 
        """Event name for final loop result."""

    @staticmethod
    def is_valid_event(name: str) -> bool: 
        """Return True if the given name is a defined event."""
    @property
    def all_events(_) -> FrozenSet[str]: 
        """Return all defined event names as a frozen set."""


def _setup_loop_event() -> _LoopEvent:
    _START = 'on_start'

    _PAUSE = 'on_pause'
    _RESUME = 'on_resume'
    
    _STOP_NORMALLY = 'on_end'
    _STOP_CANCELED = 'on_stop'
    _STOP_HANDLER_ERROR = 'on_handler_exception'
    _STOP_CIRCUIT_ERROR = 'on_circuit_exception'

    _CLEANUP = 'on_closed'
    _LOOP_RESULT = 'on_result'

    _ALL_EVENTS = {
        _START, _PAUSE, _RESUME, _STOP_NORMALLY,
        _STOP_CANCELED, _STOP_HANDLER_ERROR, _STOP_CIRCUIT_ERROR,
        _CLEANUP, _LOOP_RESULT,
    }

    class _Interface(_LoopEvent):
        @property
        def START(_):
            return _START
        @property
        def PAUSE(_):
            return _PAUSE
        @property
        def RESUME(_):
            return _RESUME            
        @property
        def STOP_NORMALLY(_):
            return _STOP_NORMALLY
        @property
        def STOP_CANCELED(_):
            return _STOP_CANCELED
        @property
        def STOP_HANDLER_ERROR(_):
            return _STOP_HANDLER_ERROR
        @property
        def STOP_CIRCUIT_ERROR(_):
            return _STOP_CIRCUIT_ERROR
        @property
        def CLEANUP(_):
            return _CLEANUP
        @property
        def LOOP_RESULT(_):
            return _LOOP_RESULT
        
        @staticmethod
        def is_valid_event(name) -> bool:
            return name in _ALL_EVENTS
        @property
        def all_events(_) -> FrozenSet[str]:
            return frozenset(_ALL_EVENTS)
        
    return _Interface()


@runtime_checkable
class _State(Protocol):
    """
    Manages a three-state transition (LOAD → ACTIVE → TERMINATED), 
    with immutable tokens, current state tracking, and validation methods.
    """

    @property
    def LOAD(self) -> object: ...
    """State token: initial load state."""

    @property
    def ACTIVE(self) -> object: ...
    """State token: active state."""

    @property
    def TERMINATED(self) -> object: ...
    """State token: terminated state."""

    @property
    def current_state(self) -> object: ...
    """Current internal state."""

    @property
    def errors(self) -> 'StateError': ...
    """Error definitions for invalid state operations."""

    @staticmethod
    def maintain_state(state: object, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any: ...
    """Run `fn` if current state matches `state`, else raise."""

    @staticmethod
    def transit_state_with(to: object, fn: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> Any: ...
    """Transition to `to` state and optionally run `fn`."""

    @staticmethod
    def transit_state(to: object) -> Any: ...
    """Transition to `to` state without running a function."""


@runtime_checkable
class StateError(Protocol):
    """
    Protocol for state-related error definitions.
    """
    UnknownStateError: Type[Exception]
    """Raised for unknown or unsupported state."""

    InvalidStateError: Type[Exception]
    """Raised when current state is invalid for the operation."""

    TerminatedError: Type[Exception]
    """Raised when state is TERMINATED and operation is invalid."""


def _setup_state() -> _State:
    _LOAD = object()
    _ACTIVE = object()
    _TERMINATED = object()

    _ALL = (_LOAD, _ACTIVE, _TERMINATED)

    _state = _LOAD

    def _validate_state_value(state):
        if not any(state is s for s in _ALL):
            raise _StateError.UnknownStateError(
                f"Unknown or unsupported state value: {state}")
        
    def _require_state(expected):
        _validate_state_value(expected)
        if expected is not _state:
            err_log = f"State error: expected = {expected}, actual = {_state}"
            if _state is _TERMINATED:
                raise _StateError.TerminatedError(err_log)
            raise _StateError.InvalidStateError(err_log)
    
    class _StateError(_StateError):
        __slots__ = ()
        class UnknownStateError(Exception):
            pass
        class InvalidStateError(Exception):
            pass
        class TerminatedError(InvalidStateError):
            pass

    class _Interface(_State):
        __slots__ = ()
        @property
        def LOAD(_):
            return _LOAD
        @property
        def ACTIVE(_):
            return _ACTIVE
        @property
        def TERMINATED(_):
            return _TERMINATED

        @property
        def current_state(_):
            return _state
        
        @property
        def errors(_) -> _StateError:
            return _StateError
        
        @staticmethod
        def maintain_state(state, fn, *fn_args, **fn_kwargs):
            _require_state(state)
            return fn(*fn_args, **fn_kwargs)
        
        @staticmethod
        def transit_state_with(to, fn, *fn_args, **fn_kwargs):
            nonlocal _state
            _validate_state_value(to)
            to_active = _state is _LOAD and to is _ACTIVE
            to_terminal = _state is _ACTIVE and to is _TERMINATED
            if not (to_active or to_terminal):
                raise _StateError.InvalidStateError(
                    f"Invalid transition: {_state} → {to}")
            if fn:
                result = _State.maintain_state(
                    _state, fn, *fn_args, **fn_kwargs)
                _state = to
                return result
            else:
                return None
            
        @staticmethod
        def transit_state(to):
            return _State.transit_state_with(to, None)
    
    return _Interface()



@runtime_checkable
class StateObserver(Protocol):
    """
    Read-only observer of a three-state lifecycle (LOAD → ACTIVE → TERMINATED).

    Provides access to the immutable state tokens, current state, and error definitions
    without allowing transitions or modifications.
    """

    @property
    def LOAD(_) -> object: ...
    """State token: initial load state."""

    @property
    def ACTIVE(_) -> object: ...
    """State token: active state."""

    @property
    def TERMINATED(_) -> object: ...
    """State token: terminated state."""

    @property
    def state(_) -> object: ...
    """Current internal state."""

    @property
    def errors(_) -> 'StateError': ...
    """Error definitions for invalid state operations."""

def _setup_state_observer(state: _State) -> StateObserver:

    class _Interface(StateObserver):
        __slots__ = ()
        @property
        def LOAD(_):
            return state.LOAD
        @property
        def ACTIVE(_):
            return state.ACTIVE
        @property
        def TERMINATED(_):
            return state.TERMINATED

        @property
        def state(_):
            return state.current_state
        
        @property
        def errors(_) -> StateError:
            return state.errors
    
    return _Interface()



@runtime_checkable
class Context(Protocol):
    """
    Represents a user-defined context object passed to handlers and actions.
    """

@runtime_checkable
class EventHandler(Protocol):
    """
    Implementation to be executed for an event.
    """
    def __call__(_, ctx: Context) -> Any:
        """Execute with the given context."""

@runtime_checkable
class _EventHandleRegistry(Protocol):
    """
    Manages registration and retrieval of event handlers.

    After cleanup() is called, this instance is no longer valid,
    and further calls to its methods are not supported.
    """
    @staticmethod
    def get_all_handlers() -> Mapping[str, EventHandler]:
        """
        Return all registered event handlers as an immutable mapping.
        """
    
    @staticmethod
    def set_event_handler(event: str, handler: EventHandler) -> None:
        """
        Register a handler for the given event.
        Validates that the event is supported and registers the handler
        only when the current state is LOAD. Raises ValueError if the event is invalid.
        """
    
    @staticmethod
    def cleanup() -> None:
        """
        Clears all registered event handlers and releases internal state.
        After calling this, the instance should not be used.
        """


def _setup_event_handler_registry(ev: _LoopEvent, state: _State) -> _EventHandleRegistry:
    _event_handlers = {}

    class _EventHandlerRegistry(_EventHandleRegistry):
        @staticmethod
        def get_all_handlers():
            return MappingProxyType(_event_handlers)
        @staticmethod
        def set_event_handler(event, handler):
            if not ev.is_valid_event(event):
                raise ValueError(f"Event '{event}' is not defined")
            def add_phase(): _event_handlers[event] = handler
            state.maintain_state(state.LOAD, add_phase)
        @staticmethod
        def cleanup():
            nonlocal _event_handlers
            _event_handlers.clear()
            # break internal state after clearing
            _event_handlers = None

    return _EventHandlerRegistry()


@runtime_checkable
class Action(Protocol):
    """
    Executable within the circuit, takes a Context.
    Can be sync or async.
    """
    def __call__(_, ctx: Context) -> Any:
        """
        Executes the action within the circuit loop
        using the given context.
        """


@runtime_checkable
class _ActionRegistry(Protocol):
    """
    Registers and retrieves actions within the circuit.

    After cleanup() is called, this instance is no longer valid,
    and further calls to its methods are not supported.
    """

    @staticmethod
    def get_actions() -> Mapping[str, Tuple[Action, str, bool]]:
        """
        Return all registered actions as an immutable mapping.
        """

    @staticmethod
    def append_action(name: str, fn: Action, notify_reactor: bool) -> None:
        """
        Register an action with the given name, implementation, and notify_reactor flag.
        If notify_reactor is True, the reactor will be notified when the action is executed.
        """

    @staticmethod
    def build_action_namespace() -> Mapping[str, Action]:
        """
        Build a namespace mapping of (callable name → action) pairs,
        used to invoke actions by their assigned names.
        """
    
    @staticmethod
    def cleanup() -> None:
        """
        Clears all registered actions and releases internal state.
        After calling this, the instance should not be used further.
        """

def _setup_action_registry(state: _State) -> _ActionRegistry:

    ACTION_SUFFIX = '_action'
    MAX_ACTIONS = 26**3  # all 3-letter lowercase aliases
    
    # Requires Python 3.7+ for guaranteed insertion order
    _linear_actions_in_circuit = {} # tuple: (hadler, raw_name, notify_ctx)

    #generates a unique 3-letter alias for each action
    def _label_action_by_index():
        index = len(_linear_actions_in_circuit)
        if index >= MAX_ACTIONS:
            raise ValueError(
                f"Too many actions: supports up to {MAX_ACTIONS}, got {index}")
        
        result = ""
        for _ in range(3):
            result = string.ascii_lowercase[index % 26] + result
            index //= 26
            if index == 0:
                break
        result = result + ACTION_SUFFIX
        return result
    
    class _Interface(_ActionRegistry):
        __slots__ = ()
        @staticmethod
        def get_actions() -> Mapping[str, Tuple[Action, str, bool]]:
            return MappingProxyType(_linear_actions_in_circuit)
        @staticmethod
        def append_action(name, fn, notify_reactor) -> None:
            def add_action():
                label = _label_action_by_index()
                _linear_actions_in_circuit[label] = (fn, str(name), notify_reactor)
            state.maintain_state(state.LOAD, add_action)
        @staticmethod
        def build_action_namespace() -> Mapping[str, Action]:
            # l = lable, t = tuple(action func, raw_name, notify_ctx)
            return {l :t[0] for l, t in _linear_actions_in_circuit.items()}
        @staticmethod
        def cleanup():
            nonlocal _linear_actions_in_circuit
            _linear_actions_in_circuit.clear()
            # break internal state after clearing
            _linear_actions_in_circuit = None 
    
    return _Interface()

@runtime_checkable
class Reactor(Protocol):
    """
    Reacts to lifecycle points (including both events and actions) and may update the Context.
    """

    def __call__(_, next_proc: str) -> None:
        """
        Handle a lifecycle point, identified by the tag, and optionally update the Context.
        """

@runtime_checkable
class ReactorFactory(Protocol):
    """
    Creates a (Reactor, Context) pair for a given LoopControl.

    The Reactor handles lifecycle points (events and actions) 
    and may update the Context. The Context is passed to handlers and actions.

    Typically implemented as a closure that captures necessary state.
    """

    def __call__(_, control: '_LoopControl') -> Tuple[Reactor, Context]:
        """
        Produce a Reactor and its associated Context for the given control.
        """

@runtime_checkable
class _ReactorRegistry(Protocol):
    """
    Manages ReactorFactory instances for events and actions.

    Allows setting and retrieving separate ReactorFactory instances
    for event and action lifecycle points.

    After cleanup() is called, this instance is no longer valid,
    and further calls to its methods are not supported.
    """

    @staticmethod
    def set_event_reactor_factory(reactor_factory: ReactorFactory) -> None:
        """
        Set the ReactorFactory used to produce Reactor+Context for events.
        """

    @staticmethod
    def set_action_reactor_factory(reactor_factory: ReactorFactory) -> None:
        """
        Set the ReactorFactory used to produce Reactor+Context for actions.
        """
    
    @property
    def event_reactor_factory(_) -> ReactorFactory:
        """
        Get the current ReactorFactory for events.
        """
    
    @property
    def action_reactor_factory(_) -> ReactorFactory:
        """
        Get the current ReactorFactory for actions.
        """
    
    @staticmethod
    def cleanup() -> None:
        """
        Clears all internal ReactorFactory references and releases state.
        After calling this, the instance should not be used further.
        """

def _setup_reactor_registry(state: _State) -> _ReactorRegistry:

    def _EVENT_REACTOR_FACTORY(control):
        """
        Default factory producing a no-op reactor and using the control 
        as context for events.
        """
        def loop_reactor(next_proc: str):
            pass
        return loop_reactor, control

    def _ACTION_REACTOR_FACTORY(control):
        """
        Default factory producing a no-op reactor and reusing the event context 
        for actions.
        """
        def circuit_reactor(next_proc: str):
            pass
        return circuit_reactor, control.event_context

    _event_reactor_factory = _EVENT_REACTOR_FACTORY
    _action_reactor_factory = _ACTION_REACTOR_FACTORY

    class _Interface(_ReactorRegistry):
        __slots__ = ()
        @staticmethod
        def set_event_reactor_factory(reactor_factory):
            def fn():
                nonlocal _event_reactor_factory
                _event_reactor_factory = reactor_factory
            state.maintain_state(state.LOAD, fn)
        
        @staticmethod
        def set_action_reactor_factory(reactor_factory):
            def fn():
                nonlocal _action_reactor_factory
                _action_reactor_factory = reactor_factory
            state.maintain_state(state.LOAD, fn)
        
        @property
        def event_reactor_factory(_):
            return _event_reactor_factory
        
        @property
        def action_reactor_factory(_):
            return _action_reactor_factory
        
        @staticmethod
        def cleanup():
            nonlocal _event_reactor_factory, _action_reactor_factory
            _event_reactor_factory = None
            _action_reactor_factory = None

    return _Interface()


@runtime_checkable
class _LoopResult(Protocol):
    """
    Represents the overall result and errors of a loop after it finishes.
    If .loop_result is accessed before the loop finishes, it holds PENDING_RESULT.
    
    Once `cleanup()` is called, the internal state becomes undefined 
    and further access to properties is not supported.
    """

    @property
    def PENDING_RESULT(self) -> object:
        """Marker: result is still pending."""

    @property
    def NO_RESULT(self) -> object:
        """Marker: loop produced no result."""

    @staticmethod
    def set_loop_result(obj: Any) -> None:
        """Record the final result of the loop."""

    @staticmethod
    def set_last_process(proc_name: str) -> None:
        """Record the last process name of the loop."""

    @property
    def loop_result(_) -> Any:
        """Return the recorded final result."""
    
    @property
    def last_process(_) -> str:
        """Return the recoded last process name."""

    @staticmethod
    def set_circuit_error(e: Exception) -> None:
        """Record an error raised by the circuit."""

    @staticmethod
    def set_event_reactor_error(e: Exception) -> None:
        """Record an error raised by the event reactor."""

    @staticmethod
    def set_handler_error(e: Exception) -> None:
        """Record an error raised by a handler."""

    @staticmethod
    def set_internal_error(e: Exception) -> None:
        """Record an internal framework error."""

    @property
    def circuit_error(_) -> Exception:
        """Return the recorded circuit error if any."""

    @property
    def event_reactor_error(_) -> Exception:
        """Return the recorded event reactor error if any."""

    @property
    def handler_error(_) -> Exception:
        """Return the recorded handler error if any."""

    @property
    def internal_error(_) -> Exception:
        """Return the recorded internal error if any."""

    @staticmethod
    def cleanup() -> None:
        """Clear all recorded results and errors."""

def _setup_loop_result() -> _LoopResult:

    _PENDING_RESULT = object()
    _NO_RESULT = object()

    # not target of cleanup
    _loop_result = _PENDING_RESULT
    
    _last_proc_name:str = None

    _circuit_error = None
    _event_reactor_error = None
    _handler_error = None
    _internal_error = None

    class _LoopResult(_LoopResult):
        __slots__ = ()
        @property
        def PENDING_RESULT(_):
            return _PENDING_RESULT
        @property
        def NO_RESULT(_):
            return _NO_RESULT
        @staticmethod
        def set_last_process(proc_name: str) -> None:
            nonlocal _last_proc_name
            _last_proc_name = proc_name
        @staticmethod
        def set_loop_result(obj):
            nonlocal _loop_result
            _loop_result = obj
        @property
        def last_process(_):
            return _last_proc_name
        @property
        def loop_result(_):
            return _loop_result
        @staticmethod
        def set_circuit_error(e: Exception) -> None:
            nonlocal _circuit_error
            _circuit_error = e
        @staticmethod
        def set_event_reactor_error(e: Exception) -> None:
            nonlocal _event_reactor_error
            _event_reactor_error = e
        @staticmethod
        def set_handler_error(e: Exception) -> None:
            nonlocal _handler_error
            _handler_error = e
        @staticmethod
        def set_internal_error(e: Exception) -> None:
            nonlocal _internal_error
            _internal_error = e
        @property
        def circuit_error(_):
            return _circuit_error
        @property
        def event_reactor_error(_):
            return _event_reactor_error
        @property
        def handler_error(_):
            return _handler_error
        @property
        def internal_error(_):
            return _internal_error
        @staticmethod
        def cleanup():
            nonlocal _loop_result, _circuit_error, _event_reactor_error,\
                _handler_error, _internal_error
            # Break reference on cleanup; no further use expected.
            _loop_result = None
            _circuit_error = None
            _event_reactor_error = None
            _handler_error = None
            _internal_error = None
    
    return _LoopResult()


@runtime_checkable
class LoopResultReader(Protocol):
    """
    Read-only view of the overall result and errors of a loop after it finishes.
    This view allows accessing the recorded results and errors without allowing modification.

    The underlying LoopResult is expected to be cleaned up by the driver.
    Once `cleanup()` is called (which must be invoked when the loop is TERMINATED),
    the internal state becomes undefined, and further access to the properties of this reader is not supported.

    If .loop_result is accessed before the loop finishes, it holds PENDING_RESULT.
    """

    @property
    def PENDING_RESULT(self) -> object:
        """Marker: result is still pending."""

    @property
    def NO_RESULT(self) -> object:
        """Marker: loop produced no result."""
    
    @property
    def last_process(_) -> str:
        """Return the recoded last process name."""

    @property
    def loop_result(_) -> Any:
        """Return the recorded final result."""

    @property
    def circuit_error(_) -> Exception:
        """Return the recorded circuit error if any."""

    @property
    def event_reactor_error(_) -> Exception:
        """Return the recorded event reactor error if any."""

    @property
    def handler_error(_) -> Exception:
        """Return the recorded handler error if any."""

    @property
    def internal_error(_) -> Exception:
        """Return the recorded internal error if any."""

def _setup_loop_result_reader(state: _State, loop_result: _LoopResult) -> LoopResultReader:

    class _Interface(LoopResultReader):
        __slots__ = ()
        @property
        def PENDING_RESULT(_):
            return loop_result.PENDING_RESULT
        @property
        def NO_RESULT(_):
            return loop_result.NO_RESULT
        @property
        def last_process(_):
            return loop_result.last_process
        @property
        def loop_result(_):
            return loop_result.loop_result
        @property
        def circuit_error(_):
            return loop_result.circuit_error
        @property
        def event_reactor_error(_):
            return loop_result.event_reactor_error
        @property
        def handler_error(_):
            return loop_result.handler_error
        @property
        def internal_error(_):
            return loop_result.internal_error
        @staticmethod
        def cleanup() -> None:
            def call_cleanup():
                return loop_result.cleanup()
            state.maintain_state(state.TERMINATED, call_cleanup)
    
    return _Interface()

@runtime_checkable
class _StepSlot(Protocol):
    """
    Temporary slot for holding the result and process name of the most recent step
    (event or action) to pass into the next processing step.

    Once `cleanup()` is called, the internal state becomes undefined 
    and further access to properties is not supported.
    """
    @property
    def UNSET(self) -> object:
        """Marker object indicating an unset result."""

    @staticmethod
    def set_prev_result(proc_name: str, result: Any) -> None:
        """
        Record the result and process name of the most recent step.
        """

    @property
    def prev_proc(_) -> str:
        """
        Return the process name of the most recent recorded step.
        """

    @property
    def prev_result(_) -> Any:
        """
        Return the result of the most recent recorded step.
        """

    @staticmethod
    def cleanup() -> None:
        """
        Clear the recorded process name and result.
        """

def _setup_step_slot() -> _StepSlot:

    _UNSET = object()

    _prev_proc = '<unset>'
    _prev_result = _UNSET

    class _Interface(_StepSlot):
        __slots__ = ()
        @property
        def UNSET(_):
            return _UNSET
        @staticmethod
        def set_prev_result(tag: str, result: Any):
            nonlocal _prev_proc, _prev_result
            _prev_proc = tag
            _prev_result = result
        @property
        def prev_proc(_):
            return _prev_proc
        @property
        def prev_result(_):
            return _prev_result
        @staticmethod
        def cleanup() -> None:
            nonlocal _prev_proc, _prev_result
            _prev_proc = None
            _prev_result = None

    return _Interface()



@runtime_checkable
class _LoopInterrupt(Protocol):
    """
    Controls and monitors the loop’s interrupt state, enabling controlled pause and resume.

    The pause and resume flow is intentionally asymmetric:
    - `request_pause()` only marks the pause request and does not unblock the loop immediately.
      The loop remains running until `consume_pause_request()` is awaited, which clears the flag,
      switches to PAUSE mode, and fires the PAUSE event.
    - Conversely, `resume()` immediately signals a pending resume by setting the flag
      and unblocking any `wait_resume()` call. When `perform_resume_event()` is awaited,
      the flag is cleared, mode returns to RUNNING, and the RESUME event is fired.

    This design allows the loop to reach a safe point before pausing, but allows resume
    to be triggered instantly and asynchronously.
    """

    @property
    def RUNNING(_) -> object:
        """Marker object indicating the loop is in RUNNING mode."""

    @property
    def PAUSE(_) -> object:
        """Marker object indicating the loop is in PAUSE mode."""

    @property
    def current_mode(self) -> object:
        """Current mode of the loop: either RUNNING or PAUSE."""

    @property
    def pause_requested(self) -> bool:
        """True if a pause has been requested but not yet consumed."""

    @property
    def resume_event_scheduled(self) -> bool:
        """
        True if the loop has already resumed (`resume()` called and unblocked)
        but the RESUME event is still pending and will be fired by `perform_resume_event()`.
        """

    @staticmethod
    async def consume_pause_request(event_processor: Callable[[str], Awaitable[None]]) -> None:
        """
        Consume the pending pause request: clears the pause flag, switches to PAUSE mode,
        fires the PAUSE event via `event_processor`, and resets the resume wait state.
        """

    @staticmethod
    async def perform_resume_event(event_processor: Callable[[str], Awaitable[None]]) -> None:
        """
        Perform the scheduled RESUME event: clears the resume flag, switches to RUNNING mode,
        and fires the RESUME event via `event_processor`.
        """

    @staticmethod
    def request_pause() -> None:
        """
        Request that the loop pauses at its next safe point.
        Sets the pause flag but does not block the loop immediately.
        """

    @staticmethod
    def resume() -> None:
        """
        Immediately signal that the loop should resume.
        Sets the resume flag and unblocks `wait_resume()`.
        """

    @staticmethod
    async def wait_resume() -> None:
        """
        Await until a resume signal is issued via `resume()`.
        Typically awaited while the loop is paused.
        """



def _setup_loop_interrupt(ev: _LoopEvent) -> _LoopInterrupt:
    
    _RUNNING = object()
    _PAUSE = object()

    _mode: object = _RUNNING
    _event: asyncio.Event = asyncio.Event()
    _pause_requested: bool = False
    _resume_event_scheduled: bool = False
    
    class _Interface(_LoopInterrupt):
        __slots__ = ()
        @property
        def RUNNING(_):
            return _RUNNING
        @property
        def PAUSE(_):
            return _PAUSE
        @property
        def current_mode(_):
            return _mode
        @staticmethod
        async def consume_pause_request(event_processor):
            nonlocal _mode, _pause_requested
            _pause_requested = False
            await event_processor(ev.PAUSE)
            _event.clear()
            _mode = _PAUSE
        @staticmethod
        async def perform_resume_event(event_processor):
            nonlocal _mode, _resume_event_scheduled
            _resume_event_scheduled = False
            await event_processor(ev.RESUME)
            _mode = _RUNNING
        @staticmethod
        def request_pause():
            nonlocal _pause_requested
            _pause_requested = True
        @staticmethod
        def resume():
            nonlocal _resume_event_scheduled
            _resume_event_scheduled = True
            _event.set()
        @staticmethod
        async def wait_resume():
            await _event.wait()
        @property
        def pause_requested(_):
            return _pause_requested
        @property
        def resume_event_scheduled(_):
            return _resume_event_scheduled
    
    return _Interface()

@runtime_checkable
class LoopInterruptObserver(Protocol):
    """
    Read-only view of the loop’s interrupt state.

    Exposes the current mode (RUNNING or PAUSE) for inspection.
    Does not allow controlling or modifying the interrupt flow.
    """
    @property
    def RUNNING(_) -> object:
        """Marker object indicating the loop is in RUNNING mode."""

    @property
    def PAUSE(_) -> object:
        """Marker object indicating the loop is in PAUSE mode."""

    @property
    def mode(_) -> object:
        """Current mode of the loop: either RUNNING or PAUSE."""

def _setup_loop_interrupt_observer(loop_interrupt: _LoopInterrupt) -> LoopInterruptObserver:
    
    class _Interface(LoopInterruptObserver):
        __slots__ = ()
        @property
        def RUNNING(_):
            return loop_interrupt.RUNNING
        @property
        def PAUSE(_):
            return loop_interrupt.PAUSE
        @property
        def mode(_):
            return loop_interrupt.current_mode
    
    return _Interface()


@runtime_checkable
class LoopError(Protocol):
    """
    Protocol for loop-related error definitions.

    Defines standard exceptions raised at specific phases
    of the loop lifecycle.
    """

    EventReactorError: Type[Exception]
    """
    Raised when the event reactor fails. Does not include action reactor 
    failures.
    """

    EventHandlerError: Type[Exception]
    """Raised when the event handler fails. Does not include action failures."""

    CircuitError: Type[Exception]
    """
    Raised when the circuit execution fails.
    Includes failures in actions and action reactors.
    """

@runtime_checkable
class LoopSignal(Protocol):
    """
    Protocol for loop control signals.

    Defines exceptions used to signal control flow changes
    in the loop lifecycle.
    """

    Break: Type[Exception]
    """
    Raised to break the loop immediately.
    This is a control signal only and does not take any arguments.
    """

@runtime_checkable
class LoopException(Protocol):
    """
    Protocol for loop exception definitions.

    Provides access to loop-related error and signal classes.
    """

    @property
    def errors(_) -> LoopError:
        """
        Returns the error definitions used in the loop.
        """
    
    @property
    def signals(_) -> LoopSignal:
        """
        Returns the control signal definitions used in the loop.
        """

def _setup_loop_exception() -> LoopException:
    class _LoopError(LoopError):
        __slots__ = ()
        class EventReactorError(Exception):
            def __init__(self, proc_name: str, e: Exception):
                self.proc_name = proc_name
                self.orig_exception = e
                super().__init__(f"at {proc_name}: {e}")
        class EventHandlerError(Exception):
            def __init__(self, proc_name: str, e: Exception):
                self.proc_name = proc_name
                self.orig_exception = e
                super().__init__(f"at {proc_name}: {e}")

        class CircuitError(Exception):
            def __init__(self, e: Exception):
                self.orig_exception = e
                super().__init__(e)
    
    class _LoopSignal(LoopSignal):
        __slots__ = ()
        class Break(Exception):
            pass
    
    class _Interface(LoopException):
        __slots__ = ()
        @property
        def errors(_) -> LoopError:
            return _LoopError
        @property
        def signals(_) -> LoopSignal:
            return _LoopSignal
    
    return _Interface()



@runtime_checkable
class _TaskControl(Protocol):
    """
    Protocol for controlling a single task.

    Provides methods to start, stop, and check the running state
    of a managed task.
    """
    @staticmethod
    def start(
        fn: Callable[..., Any], *fn_args: Any, **fn_kwargs: Any
    ) -> Optional[asyncio.Task]:
        """
        Starts the task by executing the given function.  
        If it is synchronous, None is returned.  
        If it is awaitable, it is passed to asyncio.create_task(),  
        which normally returns a task or may raise an exception.
        """
    
    @property
    def is_running(_) -> bool:
        """
        Returns True if the task is currently running and not done.
        """
    
    @staticmethod
    def stop() -> None:
        """
        Stops the task by cancelling it if it is running.
        """

def _setup_task_control(state: _State) -> _TaskControl:

    _task:Optional[asyncio.Task] = None

    def _is_running():
        return _task is not None and not _task.done()

    class _Interface(_TaskControl):
        __slots__ = ()
        @staticmethod
        def start(fn, *fn_args, **fn_kwargs):

            def create_task():
                nonlocal _task
                result = fn(*fn_args, **fn_kwargs)
                if inspect.isawaitable(result):
                    # create_task validates result
                    _task = asyncio.create_task(result)
                    return _task
                return None
            
            return state.transit_state_with(state.ACTIVE, create_task)
        
        @property
        def is_running(_):
            return _is_running()
        
        @staticmethod
        def stop():
            def cancel_task():
                if _is_running():
                    _task.cancel()
            state.maintain_state(state.ACTIVE, cancel_task)
    
    return _Interface()




@runtime_checkable
class _CircuitCodeFactory(Protocol):
    """
    Generates Python source code for a circuit function as a string.
    The function is defined as async if any action is asynchronous or IRQ is enabled.
    """
    @staticmethod
    def generate_circuit_code(
        circuit_name: str,
        actions: Mapping[str, Tuple[Callable, str, Any]],
        irq: bool
    ) -> str:
        """
        Generate the source code of the circuit as a string.

        The generated circuit will be defined as an async function
        if at least one action is asynchronous, or if irq is enabled.

        Parameters:
            circuit_name: The name of the circuit function.
            actions: Mapping of action label → (callable, raw_name, notify_reactor).
            irq: Whether to include IRQ handling code.

        Returns:
            The generated source code as a string.
        """

def _setup_circuit_code_factory() -> _CircuitCodeFactory:

    _CIRCUIT_TEMPLATE = [
        "{async_}def {name}(reactor, context, step, irq, ev_proc, signal):",
        "    try:",
        "        while True:", # see: _BASE_INDENT
        "{actions}",
        "{irq}",
        "        except signal.Break:",
        "            pass",
    ]

    # Spaces used for indentation inside the while True: block
    _BASE_INDENT = ' ' * 12
    
    _ACTION_TEMPLATE = [
        "{indent}r = {await_}{action_label}(context)",
        "{indent}step.set_prev_result({action_raw_name}, r)",
        "",
    ]
    _ACTION_TEMPLATE_WITH_REACTOR = [
        "{indent}reactor({action_raw_name})",
        *_ACTION_TEMPLATE
    ]

    _IRQ_TEMPLATE = [
        "{indent}if irq.pause_requested:",
        "{indent}    await irq.consume_pause_result(ev_proc)",
        "{indent}if irq.resume_event_scheduled:",
        "{indent}    await irq.perform_resume_event(ev_proc)",
        "{indent}await irq.wait_resume()",
    ]

    class _Interface(_CircuitCodeFactory):
        __slots__ = ()
        @staticmethod
        def generate_circuit_code(
                circuit_name: str,
                actions: Mapping[str, Tuple[Callable, str, Any]],
                irq: bool
        ) -> str:
            
            irq_code = (
                "\n".join(_IRQ_TEMPLATE).format(indent = _BASE_INDENT) 
                if irq else 
                ""
            )
            
            async_circuit = False # cumulative flag
            action_buffer = []
            for label, unit in actions.items():
                action, raw_name, notify_reactor = unit
                template = (
                    "\n".join(_ACTION_TEMPLATE_WITH_REACTOR)
                    if notify_reactor else
                    "\n".join(_ACTION_TEMPLATE)
                )
                await_ = "await " if inspect.iscoroutinefunction(action) else ""
                async_circuit |= bool(await_)
                action_buffer.append(
                   template.format(
                        indent = _BASE_INDENT,
                        action_raw_name = raw_name,
                        await_ = await_,
                        action_label = label
                    )
                )

            _circuit_code = "\n".join(_CIRCUIT_TEMPLATE).format(
                async_ = "async " if irq or async_circuit else "",
                name = circuit_name,
                actions = "\n".join(action_buffer),
                irq = irq_code
            )
            return _circuit_code

    return _Interface()



@runtime_checkable
class LoopLog(Protocol):
    """
    Provides access to the loop’s logging configuration.

    Allows setting a role name (once) and replacing the logger instance.
    The current role and logger can also be retrieved.
    """

    @staticmethod
    def set_role(role: str) -> None:
        """
        Sets the role name for the loop.
        Can only be set once during the LOAD state.
        """
    
    @staticmethod
    def set_logger(logger: logging.Logger) -> None:
        """
        Sets or replaces the logger instance.
        Can be called multiple times to change the logger.
        """
    
    @property
    def role(self) -> str:
        """
        Returns the current role name.
        If no role was explicitly set, defaults to 'loop'.
        """
    
    @property
    def logger(self) -> logging.Logger:
        """
        Returns the current logger instance.
        """

def _setup_loop_log(state: _State) -> LoopLog:

    _logger = logging.getLogger(__name__)
    _role = None

    class _Interface(LoopLog):
        __slots__ = ()
        @staticmethod
        def set_role(role: str) -> None:
            if _role is not None:
                raise RuntimeError("role can only be set once")
            def set_role():
                nonlocal _role
                _role = role
            state.maintain_state(state.LOAD, set_role)
        @staticmethod
        def set_logger(logger: logging.Logger) -> None:
            nonlocal _logger
            _logger = logger
        @property
        def logger(_) -> logging.Logger:
            return _logger
        @property
        def role(_) -> str:
            return _role if _role is not None else "loop"
    
    return _Interface()


@runtime_checkable
class _LoopControl(Protocol):
    """
    Protocol representing the control interface for a single event loop.

    Provides access to the event and action state slots, exception definitions,
    and methods for setting up reactor contexts, processing events,
    and cleaning up internal state.

    All state is encapsulated in the returned interface instance.

    After cleanup() is called, this instance is no longer valid,
    and further calls to its methods are not supported
    """

    @property
    def exceptions(_) -> LoopException:
        """
        Returns the LoopException definitions associated with this loop control.
        Contains both error and signal definitions used during loop execution.
        """

    @property
    def event(_) -> _StepSlot:
        """
        Returns the StepSlot that holds the most recent event name and its result.
        """

    @property
    def action(_) -> _StepSlot:
        """
        Returns the StepSlot that holds the most recent action name and its result.
        """

    @staticmethod
    async def process_event(event: str) -> None:
        """
        Processes the given event by invoking its reactor and handler.
        The reactor is executed first, then the event handler, and
        their results or exceptions are recorded accordingly.
        """

    @staticmethod
    def setup_event_context() -> None:
        """
        Initializes the event reactor and its context.
        Must be called before processing events.
        """

    @staticmethod
    def setup_action_context() -> None:
        """
        Initializes the action reactor and its context.
        Must be called before processing actions.
        """

    @staticmethod
    def cleanup() -> None:
        """
        Cleans up internal state, releasing all references and clearing slots.
        After cleanup, the instance should not be used further.
        """


def _setup_loop_control(
        evh: _EventHandleRegistry, context: _ReactorRegistry,
        ev_step: _StepSlot, act_step: _StepSlot,
        exc: LoopException) -> _LoopControl:
    
    _event_reactor, _event_context = None, None
    _action_reactor, _action_context = None, None
    
    _all_event_handlers = dict(evh.get_all_handlers())

    class _Interface(_LoopControl):
        __slots__ = ()
        @property
        def exceptions(_):
            return exc
        @property
        def event(_):
            return ev_step
        @property
        def action(_):
            return act_step
        @staticmethod
        def setup_event_context() -> None:
            nonlocal _event_reactor, _event_context
            _event_reactor, _event_context =\
                context.event_reactor_factory()(_iface)
        @staticmethod
        def setup_action_context() -> None:
            nonlocal _action_reactor, _action_context
            _action_reactor, _action_context =\
                  context.action_reactor_factory()(_iface)
        @staticmethod
        async def process_event(event: str) -> None:
            handler = _all_event_handlers.get(event, None)
            if not handler:
                return
            # call event reactor
            try:
                reactor_tmp = _event_reactor(event)
            except Exception as e:
                raise exc.errors.EventReactorError(event, e)
            if inspect.isawaitable(reactor_tmp):
                try:
                    await reactor_tmp
                except Exception as e:
                    raise exc.errors.EventReactorError(event, e)
            # call event handler
            try:
                handler_tmp = handler(_event_context)
            except Exception as e:
                raise exc.errors.EventHandlerError(event, e)
            if inspect.isawaitable(handler_tmp):
                try:
                    result = await handler_tmp
                except Exception as e:
                    raise exc.errors.EventHandlerError(event, e)
            else:
                result = handler_tmp
            ev_step.set_prev_result(event, result)

        @staticmethod
        def cleanup() -> None:
            nonlocal _event_reactor, _event_context,\
                _action_reactor, _action_context,\
                ev_step, act_step,\
                _all_event_handlers, exc,\
                _iface
            
            ev_step.cleanup()
            act_step.cleanup()
            _all_event_handlers.clear()

            # break internal state after clearing
            _event_reactor, _event_context = None, None
            _action_reactor, _action_context = None, None
            _all_event_handlers = None
            exc = None
            ev_step = None
            act_step = None
            _iface = None
    
    _iface = _Interface()

    return _iface

@runtime_checkable
class LoopEngineHandle(Protocol):
    """
    Driver-facing handle for managing and observing the loop engine.

    Provides methods to start, stop, and observe the loop lifecycle,
    including registering actions and handlers, generating circuit code,
    and monitoring state.

    Exposes only the intended public API. Does not expose internal state or control flow.
    """

    @property
    def log(self) -> LoopLog: ...
    """Access to loop logger and role information."""

    @staticmethod
    def set_on_start(fn: EventHandler) -> None: ...
    """Register handler for loop start event."""

    @staticmethod
    def set_on_end(fn: EventHandler) -> None: ...
    """Register handler for loop end event."""

    @staticmethod
    def set_on_stop(fn: EventHandler) -> None: ...
    """Register handler for loop stop (canceled) event."""

    @staticmethod
    def set_on_closed(fn: EventHandler) -> None: ...
    """Register handler for loop cleanup event."""

    @staticmethod
    def set_on_result(fn: EventHandler) -> None: ...
    """Register handler for loop result event."""

    @staticmethod
    def set_on_pause(fn: EventHandler) -> None: ...
    """Register handler for loop pause event."""

    @staticmethod
    def set_on_resume(fn: EventHandler) -> None: ...
    """Register handler for loop resume event."""

    @staticmethod
    def generate_circuit_code(name: str, irq: bool) -> str: ...
    """Generate source code for the circuit function."""

    @staticmethod
    def start() -> None: ...
    """Start loop engine with pre-defined circuit."""

    @staticmethod
    def start_with_compile(irq: bool) -> None: ...
    """Compile and start loop engine with generated circuit."""

    @property
    def stop(self) -> Callable[[], None]: ...
    """Stop the loop task if running."""

    @property
    def task_is_running(self) -> bool: ...
    """True if the loop task is currently running."""

    @property
    def pause(self) -> Callable[[], None]: ...
    """Request loop pause at next safe point."""

    @property
    def resume(self) -> Callable[[], None]: ...
    """Request immediate loop resume."""

    @property
    def append_action(self) -> Callable[..., None]: ...
    """Register an action to the circuit."""

    @property
    def set_event_reactor_factory(self) -> Callable[..., None]: ...
    """Set factory for event reactor and context."""

    @property
    def set_action_reactor_factory(self) -> Callable[..., None]: ...
    """Set factory for action reactor and context."""

    @property
    def state_observer(self) -> StateObserver: ...
    """Read-only view of the current state (LOAD/ACTIVE/TERMINATED)."""

    @property
    def running_observer(self) -> LoopInterruptObserver: ...
    """Read-only view of the current run/pause mode."""

    @property
    def loop_result(self) -> LoopResultReader: ...
    """Read-only view of the final result and errors."""

def make_loop_engine_handle(static_circuit = None) -> LoopEngineHandle:

    def _compile(circuit_name, circuit_code: str, action_ns: Mapping):
        namespace = {
            "__builtins__" : {},
            "Break": _loop_control.exceptions.signals.Break,
            **action_ns,
        }
        dst = {}
        exec(circuit_code, namespace, dst)
        _compiled_func = dst[circuit_name]
        return _compiled_func
    
    async def _loop_engine(
            log: LoopLog, state: _State,
            circuit, ev: _LoopEvent, control: _LoopControl,
            res: _LoopResult) -> None:
        try:
            log.logger.info(f"[{log.role}] Loop start")
            errors = control.exceptions.errors
            control.setup_event_context()
            try:
                await control.process_event(ev.START)
                control.setup_action_context()
                try:
                    circuit_tmp = circuit(control)
                except Exception as e:
                    raise errors.CircuitError(e)
                if inspect.isawaitable(circuit_tmp):
                    try:
                        await circuit_tmp
                    except Exception as e:
                        raise errors.CircuitError(e)
                await control.process_event(ev.STOP_NORMALLY)
            except asyncio.CancelledError as e:
                log.logger.info(f"[{log.role}] Loop was cancelled")
                await control.process_event(ev.STOP_CANCELED)
            finally:
                await control.process_event(ev.CLEANUP)
                await control.process_event(ev.LOOP_RESULT)
                res.set_loop_result(control.event.prev_result)
        except errors.CircuitError as e:
            # Exceptions thrown by action-reactor and action are included here.
            res.set_circuit_error(e)
            raise
        except errors.EventReactorError as e:
            res.set_event_reactor_error(e)
            raise
        except errors.EventHandlerError as e:
            res.set_handler_error(e)
            raise
        except Exception as e:
            log.logger.critical(f"[{log.role}] Internal error: {e.__class__.__name__}")
            res.set_internal_error(e)
            raise
        finally:
            res.set_last_process(_ev_step.prev_proc)
            state.transit_state(_state.TERMINATED)

            # Do not call res.cleanup() in here
            control.cleanup()
            circuit = None
            ev = None
            control = None
            res = None
    
    def _start_loop_engine(circuit_func):
        return _task_control.start(
            _loop_engine,
            circuit_func,
            _state,
            _log,
            _event,
            _loop_control,
            _loop_res)

    _event = _setup_loop_event()

    _state = _setup_state()
    _state_observer = _setup_state_observer(_state)
    
    _evh_registry = _setup_event_handler_registry(_event, _state)
    _act_registry = _setup_action_registry(_state)
    _react_registry = _setup_reactor_registry(_state)
    
    _ev_step = _setup_step_slot()
    _act_step = _setup_step_slot()
    
    _irq = _setup_loop_interrupt(_event)
    _running_observer = _setup_loop_interrupt_observer(_irq)

    _exc = _setup_loop_exception()
    _task_control = _setup_task_control(_state)
    
    _circ_code_factory = _setup_circuit_code_factory()
    
    _log = _setup_loop_log(_state)

    _loop_control = _setup_loop_control(
        evh = _evh_registry,
        context = _react_registry,
        ev_step = _ev_step,
        act_step = _act_step,
        exc = _exc
    )

    _loop_res = _setup_loop_result()
    _loop_res_reader = _setup_loop_result_reader(_state, _loop_res)


    class _Interface(LoopEngineHandle):
        __slots__ = ()
        @property
        def log(_):
            return _log
        
        @staticmethod
        def set_on_start(fn):
            _evh_registry.set_event_handler('on_start', fn)
        @staticmethod
        def set_on_end(fn):
            _evh_registry.set_event_handler('on_end', fn)
        @staticmethod
        def set_on_stop(fn):
            _evh_registry.set_event_handler('on_stop', fn)
        @staticmethod
        def set_on_closed(fn):
            _evh_registry.set_event_handler('on_closed', fn)
        @staticmethod
        def set_on_result(fn):
            _evh_registry.set_event_handler('on_result', fn)
        @staticmethod
        def set_on_pause(fn):
            _evh_registry.set_event_handler('on_pause', fn)
        @staticmethod
        def set_on_resume(fn):
            _evh_registry.set_event_handler('on_resume', fn)
        
        @staticmethod
        def generate_circuit_code(name: str, irq: bool):
            return _circ_code_factory.generate_circuit_code(
                name,
                _act_registry.build_action_namespace(),
                irq
            )
        
        @staticmethod
        def start():
            if not static_circuit:
                raise RuntimeError("XXX")
            return _start_loop_engine(static_circuit)
        @staticmethod
        def start_with_compile(irq: bool):
            circuit_name = "_generated_circuit"
            return _start_loop_engine(
                _compile(
                    circuit_name,
                    _Interface.generate_circuit_code(
                        circuit_name, irq
                    ),
                    _act_registry.build_action_namespace()
                )
            )
        @property
        def stop(_):
            return _task_control.stop
        @property
        def task_is_running(_):
            return _task_control.is_running
        @property
        def pause(_):
            return _irq.request_pause
        @property
        def resume(_):
            return _irq.resume
        
        @property
        def append_action(_):
            return _act_registry.append_action
        
        @property
        def set_event_reactor_factory(_):
            return _react_registry.set_event_reactor_factory
        @property
        def set_action_reactor_factory(_):
            return _react_registry.set_action_reactor_factory
        
        @property
        def state_observer(_) -> StateObserver:
            return _state_observer
        
        @property
        def running_observer(_) -> LoopInterruptObserver:
            return _running_observer

        @property
        def loop_result(_) -> LoopResultReader:
            return _loop_res_reader

    return _Interface()

