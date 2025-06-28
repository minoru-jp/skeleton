
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

    _circuit = None
    
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

    def dummy_context_updater_factory(env):
        ctx = SimpleNamespace()
        ctx.count = 0
        ctx.env = env
        def context_updater(event):
            if event == 'on_tick':
                ctx.count += 1
            return ctx
        return context_updater
    _context_updater_factory = dummy_context_updater_factory

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
                    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
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
                _pending_pause = True
            @staticmethod
            def set_resume():
                print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
                nonlocal _mode, _pending_resume
                _pending_resume = True
                _event.set()
        
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

    _running_manager, _running_setter, _running_event, _running_reader =\
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

    _result_cleaner, _result_setter, _result_reader = create_result_chain_some()


    _meta = SimpleNamespace()


    async def _invoke_handler(event, ctx_updater, ctx):
        handler = _handlers.get(event, None)
        if not handler:
            return
        ctx_updater(event)
        try:
            tmp = handler(ctx)
            result = await tmp if inspect.isawaitable(tmp) else tmp
            _result_setter.set_prev(event, result)
        except Exception as e:
            raise HandlerError(event, e)

    def _create_loop_environment():
        # TODO: Consider how to prevent handlers from modifying this
        env = SimpleNamespace()
        env.init = SimpleNamespace()
        env.init.role = role
        env.const = SimpleNamespace()
        env.const.states = SimpleNamespace()
        env.const.states.LOAD = LOAD
        env.const.states.ACTIVE = ACTIVE
        env.const.states.CLOSED = CLOSED
        env.const.states.UNCLEAN = UNCLEAN
        env.const.mode = SimpleNamespace()
        env.const.mode.RUNNING = RUNNING
        env.const.mode.PAUSE = PAUSE
        env.type = SimpleNamespace()
        env.type.HandlerError = HandlerError
        env.signal = SimpleNamespace()
        env.signal.Break = Break
        env.loop_task = None
        env.result_reader = _result_reader
        env.mode_reader = _running_reader
        env.state = ACTIVE
        env.exc = None
        env.nested_exc = None
        return env

    async def _loop_engine():
        nonlocal _loop_task, _meta
        try:
            env = _create_loop_environment()
            ctx_updater = _context_updater_factory(env)
            ctx = ctx_updater('get')
            await _invoke_handler('on_start', ctx_updater, ctx)
            await _circuit(ctx_updater, ctx)
            await _invoke_handler('on_end', ctx_updater, ctx)
        except asyncio.CancelledError as e:
            env.exc = e
            logger.info(f"[{role}] Loop was cancelled")
            try:
                await _invoke_handler('on_stop', ctx_updater, ctx)
            except Exception as nested_e:
                env.nested_exc = nested_e
                raise nested_e from e
        except HandlerError as e:
            event = e.event
            orig_e = e.orig_exception
            # TODO: Consider how to pass exceptions to the exception handler
            env.exc = e
            logger.exception(f"[{role}] {event} Handler failed")
            try:
                _invoke_handler('on_handler_exception', ctx_updater, ctx)
            except Exception as nested_e:
                env.nested_exc = nested_e
                raise nested_e from e
            raise orig_e from None
        except Exception as e:
            # TODO: Consider how to pass exceptions to the exception handler
            env.exc = e
            logger.exception(f"[{role}] Unknown exception in circuit")
            try:
                _invoke_handler('on_circuit_exception', ctx_updater, ctx)
            except Exception as nested_e:
                env.nested_exc = nested_e
                raise nested_e from e
            raise
        finally:
            try:
                await _invoke_handler('on_closed', ctx_updater, ctx)
                _state = CLOSED
            except Exception:
                _state = UNCLEAN
                env.state = _state
            try:
                return await _invoke_handler('on_result', ctx_updater, ctx)
            except Exception:
                return NO_RESULT
            finally:
                _result_cleaner.clean()
                _handlers.clear()
                _loop_task = None
                _meta = None


    _CIRCUIT_TEMPLATE = '''\
{async_}def {name}(ctx_updater, ctx):
    current = ''
    result = None
    try:
        while True:{should_stop}{on_tick_before}{on_tick}{on_tick_after}{on_wait}{pause_resume}
    except Break as e:
        pass
    except CircuitError as e:
        raise e.orig_exception
    except Exception as e:
        raise HandlerError(current, e)
    '''

    #Note: zero indent
    _INVOKE_HANDLER_TEMPLATE = textwrap.dedent('''\
    current = '{event}'{ctx_update}
    result = {await_}{event}(ctx)
    result_setter.set_prev(current, result)
    ''')

    #Note: zero indent
    _PAUSABLE_TEMPLATE = textwrap.dedent('''\
if running_manager.enter_if_pending_pause():{on_pause}
    try:
        running_event.clear()
    except Exception as e:
        raise CircuitError(e)

if running_manager.enter_if_pending_resume():{on_resume}
    pass
try:
    await running_event.wait()
except Exception as e:
    raise CircuitError(e)
    ''')

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
            invoking_parts[event] = textwrap.indent("\n" + _INVOKE_HANDLER_TEMPLATE.format(
                event = event,
                ctx_update = "\n" + f'ctx_updater("{event}")' if notify_ctx else '',
                await_ = 'await ' if async_func else '',
            ),
            ' ' * (12 if event not in ('on_pause', 'on_resume') else 4)
            )
            ns_for_handlers[event] = handler
        
        pause_code = textwrap.indent(_PAUSABLE_TEMPLATE.format(
            on_pause = invoking_parts.get('on_pause', ''),
            on_resume = invoking_parts.get('on_resume', '')
        ),' ' * 12) if pausable else ''

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
            'result_setter': result_setter,
            'running_manager': running_manager,
            'running_event': running_event,
            'Break': break_exc,
            'HandlerError': handler_err_exc,
            'CircuitError': circuit_err_exc,
            **ns_for_handlers
        }
        # print("=======================================================")
        # print(namespace)
        # print("=======================================================")
        dst = {}
        exec(full_code, namespace, dst)
        return dst[circuit_name], full_code


    def _check_state(*expected: int, error_msg: str, notify_closed: bool = True) -> None:
        if _state in expected:
            return
        err_log = f"{error_msg} (expected = {expected}, actual = {_state})"
        if _state in TERMINAL_STATES and notify_closed:
            raise HandleClosed(err_log)
        raise HandleStateError(err_log)
    
    def _check_mode(*expected: int, error_msg: str) -> None:
        mode = _running_reader.get_mode()
        if mode in expected:
            return
        raise HandleStateError(f"{error_msg} (expected = {expected}, actual = {mode})")
    

    def start():
        '''
        Launches the main loop as a background task.
        This function is asynchronous, but does not wait for the loop to finish.
        The loop runs independently in the background.
        '''
        nonlocal _state, _loop_task
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

    def compile():
        nonlocal _circuit
        _check_state(LOAD, error_msg="compile() must be called in LOAD state")
        _circuit, _circuit_code = _compile_circuit(
        circuit_name='_circuit',
        handlers=_handlers,
        notify_ctx=True,
        result_setter=_result_setter,
        running_manager=_running_manager,
        running_event=_running_event,
        pausable=True,
        break_exc=Break,
        handler_err_exc=HandlerError,
        circuit_err_exc=CircuitError,
        )
        #print(_circuit_code)

    def stop():
        _check_state(ACTIVE, error_msg="stop() must be called in ACTIVE state")
        if not _loop_task:
            raise RuntimeError("Cannot call stop(): loop started via ready()"
                               "and is not externally controllable")
        if _loop_task and not _loop_task.done():
            _loop_task.cancel()
    
    def pause():
        _check_state(ACTIVE, error_msg="pause() only allowed in ACTIVE")
        _check_mode(RUNNING, error_msg="pause() only allowed from RUNNING")
        _running_setter.set_pause()

    def resume():
        _check_state(ACTIVE, error_msg="resume() only allowed in ACTIVE")
        _check_mode(PAUSE, error_msg="resume() only allowed from PAUSE")
        _running_setter.set_resume()

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
        nonlocal _context_updater_factory
        _check_state_is_load_for_setter(set_context_builder_factory)
        _context_updater_factory = fn
    


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

    handle.compile = compile

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





import random
from datetime import datetime, timedelta

async def main():

    h = make_loop_engine_handle()

    def should_stop(ctx):
        if ctx.count >= 1000:
            raise ctx.env.signal.Break

    def on_tick(ctx):
        print(f'\r{"( ˶°ㅁ°) !!" if ctx.count % 2 == 0 else "!!(°ㅁ°˶ )"} {"|/-\\"[ctx.count % 4]}', end='')
        #print(f"{' ' * ctx.count} ┏(‘o’)┛ ┏(‘o’)┛ ┏(‘o’)┛", end ="\r")
        #print(' ' + ("tick" if ctx.count % 2 == 0 else "tack") + str(ctx.count), end="\r")
        #print(f"{' ' * 30}{'(|)  (0v0)  (|)' if (ctx.count % 2) == 0 else '(\\/) (0v0) (\\/)'}", end="\r")
        #print(ctx.count, end="\r")

    async def on_wait(ctx):
        await asyncio.sleep(0.5)

    def on_pause(ctx):
        print("pause")

    def on_resume(ctx):
        print("resume!")
    
    def on_end(ctx):
        print("end!")
    
    def on_stop(ctx):
        print("stop!")

    def on_handler_exception(ctx):
        print(ctx.env.exc)
    
    def on_circuit_exception(ctx):
        print(ctx.env.exc)
    
    def on_result(ctx):
        print("on_result")
        print(ctx.env)
        print(type(ctx.env.exc))
    
    # 必須イベントハンドラを登録（circuitに入るものだけで十分）
    #h.set_should_stop(dummy_handler)
    #h.set_on_tick_before(dummy_handler)
    h.set_should_stop(should_stop)
    h.set_on_tick(on_tick)
    #h.set_on_tick_after(dummy_handler)
    h.set_on_wait(on_wait)
    #h.set_on_pause(on_pause)
    #h.set_on_resume(on_resume)
    #h.set_on_end(on_end)
    #h.set_on_stop(on_stop)
    #h.set_on_handler_exception(on_handler_exception)
    #h.set_on_circuit_exception(on_circuit_exception)
    #h.set_on_result(on_result)

    # コンパイルしてcircuitコードの出力を確認
    h.compile()
    #loop_coro = h.ready()  # コルーチンを取得（まだ開始されていない）
    h.start()

    # # 別タスクとしてループ起動
    # task = asyncio.create_task(loop_coro)

    # # 1分間だけ実行し、途中で pause/resume をランダムに実行
    # end_time = datetime.now() + timedelta(seconds=20)
    # while datetime.now() < end_time:
    #     await asyncio.sleep(random.uniform(5, 10))  # 5〜10秒おきに発火
    #     h.pause()
    #     await asyncio.sleep(random.uniform(2, 4))  # 少し停止してから
    #     h.resume()

    # # 最後にループを止める（任意で明示）
    # task.cancel()

    #await task  # ループタスクの終了を待つ

    await asyncio.sleep(30)

    print("end")

# 実行
asyncio.run(main())