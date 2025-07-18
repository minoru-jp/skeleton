
from __future__ import annotations

import inspect
from types import CoroutineType, MappingProxyType
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, Mapping, Optional, Protocol, Union, runtime_checkable

if TYPE_CHECKING:
    from .record import ProcessRecordFull
    from .message import MessageFull, Message


class EventHandler(Protocol):
    def __call__(self, message: Message) -> Any:
        ...

class OnStart(EventHandler, Protocol):
    def __call__(self, message: Message) -> Any:
        ...

class OnRedo(EventHandler, Protocol):
    def __call__(self, message: Message) -> Any:
        ...

class OnEnd(EventHandler, Protocol):
    def __call__(self, message: Message) -> bool | Awaitable[bool]:
        ...

class OnCancel(EventHandler, Protocol):
    def __call__(self, message: Message) -> Any:
        ...

class OnClose(EventHandler, Protocol):
    def __call__(self, message: Message) -> Any:
        ...

class EventProcessor(Protocol):
    # Callable is used because the caller knows if each processor is sync, async, or universal.
    @property
    def on_start(_) -> Callable:
        ...
    
    @property
    def on_redo(_) -> Callable:
        ...
    
    @property
    def on_end(_) -> Callable:
        ...
    
    @property
    def on_cancel(_) -> Callable:
        ...

    @property
    def on_close(_) -> Callable:
        ...


class EventFull(Protocol):
    @staticmethod
    def setup_event_processor(dedicated: Optional[tuple[str, ...]] = None) -> EventProcessor:
        ...
    
    @staticmethod
    def set_event_handler(event: str, handler: EventHandler) -> None:
        ...

    @staticmethod
    def cleanup() -> None:
        ...

def setup_EventHandlerFull(message_full: MessageFull, record_full: ProcessRecordFull) -> EventFull:

    _ALL_EVENTS = [
        'on_start', 'on_redo', 'on_end', 'on_cancel', 'on_close'
    ]

    def _DEFAULT_EVENT_HANDLER(message: Message):
        log = message.log
        log.logger.debug(f"[{log.role}] {message.event}")
    
    _event_handler_mapping: dict[str, EventHandler]  = {k: _DEFAULT_EVENT_HANDLER for k in _ALL_EVENTS}

    class EventHandlerError(Exception):
        def __init__(self, proc_name: str, e: Exception):
            self.proc_name = proc_name
            self.orig_exception = e
            super().__init__(f"at {proc_name}: {e}")

    def _get_processor(name: str, mode: Literal['universal', 'dedicated']) -> Callable[[], Any] | Callable[[], Awaitable[Any]]:
        handler = _event_handler_mapping[name]
        message = message_full.create_message_for(name)
        if mode == 'universal':
            async def universal_processor():
                try:
                    tmp = handler(message)
                    result = await tmp if inspect.isawaitable(tmp) else tmp
                except Exception as e:
                    raise EventHandlerError(name, e)
                record_full.set_result(name, result)
                return result
            return universal_processor
        else:
            async_ = inspect.iscoroutinefunction(handler)
            if async_:
                async def async_processor():
                    try:
                        result = await handler(message)
                    except Exception as e:
                        raise EventHandlerError(name, e)
                    record_full.set_result(name, result)
                    return result
                return async_processor
            else:
                def sync_processor():
                    try:
                        result = handler(message)
                    except Exception as e:
                        raise EventHandlerError(name, e)
                    record_full.set_result(name, result)
                    return result
                return sync_processor
    
    def setup_EventProcessor(dedicated: Optional[tuple[str]]) -> EventProcessor:
        _processor_mapping: dict[str, Callable[[], Any] | Callable[[], Awaitable[Any]]] = {}
        dedicated = dedicated if dedicated is not None else tuple()
        for k in _event_handler_mapping.keys():
            _processor_mapping[k] = _get_processor(
                k, 'dedicated' if k in dedicated else 'universal')
            
        class _EventProcessor(EventProcessor):
            @property
            def on_start(_) -> Callable:
                return _processor_mapping['on_start']
            
            @property
            def on_redo(_) -> Callable:
                return _processor_mapping['on_redo']
            
            @property
            def on_end(_) -> Callable:
                return _processor_mapping['on_end']
            
            @property
            def on_cancel(_) -> Callable:
                return _processor_mapping['on_cancel']
            
            @property
            def on_close(_) -> Callable:
                return _processor_mapping['on_close']
        
        return _EventProcessor()

    class _Interface(EventFull):
        @staticmethod
        def setup_event_processor(dedicated: Optional[tuple[str]] = None) -> EventProcessor:
            if dedicated:
                if not all(k in _ALL_EVENTS for k in dedicated):
                    raise ValueError(f"Undefined event name found")
            return setup_EventProcessor(dedicated)
        
        @staticmethod
        def set_event_handler(event: str, handler: EventHandler) -> None:
            if not event in _ALL_EVENTS:
                raise ValueError(f"Event '{event}' is not defined")
            _event_handler_mapping[event] = handler
        
        @staticmethod
        def cleanup() -> None:
            _event_handler_mapping.clear()

    return _Interface()
