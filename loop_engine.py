
import asyncio
import inspect
import logging

import string
from types import MappingProxyType

from typing import Protocol, Callable, Mapping, Tuple, Any, runtime_checkable, FrozenSet, Type
from types import MappingProxyType
from typing_extensions import TypeAlias


@runtime_checkable
class LoopEvent(Protocol):
    @property
    def START(self) -> str: ...
    @property
    def PAUSE(self) -> str: ...
    @property
    def RESUME(self) -> str: ...
    @property
    def STOP_NORMALLY(self) -> str: ...
    @property
    def STOP_CANCELED(self) -> str: ...
    @property
    def STOP_HANDLER_ERROR(self) -> str: ...
    @property
    def STOP_CIRCUIT_ERROR(self) -> str: ...
    @property
    def CLEANUP(self) -> str: ...
    @property
    def LOOP_RESULT(self) -> str: ...

    @staticmethod
    def is_valid_event(name: str) -> bool: ...
    @property
    def all_events(self) -> FrozenSet[str]: ...


def _setup_loop_event() -> LoopEvent:
    START = 'on_start'

    PAUSE = 'on_pause'
    RESUME = 'on_resume'
    
    STOP_NORMALLY = 'on_end'
    STOP_CANCELED = 'on_stop'
    STOP_HANDLER_ERROR = 'on_handler_exception'
    STOP_CIRCUIT_ERROR = 'on_circuit_exception'

    CLEANUP = 'on_closed'
    LOOP_RESULT = 'on_result'

    _PHASE_EVENTS = {
        START, PAUSE, RESUME, STOP_NORMALLY,
        STOP_CANCELED, STOP_HANDLER_ERROR, STOP_CIRCUIT_ERROR,
        CLEANUP, LOOP_RESULT,
    }

    class LoopEvent:
        @property
        def START(_):
            return START
        @property
        def PAUSE(_):
            return PAUSE
        @property
        def RESUME(_):
            return RESUME            
        @property
        def STOP_NORMALLY(_):
            return STOP_NORMALLY
        @property
        def STOP_CANCELED(_):
            return STOP_CANCELED
        @property
        def STOP_HANDLER_ERROR(_):
            return STOP_HANDLER_ERROR
        @property
        def STOP_CIRCUIT_ERROR(_):
            return STOP_CIRCUIT_ERROR
        @property
        def CLEANUP(_):
            return CLEANUP
        @property
        def LOOP_RESULT(_):
            return LOOP_RESULT
        
        @staticmethod
        def is_valid_event(name):
            return name in _PHASE_EVENTS
        @property
        def all_events(_):
            return frozenset(_PHASE_EVENTS)
        
    return LoopEvent()


@runtime_checkable
class State(Protocol):
    @property
    def LOAD(self) -> object: ...
    @property
    def ACTIVE(self) -> object: ...
    @property
    def TERMINATED(self) -> object: ...

    @property
    def current_state(self) -> object: ...

    @property
    def errors(self) -> Any: ...

    @staticmethod
    def maintain_state(state: object, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any: ...

    @staticmethod
    def transit_state_with(to: object, fn: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> Any: ...

    @staticmethod
    def transit_state(to: object) -> Any: ...

def _setup_state() -> State:
    # Use int values with strictly sequential numbering.
    _LOAD = object()
    _ACTIVE = object()
    _TERMINATED = object()

    _ALL = (_LOAD, _ACTIVE, _TERMINATED)

    _state = _LOAD

    def _validate_state_value(state):
        if not any(state is s for s in _ALL):
            raise Error.UnknownStateError(
                f"Unknown or unsupported state value: {state}")
        
    def _require_state(expected):
        _validate_state_value(expected)
        if expected is not _state:
            err_log = f"State error: expected = {expected}, actual = {_state}"
            if _state is _TERMINATED:
                raise Error.TerminatedError(err_log)
            raise Error.InvalidStateError(err_log)
    
    class Error:
        __slots__ = ()
        class UnknownStateError(Exception):
            pass
        class InvalidStateError(Exception):
            pass
        class TerminatedError(InvalidStateError):
            pass

    class State:
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
        def errors(_):
            return Error
        
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
                raise Error.InvalidStateError(
                    f"Invalid transition: {_state} → {to}")
            if fn:
                result = State.maintain_state(
                    _state, fn, *fn_args, **fn_kwargs)
                _state = to
                return result
            else:
                return None
            
        @staticmethod
        def transit_state(to):
            return State.transit_state_with(to, None)
    
    return State()

@runtime_checkable
class Context(Protocol):
    """Represents a user-defined context object passed to handlers."""
    ...

Handler: TypeAlias = Callable[[Context], Any]

@runtime_checkable
class EventHandler(Protocol):
    @staticmethod
    def get_event_handlers() -> Mapping[str, Handler]:
        ...
    @staticmethod
    def set_event_handler(event: str, handler: Handler) -> None:
        ...

def _setup_event_handler(spec: LoopEvent, state) -> EventHandler:
    _phase_handlers = {}

    class _EventHandler(EventHandler):
        @staticmethod
        def get_event_handlers():
            return MappingProxyType(_phase_handlers)
        @staticmethod
        def set_event_handler(event, handler):
            if not spec.is_valid_event(event):
                raise ValueError(f"Event '{event}' is not defined")
            def add_phase(): _phase_handlers[event] = handler
            state.maintain_state(state.LOAD, add_phase)

    return _EventHandler()


@runtime_checkable
class Action(Protocol):
    @staticmethod
    def get_actions() -> Mapping[str, Tuple[Handler, str, Any]]:
        ...
    @staticmethod
    def append_action(name: str, fn: Handler, notify_ctx: Any) -> None:
        ...
    @staticmethod
    def build_action_namespace() -> Mapping[str, Handler]:
        ...

def _setup_action(state: State) -> Action:

    ACTION_SUFFIX = '_action'
    MAX_ACTIONS = 26**3
    
    # Requires Python 3.7+ for guaranteed insertion order
    _linear_actions_in_circuit = {} # tuple: (hadler, raw_name, notify_ctx)

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
    
    class _Action:
        __slots__ = ()
        @staticmethod
        def get_actions():
            return MappingProxyType(_linear_actions_in_circuit)
        @staticmethod
        def append_action(name, fn, notify_ctx):
            def add_action():
                label = _label_action_by_index()
                _linear_actions_in_circuit[label] = (fn, str(name), notify_ctx)
            state.maintain_state(state.LOAD, add_action)
        @staticmethod
        def build_action_namespace():
            # l = lable, t = tuple(action func, raw_name, notify_ctx)
            return {l :t[0] for l, t in _linear_actions_in_circuit.items()}
    
    return _Action()

@runtime_checkable
class Reactor(Protocol):
    def __call__(self, event: str) -> None:
        ...

@runtime_checkable
class ReactorFactory(Protocol):
    def __call__(self, l_iface: Any) -> Tuple[Reactor, Context]:
        ...

@runtime_checkable
class ReactorRegistry(Protocol):
    @staticmethod
    def set_event_reactor_factory(reactor_factory: ReactorFactory) -> None:
        ...

    @staticmethod
    def set_action_reactor_factory(reactor_factory: ReactorFactory) -> None:
        ...
    
    @staticmethod
    def get_event_reactor_factory() -> ReactorFactory:
        ...
    
    @staticmethod
    def get_action_reactor_factory() -> ReactorFactory:
        ...

def _setup_reactor(state: State) -> ReactorRegistry:

    def _LOOP_REACTOR_FACTORY(l_iface):
        def loop_reactor(event):
            pass
        return loop_reactor, l_iface
    
    def _CIRCUIT_REACTOR_FACTORY(l_iface):
        def circuit_reactor(event):
            pass
        return circuit_reactor, l_iface.loop_context

    _loop_reactor_factory = _LOOP_REACTOR_FACTORY
    _circuit_reactor_factory = _CIRCUIT_REACTOR_FACTORY

    class _ReactorRegistry(ReactorRegistry):
        __slots__ = ()
        @staticmethod
        def set_event_reactor_factory(reactor_factory):
            def fn():
                nonlocal _loop_reactor_factory
                _loop_reactor_factory = reactor_factory
            state.maintain_state(state.LOAD, fn)
        
        @staticmethod
        def set_action_reactor_factory(reactor_factory):
            def fn():
                nonlocal _circuit_reactor_factory
                _circuit_reactor_factory = reactor_factory
            state.maintain_state(state.LOAD, fn)
        
        @staticmethod
        def get_event_reactor_factory():
            return _loop_reactor_factory
        
        @staticmethod
        def get_action_reactor_factory():
            return _circuit_reactor_factory

    return _ReactorRegistry()


@runtime_checkable
class LoopResult(Protocol):
    @property
    def PENDING_RESULT(self) -> object: ...
    @property
    def NO_RESULT(self) -> object: ...
    @staticmethod
    def set_loop_result(obj: Any) -> None: ...
    @property
    def loop_result(_) -> Any: ...
    @staticmethod
    def set_circuit_error(e: Exception) -> None: ...
    @staticmethod
    def set_event_reactor_error(e: Exception) -> None: ...
    @staticmethod
    def set_handler_error(e: Exception) -> None: ...
    @staticmethod
    def set_internal_error(e: Exception) -> None: ...
    @property
    def circuit_error(_) -> Exception: ...
    @property
    def event_reactor_error(_) -> Exception: ...
    @property
    def handler_error(_) -> Exception: ...
    @property
    def internal_error(_) -> Exception: ...
    @staticmethod
    def cleanup() -> None: ...


def _setup_loop_result() -> LoopResult:

    _PENDING_RESULT = object()
    _NO_RESULT = object()

    # not target of cleanup
    _loop_result = _PENDING_RESULT
    
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
        def set_loop_result(obj):
            nonlocal _loop_result
            _loop_result = obj
        @property
        def loop_result():
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
            _loop_result = None
            _circuit_error = None
            _event_reactor_error = None
            _handler_error = None
            _internal_error = None
    
    return _LoopResult()

@runtime_checkable
class ResultBridge(Protocol):
    @property
    def UNSET(self) -> object: ...
    @staticmethod
    def set_prev_result(tag: str, result: Any) -> None: ...
    @property
    def prev_tag() -> str: ...
    @property
    def prev_result() -> Any: ...
    @staticmethod
    def cleanup() -> None: ...

def _setup_result_bridge() -> ResultBridge:

    _UNSET = object

    _prev_tag = '<unset>'
    _prev_result = _UNSET

    class _ResultBridge(ResultBridge):
        __slots__ = ()
        @property
        def UNSET(_):
            return _UNSET
        @staticmethod
        def set_prev_result(tag: str, result: Any):
            nonlocal _prev_tag, _prev_result
            _prev_tag = tag
            _prev_result = result
        @staticmethod
        def get_prev_tag(_):
            return _prev_tag
        @staticmethod
        def get_prev_result(_):
            return _prev_result
        @staticmethod
        def cleanup() -> None:
            nonlocal _prev_tag, _prev_result
            _prev_tag = None
            _prev_result = None

    return _ResultBridge()



@runtime_checkable
class LoopInterrupt(Protocol):
    @property
    def current_mode(self) -> object: ...

    @property
    def pause_requested(self) -> bool: ...
    
    @property
    def resume_event_scheduled(self) -> bool: ...

    @staticmethod
    async def consume_pause_request(handler: Handler, ctx: Context) -> Any: ...
    
    @staticmethod
    async def consume_resume_event(handler: Handler, ctx: Context) -> Any: ...
    
    @staticmethod
    def request_pause() -> None: ...
    
    @staticmethod
    def resume() -> None: ...
    
    @staticmethod
    async def wait_resume() -> None: ...


def _setup_loop_interrupt(state: State) -> LoopInterrupt:
    
    _RUNNING = object()
    _PAUSE = object()

    _mode: object = _RUNNING
    _event: asyncio.Event = asyncio.Event()
    _pause_requested: bool = False
    _resume_event_scheduled: bool = False
    
    class _LoopInterrupt(LoopInterrupt):
        __slots__ = ()
        @property
        def current_mode(_):
            return _mode
        @staticmethod
        async def consume_pause_request(handler: Handler, ctx: Context):
            nonlocal _mode, _pause_requested
            _pause_requested = False
            tmp = handler(ctx)
            result = await tmp if inspect.isawaitable(tmp) else tmp
            _event.clear()
            _mode = _PAUSE
            return result
        @staticmethod
        async def consume_resume_event(handler: Handler, ctx: Context):
            nonlocal _mode, _resume_event_scheduled
            _resume_event_scheduled = False
            tmp = handler(ctx)
            result = await tmp if inspect.isawaitable(tmp) else tmp
            _mode = _RUNNING
            return result
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
    
    return _LoopInterrupt()

@runtime_checkable
class LoopError(Protocol):
    EventReactorError: Type[Exception]
    HandlerError: Type[Exception]
    CircuitError: Type[Exception]


@runtime_checkable
class LoopSignal(Protocol):
    Break: Type[Exception]


@runtime_checkable
class LoopException(Protocol):
    @property
    def error(self) -> LoopError: ...
    
    @property
    def signal(self) -> LoopSignal: ...

def _setup_loop_exception() -> LoopException:
    class _LoopError(LoopError):
        __slots__ = ()
        class EventReactorError(Exception):
            def __init__(self, tag, e):
                super().__init__()
                self.event = tag
                self.orig_exception = e
        class HandlerError(Exception):
            def __init__(self, tag, e):
                super().__init__()
                self.event = tag
                self.orig_exception = e

        class CircuitError(Exception):
            def __init__(self, e):
                self.orig_exception = e
    
    class _LoopSignal(LoopSignal):
        __slots__ = ()
        class Break(Exception):
            pass
    
    class _LoopException(LoopException):
        __slots__ = ()
        @property
        def error(_) -> LoopError:
            return _LoopError
        @property
        def signal(_) -> LoopSignal:
            return _LoopSignal
    
    return _LoopException()



@runtime_checkable
class TaskControl(Protocol):
    @staticmethod
    def start(
        fn: Callable[..., Any], *fn_args: Any, **fn_kwargs: Any
    ) -> Any: ...
    
    @property
    def is_running(self) -> bool: ...
    
    @staticmethod
    def stop() -> Any: ...

def _setup_task_control(state: State) -> TaskControl:

    _task = None

    class _TaskControl:
        __slots__ = ()
        @staticmethod
        def start(fn, *fn_args, **fn_kwargs):

            def create_task():
                nonlocal _task
                result = fn(*fn_args, **fn_kwargs)
                if inspect.isawaitable(result):
                    _task = asyncio.create_task(result)
                    return _task
                return None
            
            return state.transit_state_with(state.ACTIVE, create_task)
        
        @property
        def is_running(_):
            return _task is not None and not _task.done()
        
        @staticmethod
        def stop():
            def cancel_task():
                if _TaskControl.is_running:
                    _task.cancel()
            state.maintain_state(state.ACTIVE, cancel_task)
    
    return _TaskControl()

@runtime_checkable
class LoopControl(Protocol):
    @property
    def exceptions(_) -> LoopException: ...
    @property
    def event(_) -> ResultBridge: ...
    @property
    def action(_) -> ResultBridge: ...
    @staticmethod
    async def process_event(event: str) -> None: ...
    @staticmethod
    def setup_event_context() -> None: ...
    @staticmethod
    def setup_action_context() -> None: ...
    @staticmethod
    def cleanup() -> None: ...

def _setup_loop_control(
        role: str, evh: EventHandler, res: LoopResult,
        context: ReactorRegistry) -> LoopControl:
    # ループ開始時に呼び出す
    _event_reactor, _event_context = None, None
    _action_reactor, _action_context = None, None
    _event_result_bridge = _setup_result_bridge()
    _action_result_bridge = _setup_result_bridge()
    
    _all_event_handlers = dict(evh.get_event_handlers())

    _exc = _setup_loop_exception()

    class _LoopControl(LoopControl):
        __slots__ = ()
        @property
        def event(_):
            return _event_result_bridge
        @property
        def action(_):
            return _action_result_bridge
        @staticmethod
        def setup_event_context() -> None:
            nonlocal _event_reactor, _event_context
            _event_reactor, _event_context =\
                context.get_event_reactor_factory()(_self)
        @staticmethod
        def setup_action_context() -> None:
            nonlocal _action_reactor, _action_context
            _action_reactor, _action_context =\
                  context.get_action_reactor_factory()(_self)
        @staticmethod
        async def process_event(event: str) -> None:
            handler = _all_event_handlers.get(event, None)
            if not handler:
                return
            if inspect.iscoroutinefunction(_event_reactor):
                try:
                    await _event_reactor(event)
                except Exception as e:
                    raise _exc.error.EventReactorError(e)
            else:
                try:
                    _event_reactor(event)
                except Exception as e:
                    raise _exc.error.EventReactorError(e)
            if inspect.iscoroutinefunction(handler):
                try:
                    result = await handler(_event_context)
                except Exception as e:
                    raise _exc.error.HandlerError(event, e)
            else:
                try:
                    result = handler(_event_context)
                except Exception as e:
                    raise _exc.error.HandlerError(event, e)
            _event_result_bridge.set_prev_result(event, result)
        @staticmethod
        def cleanup() -> None:
            nonlocal _event_reactor, _event_context,\
                _action_reactor, _action_context,\
                _event_result_bridge, _action_result_bridge,\
                _all_event_handlers, _exc
            
            _event_result_bridge.cleanup()
            _action_result_bridge.cleanup()
            _all_event_handlers.clear()
            _event_reactor, _event_context = None, None
            _action_reactor, _action_context = None, None
            _all_event_handlers = None
            _exc = None
            _event_result_bridge = None
            _action_result_bridge = None
    
    _self = _LoopControl()

    return _self

# def make_loop_engine_handle(role: str = 'loop', logger = None):
def make_loop_engine_handle(circuit):

    # if not logger:
    #     logger = logging.getLogger(__name__)
    
    async def _loop_engine(
            role: str, logger: logging.Logger,
            circuit, ev: LoopEvent, control: LoopControl,
            res: LoopResult) -> None:
        try:
            control.setup_event_context()
            try:
                await control.process_event(ev.START)
                control.setup_action_context()
                if inspect.iscoroutinefunction(circuit):
                    try:
                        await circuit(control)
                    except Exception as e:
                        raise control.exceptions.error.CircuitError(e)
                else:
                    try:
                        circuit(control)
                    except Exception as e:
                        raise control.exceptions.error.CircuitError(e)
                await control.process_event(ev.STOP_NORMALLY)
            except asyncio.CancelledError as e:
                logger.info(f"[{role}] Loop was cancelled")
                await control.process_event(ev.STOP_CANCELED)
            finally:
                await control.process_event(ev.CLEANUP)
                await control.process_event(ev.LOOP_RESULT)
                res.set_loop_result(control.event.prev_result)
        except control.exceptions.error.CircuitError as e:
            # Exceptions thrown by action reactor are included here.
            res.set_circuit_error(e)
            raise
        except control.exceptions.error.EventReactorError as e:
            res.set_event_reactor_error(e)
            raise
        except control.exceptions.error.HandlerError as e:
            res.set_handler_error(e)
            raise
        except Exception as e:
            logger.critical(f"[{role}] Internal error: {e.__class__.__name__}")
            res.set_internal_error(e)
            raise
        finally:
            # Do not call res.cleanup() in here
            control.cleanup()
            role = None
            logger = None
            circuit = None
            ev = None
            control = None
            res = None


    def _load_circuit_factory(spec, loop_env, injected_hook):
        @property
        def circuit_is_pausable(_):
            return _pausable
        
        @staticmethod
        def set_pausable(flag):
            def fn():
                nonlocal _pausable
                _pausable = flag
            state.maintain_state(state.LOAD, fn)
    
        _CIRCUIT_TEMPLATE = [
            ("{}def {}(control: LoopControl):", _circuit_def),
             "    try:",
             "        while True:",
            ("{}", _build_actions),
             "        if irq.pause_requested:"
             "            await irq.consume_pause_request()"
             "    except Break as e:",
             "        pass",
             "    except HandlerError as e:",
             "        raise"
             "    except Exception as e:",
             "        raise CircuitError(e)",
        ]

        _EVENT_IN_CIRCUIT_INDENT = 12
        
        _INVOKE_ACTION_TEMPLATE = [
            ("{}", 'notify'),
            ("result = {}{}(ctx)", 'invoke_handler'),
            ("result_bridge.set_prev({}, result)", 'result_bridge'),
            "",
        ]

        _INVOKE_PAUSER_HANDLER_TEMPLATE = [
            ("{}", 'notify'),
            ("{}{}(ctx)", 'invoke_handler'),
        ]

        _PAUSABLE_TEMPLATE = [
            "if pauser.pause_requested:",
            "    try:",
            "        await pauser.consume_pause_result(on_pause, ctx)",
            "if pauser.enter_if_pending_pause():",
            ("{}", 'on_pause'),
            "    try:",
            "        pauser.pause()",
            "    except Exception as e:",
            "        raise CircuitError(e)",
            "if pauser.enter_if_pending_resume():",
            ("{}", 'on_resume'),
            "try:",
            "    await pauser.wait()",
            "except Exception as e:",
            "    raise CircuitError(e)",
        ]

        _EVENT_IN_PAUSABLE_INDENT = 4

        _PAUSER_HANDLER_IN_CIRCUIT = [
            spec.PAUSE,
            spec.RESUME
        ]

        _circuit_full_code = None
        _generated_circuit = None

        def _build_template(template, tag_processor):
            lines = []
            for line in template:
                match(line):
                    case str() as code:
                        lines.append(code)
                    case (code, tag):
                        tag_processor(lines, code, tag)
            return lines
        
        def _build_invoke_action(label, raw_name, notify, await_):
            def _tag_processor(lines, code, tag):
                match(tag):
                    case 'notify':
                        if notify:
                            lines.append(
                                    code.format(f"ctx_updater('{raw_name}')"))
                    case 'invoke_handler':
                        lines.append(
                            code.format("await " if await_ else "", label))
                    case 'result_bridge':
                        lines.append(code.format(f"'{raw_name}'"))
                    case _:
                        raise ValueError(f"Unknown tag in template: {tag}")
            
            return _build_template(_INVOKE_ACTION_TEMPLATE, _tag_processor)
        
        def _build_invoke_pauser_handler(event, notify, await_):
            def _tag_processor(lines, code, tag):
                match(tag):
                    case 'current_event':
                        lines.append(code.format(event))
                    case 'notify':
                        if notify:
                            lines.append(
                                    code.format(f"ctx_updater('{event}')"))
                    case 'invoke_handler':
                        lines.append(
                            code.format("await " if await_ else "", event))
                    case _:
                        raise ValueError(f"Unknown tag in template: {tag}")
            
            return _build_template(_INVOKE_PAUSER_HANDLER_TEMPLATE, _tag_processor)
        
        def _build_pausable(handler_snippets):
            def _tag_processor(lines, code, tag):
                INDENT = ' ' * _EVENT_IN_PAUSABLE_INDENT
                match(tag):
                    case _:
                        snip = handler_snippets.get(tag, None)
                        if snip:
                            lines.extend(INDENT + s for s in snip)
                        elif tag == spec.RESUME:
                            lines.append('    pass')

            return _build_template(_PAUSABLE_TEMPLATE, _tag_processor)
        
        def _build_circuit(name, as_async, action_snippets, pausable_snippet):
            def _tag_processor(lines, code, tag):
                INDENT = ' ' * _EVENT_IN_CIRCUIT_INDENT
                match(tag):
                    case 'define':
                        prefix = 'async ' if as_async else ''
                        lines.append(code.format(prefix, name))
                    case 'pausable':
                        if pausable_snippet:
                            lines.extend(INDENT + p for p in pausable_snippet)
                    case 'actions':
                        for _, snip in action_snippets.items():
                            lines.extend(INDENT + s for s in snip)

                
            return _build_template(_CIRCUIT_TEMPLATE, _tag_processor)


        class CircuitFactory:
            __slots__ = ()
            # Has no interface
            
            @staticmethod
            def build_circuit_full_code(circuit_name):
                nonlocal _circuit_full_code
                includes_async_function = False
                actions_snippets = {}
                for label, action in injected_hook.get_actions().items():
                    # deploy action: (action, raw_name, notify_ctx)
                    action, raw_name, notify_ctx = action
                    async_func = inspect.iscoroutinefunction(action)
                    includes_async_function |= async_func
                    actions_snippets[label] =\
                        _build_invoke_action(label, raw_name, notify_ctx, async_func)
                
                pauser_handler_snippets = {}
                for name, handler in injected_hook.get_interrupt_handlers().items():
                    if not handler or name not in _PAUSER_HANDLER_IN_CIRCUIT:
                        continue
                    # deploy handler: (handler, notify_ctx)
                    handler, notify_ctx = handler
                    async_func = inspect.iscoroutinefunction(handler)
                    includes_async_function |= async_func
                    pauser_handler_snippets[name] =\
                        _build_invoke_pauser_handler(name, notify_ctx, async_func)
                
                pausable_snippet = _build_pausable(
                    pauser_handler_snippets
                ) if injected_hook.circuit_is_pausable else None

                all_snippets = _build_circuit(
                    circuit_name, includes_async_function,
                    actions_snippets, pausable_snippet
                )

                _circuit_full_code = "\n".join(all_snippets)
                return _circuit_full_code
        
            @staticmethod
            def compile():
                nonlocal _generated_circuit
                CIRCUIT_NAME = '_circuit'
                if not _circuit_full_code:
                    CircuitFactory.build_circuit_full_code(CIRCUIT_NAME)
                
                namespace = {
                    "__builtins__" : {},
                    "Exception": Exception,
                    "HandlerError": loop_env.HandlerError,
                    "CircuitError": loop_env.CircuitError,
                    "Break": loop_env.Break,
                    **injected_hook.build_action_namespace(),
                }
                dst = {}
                exec(_circuit_full_code, namespace, dst)
                _generated_circuit = dst[CIRCUIT_NAME]
                return _generated_circuit

        return CircuitFactory()
    



    STATIC_CIRCUIT_NAME = '_static_circuit'

    _spec = _setup_loop_event()
    _state = _setup_state()
    _injected_hook = _load_loop_cofig(_spec, _state)
    _loop_environment = _setup_loop_exception(_spec, _state, _injected_hook)

    _circuit_factory = _load_circuit_factory(_spec, _loop_environment, _injected_hook)
    
    _task_control = _setup_task_control(_state)

    # _meta = SimpleNamespace()

    def dump_circuit():
        code = _circuit_factory.build_circuit_full_code('_dynamic_circuit')
        # This module is currently under development.
        # The loop does not start; the purpose here is to inspect the dynamically generated code.
        print(code)

    class Handle:
        __slots__ = ()
        @property
        def role(_):
            return role
        
        @staticmethod
        def start():
            return _task_control.start(
                _loop_environment.loop_engine, _circuit_factory.compile())
        @property
        def stop(_):
            return _task_control.stop
        @property
        def task_is_running(_):
            return _task_control.is_running
        
        @property
        def pause(_):
            return _loop_environment.pauser.pause
        @property
        def resume(_):
            return _loop_environment.pauser.resume
        
        @staticmethod
        def set_on_start(fn):  # type: ignore
            _injected_hook.set_phase_handler('on_start', fn)
        @staticmethod
        def set_on_end(fn):  # type: ignore
            _injected_hook.set_phase_handler('on_end', fn)
        @staticmethod
        def set_on_stop(fn):  # type: ignore
            _injected_hook.set_phase_handler('on_stop', fn)
        @staticmethod
        def set_on_closed(fn):  # type: ignore
            _injected_hook.set_phase_handler('on_closed', fn)
        @staticmethod
        def set_on_result(fn):  # type: ignore
            _injected_hook.set_phase_handler('on_result', fn)
        @staticmethod
        def set_on_pause(fn, notify_ctx):  # type: ignore
            _injected_hook.set_interrupt_handler('on_pause', fn, notify_ctx)
        @staticmethod
        def set_on_resume(fn, notify_ctx):  # type: ignore
            _injected_hook.set_interrupt_handler('on_resume', fn, notify_ctx)
        @staticmethod
        def set_on_handler_exception(fn):  # type: ignore
            _injected_hook.set_phase_handler('on_handler_exception', fn)
        @staticmethod
        def set_on_circuit_exception(fn):  # type: ignore
            _injected_hook.set_phase_handler('on_circuit_exception', fn)
        @staticmethod
        def append_action(name, fn, notify_ctx = True):
            _injected_hook.append_action(name, fn, notify_ctx)
        @staticmethod
        def set_loop_context_builder_factory(fn):
            _injected_hook.set_loop_context_updater_factory(fn)
        @staticmethod
        def set_circuit_context_builder_factory(fn):
            _injected_hook.set_circuit_context_updater_factory(fn)
        
        @property
        def state(_):
            return _state.interface
        @property
        def is_active(_):
            return _loop_environment.interface.current_state == _state.ACTIVE
        @property
        def is_closed(_):
            return _loop_environment.interface.current_state in _state.TERMINAL_STATES
        
        @property
        def NO_RESULT(_):
            return _loop_environment.result_reader.NO_RESULT

        @property
        def PENDING_RESULT(_):
            return _loop_environment.result_reader.PENDING_RESULT
        @property
        def result(_):
            return _loop_environment.result_reader.loop_result
        @property
        def exception(_):
            return _loop_environment.result_reader.exc
        @property
        def nested_exception(_):
            return _loop_environment.result_reader.nested_exc
        
        @property
        def last_event(_):
            return _loop_environment.result_reader.prev_event
        @property
        def last_result(_):
            return _loop_environment.result_reader.prev_result
        
        @property
        def current_mode(_):
            return _loop_environment.interface.mode.current_mode
        @property
        def is_paused(_):
            return _loop_environment.interface.mode.current_mode ==\
                     _loop_environment.interface.mode.PAUSE
        @property
        def pause_pending(_):
            return _loop_environment.interface.mode.pending_pause
        @property
        def resume_pending(_):
            return _loop_environment.interface.mode.pending_resume
        
        @property
        def registered_actions(_):
            return _injected_hook.get_actions()
        @property
        def phase_handlers(_):
            return _injected_hook.get_phase_handlers()
        @property
        def interrupt_handlers(_):
            return _injected_hook.get_interrupt_handlers()

        @property
        def dump_full_code(_):
            return dump_circuit

    return Handle()

async def main():
    from types import SimpleNamespace
    handle = make_loop_engine_handle("test")

    handle.set_on_start(lambda ctx: print("[on_start]"))
    handle.set_on_end(lambda ctx: print("[on_end]"))

    handle.set_on_pause(lambda ctx: print("[on_pause]"), notify_ctx = False)
    handle.set_on_resume(lambda ctx: print("[on_resume]"), notify_ctx = True)

    def context_updater_factory(loop_interface):
        ctx = SimpleNamespace()
        ctx.count = 0
        ctx.loop_interface = loop_interface
        def context_updater(event, c_ctx):
            ctx.count += 1
            return ctx
        return context_updater, ctx
    
    handle.set_loop_context_builder_factory(context_updater_factory)

    async def action(ctx):
        print('tick' + '!' * ctx.count)
        if ctx.count > 10:
            raise ctx.loop_interface.Break
        await asyncio.sleep(1)

    handle.append_action('tick_and_stop', action, notify_ctx = True)

    task = handle.start()

    await task

asyncio.run(main())