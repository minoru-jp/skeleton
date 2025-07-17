
from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .message import Message


@runtime_checkable
class EventHandler(Protocol):
    def __call__(self, message: Message) -> Any:
        ...

@runtime_checkable
class EventHandlerFull(Protocol):
    @staticmethod
    def get_all_handlers() -> Mapping[str, EventHandler]:
        ...
    
    @staticmethod
    def set_event_handler(event: str, handler: EventHandler) -> None:
        ...
    
    @staticmethod
    def cleanup() -> None:
        ...

def setup_EventHandlerFull() -> EventHandlerFull:

    _ALL_EVENTS = [
        'on_start', 'on_continue', 'on_end', 'on_cancel', 'on_close'
    ]

    def _DEFAULT_EVENT_HANDLER(message: Message):
        log = message.log
        log.logger.info(f"[{log.role}] {message.environment['event']}")
    
    _event_handlers: dict[str, EventHandler]  = {k: _DEFAULT_EVENT_HANDLER for k in _ALL_EVENTS}

    class _Interface(EventHandlerFull):
        @staticmethod
        def get_all_handlers() -> Mapping[str, EventHandler]:
            return MappingProxyType(_event_handlers)
        
        @staticmethod
        def set_event_handler(event: str, handler: EventHandler) -> None:
            if not event in _ALL_EVENTS:
                raise ValueError(f"Event '{event}' is not defined")
            _event_handlers[event] = handler
        
        @staticmethod
        def cleanup() -> None:
            _event_handlers.clear()

    return _Interface()
