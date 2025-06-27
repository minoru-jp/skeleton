
import asyncio
import inspect
import logging

from types import SimpleNamespace

from typing import Any, Awaitable, Callable, Union, Protocol


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

    LOAD = 0
    ACTIVE = 1
    RUNNING = 10 # Sub-state of ACTIVE commute to PAUSE
    PAUSE = 11 # Sub-state of ACTIVE commute to RUNNING
    CLOSED = 2
    UNCLEAN = 20 # Terminal-state used instead of BROKEN if _on_closed() fails
    TERMINAL_STATES = (CLOSED, UNCLEAN)

    NO_RESULT = object()

    _state = LOAD # LOAD -> ACTIVE -> CLOSED | UNCLEAN

    _mode = RUNNING # RUNNING <-> PAUSE
    _running = asyncio.Event()
    _pending_pause = False
    _pending_resume = False

    _broken = False

    _prev_event = ''
    _prev_result = None
    
    _loop_task = None

    _meta = SimpleNamespace()
    
    
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
    _context_builder = lambda *a, **kw: None

    _handlers = {
        'on_start': None,
        'on_pause': None,
        'on_resume': None,
        'on_end': None,
        'on_stop': None,
        'on_closed': None,
        'on_result': None,
        'should_stop': None,
        'on_tick_before': None,
        'on_tick': None,
        'on_tick_after': None,
        'on_wait': None,
        'on_handler_exception': None,
        'on_circuit_exception': None
    }
    

    async def _invoke_handler_auto(event, **extra_ctx):
        nonlocal _state, _broken, _prev_event, _prev_result
        try:
            handler = _handlers[event]
            if not handler:
                return
            ctx = _context_builder(
                event,
                prev_event = _prev_event,
                prev_result = _prev_result,
                pending_pause = _pending_pause,
                pending_resume = _pending_resume,
                **extra_ctx
            )
            tmp = handler(ctx)
            result = await tmp if inspect.isawaitable(tmp) else tmp
            _prev_event = event
            _prev_result = result
            return result
        except Exception as e:
            logger.exception(f"[{role}] Handler {event} failed")
            _broken = True
            try:
                ex_event = "on_handler_exception"
                ex_handler = _handlers[ex_event]
                if ex_handler:
                    ctx = _context_builder(ex_event, e=e, failed=event, **extra_ctx)
                    tmp = ex_handler(ctx)
                    result = await tmp if inspect.isawaitable(tmp) else tmp
                    _prev_event = ex_event
                    _prev_result = result
            except Exception as nested_e:
                logger.exception(f"[{role}] Handler exception handler itself failed")
                raise nested_e from e
            raise
    
    async def _resolve_pause_resume():
        nonlocal _mode, _pending_pause, _pending_resume
        if _pending_pause:
            _pending_pause = False
            await _invoke_handler_auto('on_pause')
            _mode = PAUSE
            _running.clear()
        if _pending_resume:
            _pending_resume = False
            _mode = RUNNING
            await _invoke_handler_auto('on_resume')
            _running.set()

    async def _loop():
        nonlocal _state, _prev_event, _prev_result, _loop_task, _meta
        try:
            _ = _context_builder(
                'init',
                role = role,
                LOAD = LOAD, ACTIVE = ACTIVE,
                CLOSED = CLOSED, UNCLEAN = UNCLEAN,
                RUNNING = RUNNING, PAUSE = PAUSE)
            await _invoke_handler_auto('on_start')
            while True:
                if await _invoke_handler_auto('should_stop'):
                    break
                await _invoke_handler_auto('on_tick_before')
                await _invoke_handler_auto('on_tick')
                await _invoke_handler_auto('on_tick_after')
                await _invoke_handler_auto('on_wait')
                await _resolve_pause_resume()
                await _running.wait()
            await _invoke_handler_auto('on_end')
        except asyncio.CancelledError as e:
            logger.info(f"[{role}] Loop was cancelled")
            await _invoke_handler_auto('on_stop')
        except Exception as e:
            if _broken:
                raise
            logger.exception(f"[{role}] Unknown exception in circuit")
            _broken = True
            try:
                ex_event = "on_circuit_exception"
                ex_handler = _handlers[ex_event]
                if ex_handler:
                    ctx = _context_builder(ex_event, e=e)
                    tmp = ex_handler(ctx)
                    result = await tmp if inspect.isawaitable(tmp) else tmp
                    _prev_event = ex_event
                    _prev_result = result
            except Exception as nested_e:
                raise nested_e from e
            raise
        finally:
            try:
                await _invoke_handler_auto(
                    'on_closed',
                    state = _state,
                    mode = _mode,
                    broken = _broken,
                    loop_task = _loop_task)
                _state = CLOSED
            except Exception:
                _state = UNCLEAN
            try:
                return await _invoke_handler_auto(
                    'on_result', state = _state, mode = _mode, broken = _broken)
            except Exception:
                return NO_RESULT
            finally:
                _context_builder = None
                _handlers.clear()
                _prev_result = None
                _loop_task = None
                _meta = None

    def _check_state(*expected: int, error_msg: str, notify_closed: bool = True) -> None:
        if _state in expected:
            return
        err_log = f"{error_msg} (expected = {expected}, actual = {_state})"
        if _state in TERMINAL_STATES and notify_closed:
            raise HandleClosed(err_log)
        raise HandleStateError(err_log)
    
    def _check_mode(*expected: int, error_msg: str) -> None:
        if _mode in expected:
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
        _running.set()
        _loop_task = asyncio.create_task(_loop())
    
    def ready():
        '''
        Prepares the main loop coroutine for manual execution.

        This function does not start the loop immediately.
        Instead, it returns a coroutine object that the caller can await explicitly.
        The loop enters ACTIVE state only when the returned coroutine is awaited.
        This is useful for advanced control scenarios such as testing or synchronized multi-loop execution.
        '''
        _check_state(LOAD, error_msg="ready() must be called in LOAD state")
        coro = _loop()

        async def wrapped():
            nonlocal _state
            _state = ACTIVE
            _running.set()
            return await coro

        return wrapped()

    def stop():
        _check_state(ACTIVE, error_msg="stop() must be called in ACTIVE state")
        if _loop_task and not _loop_task.done():
            _loop_task.cancel()
    
    def pause():
        nonlocal _pending_pause
        _check_state(ACTIVE, error_msg="pause() only allowed in ACTIVE")
        _check_mode(RUNNING, error_msg="pause() only allowed from RUNNING")
        _pending_pause = True

    def resume():
        nonlocal _pending_resume
        _check_state(ACTIVE, error_msg="resume() only allowed in ACTIVE")
        _check_mode(PAUSE, error_msg="resume() only allowed from PAUSE")
        _pending_resume = True

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
    
    def set_context_builder(fn):
        nonlocal _context_builder
        _check_state_is_load_for_setter(set_context_builder)
        _context_builder = fn
    


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