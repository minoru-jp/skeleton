"""

make_loop_engine_handle() の使用例と解説


このモジュールが提供するイベントとそのライフサイクル:
    [LOAD]
        #ループのタスクが開始されるまで
        #ハンドルに対して値の設定ができる
    [ACTIVE]
        #ループエンジン開始
        on_start(context): 開始時に一度だけ呼ばれる
        circuit(...): ループ処理はこの内部に配置される
        on_end: circuitを例外なしで抜けた場合に呼ばれる
        on_stop: キャンセルされた場合に呼ばれる
        on_closed: 止まり方にかかわらずクリーンアップの為に呼ばれる
        on_result: 戻り値によって"ループ全体の結果"を出すために呼ばれる
    [TERMINATED]
        #ループエンジンを抜けた。クリーンアップ済みでhandleはもう使用できない
        #ただし、LoopResultReaderは参照可能
    

このモジュールの想定している使用例:
    サーキット構成してprintでコードを得る:
        def tick_tack_reactor_factory(loop_contorol):
            context = SimpleNamespace()
            context.log = loop_control.log
            context.count = 0
            Break = loop_control.exceptions.signals.Break

            def tick_tack_reactor(proc_name: str):
                context.needle = "tick" if context.count % 2 == 0 else "tack"
                context.count += 1
                if context.count > 10:
                    raise Break

            return tick_tack_reactor, context

        def dump_needle(context):
            print(f"[{context.log.role}]: {context.needle}")

        async def wait(context):
            await asyncio.sleep(1)

        handle = make_loop_engine_handle() # this document for this funcition

        handle.log.set_role("clock")

        handle.set_action_reactor_factory(tick_tack_reactor_factory)

        handle.append_action("dump_needle", dump_needle, notify_reactor = True)
        handle.append_action("wait", wait, notify_reactor = False)

        # 実験・クイックスタート
        # await handle.start_with_compile(irq = False)

        print(handle.generate_circuit_code('_tick_tack_circuit', irq = True))
    
    生成されるコード文字列:
        async def _tick_tack_circuit(reactor, context, step, irq, ev_proc, signal):
        try:
            while True:
                reactor('dump_needle')
                r = dump_needle(context)
                step.set_prev_result(dump_needle, r)

                r = await wait(context)
                step.set_prev_result(wait, r)

                if irq.pause_requested:
                    await irq.consume_pause_result(ev_proc)
                if irq.resume_event_scheduled:
                    await irq.perform_resume_event(ev_proc)
                await irq.wait_resume()
        except signal.Break:
            pass

    コードを張り付けて静的な関数定義にして、それをmake_loop_engine_handle()に渡す:

        def tick_tack_reactor_factory(loop_contorol):
            context = SimpleNamespace()
            context.log = loop_control.log
            context.count = 0
            Break = loop_control.exceptions.signals.Break

            def tick_tack_reactor(proc_name: str):
                context.needle = "tick" if context.count % 2 == 0 else "tack"
                context.count += 1
                if context.count > 10:
                    raise Break

            return tick_tack_reactor, context

        def dump_needle(context):
            print(f"[{context.log.role}]: {context.needle}")

        async def wait(context):
            await asyncio.sleep(1)

        async def _tick_tack_circuit(reactor, context, step, irq, ev_proc, signal):
            try:
                while True:
                    reactor('dump_needle')
                    r = dump_needle(context)
                    step.set_prev_result(dump_needle, r)

                    r = await wait(context)
                    step.set_prev_result(wait, r)

                    if irq.pause_requested:
                        await irq.consume_pause_result(ev_proc)
                    if irq.resume_event_scheduled:
                        await irq.perform_resume_event(ev_proc)
                    await irq.wait_resume()
            except signal.Break:
                pass
        
        tick_tack_handle = make_loop_engine_handle(_tick_tack_circuit)

        tick_tack_handle.set_action_reactor_factory(tick_tack_reactor_factory)

        tick_tack_handle.start()

このモジュールの最終的な目的は、.generate_circuit_code()を用いて、コードを得、
それをコピペして静的な定義に落とし込み、それをmake_loop_engine_handle()の引数として与えて、
"静的に定義された"circuit関数のラッパとして機能することです。

circuit関数は呼び出し形式のみが定義され、関数の内容についてこのモジュールが仕様として定義するものは
なにもありません。circuit関数に与えられる各引数はツールとして存在し、その使用を強制するものではありません。

以下は.generate_circuit_code()が出力する最小構成のcircuitです:
    設定されたアクションがなく、IRQも使用しない空の実装:
        def _empty_circuit(reactor, context, step, irq, ev_proc, signal):
            try:
                while True:
                    pass

            except signal.Break:
                pass
    
    IRQのみ使用する場合:
        async def _irq_circuit(reactor, context, step, irq, ev_proc, signal):
            try:
                while True:
                    pass
                    if irq.pause_requested:
                        await irq.consume_pause_result(ev_proc)
                    if irq.resume_event_scheduled:
                        await irq.perform_resume_event(ev_proc)
                    await irq.wait_resume()
            except signal.Break:
                pass
    
    アクションに非同期関数が存在しないかつIRQを使用しない場合、circuit関数は同期関数として出力されます。

例外の取り扱い:
    このモジュールが提供するサーキットのラッパはfail-stopで設計されています。
    サーキット内のev_proc以外で発生した例外はCircuitErrorにラップされ再スローされます。
    イベントハンドラ内で発生した例外はEventHandlerErrorにラップされ再スローされます。
    リアクタ内で発生した例外はサーキット内のアクションかイベントのハンドル時かで違いがあり、
    サーキット内で発生した場合、その判別はされず、すべてCircuitErrorとして報告されます。
    イベントのハンドル時に発生した場合は、EventReactorErrorとして報告されます。
    キャンセルを含め、すべての例外が発生した場合、このラッパは直ちに停止せずon_closed,on_resultを
    実行して終了することを試みます。

"""

import logging
from typing import Any, Awaitable, Callable, Optional, Protocol, Tuple, Type, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from internal import LoopControl

@runtime_checkable
class StateError(Protocol):
    """Protocol for state-related error definitions."""

    UnknownStateError: Type[Exception]
    """Raised for unknown or unsupported state."""

    InvalidStateError: Type[Exception]
    """Raised when current state is invalid for the operation."""

    TerminatedError: Type[Exception]
    """Raised when state is TERMINATED and operation is invalid."""


@runtime_checkable
class StateObserver(Protocol):
    """
    Read-only observer of a three-state lifecycle (LOAD → ACTIVE → TERMINATED).

    Provides access to the immutable state tokens, current state, and error definitions
    without allowing transitions or modifications.
    """

    @property
    def LOAD(_) -> object:
        """State token: initial load state."""
        ...

    @property
    def ACTIVE(_) -> object:
        """State token: active state."""
        ...

    @property
    def TERMINATED(_) -> object:
        """State token: terminated state."""
        ...

    @property
    def state(_) -> object:
        """Current internal state."""
        ...

    @property
    def errors(_) -> 'StateError':
        """Error definitions for invalid state operations."""
        ...



@runtime_checkable
class Context(Protocol):
    """
    Represents a user-defined context object passed to handlers and actions.
    """

@runtime_checkable
class EventHandler(Protocol):
    """
    Implementation to be executed for an event.
    """
    def __call__(self, ctx: Context) -> Any:
        """Execute with the given context."""
        ...


@runtime_checkable
class Action(Protocol):
    """
    Executable within the circuit, takes a Context.
    Can be sync or async.
    """
    def __call__(self, ctx: Context) -> Any:
        """
        Executes the action within the circuit loop
        using the given context.
        """
        ...

@runtime_checkable
class Reactor(Protocol):
    """
    Reacts to lifecycle points (including both events and actions) and may update the Context.
    """

    def __call__(self, next_proc: str) -> Optional[Awaitable[None]]:
        """
        Handle a lifecycle point, identified by the tag, and optionally update the Context.
        """
        ...


@runtime_checkable
class ReactorFactory(Protocol):
    """
    Creates a (Reactor, Context) pair for a given LoopControl.

    The Reactor handles lifecycle points (events and actions) 
    and may update the Context. The Context is passed to handlers and actions.

    Typically implemented as a closure that captures necessary state.
    """

    def __call__(self, control: LoopControl) -> Tuple[Reactor, Context]:
        """
        Produce a Reactor and its associated Context for the given control.
        """
        ...


@runtime_checkable
class LoopResultReader(Protocol):
    """
    Read-only view of the overall result and errors of a loop after it finishes.
    This view allows accessing the recorded results and errors without allowing modification.

    The underlying LoopResult is expected to be cleaned up by the driver.
    Once `cleanup()` is called (which must be invoked when the loop is TERMINATED),
    the internal state becomes undefined, and further access to the properties of this reader is not supported.

    If .loop_result is accessed before the loop finishes, it holds PENDING_RESULT.
    """

    @property
    def PENDING_RESULT(self) -> object:
        """Marker: result is still pending."""
        ...

    @property
    def NO_RESULT(self) -> object:
        """Marker: loop produced no result."""
        ...
    
    @property
    def last_process(_) -> str:
        """Return the recoded last process name."""
        ...

    @property
    def loop_result(_) -> Any:
        """Return the recorded final result."""
        ...

    @property
    def circuit_error(_) -> Exception:
        """Return the recorded circuit error if any."""
        ...

    @property
    def event_reactor_error(_) -> Exception:
        """Return the recorded event reactor error if any."""
        ...

    @property
    def handler_error(_) -> Exception:
        """Return the recorded handler error if any."""
        ...

    @property
    def internal_error(_) -> Exception:
        """Return the recorded internal error if any."""
        ...



@runtime_checkable
class LoopInterruptObserver(Protocol):
    """
    Read-only view of the loop’s interrupt state.

    Exposes the current mode (RUNNING or PAUSE) for inspection.
    Does not allow controlling or modifying the interrupt flow.
    """
    @property
    def RUNNING(_) -> object:
        """Marker object indicating the loop is in RUNNING mode."""
        ...

    @property
    def PAUSE(_) -> object:
        """Marker object indicating the loop is in PAUSE mode."""
        ...

    @property
    def mode(_) -> object:
        """Current mode of the loop: either RUNNING or PAUSE."""
        ...


@runtime_checkable
class LoopError(Protocol):
    """
    Protocol for loop-related error definitions.

    Defines standard exceptions raised at specific phases
    of the loop lifecycle.
    """

    EventReactorError: Type[Exception]
    """
    Raised when the event reactor fails. Does not include action reactor 
    failures.
    """

    EventHandlerError: Type[Exception]
    """Raised when the event handler fails. Does not include action failures."""

    CircuitError: Type[Exception]
    """
    Raised when the circuit execution fails.
    Includes failures in actions and action reactors.
    """

@runtime_checkable
class LoopSignal(Protocol):
    """
    Protocol for loop control signals.

    Defines exceptions used to signal control flow changes
    in the loop lifecycle.
    """

    Break: Type[Exception]
    """
    Raised to break the loop immediately.
    This is a control signal only and does not take any arguments.
    """

@runtime_checkable
class LoopException(Protocol):
    """
    Protocol for loop exception definitions.

    Provides access to loop-related error and signal classes.
    """

    @property
    def errors(_) -> Type[LoopError]:
        """
        Returns the error definitions used in the loop.
        """
        ...
    
    @property
    def signals(_) -> Type[LoopSignal]:
        """
        Returns the control signal definitions used in the loop.
        """
        ...


@runtime_checkable
class LoopLog(Protocol):
    """
    Provides access to the loop’s logging configuration.

    Allows setting a role name (once) and replacing the logger instance.
    The current role and logger can also be retrieved.
    """

    @staticmethod
    def set_role(role: str) -> None:
        """
        Sets the role name for the loop.
        Can only be set once during the LOAD state.
        """
        ...
    
    @staticmethod
    def set_logger(logger: logging.Logger) -> None:
        """
        Sets or replaces the logger instance.
        Can be called multiple times to change the logger.
        """
        ...
    
    @property
    def role(self) -> str:
        """
        Returns the current role name.
        If no role was explicitly set, defaults to 'loop'.
        """
        ...
    
    @property
    def logger(self) -> logging.Logger:
        """
        Returns the current logger instance.
        """
        ...



@runtime_checkable
class LoopEngineHandle(Protocol):
    """
    Driver-facing handle for managing and observing the loop engine.

    Provides methods to start, stop, and observe the loop lifecycle,
    including registering actions and handlers, generating circuit code,
    and monitoring state.

    Exposes only the intended public API. Does not expose internal state or control flow.
    """

    @property
    def log(self) -> LoopLog:
        """Access to loop logger and role information."""
        ...

    @staticmethod
    def set_on_start(fn: EventHandler) -> None:
        """Register handler for loop start event."""
        ...

    @staticmethod
    def set_on_end(fn: EventHandler) -> None:
        """Register handler for loop end event."""
        ...

    @staticmethod
    def set_on_stop(fn: EventHandler) -> None:
        """Register handler for loop stop (canceled) event."""
        ...

    @staticmethod
    def set_on_closed(fn: EventHandler) -> None:
        """Register handler for loop cleanup event."""
        ...

    @staticmethod
    def set_on_result(fn: EventHandler) -> None:
        """Register handler for loop result event."""
        ...

    @staticmethod
    def set_on_pause(fn: EventHandler) -> None:
        """Register handler for loop pause event."""
        ...

    @staticmethod
    def set_on_resume(fn: EventHandler) -> None:
        """Register handler for loop resume event."""
        ...

    @staticmethod
    def generate_circuit_code(name: str, irq: bool) -> str:
        """Generate source code for the circuit function."""
        ...

    @staticmethod
    def start() -> None:
        """Start loop engine with pre-defined circuit."""
        ...

    @staticmethod
    def start_with_compile(irq: bool) -> None:
        """Compile and start loop engine with generated circuit."""
        ...

    @property
    def stop(self) -> Callable[[], None]:
        """Stop the loop task if running."""
        ...

    @property
    def task_is_running(self) -> bool:
        """True if the loop task is currently running."""
        ...

    @property
    def pause(self) -> Callable[[], None]:
        """Request loop pause at next safe point."""
        ...

    @property
    def resume(self) -> Callable[[], None]:
        """Request immediate loop resume."""
        ...

    @property
    def append_action(self) -> Callable[..., None]:
        """Register an action to the circuit."""
        ...

    @property
    def set_event_reactor_factory(self) -> Callable[..., None]:
        """Set factory for event reactor and context."""
        ...

    @property
    def set_action_reactor_factory(self) -> Callable[..., None]:
        """Set factory for action reactor and context."""
        ...

    @property
    def state_observer(self) -> StateObserver:
        """Read-only view of the current state (LOAD/ACTIVE/TERMINATED)."""
        ...

    @property
    def running_observer(self) -> LoopInterruptObserver:
        """Read-only view of the current run/pause mode."""
        ...

    @property
    def loop_result(self) -> LoopResultReader:
        """Read-only view of the final result and errors."""
        ...
