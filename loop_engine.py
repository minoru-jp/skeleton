import asyncio
import inspect
from types import SimpleNamespace
import logging

def make_loop_engine_handle(role: str = 'loop', logger = None):

    if not logger:
        logger = logging.getLogger(__name__)

    LOAD = 0
    ACTIVE = 1
    RUNNING = 10 # Sub-state of ACTIVE commute to PAUSE
    PAUSE = 11 # Sub-state of ACTIVE commute to RUNNING
    CLOSED = 2
    UNCLEAN = 20 # Final state used instead of CLOSED if _on_closed() fails
    BROKEN = 21 # Final state used instead of CLOSED if exception happened in circuit
    TERMINAL_STATES = (CLOSED, UNCLEAN, BROKEN)

    _state = LOAD #assign only main state(LOAD, ACTIVE, CLOSED)
    _mode = RUNNING #assign only sub state(RUNNING, PAUSE)
    _running = asyncio.Event()
    _loop_task = None
    _meta = SimpleNamespace()
    _pending_pause = False
    _pending_resume = False
    _prev_event = ''
    _prev_result = None

    class HandleStateError(Exception):
        pass
    class HandleClosed(HandleStateError):
        pass

    async def _invoke_handler_auto(event, handler, **extra_ctx):
        nonlocal _state, _prev_event, _prev_result
        try:
            if not handler:
                return
            ctx = _context_builder(
                event,
                prev_ev = _prev_event,
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
            _state = BROKEN
            if _on_handler_exception:
                try:
                    ctx = _context_builder('on_exception', e=e, failed_event=event, **extra_ctx)
                    _on_handler_exception(ctx, e)
                except Exception as nested_e:
                    logger.exception(f"[{role}] Handler exception handler itself failed")
                    raise nested_e from e
            raise
    
    async def _resolve_pause_resume():
        nonlocal _mode, _pending_pause, _pending_resume
        if _pending_pause:
            _pending_pause = False
            await _invoke_handler_auto('on_pause', _on_pause)
            _mode = PAUSE
            _running.clear()
        if _pending_resume:
            _pending_resume = False
            _mode = RUNNING
            await _invoke_handler_auto('on_resume', _on_resume)
            _running.set()

    async def _loop():
        nonlocal _state
        try:
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
            _ = _context_builder(
                'init',
                role = role,
                RUNNING = RUNNING, PAUSE = PAUSE)
            await _invoke_handler_auto('on_start', _on_start)
            while True:
                if _should_stop:
                    if await _invoke_handler_auto('on_should_stop', _should_stop):
                        break
                await _invoke_handler_auto('on_tick_before', _on_tick_before)
                await _invoke_handler_auto('on_tick', _on_tick)
                await _invoke_handler_auto('on_tick_after', _on_tick_after)
                await _invoke_handler_auto('on_wait', _on_wait)
                await _resolve_pause_resume()
                await _running.wait()
            await _invoke_handler_auto('on_end', _on_end)
        except asyncio.CancelledError as e:
            logger.info(f"[{role}] Loop was cancelled")
            await _invoke_handler_auto('_on_stop', _on_stop)
        except Exception as e:
            if _state == BROKEN:
                raise
            logger.exception(f"[{role}] Unknown exception in circuit")
            _state = BROKEN
            try:
                if _on_circuit_exception:
                    ctx = _context_builder('on_circuit_exception', e = e)
                    _on_circuit_exception(ctx, e)
            except Exception as nested_e:
                raise nested_e from e
            raise
        finally:
            try:
                await _invoke_handler_auto('on_closed', _on_closed)
                _state = CLOSED
            except Exception:
                _state = UNCLEAN
            try:
                await _invoke_handler_auto('on_result', _on_result)
            except Exception:
                return

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
    _on_start = None
    _on_end = None
    _on_stop = None 
    _on_pause = None 
    _on_resume = None
    _on_closed = None
    _on_tick_before = None 
    _on_tick = None 
    _on_tick_after = None 
    _on_handler_exception = None
    _on_circuit_exception = None
    _on_wait = None
    _on_result = None
    _should_stop = None
    _context_builder = lambda *a, **kw: None

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

    def set_should_stop(fn):
        nonlocal _should_stop
        _check_state_is_load_for_setter(set_should_stop)
        _should_stop = fn

    def set_on_pause(fn):
        nonlocal _on_pause
        _check_state_is_load_for_setter(set_on_pause)
        _on_pause = fn

    def set_on_resume(fn):
        nonlocal _on_resume
        _check_state_is_load_for_setter(set_on_resume)
        _on_resume = fn
    
    def set_on_handler_exception(fn):
        nonlocal _on_handler_exception
        _check_state_is_load_for_setter(set_on_handler_exception)
        _on_handler_exception = fn

    def set_on_circuit_exception(fn):
        nonlocal _on_circuit_exception
        _check_state_is_load_for_setter(set_on_circuit_exception)
        _on_circuit_exception = fn
    
    def set_on_result(obj):
        nonlocal _on_result
        _check_state_is_load_for_setter(set_on_result)
        _on_result = obj
    
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
    handle.RUNNING = RUNNING
    handle.PAUSE = PAUSE
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
    handle.set_on_handler_exception = set_on_handler_exception
    handle.set_on_circuit_exception = set_on_circuit_exception
    handle.set_on_wait = set_on_wait
    handle.set_should_stop = set_should_stop
    handle.set_on_result = set_on_result

    handle.start = start
    handle.ready = ready
    handle.stop = stop
    handle.pause = pause
    handle.resume = resume

    return handle
