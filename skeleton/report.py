
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from . import log
from . import context


class Message(Protocol):
    @staticmethod
    def update(key: str, value: Any) -> None:
        ...
    @staticmethod
    def delete(key: str) -> None:
        ...
    @staticmethod
    def clear() -> None:
        ...
    @property
    def mapping(_) -> Mapping[str, Any]:
        ...

@runtime_checkable
class ReportReader(Protocol):
    @property
    def log(_) -> log.Log:
        ...

    @property
    def error(_) -> Exception | None:
        ...
    
    @property
    def last_routine_process(_) -> str | None:
        ...

    @property
    def last_routine_result(_) -> Any:
        ...
    
    @property
    def event_message(_) -> Message:
        ...

    @property
    def environment(_) -> Mapping[str, Any]:
        ...
    
    @property
    def routine_message(_) -> Mapping[str, Any]:
        ...
    
    @property
    def event(_) -> str:
        ...


@runtime_checkable
class ReportFull(Protocol):
    @staticmethod
    def get_reader() -> ReportReader:
        ...
    
    @staticmethod
    def set_error(e: Exception) -> None:
        ...

    @staticmethod
    def set_last_routine_process(process: str) -> None:
        ...
    
    @staticmethod
    def set_last_routine_result(result: Any) -> None:
        ...

    @staticmethod
    def get_environment() -> Message:
        ...
    
    @staticmethod
    def get_event_message() -> Message:
        ...

    @staticmethod
    def get_routine_message() -> Message:
        ...
    
    @staticmethod
    def set_event_name(evnet_name: str) -> None:
        ...
    
    @staticmethod
    def cleanup() -> None:
        ...
    

def setup_ReportFull(log: log.Log) -> ReportFull:

    _error = None
    _last_routine_process = None
    _last_routine_result = None
    _event_name: str = '<unset>'


    _environment: dict[str, Any] = {}
    _read_only_environment = MappingProxyType(_environment)
    
    class _EnvironmentInterface(Message):
        __slots__ = ()
        @staticmethod
        def update(key: str, value: Any) -> None:
            if not isinstance(key, str):
                raise ValueError(f"key must be a str not '{type(key)}'")
            _environment[key] = value
        
        @staticmethod
        def delete(key: str) -> None:
            _environment.pop(key, None)
        
        @staticmethod
        def clear() -> None:
            _environment.clear()
        
        @property
        def mapping(_) -> Mapping[str, Any]:
            return _read_only_environment
    
    _environment_interface = _EnvironmentInterface()



    _event_message: dict[str, Any] = {}
    _read_only_event_message = MappingProxyType(_event_message)

    class _EventMessageInterface(Message):
        __slots__ = ()
        @staticmethod
        def update(key: str, value: Any) -> None:
            if not isinstance(key, str):
                raise ValueError(f"key must be a str not '{type(key)}'")
            _event_message[key] = value
        
        @staticmethod
        def delete(key: str) -> None:
            _event_message.pop(key, None)
        
        @staticmethod
        def clear() -> None:
            _event_message.clear()
        
        @property
        def mapping(_) -> Mapping[str, Any]:
            return _read_only_event_message

    
    _event_message_interface = _EventMessageInterface()

    _routine_message: dict[str, Any] = {}
    _read_only_routine_message = MappingProxyType(_routine_message)

    class _RoutineMessageInterface(Message):
        __slots__ = ()
        @staticmethod
        def update(key: str, value: Any) -> None:
            if not isinstance(key, str):
                raise ValueError(f"key must be a str not '{type(key)}'")
            _routine_message[key] = value
        
        @staticmethod
        def delete(key: str) -> None:
            _routine_message.pop(key, None)
        
        @staticmethod
        def clear() -> None:
            _routine_message.clear()
        
        @property
        def mapping(_) -> Mapping[str, Any]:
            return _read_only_routine_message
    
    _routine_message_interface = _RoutineMessageInterface()



    def setup_ReportReader() -> ReportReader:
        
        _snapshot_error = _error
        _snapshot_last_routine_process = _last_routine_process
        _snapshot_last_routine_result = _last_routine_result
        _snapshot_event_name = _event_name

        class _Interface(ReportReader):
            __slots__ = ()
            @property
            def log(_) -> log.Log:
                return log
            
            @property
            def error(_) -> Exception | None:
                return _snapshot_error
            
            @property
            def last_routine_process(_) -> str | None:
                return _snapshot_last_routine_process

            @property
            def last_routine_result(_) -> Any:
                return _snapshot_last_routine_result
            
            @property
            def event_message(_) -> Message:
                return _event_message_interface
            
            @property
            def environment(_) -> Mapping[str, Any]:
                return _read_only_environment
            
            @property
            def routine_message(_) -> Mapping[str, Any]:
                return _read_only_routine_message
            
            @property
            def event(_) -> str:
                return _snapshot_event_name
    
        return _Interface()
    

    
    class _Interface(ReportFull):
        __slots__ = ()
        @staticmethod
        def get_reader() -> ReportReader:
            return setup_ReportReader()
        
        @staticmethod
        def set_error(e: Exception) -> None:
            nonlocal _error
            _error = e

        @staticmethod
        def set_last_routine_process(process: str) -> None:
            nonlocal _last_routine_process
            _last_routine_process = process
        
        @staticmethod
        def set_last_routine_result(result: Any) -> None:
            nonlocal _last_routine_result
            _last_routine_result = result

        @staticmethod
        def get_environment() -> Message:
            return _environment_interface
        
        @staticmethod
        def get_event_message() -> Message:
            return _event_message_interface
        
        @staticmethod
        def get_routine_message() -> Message:
            return _routine_message_interface
        
        @staticmethod
        def set_event_name(event_name: str) -> None:
            nonlocal _event_name
            _event_name = event_name
        
        @staticmethod
        def cleanup() -> None:
            _event_message.clear()
            _environment.clear()
            _environment.clear()

    return _Interface()
