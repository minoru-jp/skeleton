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

from typing import Awaitable, Optional, Protocol, Callable, Mapping, Tuple, Any, runtime_checkable,Type

from internal import *

@runtime_checkable
class StateError(Protocol):
    """Protocol for state-related error definitions."""

    UnknownStateError: Type[Exception]
    """Raised for unknown or unsupported state."""

    InvalidStateError: Type[Exception]
    """Raised when current state is invalid for the operation."""

    TerminatedError: Type[Exception]
    """Raised when state is TERMINATED and operation is invalid."""


@runtime_checkable
class StateObserver(Protocol):
    """
    Read-only observer of a three-state lifecycle (LOAD → ACTIVE → TERMINATED).

    Provides access to the immutable state tokens, current state, and error definitions
    without allowing transitions or modifications.
    """

    @property
    def LOAD(_) -> object:
        """State token: initial load state."""
        ...

    @property
    def ACTIVE(_) -> object:
        """State token: active state."""
        ...

    @property
    def TERMINATED(_) -> object:
        """State token: terminated state."""
        ...

    @property
    def state(_) -> object:
        """Current internal state."""
        ...

    @property
    def errors(_) -> 'StateError':
        """Error definitions for invalid state operations."""
        ...



def _setup_state_observer(state: State) -> StateObserver:

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
        ...


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
        ...

@runtime_checkable
class Reactor(Protocol):
    """
    Reacts to lifecycle points (including both events and actions) and may update the Context.
    """

    def __call__(_, next_proc: str) -> Optional[Awaitable[None]]:
        """
        Handle a lifecycle point, identified by the tag, and optionally update the Context.
        """
        ...


@runtime_checkable
class ReactorFactory(Protocol):
    """
    Creates a (Reactor, Context) pair for a given LoopControl.

    The Reactor handles lifecycle points (events and actions) 
    and may update the Context. The Context is passed to handlers and actions.

    Typically implemented as a closure that captures necessary state.
    """

    def __call__(_, control: 'LoopControl') -> Tuple[Reactor, Context]:
        """
        Produce a Reactor and its associated Context for the given control.
        """
        ...


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
        ...

    @property
    def NO_RESULT(self) -> object:
        """Marker: loop produced no result."""
        ...
    
    @property
    def last_process(_) -> str:
        """Return the recoded last process name."""
        ...

    @property
    def loop_result(_) -> Any:
        """Return the recorded final result."""
        ...

    @property
    def circuit_error(_) -> Exception:
        """Return the recorded circuit error if any."""
        ...

    @property
    def event_reactor_error(_) -> Exception:
        """Return the recorded event reactor error if any."""
        ...

    @property
    def handler_error(_) -> Exception:
        """Return the recorded handler error if any."""
        ...

    @property
    def internal_error(_) -> Exception:
        """Return the recorded internal error if any."""
        ...


def _setup_loop_result_reader(state: State, loop_result: LoopResult) -> LoopResultReader:

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
class LoopInterruptObserver(Protocol):
    """
    Read-only view of the loop’s interrupt state.

    Exposes the current mode (RUNNING or PAUSE) for inspection.
    Does not allow controlling or modifying the interrupt flow.
    """
    @property
    def RUNNING(_) -> object:
        """Marker object indicating the loop is in RUNNING mode."""
        ...

    @property
    def PAUSE(_) -> object:
        """Marker object indicating the loop is in PAUSE mode."""
        ...

    @property
    def mode(_) -> object:
        """Current mode of the loop: either RUNNING or PAUSE."""
        ...


def _setup_loop_interrupt_observer(loop_interrupt: LoopInterrupt) -> LoopInterruptObserver:
    
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
    def errors(_) -> Type[LoopError]:
        """
        Returns the error definitions used in the loop.
        """
        ...
    
    @property
    def signals(_) -> Type[LoopSignal]:
        """
        Returns the control signal definitions used in the loop.
        """
        ...

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
        def errors(_) -> Type[LoopError]:
            return _LoopError
        @property
        def signals(_) -> Type[LoopSignal]:
            return _LoopSignal
    
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
        ...
    
    @staticmethod
    def set_logger(logger: logging.Logger) -> None:
        """
        Sets or replaces the logger instance.
        Can be called multiple times to change the logger.
        """
        ...
    
    @property
    def role(self) -> str:
        """
        Returns the current role name.
        If no role was explicitly set, defaults to 'loop'.
        """
        ...
    
    @property
    def logger(self) -> logging.Logger:
        """
        Returns the current logger instance.
        """
        ...

def _setup_loop_log(state: State) -> LoopLog:

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
class LoopEngineHandle(Protocol):
    """
    Driver-facing handle for managing and observing the loop engine.

    Provides methods to start, stop, and observe the loop lifecycle,
    including registering actions and handlers, generating circuit code,
    and monitoring state.

    Exposes only the intended public API. Does not expose internal state or control flow.
    """

    @property
    def log(self) -> LoopLog:
        """Access to loop logger and role information."""
        ...

    @staticmethod
    def set_on_start(fn: EventHandler) -> None:
        """Register handler for loop start event."""
        ...

    @staticmethod
    def set_on_end(fn: EventHandler) -> None:
        """Register handler for loop end event."""
        ...

    @staticmethod
    def set_on_stop(fn: EventHandler) -> None:
        """Register handler for loop stop (canceled) event."""
        ...

    @staticmethod
    def set_on_closed(fn: EventHandler) -> None:
        """Register handler for loop cleanup event."""
        ...

    @staticmethod
    def set_on_result(fn: EventHandler) -> None:
        """Register handler for loop result event."""
        ...

    @staticmethod
    def set_on_pause(fn: EventHandler) -> None:
        """Register handler for loop pause event."""
        ...

    @staticmethod
    def set_on_resume(fn: EventHandler) -> None:
        """Register handler for loop resume event."""
        ...

    @staticmethod
    def generate_circuit_code(name: str, irq: bool) -> str:
        """Generate source code for the circuit function."""
        ...

    @staticmethod
    def start() -> None:
        """Start loop engine with pre-defined circuit."""
        ...

    @staticmethod
    def start_with_compile(irq: bool) -> None:
        """Compile and start loop engine with generated circuit."""
        ...

    @property
    def stop(self) -> Callable[[], None]:
        """Stop the loop task if running."""
        ...

    @property
    def task_is_running(self) -> bool:
        """True if the loop task is currently running."""
        ...

    @property
    def pause(self) -> Callable[[], None]:
        """Request loop pause at next safe point."""
        ...

    @property
    def resume(self) -> Callable[[], None]:
        """Request immediate loop resume."""
        ...

    @property
    def append_action(self) -> Callable[..., None]:
        """Register an action to the circuit."""
        ...

    @property
    def set_event_reactor_factory(self) -> Callable[..., None]:
        """Set factory for event reactor and context."""
        ...

    @property
    def set_action_reactor_factory(self) -> Callable[..., None]:
        """Set factory for action reactor and context."""
        ...

    @property
    def state_observer(self) -> StateObserver:
        """Read-only view of the current state (LOAD/ACTIVE/TERMINATED)."""
        ...

    @property
    def running_observer(self) -> LoopInterruptObserver:
        """Read-only view of the current run/pause mode."""
        ...

    @property
    def loop_result(self) -> LoopResultReader:
        """Read-only view of the final result and errors."""
        ...

    
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
            log: LoopLog, state: State,
            circuit, ev: LoopEvent, control: LoopControl,
            res: LoopResult) -> None:
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
            ev = None # type: ignore
            control = None # type: ignore
            res = None # type: ignore
    
    def _start_loop_engine(circuit_func):
        return _task_control.start(
            _loop_engine,
            circuit_func,
            _state,
            _log,
            _event,
            _loop_control,
            _loop_res)

    _event = setup_loop_event()

    _state = setup_state()
    _state_observer = _setup_state_observer(_state)
    
    _evh_registry = setup_event_handler_registry(_event, _state)
    _act_registry = setup_action_registry(_state)
    _react_registry = setup_reactor_registry(_state)
    
    _ev_step = setup_step_slot()
    _act_step = setup_step_slot()
    
    _irq = setup_loop_interrupt(_event)
    _running_observer = _setup_loop_interrupt_observer(_irq)

    _exc = _setup_loop_exception()
    _task_control = setup_task_control(_state)
    
    _circ_code_factory = setup_circuit_code_factory()
    
    _log = _setup_loop_log(_state)

    _loop_control = setup_loop_control(
        evh = _evh_registry,
        context = _react_registry,
        ev_step = _ev_step,
        act_step = _act_step,
        exc = _exc
    )

    _loop_res = setup_loop_result()
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

