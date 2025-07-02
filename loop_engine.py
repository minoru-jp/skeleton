
import asyncio
import inspect
import logging

import string
from types import MappingProxyType

def make_loop_engine_handle(role: str = 'loop', logger = None):

    if not logger:
        logger = logging.getLogger(__name__)

    def _load_loop_specification():

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

        _INTERRUPT_EVENTS = {
            PAUSE, RESUME
        }

        class LoopSpec:
            @property
            def interface(_):
                return LoopSpec

            @staticmethod
            def is_valid_phase(name):
                return name in _PHASE_EVENTS
            @staticmethod
            def is_valid_interrupt(name):
                return name in _INTERRUPT_EVENTS
            @property
            def all_phase(_):
                return frozenset(_PHASE_EVENTS)
            @property
            def all_interrupt(_):
                return frozenset(_INTERRUPT_EVENTS)
            @property
            def all_events(_):
                return frozenset(_PHASE_EVENTS | _INTERRUPT_EVENTS)
            
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
            
        return LoopSpec()
    
    def _load_state():

        _LOAD = 0
        _ACTIVE = 1
        _CLOSED = 2
        _UNCLEAN = 20 # Terminal-state used instead of CLOSED if _on_closed() fails
        _TERMINAL_STATES = (_CLOSED, _UNCLEAN)

        _state = _LOAD

        def _validate_state_value(state):
            if state not in (_LOAD, _ACTIVE, *_TERMINAL_STATES):
                raise State.UnknownStateError(
                    f"Unknown or unsupported state value: {state}")
            
        def _require_state(expected):
            _validate_state_value(expected)
            if expected != _state:
                err_log = f"State error: expected = {expected}, actual = {_state}"
                if _state in _TERMINAL_STATES:
                    raise State.InvalidStateError(err_log)
                raise State.ClosedError(err_log)
        
        class Interface:
            class UnknownStateError(Exception):
                pass
            class InvalidStateError(Exception):
                pass
            class ClosedError(InvalidStateError):
                pass

            __slots__ = ()
            @property
            def LOAD(_):
                return _LOAD
            @property
            def ACTIVE(_):
                return _ACTIVE
            @property
            def CLOSED(_):
                return _CLOSED
            @property
            def UNCLEAN(_):
                return _UNCLEAN
            @property
            def TERMINAL_STATES(_):
                return _TERMINAL_STATES
            
            @property
            def current_state(_):
                return _state
        
        _interface = Interface()

        class State(Interface):
            __slots__ = ()
            @property
            def interface(_):
                return _interface
            
            @staticmethod
            def maintain_state(state, fn, *fn_args, **fn_kwargs):
                _require_state(state)
                return fn(*fn_args, **fn_kwargs)
            
            @staticmethod
            def transit_state_with(to, fn, *fn_args, **fn_kwargs):
                nonlocal _state
                _validate_state_value(to)
                to_active = _state == _LOAD and to == _ACTIVE
                to_terminal = _state == _ACTIVE and to in _TERMINAL_STATES
                if not (to_active or to_terminal):
                    raise State.InvalidStateError(
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
    
    def _load_loop_cofig(spec, state):
        
        def _DEFAULT_CONTEXT_UPDATER_FACTORY(loop_interface):
            loop_context = loop_interface
            def loop_context_updater(event, circuit_context):
                return loop_interface
            return loop_context_updater, loop_context
        
        # def _CIRCUIT_UPDATER_FACTORY_SMAPLE(loop_interface, loop_context):
        #     circuit_context = some_goodness
        #     def circuit_context_updater(event):
        #         return circuit_context
        #     return circuit_context_updater, circuit_context
        
        ACTION_SUFFIX = '_action'
        MAX_ACTIONS = 26**3

        _phase_handlers = {}
        _interrupt_handlers = {} # tuple: (handler, notify_ctx)
        
        # Requires Python 3.7+ for guaranteed insertion order
        _linear_actions_in_circuit = {} # tuple: (hadler, notify_ctx)
        
        _loop_ctx_updater_factory = _DEFAULT_CONTEXT_UPDATER_FACTORY
        _circuit_ctx_updater_factory = None
        _pausable = True

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

        class Interface:
            __slots__ = ()
            @staticmethod
            def get_phase_handlers():
                return MappingProxyType(_phase_handlers)
            @staticmethod
            def get_interrupt_handlers():
                return MappingProxyType(_interrupt_handlers)
            @staticmethod
            def get_actions():
                return MappingProxyType(_linear_actions_in_circuit)
            @staticmethod
            def get_loop_context_updater_factory():
                return _loop_ctx_updater_factory
            @staticmethod
            def get_circuit_context_updater_factory():
                return _circuit_ctx_updater_factory
            @staticmethod
            def circuit_is_pausable():
                return _pausable

        _interface = Interface()

        class LoopConfig(Interface):
            __slots__ = ()
            @property
            def interface(_):
                return _interface
            
            @staticmethod
            def set_phase_handler(event, handler):
                if not spec.is_valid_phase(event):
                    raise ValueError(f"Event '{event}' is not defined")
                def add_phase(): _phase_handlers[event] = handler
                state.maintain_state(state.LOAD, add_phase)
            
            @staticmethod
            def set_interrupt_handler(event, handler, notify_ctx):
                if not spec.is_valid_interrupt(event):
                    raise ValueError(f"Event '{event}' is not defined")
                def add_interrupt(): _interrupt_handlers[event] = (handler, notify_ctx)
                state.maintain_state(state.LOAD, add_interrupt)
            
            @staticmethod
            def append_action(name, fn, notify_ctx):
                def add_action():
                    label = _label_action_by_index()
                    _linear_actions_in_circuit[label] = (str(name), fn, notify_ctx)
                state.maintain_state(state.LOAD, add_action)
            
            @staticmethod
            def set_loop_context_updater_factory(ctx_updater_factory):
                def fn():
                    nonlocal _loop_ctx_updater_factory
                    _loop_ctx_updater_factory = ctx_updater_factory
                state.maintain_state(state.LOAD, fn)
            
            @staticmethod
            def set_circuit_context_updater_factory(ctx_updater_factory):
                def fn():
                    nonlocal _circuit_ctx_updater_factory
                    _circuit_ctx_updater_factory = ctx_updater_factory
                state.maintain_state(state.LOAD, fn)
            
            @staticmethod
            def set_pausable(flag):
                def fn():
                    nonlocal _pausable
                    _pausable = flag
                state.maintain_state(state.LOAD, fn)

        return LoopConfig()


    def _load_loop_environment(spec, state, injected_hook):

        # Each handler's return value is always updated via _result_bridge.set_prev.
        # Therefore, if a specific handler depends on the return value from another,
        # all intermediate handlers must propagate the return value properly.
        # In particular, be careful with on_pause and on_resume,
        # as they may not be called in a strictly linear sequence.

        RUNNING = 10 # Sub-state of ACTIVE commute to PAUSE
        PAUSE = 11 # Sub-state of ACTIVE commute to RUNNING

        PENDING_RESULT = object()
        NO_RESULT = object()
        
        _prev_event = None
        _prev_result = None

        _mode = RUNNING
        _event = asyncio.Event()
        _pending_pause = False
        _pending_resume = False

        _exc = None
        _nested_exc = None

        # not target of cleanup
        _loop_result = PENDING_RESULT

        def clean_environment():
            nonlocal\
                _prev_event, _prev_result, _event, _exc, _nested_exc,\
                _mode, _pending_pause, _pending_resume
            _prev_event = None
            _prev_result = None
            _event = None
            _exc = None
            _nested_exc = None
            
            _mode = RUNNING
            _pending_pause = False
            _pending_resume = False
        
        class LoopResultReader:
            __slots__ = ()
            @property
            def PENDING_RESULT(_):
                return PENDING_RESULT
            @property
            def NO_RESULT(_):
                return NO_RESULT
            @property
            def exc(_):
                return _exc
            @property
            def nested_exc(_):
                return _nested_exc
            @property
            def loop_result(_):
                return _loop_result
            
        _loop_result_reader = LoopResultReader()

        
        class HandlerResultReader:
            __slots__ = ()
            @property
            def prev_event(_):
                return _prev_event
            @property
            def prev_result(_):
                return _prev_result
            @property
            def exc(_):
                return _exc
            @property
            def nested_exc(_):
                return _nested_exc
        
        _handler_result_reader = HandlerResultReader()


        class ResultBridge:
            __slots__ = ()
            @property
            def reader(_):
                return _handler_result_reader
            @staticmethod
            def set_prev(event, result):
                nonlocal _prev_event, _prev_result
                _prev_event = event
                _prev_result = result
        
        _result_bridge = ResultBridge()


        class Pauser:
            __slots__ = ()
            @staticmethod
            def enter_if_pending_pause():
                nonlocal _mode, _pending_pause
                if _pending_pause:
                    _pending_pause = False
                    _mode = PAUSE
                    return True
                else:
                    return False
            @staticmethod
            def enter_if_pending_resume():
                nonlocal _mode, _pending_resume
                if _pending_resume:
                    _pending_resume = False
                    _mode = RUNNING
                    return True
                else:
                    return False
            @staticmethod
            def set():
                _event.set()
            @staticmethod
            def clear():
                _event.clear()
            @staticmethod
            async def wait():
                await _event.wait()
            @property
            def pending_pause(_):
                return _pending_pause
            @property
            def pending_resume(_):
                return _pending_resume
            @staticmethod
            def pause():
                nonlocal _pending_pause
                _pending_pause = True
            @staticmethod
            def resume():
                nonlocal _pending_resume
                _pending_resume = True
                _event.set()

        _pauser = Pauser()


        class ModeReader:
            __slots__ = ()
            @property
            def RUNNING(_):
                return RUNNING
            @property
            def PAUSE(_):
                return PAUSE
            @property
            def current_mode(_):
                return _mode
            @property
            def pending_pause(_):
                return _pauser.pending_pause
            @property
            def pending_resume(_):
                return _pauser.pending_resume
        
        _mode_reader = ModeReader()

        class Interface:

            class HandlerError(Exception):
                def __init__(self, event, exception):
                    super().__init__()
                    self.event = event
                    self.orig_exception = exception
            
            class CircuitError(Exception):
                def __init__(self, exception):
                    self.orig_exception = exception
            
            class Break(Exception):
                pass

            __slots__ = ()
            @property
            def RUNNING(_):
                return _mode_reader.RUNNING
            @property
            def PAUSE(_):
                return _mode_reader.PAUSE
            @property
            def mode(_):
                return _mode_reader.current_mode
            @property
            def pause(_):
                return _pauser.pause
            @property
            def resume(_):
                return _pauser.resume
            @property
            def result(_):
                return _loop_result_reader

        _interface = Interface()


        async def _process_loop_event(event, l_ctx_updater, l_ctx, c_ctx):
            handler = injected_hook.get_phase_handler().get(event, None)
            if not handler:
                return
            l_ctx_updater(event, c_ctx)
            try:
                tmp = handler(l_ctx)
                result = await tmp if inspect.isawaitable(tmp) else tmp
                _result_bridge.set_prev(event, result)
            except Exception as e:
                raise Interface.HandlerError(event, e)

        async def _loop_engine(circuit):
            nonlocal _loop_result, _exc, _nested_exc
            iface = _interface
            l_ctx_factory = injected_hook.get_loop_context_updater_factory()
            c_ctx_factory = injected_hook.get_circuit_context_updater_factory()
            l_ctx_updater, l_ctx = l_ctx_factory(iface)
            try:
                try:
                    await _process_loop_event(spec.START, l_ctx_updater, l_ctx, None)
                    # Use loop-level context (l_ctx_updater, l_ctx) as a fallback
                    # if circuit_context_updater_factory is not provided.
                    if c_ctx_factory:
                        c_ctx_updater, c_ctx = c_ctx_factory(iface, l_ctx)
                    else:
                        c_ctx_updater = l_ctx_updater
                        c_ctx = l_ctx
                    if inspect.iscoroutinefunction(circuit):
                        await circuit(c_ctx_updater, c_ctx, _result_bridge, _pauser)
                    else:
                        circuit(c_ctx_updater, c_ctx, _result_bridge, _pauser)
                    await _process_loop_event(spec.STOP_NORMALLY, l_ctx_updater, l_ctx, c_ctx)
                except Exception as e:
                    _exc = e
                    raise
                finally:
                    l_ctx_updater('ctx_circuit_end', c_ctx)

            except asyncio.CancelledError as e:
                logger.info(f"[{role}] Loop was cancelled")
                try:
                    await _process_loop_event(spec.STOP_CANCELED, l_ctx_updater, l_ctx, c_ctx)
                except Exception as nested_exc:
                    _nested_exc = nested_exc
                    raise nested_exc from e
            except Interface.HandlerError as e:
                logger.exception(f"[{role}] {e.event} Handler failed")
                try:
                    await _process_loop_event(spec.STOP_HANDLER_ERROR, l_ctx_updater, l_ctx, c_ctx)
                except Exception as nested_exc:
                    _nested_exc = nested_exc
            except Exception as e:
                logger.exception(f"[{role}] Unknown exception in circuit")
                try:
                    await _process_loop_event(spec.STOP_CIRCUIT_ERROR, l_ctx_updater, l_ctx, c_ctx)
                except Exception as nested_exc:
                    _nested_exc = nested_exc
            finally:
                # Currently, exceptions raised from on_closed or on_result are not handled.
                # Consider whether to introduce explicit handlers or allow propagation.
                # Additional note: Exceptions thrown by these two are not captured in _exc.
                try:
                    await _process_loop_event(spec.CLEANUP, l_ctx_updater, l_ctx)
                    state.transit_state(state.CLOSED)
                except Exception:
                    logger.exception(f"[{role}] on_closed handler failed")
                    state.transit_state(state.UNCLEAN)
                try:
                    await _process_loop_event(spec.LOOP_RESULT, l_ctx_updater, l_ctx)
                    _loop_result = _result_bridge.prev_result
                    return
                except Exception:
                    logger.exception(f"[{role}] on_result handler failed")
                    _loop_result = NO_RESULT
                    return
                finally:
                    # Cleanup local references
                    iface = None
                    l_ctx_updater = None
                    l_ctx = None
                    c_ctx_updater = None
                    c_ctx = None
                    # Cleanup closure states
                    clean_environment()

        class LoopEnvironment(Interface):
            __slots__ = ()
            @property
            def interface(_):
                return _interface
        
        return LoopEnvironment()


    def _load_circuit_factory(spec, loop_env, injected_hook):
    
        _CIRCUIT_TEMPLATE = [
            ("{}def {}(ctx_updater, ctx, result_bridge, pauser):", 'define'),
            "    try:",
            "        while True:",
            ("{}", 'actions'),
            "    except Break as e:",
            "        pass",
            "    except CircuitError as e:",
            "        raise e.orig_exception",
            "    except Exception as e:",
            "        raise HandlerError(current, e)",
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
            "if pauser.enter_if_pending_pause():",
            ("{}", 'on_pause'),
            "    try:",
            "        pauser.clear()",
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
        
        def _build_invoke_action(event, notify, await_):
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
                    case 'result_bridge':
                        lines.append(code.format(f"'{event}'"))
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
                    case _:
                        snip = action_snippets.get(tag, None)
                        if snip:
                            lines.extend(INDENT + h for h in snip)
                
            return _build_template(_CIRCUIT_TEMPLATE, _tag_processor)


        class CircuitFactory:
            __slots__ = ()
            # Has no interface
            
            @staticmethod
            def build_circuit_full_code(name):
                nonlocal _circuit_full_code
                includes_async_function = False
                linear_handler_snippets = {}
                for name, action in injected_hook.get_actions.items():
                    # deploy action: (action, notify_ctx)
                    action, notify_ctx = action
                    async_func = inspect.iscoroutinefunction(action)
                    includes_async_function |= async_func
                    linear_handler_snippets[name] =\
                        _build_invoke_action(name, notify_ctx, async_func)
                
                pauser_handler_snippets = {}
                for name, handler in injected_hook.get_phase_handlers().items():
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
                    name, includes_async_function,
                    linear_handler_snippets, pausable_snippet
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
                    "HandlerError": loop_env.HandlerError,
                    "CircuitError": loop_env.CircuitError,
                    "Break": loop_env.Break,
                }
                dst = {}
                exec(_circuit_full_code, namespace, dst)
                _generated_circuit = dst[CIRCUIT_NAME]
                return _generated_circuit

        return CircuitFactory()

    def _load_task_control(state):

        _task = None

        class Interface:
            __slots__ = ()
            @property
            def is_running(_):
                return _task is not None and not _task.done()
            
            @staticmethod
            def stop():
                def cancel_task():
                    if TaskControl.is_running:
                        _task.cancel()
                return state.maintain_state(state.ACTIVE, cancel_task)
        
        _interface = Interface()

        class TaskControl(Interface):
            __slots__ = ()
            @property
            def interface(_):
                return _interface
            @staticmethod
            def start(async_fn):
                def create_task():
                    nonlocal _task
                    _task = asyncio.create_task(async_fn)
                    return _task
                return state.transit_state_with(state.ACTIVE, create_task)
        
        return TaskControl()


    STATIC_CIRCUIT_NAME = '_static_circuit'

    _spec = _load_loop_specification()
    _state = _load_state()
    _injected_hook = _load_loop_cofig(_spec, _state)
    _loop_environment = _load_loop_environment(_spec, _state, _injected_hook)

    _circuit_factory = _load_circuit_factory(_spec, _loop_environment, _injected_hook)
    
    _task_control = _load_task_control(_state)

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
        
        @property
        def start(_):
            return _task_control.start
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
