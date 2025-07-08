

import logging
from typing import Any, FrozenSet, Type

from .hidden_components import (
    StateMachine,
    LoopResult,
    LoopInterrupt,

)

from .loop_engine_manual import (
    LoopEvent,
    State,
    StateError,
    StateMachineObserver,
    StepSlot,
    LoopResultReader,
    LoopInterruptObserver,
    LoopException,
    LoopError,
    LoopSignal,
    LoopLog,
)

def setup_loop_event() -> LoopEvent:
    _START = 'on_start'

    _PAUSE = 'on_pause'
    _RESUME = 'on_resume'
    
    _STOP_NORMALLY = 'on_end'
    _STOP_CANCELED = 'on_stop'

    _CLEANUP = 'on_closed'
    _LOOP_RESULT = 'on_result'

    _ALL_EVENTS = {
        _START, _PAUSE, _RESUME, _STOP_NORMALLY,
        _STOP_CANCELED, _CLEANUP, _LOOP_RESULT,
    }

    class _Interface(LoopEvent):
        @property
        def START(_):
            return _START
        @property
        def PAUSE(_):
            return _PAUSE
        @property
        def RESUME(_):
            return _RESUME            
        @property
        def STOP_NORMALLY(_):
            return _STOP_NORMALLY
        @property
        def STOP_CANCELED(_):
            return _STOP_CANCELED
        @property
        def CLEANUP(_):
            return _CLEANUP
        @property
        def LOOP_RESULT(_):
            return _LOOP_RESULT
        
        @staticmethod
        def is_valid_event(name) -> bool:
            return name in _ALL_EVENTS
        @property
        def all_events(_) -> FrozenSet[str]:
            return frozenset(_ALL_EVENTS)
        
    return _Interface()


def setup_state() -> State:
    _LOAD = object()
    _ACTIVE = object()
    _TERMINATED = object()

    _ALL = (_LOAD, _ACTIVE, _TERMINATED)
    
    class _StateError(StateError):
        __slots__ = ()
        class UnknownStateError(Exception):
            pass
        class InvalidStateError(Exception):
            pass
        class TerminatedError(InvalidStateError):
            pass

    class _Interface(State):
        __slots__ = ()
        @property
        def LOAD(_):
            return _LOAD
        @property
        def ACTIVE(_):
            return _ACTIVE
        @property
        def TERMINATED(_):
            return _TERMINATED
        
        @property
        def errors(_) -> Type[StateError]:
            return _StateError
        
        @staticmethod
        def validate_state_value(state: object):
            if not any(state is s for s in _ALL):
                raise _StateError.UnknownStateError(
                    f"Unknown or unsupported state value: {state}")
    
    return _Interface()


def setup_state_machine_observer(state_machine: StateMachine) -> StateMachineObserver:
    class _Interface(StateMachineObserver, state_machine._realized):
        @property
        def current_state(_):
            return state_machine.current_state
        
    return _Interface() # type: ignore


def setup_step_slot() -> StepSlot:

    _UNSET = object()

    _prev_proc = '<unset>'
    _prev_result = _UNSET

    class _Interface(StepSlot):
        __slots__ = ()
        @property
        def UNSET(_):
            return _UNSET
        @staticmethod
        def set_prev_result(tag: str, result: Any):
            nonlocal _prev_proc, _prev_result
            _prev_proc = tag
            _prev_result = result
        @property
        def prev_proc(_):
            return _prev_proc
        @property
        def prev_result(_):
            return _prev_result
        @staticmethod
        def cleanup() -> None:
            nonlocal _prev_proc, _prev_result
            _prev_proc = None
            _prev_result = None

    return _Interface()



def _setup_loop_result_reader(state: StateMachine, loop_result: LoopResult) -> LoopResultReader:

    class _Interface(LoopResultReader):
        __slots__ = ()
        @property
        def PENDING_RESULT(_):
            return loop_result.PENDING_RESULT
        @property
        def NO_RESULT(_):
            return loop_result.NO_RESULT
        @property
        def last_process(_):
            return loop_result.last_process
        @property
        def loop_result(_):
            return loop_result.loop_result
        @property
        def circuit_error(_):
            return loop_result.circuit_error
        @property
        def event_reactor_error(_):
            return loop_result.event_reactor_error
        @property
        def handler_error(_):
            return loop_result.handler_error
        @property
        def internal_error(_):
            return loop_result.internal_error
        @staticmethod
        def cleanup() -> None:
            def call_cleanup():
                return loop_result.cleanup()
            state.maintain_state(state.TERMINATED, call_cleanup)
    
    return _Interface()





def _setup_loop_interrupt_observer(loop_interrupt: LoopInterrupt) -> LoopInterruptObserver:
    
    class _Interface(LoopInterruptObserver):
        __slots__ = ()
        @property
        def RUNNING(_):
            return loop_interrupt.RUNNING
        @property
        def PAUSE(_):
            return loop_interrupt.PAUSE
        @property
        def mode(_):
            return loop_interrupt.current_mode
    
    return _Interface()


def _setup_loop_exception() -> LoopException:
    class _LoopError(LoopError):
        __slots__ = ()
        class EventReactorError(Exception):
            def __init__(self, proc_name: str, e: Exception):
                self.proc_name = proc_name
                self.orig_exception = e
                super().__init__(f"at {proc_name}: {e}")
        class EventHandlerError(Exception):
            def __init__(self, proc_name: str, e: Exception):
                self.proc_name = proc_name
                self.orig_exception = e
                super().__init__(f"at {proc_name}: {e}")

        class CircuitError(Exception):
            def __init__(self, e: Exception):
                self.orig_exception = e
                super().__init__(e)
    
    class _LoopSignal(LoopSignal):
        __slots__ = ()
        class Break(Exception):
            pass
    
    class _Interface(LoopException):
        __slots__ = ()
        @property
        def errors(_) -> Type[LoopError]:
            return _LoopError
        @property
        def signals(_) -> Type[LoopSignal]:
            return _LoopSignal
    
    return _Interface()


def _setup_loop_log(state: StateMachine) -> LoopLog:

    _logger = logging.getLogger(__name__)
    _role = None

    class _Interface(LoopLog):
        __slots__ = ()
        @staticmethod
        def set_role(role: str) -> None:
            if _role is not None:
                raise RuntimeError("role can only be set once")
            def set_role():
                nonlocal _role
                _role = role
            state.maintain_state(state.LOAD, set_role)
        @staticmethod
        def set_logger(logger: logging.Logger) -> None:
            nonlocal _logger
            _logger = logger
        @property
        def logger(_) -> logging.Logger:
            return _logger
        @property
        def role(_) -> str:
            return _role if _role is not None else "loop"
    
    return _Interface()