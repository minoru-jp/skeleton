
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Literal, Mapping, Optional, Protocol, Tuple, Type, TypeVar, cast, runtime_checkable


from .record import setup_ProcessRecordFull


if TYPE_CHECKING:
    from .log import Log
    from .subroutine import Subroutine, SubroutineFull, CallerAccessor, FunctionAccessor
    from .control import Pauser
    from .message import Message
    from .record import ProcessRecordFull, ProcessRecordReader
    from .message import Messenger

T_im = TypeVar("T_im")
T_out = TypeVar("T_out", covariant=True)
T = TypeVar("T", contravariant=True)


class ReturnValue(Exception):
    def __init__(self, obj: Any):
        self.result = obj

@runtime_checkable
class Signal(Protocol):
    @property
    def Redo(_) -> Type[Exception]:
        ...
    
    @property
    def Graceful(_) -> Type[ReturnValue]:
        ...
    
    @property
    def Resigned(_) -> Type[ReturnValue]:
        ...

@runtime_checkable
class PrevResultReader(Protocol):
    @property
    def process(_) -> str:
        ...
    
    @property
    def result(_) -> Any:
        ...


@runtime_checkable
class Context(Protocol, Generic[T_out]):
    
    @property
    def log(_) -> Log:
        ...

    @property
    def pauser(_) -> Pauser:
        ...

    @property
    def signal(_) -> Signal:
        ...

    @property
    def prev(_) -> PrevResultReader:
        ...
    
    @property
    def caller(_) -> CallerAccessor:
        ...
    
    @property
    def function(_) -> FunctionAccessor:
        ...

    @property
    def environment(_) -> Mapping[str, Any]:
        ...
    
    @property
    def event_message(_) -> Mapping[str, Any]:
        ...

    @property
    def routine_message(_) -> Messenger:
        ...
    
    @property
    def field(_) -> T_out:
        ...

    

@runtime_checkable
class ContextFull(Protocol, Generic[T_im]):
    @staticmethod
    def setup_context() -> Context[T_im]:
        ...
    
    @staticmethod
    def load_context_caller_accessors() -> None:
        ...
    
    @staticmethod
    def set_field(field: T_im) -> None:
        ...

    @staticmethod
    def cleanup() -> None:
        ...
    

def setup_ContextFull(
        log: Log,
        subroutine_full: SubroutineFull,
        pauser: Pauser,
        routine_process_record: ProcessRecordFull,
        environment: Mapping[str, Any],
        event_message: Mapping[str, Any],
        routine_message: Messenger):
    
    class Redo(Exception):
        pass


    class Graceful(ReturnValue):
        pass

    class Resigned(ReturnValue):
        pass

    class _Signal(Signal):
        @property
        def Redo(_) -> Type[Exception]:
            return Redo
        
        @property
        def Graceful(_) -> Type[Exception]:
            return Graceful
        
        @property
        def Resigned(_) -> Type[Exception]:
            return Resigned
        
    _signal = _Signal()

    _routine_process_record_reader = routine_process_record.get_reader()

    class _PrevResultReaderInterface(PrevResultReader):
        @property
        def process(_) -> str:
            return _routine_process_record_reader.last_recorded_process
        
        @property
        def result(_) -> Any:
            return _routine_process_record_reader.last_recorded_result
    
    _prev_result_reader = _PrevResultReaderInterface()

    _caller_accessor = None
    _function_accessor = None

    def setup_Context(field: T_im) -> Context[T_im]:
        
        class _Interface(Context):
            __slots__ = ()
            @property
            def log(_) -> Log:
                return log
            
            @property
            def pauser(_) -> Pauser:
                return pauser
            
            @property
            def signal(_) -> Signal:
                return _signal
            
            @property
            def prev(_) -> PrevResultReader:
                return _prev_result_reader

            @property
            def caller(_) -> CallerAccessor:
                assert _caller_accessor is not None
                return _caller_accessor
            
            @property
            def function(_) -> FunctionAccessor:
                assert _function_accessor is not None
                return _function_accessor
            
            @property
            def environment(_) -> Mapping[str, Any]:
                return environment
            
            @property
            def event_message(_) -> Mapping[str, Any]:
                return event_message
            
            @property
            def routine_message(_) -> Messenger:
                return routine_message
        
            @property
            def field(_) -> T_im:
                return field
        
        return _Interface()
    
    _NO_SETUP = object()

    _context = _NO_SETUP
    
    _field = None
    
    class _Interface(ContextFull[T_im]):
        @staticmethod
        def setup_context() -> Context[T_im]:
            nonlocal _context
            if _context is not _NO_SETUP:
                if isinstance(_context, Context):
                    raise RuntimeError("context has already been set up.")
                elif _context is None:
                    raise RuntimeError("ContextFull has been cleaned up")
                else:
                    raise RuntimeError("Internal error")
            
            _context = setup_Context(cast(T_im, _field))
            return _context
        
        @staticmethod
        def load_context_caller_accessors() -> None:
            nonlocal _caller_accessor, _function_accessor
            if not isinstance(_context, Context):
                if _context is _NO_SETUP:
                    raise RuntimeError("setup_context has not been called")
                elif _context is None:
                    raise RuntimeError("ContextFull has been cleaned up")
                else:
                    raise RuntimeError("Internal error")
            _caller_accessor = subroutine_full.get_accessor(_context, routine_process_record)
            _function_accessor = subroutine_full.get_raw_accessor()
        
        @staticmethod
        def set_field(field: T_im) -> None:
            nonlocal _field
            _field = field
        
        @staticmethod
        def cleanup() -> None:
            nonlocal _context, _caller_accessor, _function_accessor, _field
            _context = None
            _caller_accessor = None
            _function_accessor = None
            _field = None

    
    return _Interface()
