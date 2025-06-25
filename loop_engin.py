import asyncio
import inspect
from types import SimpleNamespace
import logging

def make_loop_engine_handle(role: str, note: str, logger = None):
    if not logger:
        logger = logging.getLogger(__name__)

    LOAD = 0
    ACTIVE = 1
    CLOSED = 2
    RUNNING = 10 #sub-state of ACTIVE commute to PAUSE
    PAUSE = 11 #sub-state of ACTIVE commute to RUNNING
    MEANS_CLOSED = (CLOSED,)

    _state = LOAD #assign only main state(LOAD, ACTIVE, CLOSED)
    _mode = RUNNING #assign only sub state(RUNNING, PAUSE)
    _running = asyncio.Event()

    class HandleStateError(Exception):
        pass
    class HandleClosed(HandleStateError):
        pass

    def _check_state(*expected: int, error_msg: str, notify_closed: bool = True) -> None:
        if _state in expected:
            return
        err_log = f"{error_msg} (expected = {expected}, actual = {_state})"
        if _state in MEANS_CLOSED and notify_closed:
            raise HandleClosed(err_log)
        raise HandleStateError(err_log)
    
    def _check_mode(*expected: int, error_msg: str) -> None:
        if _mode in expected:
            return
        raise HandleStateError(f"{error_msg} (expected = {expected}, actual = {_mode})")
    

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

    _meta = SimpleNamespace()

    handle._split = _split
    handle.meta = _meta


    handle.LOAD = LOAD
    handle.ACTIVE = ACTIVE
    handle.CLOSED = CLOSED
    handle.HandleStateError = HandleStateError
    handle.HandleClosed = HandleClosed

    # --- internal state ---
    _SUCCESS = True
    _FAILED = False

    _on_start = None
    _on_end = None
    _on_stop = None
    _on_pause = None
    _on_resume = None
    _on_closed = None
    _on_tick_before = None
    _on_tick = None
    _on_tick_after = None
    _on_exception = None
    _on_interval = lambda: None
    _next = lambda: True

    _loop_task = None

    _common_context = None

    def _default_handler_caller(handler, *args, **kwargs):
        return handler(_common_context) #Note:共通コンテキスト以外の引数について決まっていない。
    
    _handler_caller = _default_handler_caller

    # --- handler call helper ---
    async def _call_handler(handler, obj):
        if not handler:
            return
        try:
            result = _handler_caller(handler, ...) #現時点でコーラーに渡す情報はない
            if inspect.isawaitable(result):
                await result
        except Exception as e:
            #Note:_handler_callerを導入したことにより、ここには
            #handlerが投げた例外ではない例外も補足されていることに注意
            #CONSIDER: _handler_callerはハンドラからの例外を伝播させないという
            #仕様を定めるか？いや、handler_callerから上に上ってきた例外は無条件で
            #再スローされるという仕様の方がいい。か

            #Note: ここで、例えば、_on_handler_excpeptionのような
            #ハンドラーに例外を投げたhandlerを渡して、回復処理ができるか？
            #回復処理ができれば（回復不能、またはその必要なしという判断も含めて）
            #例外を握りつぶす実装を入れることも視野に入る
            logger.exception("handler_caller error")
            raise

    async def _loop():
        nonlocal _state
        _check_state(LOAD, error_msg="loop() must be called in LOAD state")
        nonlocal _on_start, _on_end, _on_tick_before, _on_tick_after, _on_tick
        try:
            await _call_handler(_on_start, handle)
            while _next():
                await _call_handler(_on_tick_before, handle)
                await _call_handler(_on_tick, handle)
                await _call_handler(_on_tick_after, handle)
                await _on_interval()
                await _running.wait()
            await _call_handler(_on_end, handle)
        except asyncio.CancelledError as e:
            logger.info("Loop was cancelled by stop()")
            await _call_handler(_on_stop, handle)
        except Exception:
            logger.exception("Unhandled exception in _loop()")
            raise
        finally:
            await _call_handler(_on_closed, handle)
            _state = CLOSED
    
    def start():
        nonlocal _state, _loop_task
        _check_state(LOAD, error_msg="start() must be called in LOAD state")
        _state = ACTIVE
        _loop_task = asyncio.create_task(_loop())

    def stop():
        _check_state(ACTIVE, error_msg="stop() must be called in ACTIVE state")
        _loop_task.cancel()
    
    def pause():
        nonlocal _mode
        _check_state(ACTIVE, error_msg="pause() only allowed in ACTIVE")
        _check_mode(RUNNING, error_msg="pause() only allowed from RUNNING")
        _mode = PAUSE
        _running.clear()

    def resume():
        nonlocal _mode
        _check_state(ACTIVE, error_msg="resume() only allowed in ACTIVE")
        _check_mode(PAUSE, error_msg="resume() only allowed from PAUSE")
        _mode = RUNNING
        _running.set()


    # --- explicit handler setters ---

    def _check_state_is_load_for_setter(setter):
        _check_state(LOAD, error_msg=f"{setter.__name__} only allowed in LOAD")

    def set_on_start(fn):
        nonlocal _on_start
        _check_state_is_load_for_setter(set_on_start)
        _on_start = fn

    def set_on_end(fn):
        nonlocal _on_end
        _check_state_is_load_for_setter(set_on_end)
        _on_end = fn

    def set_on_stop(fn):
        nonlocal _on_stop
        _check_state_is_load_for_setter(set_on_stop)
        _on_stop = fn

    def set_on_closed(fn):
        nonlocal _on_closed
        _check_state_is_load_for_setter(set_on_closed)
        _on_closed = fn

    def set_on_tick_before(fn):
        nonlocal _on_tick_before
        _check_state_is_load_for_setter(set_on_tick_before)
        _on_tick_before = fn

    def set_on_tick(fn):
        nonlocal _on_tick
        _check_state_is_load_for_setter(set_on_tick)
        _on_tick = fn

    def set_on_tick_after(fn):
        nonlocal _on_tick_after
        _check_state_is_load_for_setter(set_on_tick_after)
        _on_tick_after = fn

    def set_on_interval(fn):
        nonlocal _on_interval
        _check_state_is_load_for_setter(set_on_interval)
        _on_interval = fn

    def set_next(fn):
        nonlocal _next
        _check_state_is_load_for_setter(set_next)
        _next = fn

    def set_on_pause(fn):
        nonlocal _on_pause
        _check_state_is_load_for_setter(set_on_pause)
        _on_pause = fn

    def set_on_resume(fn):
        nonlocal _on_resume
        _check_state_is_load_for_setter(set_on_resume)
        _on_resume = fn

    def set_on_exception(fn):
        nonlocal _on_exception
        _check_state_is_load_for_setter(set_on_exception)
        _on_exception = fn

    def set_handler_caller(fn):
        nonlocal _handler_caller
        _check_state_is_load_for_setter(set_handler_caller)
        _handler_caller = fn

    def set_common_context(obj):
        nonlocal _common_context
        _check_state_is_load_for_setter(set_common_context)
        _common_context = obj


    # --- bind to handle ---
    handle.set_on_start = set_on_start
    handle.set_on_end = set_on_end
    handle.set_on_stop = set_on_stop
    handle.set_on_pause = set_on_pause
    handle.set_on_resume = set_on_resume
    handle.set_on_closed = set_on_closed
    handle.set_on_tick_before = set_on_tick_before
    handle.set_on_tick = set_on_tick
    handle.set_on_tick_after = set_on_tick_after
    handle.set_on_exception = set_on_exception
    handle.set_on_interval = set_on_interval
    handle.set_next = set_next

    handle.set_handler_caller = set_handler_caller
    handle.set_common_context = set_common_context

    handle.start = start
    handle.stop = stop
    handle.pause = pause
    handle.resume = resume

    return handle