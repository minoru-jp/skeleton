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
    
    _meta_hms = SimpleNamespace()
    def _handle_hms(**kwargs):
        '''
        The handle functions as a container that provides the interface to the driver.

        When invoked with keyword arguments, it assigns metadata to the handle.  
        This metadata can be accessed via `handle.meta.xxx`.  
        This function returns the handle itself.
        '''
        vars(_meta).update(kwargs)
        return handle

    def _split_hss(*names):
        def new_handle():
            return id(handle)
        vars(new_handle).update({k: getattr(handle, k) for k in names})
        return new_handle

    _meta = _meta_hms
    handle = _handle_hms
    handle._split = _split_hss

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
    _on_closed = None
    _on_tick_before = None
    _on_tick = None
    _on_tick_after = None
    _on_interval = lambda: None
    _next = lambda: True

    _loop_task = None

    # --- handler call helper ---
    async def _call_handler(handler, obj):
        if not handler:
            return _SUCCESS
        try:
            result = handler(obj)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("Handler error")
            return _FAILED
        return _SUCCESS

    async def _loop():
        nonlocal _state
        _check_state(LOAD, error_msg="loop() must be called in LOAD state")
        nonlocal _on_start, _on_end, _on_tick_before, _on_tick_after, _on_tick
        try:
            if await _call_handler(_on_start, handle) == _FAILED:
                _on_start = None
            while _next():
                if await _call_handler(_on_tick_before, handle) == _FAILED:
                    _on_tick_before = None
                if await _call_handler(_on_tick, handle) == _FAILED:
                    _on_tick = None
                if await _call_handler(_on_tick_after, handle) == _FAILED:
                    _on_tick_after = None
                await _on_interval()
                await _running.wait()
            if await _call_handler(_on_end, handle) == _FAILED:
                _on_end = None
        except asyncio.CancelledError as e:
            logger.info("Loop was cancelled by stop()")
            await _call_handler(_on_stop, handle)
        except Exception:
            logger.exception("Unhandled exception in _loop()")
            raise
        finally:
            _call_handler(_on_closed, handle)
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
    def set_on_start(fn):
        nonlocal _on_start
        _check_state(LOAD, error_msg="set_on_start only allowed in LOAD")
        _on_start = fn

    def set_on_end(fn):
        nonlocal _on_end
        _check_state(LOAD, error_msg="set_on_end only allowed in LOAD")
        _on_end = fn
    
    def set_on_stop(fn):
        nonlocal _on_stop
        _check_state(LOAD, error_msg="set_on_stop only allowed in LOAD")
        _on_stop = fn
    
    def set_on_closed(fn):
        nonlocal _on_closed
        _check_state(LOAD, error_msg="set_on_finally only allowed in LOAD")
        _on_closed = fn

    def set_on_tick_before(fn):
        nonlocal _on_tick_before
        _check_state(LOAD, error_msg="set_on_tick_before only allowed in LOAD")
        _on_tick_before = fn

    def set_on_tick(fn):
        nonlocal _on_tick
        _check_state(LOAD, error_msg="set_on_tick only allowed in LOAD")
        _on_tick = fn

    def set_on_tick_after(fn):
        nonlocal _on_tick_after
        _check_state(LOAD, error_msg="set_on_tick_after only allowed in LOAD")
        _on_tick_after = fn

    def set_on_interval(fn):
        nonlocal _on_interval
        _check_state(LOAD, error_msg="set_on_interval only allowed in LOAD")
        _on_interval = fn

    def set_next(fn):
        nonlocal _next
        _check_state(LOAD, error_msg="set_next only allowed in LOAD")
        _next = fn

    # --- bind to handle ---
    handle.set_on_start = set_on_start
    handle.set_on_end = set_on_end
    handle.set_on_stop = set_on_stop
    handle.set_on_closed = set_on_closed
    handle.set_on_tick_before = set_on_tick_before
    handle.set_on_tick = set_on_tick
    handle.set_on_tick_after = set_on_tick_after
    handle.set_on_interval = set_on_interval
    handle.set_next = set_next

    handle.start = start
    handle.stop = stop

    handle.meta = _meta

    return handle