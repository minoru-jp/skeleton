
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from . import log
from . import context


class Messenger(Protocol):
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
class Message(Protocol):
    @property
    def log(_) -> log.Log:
        ...
    
    @property
    def event_messenger(_) -> Messenger:
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
class MessageFull(Protocol):
    @staticmethod
    def create_message_for(event_name: str) -> Message:
        ...

    @staticmethod
    def get_environment() -> Messenger:
        ...
    
    @staticmethod
    def get_event_messenger() -> Messenger:
        ...

    @staticmethod
    def get_routine_messenger() -> Messenger:
        ...
    
    @staticmethod
    def cleanup() -> None:
        ...
    

def setup_MessageFull(log: log.Log) -> MessageFull:

    _environment: dict[str, Any] = {}
    _read_only_environment = MappingProxyType(_environment)
    
    class _EnvironmentInterface(Messenger):
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

    class _EventMessengerInterface(Messenger):
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

    
    _event_messenger_interface = _EventMessengerInterface()

    _routine_message: dict[str, Any] = {}
    _read_only_routine_message = MappingProxyType(_routine_message)

    class _RoutineMessengerInterface(Messenger):
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
    
    _routine_messenger_interface = _RoutineMessengerInterface()



    # Create a message bound to an event name
    def setup_Message(event_name) -> Message:

        class _Interface(Message):
            __slots__ = ()
            @property
            def log(_) -> log.Log:
                return log
            
            @property
            def event_messenger(_) -> Messenger:
                return _event_messenger_interface
            
            @property
            def environment(_) -> Mapping[str, Any]:
                return _read_only_environment
            
            @property
            def routine_message(_) -> Mapping[str, Any]:
                return _read_only_routine_message
            
            @property
            def event(_) -> str:
                return event_name
    
        return _Interface()
    

    
    class _Interface(MessageFull):
        __slots__ = ()
        @staticmethod
        def create_message_for(event_name: str) -> Message:
            return setup_Message(event_name)

        @staticmethod
        def get_environment() -> Messenger:
            return _environment_interface
        
        @staticmethod
        def get_event_messenger() -> Messenger:
            return _event_messenger_interface
        
        @staticmethod
        def get_routine_messenger() -> Messenger:
            return _routine_messenger_interface
        
        @staticmethod
        def cleanup() -> None:
            _event_message.clear()
            _environment.clear()
            _environment.clear()

    return _Interface()
