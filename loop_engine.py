
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
    def set_context_builder(self, fn: Callable[..., Any]) -> None: ...

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


def make_loop_engine_handle(role: str = 'loop', logger = None) -> LoopEngineHandleProtocol:

    if not logger:
        logger = logging.getLogger(__name__)

    class HandleStateError(Exception):
        pass
    class HandleClosed(HandleStateError):
        pass

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

    LOAD = 0
    ACTIVE = 1
    RUNNING = 10 # Sub-state of ACTIVE commute to PAUSE
    PAUSE = 11 # Sub-state of ACTIVE commute to RUNNING
    CLOSED = 2
    UNCLEAN = 20 # Terminal-state used instead of BROKEN if _on_closed() fails
    TERMINAL_STATES = (CLOSED, UNCLEAN)

    NO_RESULT = object()

    _state = LOAD # LOAD -> ACTIVE -> CLOSED | UNCLEAN
    
    _loop_task = None

    # _context_builder is expected derives from a closure, like this
    # def create_context_builder():
    #    ctx = ...
    #    def context_builder(event, **kwargs):
    #        if event == 'init':
    #            vars(ctx).update(kwargs)
    #        elif event == 'on_start':
    #            ...
    #        elif ...
    #        return ctx
    #    return context_builder
    _context_builder_factory = lambda *a, **kw: None

    _handlers = {}

    def create_running_mode_some():

        _mode = RUNNING
        _event = asyncio.Event()
        _pending_pause = False
        _pending_resume = False

        class RunningModeManager:
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

        class RunningModeSetter:
            __slots__ = ()
            @staticmethod
            def set_pause():
                nonlocal _mode, _pending_pause
                _mode = PAUSE
                _pending_pause = True
            @staticmethod
            def set_resume():
                nonlocal _mode, _pending_resume
                _mode = RUNNING
                _pending_resume = True
        
        class RunningEvent:
            __slots__ = ()
            @staticmethod
            def set():
                _event.set()
            @staticmethod
            def clear():
                _event.clear()
            @staticmethod
            async def wait():
                await _event.wait()
        
        class RunningModeReader:
            __slots__ = ()
            @staticmethod
            def get_mode():
                return _mode
            @staticmethod
            def is_pending_pause():
                return _pending_pause
            @staticmethod
            def is_pending_resume():
                return _pending_resume
        
        return (RunningModeManager(),
                RunningModeSetter(),
                RunningEvent(),
                RunningModeReader())

    running_manager, running_setter, running_event, running_reader =\
        create_running_mode_some()

    def create_result_chain_some():

        _prev_event = ''
        _prev_result = None

        class ResultCleaner:
            __slots__ = ()
            @staticmethod
            def clean():
                nonlocal _prev_event, _prev_result
                _prev_event = None
                _prev_result = None

        class ResultSetter:
            __slots__ = ()
            @staticmethod
            def set_prev(event, result):
                nonlocal _prev_event, _prev_result
                _prev_event = event
                _prev_result = result
        
        class ResultReader:
            __slots__ = ()
            @staticmethod
            def get_prev_event():
                return _prev_event
            @staticmethod
            def get_prev_result():
                return _prev_result
        
        return ResultCleaner(), ResultSetter(), ResultReader()

    result_cleaner, result_setter, result_reader = create_result_chain_some()


    _meta = SimpleNamespace()
    
    async def _loop_engine():
        try:
            init = SimpleNamespace()
            init.role = role
            result_reader = result_reader
            const = SimpleNamespace()
            const.states = SimpleNamespace()
            const.states.LOAD = LOAD
            const.states.ACTIVE = ACTIVE
            const.states.CLOSED = CLOSED
            const.states.UNCLEAN = UNCLEAN
            const.mode = SimpleNamespace()
            const.mode.RUNNING = RUNNING
            const.mode.PAUSE = PAUSE
            signals = SimpleNamespace()
            signals.Break = Break
            ctx_updater = _context_builder_factory(init, const, signals)
            await _invoke_handler('on_start', ctx_updater)
            await _circuit(ctx_updater) 
            await _invoke_handler('on_end', ctx_updater)
        except asyncio.CancelledError as e:
            logger.info(f"[{role}] Loop was cancelled")
            await _invoke_handler('on_stop')
        except HandlerError as e:
            event = e.event
            orig_e = e.orig_exception
            logger.exception(f"[{role}] {event} Handler failed")
            try:
                _invoke_exception_handler('on_handler_exception', e)
            except Exception as nested_e:
                raise nested_e from e
            raise orig_e from None
        except Exception as e:
            logger.exception(f"[{role}] Unknown exception in circuit")
            try:
                _invoke_exception_handler('on_circuit_exception', e)
            except Exception as nested_e:
                raise nested_e from e
            raise
        finally:
            try:
                await _invoke_handler(
                    'on_closed',
                    state = _state,
                    mode = _mode,
                    loop_task = _loop_task)
                _state = CLOSED
            except Exception:
                _state = UNCLEAN
            try:
                return await _invoke_handler(
                    'on_result', state = _state, mode = _mode)
            except Exception:
                return NO_RESULT
            finally:
                _context_builder = None
                _handlers.clear()
                _prev_result = None
                _loop_task = None
                _meta = None

    #asyncの場合、末尾スペースを忘れない->'async '
    _CIRCUIT_TEMPLATE = '''\
    {async_}def {name}(ctx_updater)
        current = ''
        prev = ''
        result = None
        try:
            while True:
                {should_stop}
                {on_tick_before}
                {on_tick}
                {on_tick_after}
                {on_wait}
                {pause_resume}
        except Break as e:
            pass
        except CircuitError as e:
            raise e.orig_exception
        except Exception as e:
            raise HandlerError(current, e)
    '''

    _INVOKE_HANDLER_TEMPLATE = '''\
    current = '{event}'
    {ctx_update}
    result = {await_}{event}(ctx)
    result_setter.set_prev(current, result)
    '''

    _PAUSABLE_TEMPLATE = '''\
    if running_manager.enter_if_pending_pause():
        {on_pause}
        try:
            running_event.clear()
        except Exception as e:
            raise CircuitError(e)

    if running_manager.enter_if_pending_resume():
        {on_resume}
        try:
            running_event.event.set()
        except Exception as e:
            raise CircuitError(e)
    try:
        await running_event.wait()
    except Exception as e:
        raise CircuitError(e)
    '''

    HANDLER_IN_CIRCUIT = {
        'should_stop',
        'on_tick_before',
        'on_tick',
        'on_tick_after',
        'on_wait',
        'on_pause',
        'on_resume'
    }

    def _compile_circuit(
        circuit_name: str,
        handlers: dict[str: callable],
        ctx_updater,
        notify_ctx: bool,
        result_setter,
        running_manager,
        running_event,
        pausable:bool,
        break_exc,
        handler_err_exc,
        circuit_err_exc,
    ) -> tuple:
        includes_async_function = False
        invoking_parts = {}
        ns_for_handlers = {}
        for event, handler in handlers.items():
            if event not in HANDLER_IN_CIRCUIT:
                continue
            async_func = inspect.iscoroutinefunction(handler)
            includes_async_function |= async_func
            invoking_parts[event] = _INVOKE_HANDLER_TEMPLATE.format(
                event = event,
                ctx_update = f'ctx_updater({event})' if notify_ctx else '',
                await_ = 'await ' if async_func else '',
            )
            ns_for_handlers[event] = handler
        
        pause_code = _PAUSABLE_TEMPLATE.format(
            on_pause = invoking_parts.get('on_pause', ''),
            on_resume = invoking_parts.get('on_resume', '')
        ) if pausable else ''

        full_code = textwrap.dedent(_CIRCUIT_TEMPLATE.format(
            async_ = 'async ' if includes_async_function else '',
            name = circuit_name,
            should_stop = invoking_parts.get('should_stop', ''),
            on_tick_before = invoking_parts.get('on_tick_before', ''),
            on_tick = invoking_parts.get('on_tick', ''),
            on_tick_after = invoking_parts.get('on_tick_after', ''),
            on_wait = invoking_parts.get('on_wait', ''),
            pause_resume = pause_code
        ))

        namespace = {
            'ctx_updater': ctx_updater,
            'result_setter': result_setter,
            'running_manager': running_manager,
            'running_event': running_event,
            'Break': break_exc,
            'HandlerError': handler_err_exc,
            'CircuitError': circuit_err_exc,
            **ns_for_handlers
        }
        exec(full_code, globals(), namespace)
        return namespace[circuit_name], full_code


    def _check_state(*expected: int, error_msg: str, notify_closed: bool = True) -> None:
        if _state in expected:
            return
        err_log = f"{error_msg} (expected = {expected}, actual = {_state})"
        if _state in TERMINAL_STATES and notify_closed:
            raise HandleClosed(err_log)
        raise HandleStateError(err_log)
    
    def _check_mode(*expected: int, error_msg: str) -> None:
        if running_reader.get_mode() in expected:
            return
        raise HandleStateError(f"{error_msg} (expected = {expected}, actual = {_mode})")
    

    def start():
        '''
        Launches the main loop as a background task.
        This function is asynchronous, but does not wait for the loop to finish.
        The loop runs independently in the background.
        '''
        nonlocal _state, _loop_task
        _check_state(LOAD, error_msg="start() must be called in LOAD state")
        _state = ACTIVE
        running_event.set()
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
            running_event.set()
            return await coro

        return wrapped()

    def stop():
        _check_state(ACTIVE, error_msg="stop() must be called in ACTIVE state")
        if _loop_task and not _loop_task.done():
            _loop_task.cancel()
    
    def pause():
        _check_state(ACTIVE, error_msg="pause() only allowed in ACTIVE")
        _check_mode(RUNNING, error_msg="pause() only allowed from RUNNING")
        running_setter.set_pause()

    def resume():
        _check_state(ACTIVE, error_msg="resume() only allowed in ACTIVE")
        _check_mode(PAUSE, error_msg="resume() only allowed from PAUSE")
        running_setter.set_pause()

    # --- explicit handler setters ---

    _Handler = Callable[[Any], Union[Any, Awaitable[Any]]]

    def _check_state_is_load_for_setter(setter):
        _check_state(LOAD, error_msg=f"{setter.__name__} only allowed in LOAD")

    def set_on_start(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_start)
        _handlers['on_start'] = fn

    def set_on_end(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_end)
        _handlers["on_end"] = fn

    def set_on_stop(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_stop)
        _handlers["on_stop"] = fn

    def set_on_closed(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_closed)
        _handlers["on_closed"] = fn

    def set_on_tick_before(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_tick_before)
        _handlers["on_tick_before"] = fn

    def set_on_tick(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_tick)
        _handlers["on_tick"] = fn

    def set_on_tick_after(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_tick_after)
        _handlers["on_tick_after"] = fn

    def set_on_wait(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_wait)
        _handlers["on_wait"] = fn

    def set_should_stop(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_should_stop)
        _handlers["should_stop"] = fn

    def set_on_pause(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_pause)
        _handlers["on_pause"] = fn

    def set_on_resume(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_resume)
        _handlers["on_resume"] = fn
    
    def set_on_handler_exception(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_handler_exception)
        _handlers["on_handler_exception"] = fn

    def set_on_circuit_exception(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_circuit_exception)
        _handlers["on_circuit_exception"] = fn
    
    def set_on_result(fn: _Handler): # type: ignore
        _check_state_is_load_for_setter(set_on_result)
        _handlers["on_result"] = fn
    
    def set_context_builder_factory(fn):
        nonlocal _context_builder_factory
        _check_state_is_load_for_setter(set_context_builder_factory)
        _context_builder_factory = fn
    


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

    handle.LOAD = LOAD
    handle.ACTIVE = ACTIVE
    handle.CLOSED = CLOSED
    handle.UNCLEAN = UNCLEAN
    handle.RUNNING = RUNNING
    handle.PAUSE = PAUSE

    handle.NO_RESULT = NO_RESULT

    handle.HandleStateError = HandleStateError
    handle.HandleClosed = HandleClosed

    handle.start = start
    handle.ready = ready
    handle.stop = stop
    handle.pause = pause
    handle.resume = resume

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


h = make_loop_engine_handle()