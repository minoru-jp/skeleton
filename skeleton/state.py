
from __future__ import annotations

from typing import Any, Callable, Protocol, Type, runtime_checkable


@runtime_checkable
class UsageState(Protocol):
    @property
    def LOAD(_) -> object:
        ...

    @property
    def ACTIVE(_) -> object:
        ...

    @property
    def TERMINATED(_) -> object:
        ...

    @property
    def UnknownStateError(_) -> Type[Exception]:
        ...
    
    @property
    def InvalidStateError(_) -> Type[Exception]:
        ...
    
    @property
    def TerminatedError(_) -> Type[Exception]:
        ...

    @staticmethod
    def validate_state_value(state: object):
        ...


def setup_UsageState() -> UsageState:
    _LOAD = object()
    _ACTIVE = object()
    _TERMINATED = object()

    _ALL = (_LOAD, _ACTIVE, _TERMINATED)
    
    class UnknownStateError(Exception):
        pass
    class InvalidStateError(Exception):
        pass
    class TerminatedError(InvalidStateError):
        pass

    class _Interface(UsageState):
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
        def UnknownStateError(_) -> Type[Exception]:
            return UnknownStateError
        
        @property
        def InvalidStateError(_) -> Type[Exception]:
            return InvalidStateError
        
        @property
        def TerminatedError(_) -> Type[Exception]:
            return TerminatedError
        
        @staticmethod
        def validate_state_value(state: object):
            if not any(state is s for s in _ALL):
                raise UnknownStateError(
                    f"Unknown or unsupported state value: {state}")
    
    return _Interface()



@runtime_checkable
class UsageStateObserver(UsageState, Protocol):
    @property
    def current_state(_) -> object:
        ...


@runtime_checkable
class UsageStateFull(UsageState, Protocol):
    @staticmethod
    def get_observer() -> UsageStateObserver:
        ...

    @staticmethod
    def maintain_state(state: object, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        ...

    @staticmethod
    def transit_state_with(to: object, fn: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> Any:
        ...

    @staticmethod
    def transit_state(to: object) -> Any:
        ...

    @property
    def current_state(_) -> object:
        ...



def setup_UsageStateFull() -> UsageStateFull:

    _state = setup_UsageState()

    _current = _state.LOAD

    class _ObserverInterface(UsageStateObserver, type(_state)):
        @property
        def current_state(_) -> object:
            return _current
    
    _observer = _ObserverInterface() # type: ignore
    
    def _require_state(expected):
        _state.validate_state_value(expected)
        if expected is not _current:
            err_log = f"State error: expected = {expected}, actual = {_current}"
            if _current is _state.TERMINATED:
                raise _state.TerminatedError(err_log)
            raise _state.InvalidStateError(err_log)
    
    class _Interface(UsageStateFull, type(_state)):
        __slots__ = ()
        @staticmethod
        def get_observer() -> UsageStateObserver:
            return _observer
        
        @property
        def current_state(_):
            return _current
        
        @staticmethod
        def maintain_state(state, fn, *fn_args, **fn_kwargs):
            _require_state(state)
            return fn(*fn_args, **fn_kwargs)
        
        @staticmethod
        def transit_state_with(to, fn, *fn_args, **fn_kwargs):
            nonlocal _current
            _state.validate_state_value(to)
            to_active = _current is _state.LOAD and to is _state.ACTIVE
            to_terminal = _current is _state.ACTIVE and to is _state.TERMINATED
            if not (to_active or to_terminal):
                raise _state.InvalidStateError(
                    f"Invalid transition: {_current} → {to}")
            if fn:
                result = iface.maintain_state(
                    _current, fn, *fn_args, **fn_kwargs)
                _current = to
                return result
            else:
                return None
            
        @staticmethod
        def transit_state(to):
            return iface.transit_state_with(to, None)
    
    iface = _Interface() # type: ignore

    return iface

