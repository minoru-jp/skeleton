


import asyncio
import inspect
import string
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Coroutine, FrozenSet, Mapping, Optional, Protocol, Tuple, runtime_checkable, TYPE_CHECKING

from loop_engine import EventHandler

if TYPE_CHECKING:
    from loop_engine import *


@runtime_checkable
class LoopEvent(Protocol):
    """
    Protocol for standard loop lifecycle events and validation.
    """

    @property
    def START(_) -> str: 
        """Event name for loop start."""
        ...
    @property
    def PAUSE(_) -> str: 
        """Event name for loop pause."""
        ...
    @property
    def RESUME(_) -> str: 
        """Event name for loop resume."""
        ...
    @property
    def STOP_NORMALLY(_) -> str: 
        """Event name for normal loop stop."""
        ...
    @property
    def STOP_CANCELED(_) -> str: 
        """Event name for canceled loop stop."""
        ...
    @property
    def STOP_HANDLER_ERROR(_) -> str: 
        """Event name when a event handler raises an error."""
        ...
    @property
    def STOP_CIRCUIT_ERROR(_) -> str: 
        """Event name when a circuit raises an error."""
        ...
    @property
    def CLEANUP(_) -> str: 
        """Event name for loop cleanup."""
        ...
    @property
    def LOOP_RESULT(_) -> str: 
        """Event name for final loop result."""
        ...

    @staticmethod
    def is_valid_event(name: str) -> bool: 
        """Return True if the given name is a defined event."""
        ...
    @property
    def all_events(_) -> FrozenSet[str]: 
        """Return all defined event names as a frozen set."""
        ...


def setup_loop_event() -> LoopEvent:
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

    class _Interface(LoopEvent):
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
class State(Protocol):
    """
    Manages a three-state transition (LOAD → ACTIVE → TERMINATED), 
    with immutable tokens, current state tracking, and validation methods.
    """

    @property
    def LOAD(self) -> object:
        """State token: initial load state."""
        ...


    @property
    def ACTIVE(self) -> object:
        """State token: active state."""
        ...

    @property
    def TERMINATED(self) -> object:
        """State token: terminated state."""
        ...

    @property
    def current_state(self) -> object:
        """Current internal state."""
        ...

    @property
    def errors(self) -> 'StateError':
        """Error definitions for invalid state operations."""
        ...

    @staticmethod
    def maintain_state(state: object, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run `fn` if current state matches `state`, else raise."""
        ...

    @staticmethod
    def transit_state_with(to: object, fn: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> Any:
        """Transition to `to` state and optionally run `fn`."""
        ...

    @staticmethod
    def transit_state(to: object) -> Any:
        """Transition to `to` state without running a function."""
        ...

def setup_state() -> State:
    _LOAD = object()
    _ACTIVE = object()
    _TERMINATED = object()

    _ALL = (_LOAD, _ACTIVE, _TERMINATED)

    _state = _LOAD

    def _validate_state_value(state):
        if not any(state is s for s in _ALL):
            raise _errors.UnknownStateError(
                f"Unknown or unsupported state value: {state}")
        
    def _require_state(expected):
        _validate_state_value(expected)
        if expected is not _state:
            err_log = f"State error: expected = {expected}, actual = {_state}"
            if _state is _TERMINATED:
                raise _errors.TerminatedError(err_log)
            raise _errors.InvalidStateError(err_log)
    
    class _StateError(StateError):
        __slots__ = ()
        class UnknownStateError(Exception):
            pass
        class InvalidStateError(Exception):
            pass
        class TerminatedError(InvalidStateError):
            pass
    
    _errors = _StateError()

    class _Interface(State):
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
        def errors(_) -> StateError:
            return _errors
        
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
                raise StateError.InvalidStateError(
                    f"Invalid transition: {_state} → {to}")
            if fn:
                result = iface.maintain_state(
                    _state, fn, *fn_args, **fn_kwargs)
                _state = to
                return result
            else:
                return None
            
        @staticmethod
        def transit_state(to):
            return iface.transit_state_with(to, None)
    
    iface = _Interface()

    return iface




@runtime_checkable
class EventHandleRegistry(Protocol):
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
        ...
    
    @staticmethod
    def set_event_handler(event: str, handler: EventHandler) -> None:
        """
        Register a handler for the given event.
        Validates that the event is supported and registers the handler
        only when the current state is LOAD. Raises ValueError if the event is invalid.
        """
        ...
    
    @staticmethod
    def cleanup() -> None:
        """
        Clears all registered event handlers and releases internal state.
        After calling this, the instance should not be used.
        """
        ...

def setup_event_handler_registry(ev: LoopEvent, state: State) -> EventHandleRegistry:
    _event_handlers:dict  = {}

    class _EventHandlerRegistry(EventHandleRegistry):
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
            _event_handlers = None # type: ignore

    return _EventHandlerRegistry()





@runtime_checkable
class _ActionRegistry(Protocol):
    """
    Registers and retrieves actions within the circuit.

    After cleanup() is called, this instance is no longer valid,
    and further calls to its methods are not supported.
    """

    @staticmethod
    def get_actions() -> Mapping[str, Tuple['Action', str, bool]]:
        """
        Return all registered actions as an immutable mapping.
        """
        ...

    @staticmethod
    def append_action(name: str, fn: 'Action', notify_reactor: bool) -> None:
        """
        Register an action with the given name, implementation, and notify_reactor flag.
        If notify_reactor is True, the reactor will be notified when the action is executed.
        """
        ...

    @staticmethod
    def build_action_namespace() -> Mapping[str, 'Action']:
        """
        Build a namespace mapping of (callable name → action) pairs,
        used to invoke actions by their assigned names.
        """
        ...
    
    @staticmethod
    def cleanup() -> None:
        """
        Clears all registered actions and releases internal state.
        After calling this, the instance should not be used further.
        """
        ...

def setup_action_registry(state: State) -> _ActionRegistry:

    ACTION_SUFFIX = '_action'
    MAX_ACTIONS = 26**3  # all 3-letter lowercase aliases
    
    # Requires Python 3.7+ for guaranteed insertion order
    _linear_actions_in_circuit:dict = {} # tuple: (hadler, raw_name, notify_ctx)

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
        def get_actions() -> Mapping[str, Tuple['Action', str, bool]]:
            return MappingProxyType(_linear_actions_in_circuit)
        @staticmethod
        def append_action(name, fn, notify_reactor) -> None:
            def add_action():
                label = _label_action_by_index()
                _linear_actions_in_circuit[label] = (fn, str(name), notify_reactor)
            state.maintain_state(state.LOAD, add_action)
        @staticmethod
        def build_action_namespace() -> Mapping[str, 'Action']:
            # l = lable, t = tuple(action func, raw_name, notify_ctx)
            return {l :t[0] for l, t in _linear_actions_in_circuit.items()}
        @staticmethod
        def cleanup():
            nonlocal _linear_actions_in_circuit
            _linear_actions_in_circuit.clear()
            # break internal state after clearing
            _linear_actions_in_circuit = None # type: ignore
    
    return _Interface()




@runtime_checkable
class ReactorRegistry(Protocol):
    """
    Manages ReactorFactory instances for events and actions.

    Allows setting and retrieving separate ReactorFactory instances
    for event and action lifecycle points.

    After cleanup() is called, this instance is no longer valid,
    and further calls to its methods are not supported.
    """

    @staticmethod
    def set_event_reactor_factory(reactor_factory: 'ReactorFactory') -> None:
        """
        Set the ReactorFactory used to produce Reactor+Context for events.
        """
        ...

    @staticmethod
    def set_action_reactor_factory(reactor_factory: 'ReactorFactory') -> None:
        """
        Set the ReactorFactory used to produce Reactor+Context for actions.
        """
        ...
    
    @property
    def event_reactor_factory(_) -> 'ReactorFactory':
        """
        Get the current ReactorFactory for events.
        """
        ...
    
    @property
    def action_reactor_factory(_) -> 'ReactorFactory':
        """
        Get the current ReactorFactory for actions.
        """
        ...
    
    @staticmethod
    def cleanup() -> None:
        """
        Clears all internal ReactorFactory references and releases state.
        After calling this, the instance should not be used further.
        """
        ...

def setup_reactor_registry(state: State) -> ReactorRegistry:

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

    _event_reactor_factory: ReactorFactory = _EVENT_REACTOR_FACTORY
    _action_reactor_factory: ReactorFactory = _ACTION_REACTOR_FACTORY

    class _Interface(ReactorRegistry):
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
            _event_reactor_factory = None # type: ignore
            _action_reactor_factory = None # type: ignore

    return _Interface()



@runtime_checkable
class LoopResult(Protocol):
    """
    Represents the overall result and errors of a loop after it finishes.
    If .loop_result is accessed before the loop finishes, it holds PENDING_RESULT.
    
    Once `cleanup()` is called, the internal state becomes undefined 
    and further access to properties is not supported.
    """

    @property
    def PENDING_RESULT(self) -> object:
        """Marker: result is still pending."""
        ...

    @property
    def NO_RESULT(self) -> object:
        """Marker: loop produced no result."""
        ...

    @staticmethod
    def set_loop_result(obj: Any) -> None:
        """Record the final result of the loop."""
        ...

    @staticmethod
    def set_last_process(proc_name: str) -> None:
        """Record the last process name of the loop."""
        ...

    @property
    def loop_result(_) -> Any:
        """Return the recorded final result."""
        ...
    
    @property
    def last_process(_) -> str:
        """Return the recoded last process name."""
        ...

    @staticmethod
    def set_circuit_error(e: Exception) -> None:
        """Record an error raised by the circuit."""
        ...

    @staticmethod
    def set_event_reactor_error(e: Exception) -> None:
        """Record an error raised by the event reactor."""
        ...

    @staticmethod
    def set_handler_error(e: Exception) -> None:
        """Record an error raised by a handler."""
        ...

    @staticmethod
    def set_internal_error(e: Exception) -> None:
        """Record an internal framework error."""
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

    @staticmethod
    def cleanup() -> None:
        """Clear all recorded results and errors."""
        ...

def setup_loop_result() -> LoopResult:

    _PENDING_RESULT = object()
    _NO_RESULT = object()

    # not target of cleanup
    _loop_result = _PENDING_RESULT
    
    _last_proc_name:Optional[str] = None

    _circuit_error = None
    _event_reactor_error = None
    _handler_error = None
    _internal_error = None

    class _LoopResult(LoopResult):
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
class StepSlot(Protocol):
    """
    Temporary slot for holding the result and process name of the most recent step
    (event or action) to pass into the next processing step.

    Once `cleanup()` is called, the internal state becomes undefined 
    and further access to properties is not supported.
    """
    @property
    def UNSET(self) -> object:
        """Marker object indicating an unset result."""
        ...

    @staticmethod
    def set_prev_result(proc_name: str, result: Any) -> None:
        """
        Record the result and process name of the most recent step.
        """
        ...

    @property
    def prev_proc(_) -> str:
        """
        Return the process name of the most recent recorded step.
        """
        ...

    @property
    def prev_result(_) -> Any:
        """
        Return the result of the most recent recorded step.
        """
        ...

    @staticmethod
    def cleanup() -> None:
        """
        Clear the recorded process name and result.
        """
        ...

def setup_step_slot() -> StepSlot:

    _UNSET = object()

    _prev_proc = '<unset>'
    _prev_result = _UNSET

    class _Interface(StepSlot):
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
class LoopInterrupt(Protocol):
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
        ...

    @property
    def PAUSE(_) -> object:
        """Marker object indicating the loop is in PAUSE mode."""
        ...

    @property
    def current_mode(self) -> object:
        """Current mode of the loop: either RUNNING or PAUSE."""
        ...

    @property
    def pause_requested(self) -> bool:
        """True if a pause has been requested but not yet consumed."""
        ...

    @property
    def resume_event_scheduled(self) -> bool:
        """
        True if the loop has already resumed (`resume()` called and unblocked)
        but the RESUME event is still pending and will be fired by `perform_resume_event()`.
        """
        ...

    @staticmethod
    async def consume_pause_request(event_processor: Callable[[str], Awaitable[None]]) -> None:
        """
        Consume the pending pause request: clears the pause flag, switches to PAUSE mode,
        fires the PAUSE event via `event_processor`, and resets the resume wait state.
        """
        ...

    @staticmethod
    async def perform_resume_event(event_processor: Callable[[str], Awaitable[None]]) -> None:
        """
        Perform the scheduled RESUME event: clears the resume flag, switches to RUNNING mode,
        and fires the RESUME event via `event_processor`.
        """
        ...

    @staticmethod
    def request_pause() -> None:
        """
        Request that the loop pauses at its next safe point.
        Sets the pause flag but does not block the loop immediately.
        """
        ...

    @staticmethod
    def resume() -> None:
        """
        Immediately signal that the loop should resume.
        Sets the resume flag and unblocks `wait_resume()`.
        """
        ...

    @staticmethod
    async def wait_resume() -> None:
        """
        Await until a resume signal is issued via `resume()`.
        Typically awaited while the loop is paused.
        """
        ...

def setup_loop_interrupt(ev: LoopEvent) -> LoopInterrupt:
    
    _RUNNING = object()
    _PAUSE = object()

    _mode: object = _RUNNING
    _event: asyncio.Event = asyncio.Event()
    _pause_requested: bool = False
    _resume_event_scheduled: bool = False
    
    class _Interface(LoopInterrupt):
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
class TaskControl(Protocol):
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
        ...
    
    @property
    def is_running(_) -> bool:
        """
        Returns True if the task is currently running and not done.
        """
        ...
    
    @staticmethod
    def stop() -> None:
        """
        Stops the task by cancelling it if it is running.
        """
        ...

def setup_task_control(state: State) -> TaskControl:

    _task:Optional[asyncio.Task] = None

    def _is_running():
        return _task is not None and not _task.done()

    class _Interface(TaskControl):
        __slots__ = ()
        @staticmethod
        def start(fn, *fn_args, **fn_kwargs):

            def create_task():
                nonlocal _task
                result = fn(*fn_args, **fn_kwargs)
                if isinstance(result, Coroutine):
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
                if _task and _is_running():
                    _task.cancel()
            state.maintain_state(state.ACTIVE, cancel_task)
    
    return _Interface()




@runtime_checkable
class CircuitCodeFactory(Protocol):
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
        ...

def setup_circuit_code_factory() -> CircuitCodeFactory:

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

    class _Interface(CircuitCodeFactory):
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
class LoopControl(Protocol):
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
    def exceptions(_) -> 'LoopException':
        """
        Returns the LoopException definitions associated with this loop control.
        Contains both error and signal definitions used during loop execution.
        """
        ...

    @property
    def event(_) -> StepSlot:
        """
        Returns the StepSlot that holds the most recent event name and its result.
        """
        ...

    @property
    def action(_) -> StepSlot:
        """
        Returns the StepSlot that holds the most recent action name and its result.
        """
        ...

    @staticmethod
    async def process_event(event: str) -> None:
        """
        Processes the given event by invoking its reactor and handler.
        The reactor is executed first, then the event handler, and
        their results or exceptions are recorded accordingly.
        """
        ...

    @staticmethod
    def setup_event_context() -> None:
        """
        Initializes the event reactor and its context.
        Must be called before processing events.
        """
        ...

    @staticmethod
    def setup_action_context() -> None:
        """
        Initializes the action reactor and its context.
        Must be called before processing actions.
        """
        ...

    @staticmethod
    def cleanup() -> None:
        """
        Cleans up internal state, releasing all references and clearing slots.
        After cleanup, the instance should not be used further.
        """
        ...

def setup_loop_control(
        evh: EventHandleRegistry, context: ReactorRegistry,
        ev_step: StepSlot, act_step: StepSlot,
        exc: 'LoopException') -> LoopControl:
    
    _event_reactor, _event_context = None, None
    _action_reactor, _action_context = None, None
    
    _all_event_handlers = dict(evh.get_all_handlers())

    class _Interface(LoopControl):
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
                context.event_reactor_factory(_iface)
        @staticmethod
        def setup_action_context() -> None:
            nonlocal _action_reactor, _action_context
            _action_reactor, _action_context =\
                  context.action_reactor_factory(_iface)
        @staticmethod
        async def process_event(event: str) -> None:
            assert _event_reactor is not None
            assert _all_event_handlers is not None
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
            exc = None # type: ignore
            ev_step = None # type: ignore
            act_step = None # type: ignore
            _iface = None # type: ignore
    
    _iface:LoopControl = _Interface()

    return _iface
