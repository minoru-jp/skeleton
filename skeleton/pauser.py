
import asyncio
from typing import Optional, Protocol, Type, runtime_checkable

from .subroutine import SubroutineCaller


@runtime_checkable
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
    def current_mode(self) -> object:
        ...


@runtime_checkable
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


@runtime_checkable
class PauserFull(Protocol):
    @staticmethod
    def get_routine_interface() -> Pauser:
        ...
    
    @staticmethod
    def get_observer_interface() -> RunningObserver:
        ...

    @staticmethod
    def request_super_pause() -> None:
        ...
    
    @staticmethod
    def super_resume() -> None:
        ...
    
    @staticmethod
    def reset() -> None:
        ...

def setup_PauserFull() -> PauserFull:
    
    _RUNNING = object()
    _PAUSE = object()
    _SUPER_PAUSE = object()

    _mode: object = _RUNNING
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



    class _Interface(PauserFull):
        @staticmethod
        def get_routine_interface() -> Pauser:
            return _routine_interface
    
        @staticmethod
        def get_observer_interface() -> RunningObserver:
            return _observer_interface
        
        @staticmethod
        def request_super_pause() -> None:
            nonlocal _super_pause_active, _pause_requested
            _super_pause_active = True
            _pause_requested = True

        @staticmethod
        def super_resume() -> None:
            _resume()
        
        @staticmethod
        def reset() -> None:
            nonlocal _mode, _pause_requested, _resumed_flag, _super_pause_active
            _mode = _RUNNING
            _event.set()
            _pause_requested = False
            _resumed_flag = False
            _pause_ids.clear()
            _super_pause_active = False
    
    
    return _Interface()

