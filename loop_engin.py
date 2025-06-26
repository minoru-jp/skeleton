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
    UNCLEAN = 99 # Final state used instead of CLOSED if _on_closed() fails
    RUNNING = 10 # Sub-state of ACTIVE commute to PAUSE
    PAUSE = 11 # Sub-state of ACTIVE commute to RUNNING
    MEANS_CLOSED = (CLOSED, UNCLEAN)

    _state = LOAD #assign only main state(LOAD, ACTIVE, CLOSED)
    _mode = RUNNING #assign only sub state(RUNNING, PAUSE)
    _running = asyncio.Event()
    _loop_task = None
    _meta = SimpleNamespace()
    _pending_pause = False
    _pending_resume = False

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

    # --- handler call helper ---
    async def _call_normal_path_handler(handler, loop_info):
        if not handler:
            return
        try:
            result = _handler_caller(handler, _common_context, loop_info)
            if inspect.isawaitable(result):
                await result
        except Exception as e:
            logger.exception("_handler_caller failed")
            if _on_handler_exception:
                try:
                    #再入を防ぐために直接呼び出す(引数は固定)
                    _on_handler_exception(handler)
                except Exception as handle_exception_err:
                    logger.exception(
                        "Unknown exception in _handler_caller()")
                    raise handle_exception_err from e
            raise
    
    async def _resolve_pause_resume(loop_info):
        nonlocal _mode
        if _pending_pause:
            _pending_pause = False
            await _call_normal_path_handler(_on_pause, loop_info)
            _mode = PAUSE
            _running.clear()
        if _pending_resume:
            _pending_resume = False
            _mode = RUNNING
            _running.set()
            await _call_normal_path_handler(_on_resume, loop_info)

    async def _loop():
        nonlocal _state
        _check_state(LOAD, error_msg="loop() must be called in LOAD state")
        info = SimpleNamespace()
        try:
            await _call_normal_path_handler(_on_start, info)
            while _call_normal_path_handler(_next, info):
                await _call_normal_path_handler(_on_tick_before, info)
                await _call_normal_path_handler(_on_tick, info)
                await _call_normal_path_handler(_on_tick_after, info)
                await _call_normal_path_handler(_on_wait, info)
                await _resolve_pause_resume(info)
                await _running.wait()
            await _call_normal_path_handler(_on_end, info)
        except asyncio.CancelledError as e:
            logger.info("Loop was cancelled by stop()")
            try:
                await _call_normal_path_handler(_on_stop, info)
            except Exception as expt_at_stop:
                logger.debug("on_stop failed")
                raise expt_at_stop from e
        except Exception as e:
            logger.exception("Unknown exception in _loop()")
            try:
                if _on_exception:
                    _on_exception(e, _common_context, info)
            except Exception as expt_at_handle_exception:
                raise expt_at_handle_exception from e
            raise
        finally:
            try:
                await _call_normal_path_handler(_on_closed, info)
            except Exception as expt_on_closed:
                logger.exception(
                    "Unknown exception in _on_closed handler")
                _state = UNCLEAN
                raise expt_on_closed
            _state = CLOSED

    
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
    _on_start = None
    _on_end = None
    _on_stop = None 
    _on_pause = None 
    _on_resume = None
    _on_closed = None
    _on_tick_before = None 
    _on_tick = None 
    _on_tick_after = None 
    _on_exception = None # sync only!
    _on_wait = lambda: None
    _on_handler_exception = None #sync only!
    _next = lambda: True # sync only!
    _common_context = None

    async def _default_handler_caller(handler, context, loop_info):
        return handler(context, loop_info)
    _handler_caller = _default_handler_caller

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

    def set_on_wait(fn):
        nonlocal _on_wait
        _check_state_is_load_for_setter(set_on_wait)
        _on_wait = fn

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
    
    def set_on_handler_exception(fn):
        nonlocal _on_handler_exception
        _check_state_is_load_for_setter(set_on_handler_exception)
        _on_handler_exception = fn


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
    handle.HandleStateError = HandleStateError
    handle.HandleClosed = HandleClosed

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
    handle.set_on_wait = set_on_wait
    handle.set_next = set_next

    handle.set_handler_caller = set_handler_caller
    handle.set_common_context = set_common_context

    handle.start = start
    handle.stop = stop
    handle.pause = pause
    handle.resume = resume

    return handle