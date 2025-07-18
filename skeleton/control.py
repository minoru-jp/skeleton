
import asyncio
from typing import Optional, Protocol, Type, runtime_checkable

from .subroutine import SubroutineCaller


class RunningObserver(Protocol):
    @property
    def RUNNING(_) -> object:
        ...

    @property
    def PAUSE(_) -> object:
        ...
    
    @property
    def SUPER_PAUSE(_) -> object:
        ...

    @property
    def STOP(_) -> object:
        ...

    @property
    def current_mode(self) -> object:
        ...


class Pauser(RunningObserver, Protocol):
    
    @staticmethod
    async def consume_on_pause_requested() -> None:
        ...

    @staticmethod
    async def consume_resumed_flag() -> None:
        ...

    @staticmethod
    def request_pause() -> None:
        ...

    @staticmethod
    def resume() -> bool:
        ...

    @staticmethod
    async def wait_resume() -> None:
        ...


class DriverRequest(Protocol):
    @staticmethod
    def stop() -> None:
        ...
    
    @staticmethod
    def pause() -> None:
        ...
    
    @staticmethod
    def resume() -> None:
        ...


class ControlFull(Protocol):
    @staticmethod
    def get_request() -> DriverRequest:
        ...

    @staticmethod
    def get_pauser() -> Pauser:
        ...
    
    @staticmethod
    def get_observer() -> RunningObserver:
        ...
    
    @staticmethod
    def reset() -> None:
        ...
    
    @staticmethod
    def stopped() -> None:
        ...
    
    @staticmethod
    def cleanup() -> None:
        ...

def setup_ControlFull() -> ControlFull:
    
    _RUNNING = object()
    _PAUSE = object()
    _SUPER_PAUSE = object()
    _STOP = object()

    _mode: object = _RUNNING
    
    _stop = False

    _event: asyncio.Event = asyncio.Event()
    _event.set()
    _pause_requested: bool = False
    _resumed_flag: bool = False

    _pause_ids: set[object] = set()

    _super_pause_active = False
    _super_resume_active = False

    class _ObserverInterface(RunningObserver):
        __slots__ = ()
        @property
        def RUNNING(_):
            return _RUNNING
        @property
        def PAUSE(_):
            return _PAUSE
        @property
        def SUPER_PAUSE(_):
            return _SUPER_PAUSE
        @property
        def STOP(_):
            return _STOP
        
        @property
        def current_mode(_):
            return _mode
    
    _observer_interface = _ObserverInterface()

    def _resume():
        nonlocal _resumed_flag, _mode, _super_pause_active, _super_resume_active
        _resumed_flag = True
        _mode = _RUNNING
        _super_resume_active = _super_pause_active
        _super_pause_active = False
        _pause_ids.clear()
        _event.set()
    
    class _RoutineInterface(Pauser, type(_observer_interface)):
        __slots__ = ()
        @staticmethod
        async def consume_on_pause_requested(s: Optional[SubroutineCaller] = None, n: Optional[SubroutineCaller] = None) -> None:
            nonlocal _mode, _pause_requested
            if _pause_requested:
                _pause_requested = False
                _event.clear()
                if _super_pause_active:
                    _mode = _SUPER_PAUSE
                    if s: s()
                else:
                    _mode = _PAUSE
                    if n: n()
        
        @staticmethod
        async def consume_resumed_flag(s: Optional[SubroutineCaller] = None, n: Optional[SubroutineCaller] = None) -> None:
            nonlocal _resumed_flag, _super_resume_active
            if _resumed_flag:
                _resumed_flag = False
                if _super_resume_active:
                    _super_resume_active = False
                    if s: s()
                else:
                    if n: n()
        
        @staticmethod
        def request_pause(id: Optional[object] = None):
            nonlocal _pause_requested
            if id:
                _pause_ids.add(id)
            _pause_requested = True
        
        @staticmethod
        def resume(id: Optional[object] = None) -> bool:
            nonlocal _resumed_flag
            if id and id not in _pause_ids:
                return True
            if _super_pause_active:
                return False
            _resume()
            return True
        
        @staticmethod
        async def wait_resume():
            await _event.wait()
    
    _routine_interface = _RoutineInterface()

    class _RequestInterface(DriverRequest):
        @staticmethod
        def stop() -> None:
            nonlocal _stop
            _stop = True
        
        @staticmethod
        def pause() -> None:
            nonlocal _super_pause_active, _pause_requested
            _super_pause_active = True
            _pause_requested = True
        
        @staticmethod
        def resume() -> None:
            _resume()
    
    _request_interface = _RequestInterface()


    class _Interface(ControlFull):
        @staticmethod
        def get_request() -> DriverRequest:
            return _request_interface

        @staticmethod
        def get_pauser() -> Pauser:
            return _routine_interface
    
        @staticmethod
        def get_observer() -> RunningObserver:
            return _observer_interface
        
        @staticmethod
        def stopped() -> None:
            nonlocal _mode
            _mode = _STOP
        
        @staticmethod
        def reset() -> None:
            nonlocal _mode, _pause_requested, _resumed_flag, _super_pause_active
            _mode = _RUNNING
            _event.set()
            _pause_requested = False
            _resumed_flag = False
            _pause_ids.clear()
            _super_pause_active = False
        
        @staticmethod
        def cleanup() -> None:
            _pause_ids.clear()
    
    
    return _Interface()

