
import asyncio
import inspect
import logging

from types import SimpleNamespace

from typing import Any, Awaitable, Callable, Union, Protocol

import textwrap


_Handler = Callable[[Any], Union[Any, Awaitable[Any]]]

class LoopEngineHandleProtocol(Protocol):
    # --- 基本操作 ---
    def start(self) -> None: ...
    def ready(self) -> Awaitable[Any]: ...
    def stop(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...

    # --- イベントハンドラ設定 ---
    def set_on_start(self, fn: _Handler) -> None: ...
    def set_on_pause(self, fn: _Handler) -> None: ...
    def set_on_resume(self, fn: _Handler) -> None: ...
    def set_on_end(self, fn: _Handler) -> None: ...
    def set_on_stop(self, fn: _Handler) -> None: ...
    def set_on_closed(self, fn: _Handler) -> None: ...
    def set_on_result(self, fn: _Handler) -> None: ...
    def set_should_stop(self, fn: _Handler) -> None: ...
    def set_on_tick_before(self, fn: _Handler) -> None: ...
    def set_on_tick(self, fn: _Handler) -> None: ...
    def set_on_tick_after(self, fn: _Handler) -> None: ...
    def set_on_wait(self, fn: _Handler) -> None: ...
    def set_on_handler_exception(self, fn: _Handler) -> None: ...
    def set_on_circuit_exception(self, fn: _Handler) -> None: ...
    def set_context_builder_factory(self, fn: Callable[..., Any]) -> None: ...

    # --- メタ・属性 ---
    @property
    def meta(self) -> Any: ...

    # --- ヘルパ ---
    def _split(self, *names: str) -> Callable[[], int]: ...

    # --- 定数類 ---
    LOAD: int
    ACTIVE: int
    CLOSED: int
    UNCLEAN: int
    RUNNING: int
    PAUSE: int
    NO_RESULT: Any

    # --- エラークラス ---
    HandleStateError: type
    HandleClosed: type

    # --- 呼び出し可能本体（handle(...)でmeta登録） ---
    def __call__(self, **kwargs: Any) -> "LoopEngineHandleProtocol": ...


logging.basicConfig(level=logging.INFO)

def make_loop_engine_handle(role: str = 'loop', logger = None) -> LoopEngineHandleProtocol:

    if not logger:
        logger = logging.getLogger(__name__)
    
    class Break(Exception):
        pass
    
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
        
        class StateInterface:
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


        class State(StateInterface):
            __slots__ = ()
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
    
    def _load_injected_hook(state):
        
        def _DEFAULT_CPF(interface):
            def context_updater(event):
                return interface
            return context_updater, interface

        _handlers = {} # event: tuple(handler, notify)
        _context_updater_factory = _DEFAULT_CPF
        _pausable = True

        class InjectedHook:
            __slots__ = ()
            @staticmethod
            def set_handler(event, handler, notify):
                def fn(): _handlers[event] = (handler, notify)
                state.maintain_state(state.LOAD, fn)

            @staticmethod
            def get_handler(event):
                return _handlers.get(event, None)
            
            @staticmethod
            def set_context_updater_factory(ctx_updater_factory):
                def fn():
                    nonlocal _context_updater_factory
                    _context_updater_factory = ctx_updater_factory
                state.maintain_state(state.LOAD, fn)

            @staticmethod
            def get_context_updater_factory():
                return _context_updater_factory
            
            @staticmethod
            def set_pausable(flag):
                def fn():
                    nonlocal _pausable
                    _pausable = flag
                state.maintain_state(state.LOAD, fn)

            @staticmethod
            def cirucit_is_pausable():
                return _pausable
        
        return InjectedHook()


    def _load_loop_environment(state_, injected_hook, circuit_factory):

        # Each handler's return value is always updated via _result_bridge.set_prev.
        # Therefore, if a specific handler depends on the return value from another,
        # all intermediate handlers must propagate the return value properly.
        # In particular, be careful with on_pause and on_resume,
        # as they may not be called in a strictly linear sequence.

        RUNNING = 10 # Sub-state of ACTIVE commute to PAUSE
        PAUSE = 11 # Sub-state of ACTIVE commute to RUNNING

        LOOP_PENDING_RESULT = object()
        NO_RESULT = object()

        _loop_task = None
        
        _prev_event = None
        _prev_result = None

        _mode = RUNNING
        _event = asyncio.Event()
        _pending_pause = False
        _pending_resume = False

        _exc = None
        _nested_exc = None

        # not target of cleanup
        _loop_result = LOOP_PENDING_RESULT

        def clean_environment():
            nonlocal _loop_task, _prev_event, _prev_result, _event, _exc, _nested_exc
            _loop_task = None
            _prev_event = None
            _prev_result = None
            _event = None
            _exc = None
            _nested_exc = None
        
        class LoopResultReader:
            __slots__ = ()
            @property
            def LOOP_PENDING_RESULT(_):
                return LOOP_PENDING_RESULT
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
            def set_pause():
                nonlocal _pending_pause
                _pending_pause = True
            @staticmethod
            def set_resume():
                nonlocal _pending_resume
                _pending_resume = True
                _event.set()
            @property
            def current_mode(_):
                return _mode

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
            def current(_):
                return _mode
            @property
            def pending_pause(_):
                return _pauser.pending_pause
            @property
            def pending_resume(_):
                return _pauser.pending_resume
        
        _mode_reader = ModeReader()


        class LoopInterface:

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
            def role(_):
                return role
            @property
            def state(_):
                return state_.state
            @property
            def mode(_):
                return _mode_reader
            @property
            def result_reader(_):
                return _handler_result_reader
            @property
            def task(_):
                return _loop_task
        

        _loop_interface = LoopInterface()


        async def _invoke_handler(event, ctx_updater, ctx):
            handler = injected_hook.get_handler(event)
            if not handler:
                return
            # deploy handler: (handler, notify)
            handler, notify = handler
            if notify:
                ctx_updater(event)
            try:
                tmp = handler(ctx)
                result = await tmp if inspect.isawaitable(tmp) else tmp
                _result_bridge.set_prev(event, result)
            except Exception as e:
                raise LoopInterface.HandlerError(event, e)

        async def _loop_engine(circuit):
            nonlocal _loop_result, _exc, _nested_exc
            try:
                loop_interface = _loop_interface
                ctx_updater, ctx = injected_hook.get_context_updater_factory(
                    loop_interface)
                
                await _invoke_handler('on_start', ctx_updater, ctx)

                if inspect.iscoroutinefunction(circuit):
                    await circuit(ctx_updater, ctx, _result_bridge, _pauser)
                else:
                    circuit(ctx_updater, ctx, _result_bridge, _pauser)
                
                await _invoke_handler('on_end', ctx_updater, ctx)

            except asyncio.CancelledError as e:
                _exc = e
                logger.info(f"[{role}] Loop was cancelled")
                try:
                    await _invoke_handler('on_stop', ctx_updater, ctx)
                except Exception as nested_exc:
                    _nested_exc = nested_exc
                    raise nested_exc from e
            except LoopInterface.HandlerError as e:
                event = e.event
                orig_e = e.orig_exception
                _exc = e
                logger.exception(f"[{role}] {event} Handler failed")
                try:
                    await _invoke_handler('on_handler_exception', ctx_updater, ctx)
                except Exception as nested_exc:
                    _nested_exc = nested_exc
                    raise nested_exc from e
                raise orig_e from None
            except Exception as e:
                _exc = e
                logger.exception(f"[{role}] Unknown exception in circuit")
                try:
                    await _invoke_handler('on_circuit_exception', ctx_updater, ctx)
                except Exception as nested_exc:
                    _nested_exc = nested_exc
                    raise nested_exc from e
                raise
            finally:
                # Currently, exceptions raised from on_closed or on_result are not handled.
                # Consider whether to introduce explicit handlers or allow propagation.
                # Additional note: Exceptions thrown by these two are not captured in _exc.
                try:
                    await _invoke_handler('on_closed', ctx_updater, ctx)
                    state_.transit_state(state_.CLOSED)
                except Exception:
                    logger.exception(f"[{role}] on_closed handler failed")
                    state_.transit_state(state_.UNCLEAN)
                try:
                    await _invoke_handler('on_result', ctx_updater, ctx)
                    _loop_result = _result_bridge.prev_result
                    return
                except Exception:
                    logger.exception(f"[{role}] on_result handler failed")
                    _loop_result = NO_RESULT
                    return
                finally:
                    clean_environment()


        class LoopEnvironment:
            __slots__ = ()
            @staticmethod
            def loop_start(circuit):
                _loop_engine(circuit)
            @property
            def pauser(_):
                return _pauser
            @property
            def result_reader(_):
                return _loop_result_reader
        

        return LoopEnvironment()



    def _load_circuit_factory(injected_hook, loop_environment):
    
        _CIRCUIT_TEMPLATE = [
            ("{}def {}(ctx_updater, ctx, result_bridge, pauser):", 'define'),
            "    current = ''",
            "    result = None",
            "    try:",
            "        while True:",
            ("{}", 'should_stop'),
            ("{}", 'on_tick_befoer'),
            ("{}", 'on_tick'),
            ("{}", 'on_tick_after'),
            ("{}", 'on_wait'),
            ("{}", 'pausable'),
            "    except Break as e:",
            "        pass",
            "    except CircuitError as e:",
            "        raise e.orig_exception",
            "    except Exception as e:",
            "        raise HandlerError(current, e)",
        ]

        _EVENT_IN_CIRCUIT_INDENT = 8
        
        _INVOKE_HANDLER_TEMPLATE = [
            ("current = '{}'", 'current_event'),
            ("{}", 'notify'),
            ("result = {}{}(ctx)", 'invoke_handler'),
            ("result_bridge.set_prev(current, result)", 'result_bridge'),
        ]

        _PAUSABLE_TEMPLATE = [
            "if pauser.enter_if_pending_pause():",
            ("{}", 'on_pause'),
            "    try:",
            "        pauser.clear()",
            "    except Exception as e:",
            "        raise CircuitError(e)",
            "",
            "if pauser.enter_if_pending_resume():",
            ("{}", 'on_resume'),
            "    pass",
            "try:",
            "    await pauser.wait()",
            "except Exception as e:",
            "    raise CircuitError(e)",
        ]

        _EVENT_IN_PAUSABLE_INDENT = 4

        _HANDLER_IN_CIRCUIT = {
            'should_stop',
            'on_tick_before',
            'on_tick',
            'on_tick_after',
            'on_wait',
            'on_pause',
            'on_resume'
        }

        _circuit_full_code = None
        _generated_circuit = None

        class CircuitFactory:
            __slots__ = ()
            @staticmethod
            def _build_template(template, tag_processor):
                lines = []
                for line in template:
                    match(line):
                        case str() as code:
                            lines.append(code)
                        case (code, tag):
                            tag_processor(lines, code, tag)
                return lines
            
            @staticmethod
            def _build_invoke_handler(event, notify, await_):
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
                            if event in ('on_pause', 'on_resume'):
                                pass
                            else:
                                lines.append(code)
                        case _:
                            raise ValueError(f"Unknown tag in template: {tag}")
                
                return CircuitFactory._build_template(
                   _INVOKE_HANDLER_TEMPLATE, _tag_processor)
            
            @staticmethod
            def _build_pausable(handler_snippets):
                def _tag_processor(lines, code, tag):
                    INDENT = _EVENT_IN_PAUSABLE_INDENT
                    match(tag):
                        case _:
                            snip = handler_snippets.get(tag, None)
                            if snip:
                                lines.extend(INDENT + s for s in snip)

                return CircuitFactory._build_template(
                    _PAUSABLE_TEMPLATE, _tag_processor)
            
            @staticmethod
            def _build_circuit(handler_snippets, pausable_snippet):
                def _tag_processor(lines, code, tag):
                    INDENT = _EVENT_IN_CIRCUIT_INDENT
                    match(tag):
                        case 'pausable':
                            if pausable_snippet:
                                lines.extend(INDENT + p for p in pausable_snippet)
                        case _:
                            snip = handler_snippets.get(tag, None)
                            if snip:
                                lines.extend(INDENT + h for h in snip)
                    
                return CircuitFactory._build_template(
                _CIRCUIT_TEMPLATE, _tag_processor)

            @staticmethod
            def build_circuit_full_code(name):
                nonlocal _circuit_full_code
                includes_async_function = False
                handler_snippets = {}
                for event in _HANDLER_IN_CIRCUIT:
                    handler = injected_hook.get_handler(event)
                    if not handler:
                        continue
                    # deploy handler: (handler, notify)
                    handler, notify = handler
                    async_func = inspect.iscoroutinefunction(handler)
                    includes_async_function |= async_func
                    handler_snippets[event] =\
                        CircuitFactory._build_invoke_handler(
                            event, notify, async_func)
                
                pausable_snippet = CircuitFactory._build_pausable(
                    handler_snippets
                ) if injected_hook.circuit_is_pausable else None

                all_snippets = CircuitFactory._build_circuit(
                    handler_snippets, pausable_snippet
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
                    "HandlerError": loop_environment.interface.HandlerError,
                    "CircuitError": loop_environment.interface.CircuitError,
                    "Break": loop_environment.interface.Break,
                }
                dst = {}
                exec(_circuit_full_code, namespace, dst)
                _generated_circuit = dst[CIRCUIT_NAME]
                return _generated_circuit

        return CircuitFactory()
    
    #==================================================================================
    # def _static_circuit(ctx_updater, ctx, result_bridge, pauser):
    #     ...
    # If a circuit with this name is defined, _load_circuit_factory will be skipped,
    # and the loop will start directly using the predefined circuit.
    # This serves as a placeholder for hardcoding a generated circuit.
    # If _static_circuit is defined and _load_circuit_factory is no longer used,
    # the _load_circuit_factory function can be safely removed from the codebase.
    #==================================================================================

    STATIC_CIRCUIT_NAME = '_static_circuit'

    _state = _load_state()
    _injected_hook = _load_injected_hook(_state)
    _loop_environment = _load_loop_environment(_state)

    _circuit = locals().get(STATIC_CIRCUIT_NAME, None)
    if not _circuit:
        _circuit_factory = _load_circuit_factory(_injected_hook, _loop_environment)
    
    # This function is currently under development.
    # The loop does not start; the purpose here is to inspect the dynamically generated code.
    

    _meta = SimpleNamespace()



    def start():
        '''
        Launches the main loop as a background task.
        This function is asynchronous, but does not wait for the loop to finish.
        The loop runs independently in the background.
        '''
        _check_state(LOAD, error_msg="start() must be called in LOAD state")
        _state = ACTIVE
        _running_event.set()
        _loop_task = asyncio.create_task(_loop_engine())
    
    def ready():
        '''
        Prepares the main loop coroutine for manual execution.

        This function does not start the loop immediately.
        Instead, it returns a coroutine object that the caller can await explicitly.
        The loop enters ACTIVE state only when the returned coroutine is awaited.
        This is useful for advanced control scenarios such as testing or synchronized multi-loop execution.
        '''
        _check_state(LOAD, error_msg="ready() must be called in LOAD state")
        coro = _loop_engine()

        async def wrapped():
            nonlocal _state
            _state = ACTIVE
            _running_event.set()
            return await coro

        return wrapped()

    # def stop():
    #     _check_state(ACTIVE, error_msg="stop() must be called in ACTIVE state")
    #     if not _loop_task:
    #         raise RuntimeError("Cannot call stop(): loop started via ready()"
    #                            "and is not externally controllable")
    #     if _loop_task and not _loop_task.done():
    #         _loop_task.cancel()
    
    # def pause():
    #     _check_state(ACTIVE, error_msg="pause() only allowed in ACTIVE")
    #     _check_mode(RUNNING, error_msg="pause() only allowed from RUNNING")
    #     _running_setter.set_pause()

    # def resume():
    #     _check_state(ACTIVE, error_msg="resume() only allowed in ACTIVE")
    #     _check_mode(PAUSE, error_msg="resume() only allowed from PAUSE")
    #     _running_setter.set_resume()

    def dump_circuit():
        code = _circuit_factory.build_circuit_full_code('_dynamic_circuit')
        # This module is currently under development.
        # The loop does not start; the purpose here is to inspect the dynamically generated code.
        print(code)

    # --- explicit handler setters ---
    def set_on_start(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_start', fn, notify)

    def set_on_end(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_end', fn, notify)

    def set_on_stop(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_stop', fn, notify)

    def set_on_closed(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_closed', fn, notify)

    def set_on_tick_before(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_tick_before', fn, notify)

    def set_on_tick(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_tick', fn, notify)

    def set_on_tick_after(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_tick_after', fn, notify)

    def set_on_wait(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_wait', fn, notify)

    def set_should_stop(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('should_stop', fn, notify)

    def set_on_pause(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_pause', fn, notify)

    def set_on_resume(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_resume', fn, notify)

    def set_on_handler_exception(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_handler_exception', fn, notify)

    def set_on_circuit_exception(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_circuit_exception', fn, notify)

    def set_on_result(fn: _Handler, notify=False):  # type: ignore
        _injected_hook.set_handler('on_result', fn, notify)
    
    def set_context_builder_factory(fn):
        _injected_hook.set_context_updater_factory(fn)
    


    # --- bind to handle ---
    def handle(**kwargs):
        '''
        The handle functions as a container that provides the interface to the driver.

        When invoked with keyword arguments, it assigns metadata to the handle.  
        This metadata can be accessed via `handle.meta.xxx`.  
        This function returns the handle itself.
        '''
        vars(_meta).update(kwargs)
        return handle

    def _split(*names):
        def new_handle():
            return id(handle)
        vars(new_handle).update({k: getattr(handle, k) for k in names})
        return new_handle

    handle._split = _split
    handle.meta = _meta

    handle.start = start
    handle.ready = ready
    # handle.stop = stop
    # handle.pause = pause
    # handle.resume = resume

    handle.set_pausable = _injected_hook.set_pausable

    #handle.compile = compile
    handle.dump_circuit = dump_circuit

    handle.set_on_start = set_on_start
    handle.set_on_pause = set_on_pause
    handle.set_on_resume = set_on_resume
    handle.set_on_end = set_on_end
    handle.set_on_stop = set_on_stop
    handle.set_on_closed = set_on_closed
    handle.set_on_result = set_on_result
    
    handle.set_should_stop = set_should_stop
    handle.set_on_tick_before = set_on_tick_before
    handle.set_on_tick = set_on_tick
    handle.set_on_tick_after = set_on_tick_after
    handle.set_on_wait = set_on_wait
    
    handle.set_on_handler_exception = set_on_handler_exception
    handle.set_on_circuit_exception = set_on_circuit_exception

    return handle


handle = make_loop_engine_handle()

# 各ハンドラを登録
handle.set_on_tick(lambda ctx: print("tick"))
handle.set_on_wait(lambda ctx: print("wait"))
handle.set_should_stop(lambda ctx: False)

# サーキットコードをダンプ出力
handle.dump_circuit()


# import random
# from datetime import datetime, timedelta

# async def main():

#     h = make_loop_engine_handle()

#     def should_stop(ctx):
#         if ctx.count >= 1000:
#             raise ctx.env.signal.Break

#     def on_tick(ctx):
#         print(f'\r{"( ˶°ㅁ°) !!" if ctx.count % 2 == 0 else "!!(°ㅁ°˶ )"} {"|/-\\"[ctx.count % 4]}', end='')
#         #print(f"{' ' * ctx.count} ┏(‘o’)┛ ┏(‘o’)┛ ┏(‘o’)┛", end ="\r")
#         #print(' ' + ("tick" if ctx.count % 2 == 0 else "tack") + str(ctx.count), end="\r")
#         #print(f"{' ' * 30}{'(|)  (0v0)  (|)' if (ctx.count % 2) == 0 else '(\\/) (0v0) (\\/)'}", end="\r")
#         #print(ctx.count, end="\r")

#     async def on_wait(ctx):
#         await asyncio.sleep(0.5)

#     def on_pause(ctx):
#         print("pause")

#     def on_resume(ctx):
#         print("resume!")
    
#     def on_end(ctx):
#         print("end!")
    
#     def on_stop(ctx):
#         print("stop!")

#     def on_handler_exception(ctx):
#         print(ctx.env.exc)
    
#     def on_circuit_exception(ctx):
#         print(ctx.env.exc)
    
#     def on_result(ctx):
#         print("on_result")
#         print(ctx.env)
#         print(type(ctx.env.exc))
    
#     # 必須イベントハンドラを登録（circuitに入るものだけで十分）
#     #h.set_should_stop(dummy_handler)
#     #h.set_on_tick_before(dummy_handler)
#     h.set_should_stop(should_stop)
#     h.set_on_tick(on_tick)
#     #h.set_on_tick_after(dummy_handler)
#     h.set_on_wait(on_wait)
#     #h.set_on_pause(on_pause)
#     #h.set_on_resume(on_resume)
#     #h.set_on_end(on_end)
#     #h.set_on_stop(on_stop)
#     #h.set_on_handler_exception(on_handler_exception)
#     #h.set_on_circuit_exception(on_circuit_exception)
#     #h.set_on_result(on_result)

#     # コンパイルしてcircuitコードの出力を確認
#     h.compile()
#     #loop_coro = h.ready()  # コルーチンを取得（まだ開始されていない）
#     h.start()

#     # # 別タスクとしてループ起動
#     # task = asyncio.create_task(loop_coro)

#     # # 1分間だけ実行し、途中で pause/resume をランダムに実行
#     # end_time = datetime.now() + timedelta(seconds=20)
#     # while datetime.now() < end_time:
#     #     await asyncio.sleep(random.uniform(5, 10))  # 5〜10秒おきに発火
#     #     h.pause()
#     #     await asyncio.sleep(random.uniform(2, 4))  # 少し停止してから
#     #     h.resume()

#     # # 最後にループを止める（任意で明示）
#     # task.cancel()

#     #await task  # ループタスクの終了を待つ

#     await asyncio.sleep(30)

#     print("end")

# # 実行
# asyncio.run(main())