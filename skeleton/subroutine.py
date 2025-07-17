
from __future__ import annotations

import inspect
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Callable, Generic, Optional, Protocol, Tuple, Type, TypeVar, cast, runtime_checkable

from .context import T_in

if TYPE_CHECKING:
    from .context import Context
    from .step import StepSlot

CAST = TypeVar("CAST")

@runtime_checkable
class Subroutine(Protocol, Generic[T_in]):
    def __call__(self, context: Context[T_in]) -> Any:
        ...

class SubroutineCaller(Protocol):
    def __call__(self) -> Any:
        ...

@runtime_checkable
class CallerAccessor(Protocol):
    def __call__(self, proto: Type[CAST]) -> CAST:
        ...

@runtime_checkable
class FunctionAccessor(Protocol):
    def __call__(self, proto: Type[CAST]) -> CAST:
        ...

SecureNameMapper = Callable[[Optional[str]], Optional[str]]

@runtime_checkable
class SubroutineFull(Protocol):
    @staticmethod
    def get_accessor(context: Context, step: StepSlot) -> CallerAccessor:
        ...
    
    @staticmethod
    def get_raw_accessor() -> FunctionAccessor:
        ...

    @staticmethod
    def append_subroutine(fn: Subroutine, name: Optional[str] = None) -> None:
        ...
    
    @staticmethod
    def get_subroutines() -> MappingProxyType[str, Subroutine]:
        ...
    
    @staticmethod
    def remap_to_secure_subroutine_name():
        ...
    
    @staticmethod
    def remap_to_raw_subroutine_name():
        ...
    
    @staticmethod
    def translate_raw_to_secure_name(raw_call_name) -> str:
        ...

    @staticmethod
    def cleanup() -> None:
        ...


def setup_SubroutineFull() -> SubroutineFull:

    def _get_wrapper(call_name: str, fn: Subroutine, context: Context, step: StepSlot):
        async_ = inspect.iscoroutinefunction(fn)
        set_result = step.set_result
        if async_:
            async def calla():
                set_result(call_name, await fn(context))
            return calla
        else:
            def call():
                set_result(call_name, fn(context))
            return call
    
    # _cast() applied to accessor __call__
    def _cast(self, proto: Type[CAST]) -> CAST:
        if not isinstance(proto, type):
            raise TypeError(f"Expected a type, got {type(proto).__name__}")
        if isinstance(self, proto):
            return cast(CAST, self)
        else:
            raise TypeError(f"Object of type {type(self).__name__} does not implement {proto.__name__}")
    

    _secure_subroutine_mapping = {}
    _raw_subroutine_mapping = {}

    # mapped raw subroutine name to secure subroutine name
    _subroutine_name_correspound_table: dict[str, str] = {}

    _subroutine_mapping = _raw_subroutine_mapping

    class _Imple(SubroutineFull):
        __slots__ = ()
        @staticmethod
        def get_accessor(context: Context, step: StepSlot) -> CallerAccessor:

            _wrapped_subroutines = {} # call name: wrapped subroutine

            for call_name, subroutine in _subroutine_mapping.items():
                _wrapped_subroutines[call_name] = _get_wrapper(call_name, subroutine, context, step)
            
            ns: dict[str, Callable] = {k: staticmethod(v) for k, v in _wrapped_subroutines.items()}
            ns["__call__"] = _cast

            _Accessor = type('_SubroutineAccessor', (CallerAccessor,), ns)
            
            return _Accessor()
        
        @staticmethod
        def get_raw_accessor() -> FunctionAccessor:

            _raw_subroutines = {k: v for k, v in _subroutine_mapping.items()}
            
            ns: dict[str, Callable] = {k: staticmethod(v) for k, v in _raw_subroutines.items()}
            ns["__call__"] = _cast

            _Accessor = type('_SubroutineRawAccessor', (FunctionAccessor,), ns)
            
            return _Accessor()
            
        @staticmethod
        def append_subroutine(fn: Subroutine, name: Optional[str] = None) -> None:
            raw_call_name = name or getattr(fn, '__name__', None)
            if not raw_call_name or not isinstance(raw_call_name, str) or not raw_call_name.isidentifier():
                raise ValueError(f"Subroutine name must be defined as valid python identifier. Not '{raw_call_name}'")
            if raw_call_name in _subroutine_mapping:
                raise ValueError(f"Subroutine name is duplicated '{raw_call_name}'.")
            _raw_subroutine_mapping[raw_call_name] = fn
            secure_call_name = f"subroutine{len(_secure_subroutine_mapping)}"
            _secure_subroutine_mapping[secure_call_name] = fn
            _subroutine_name_correspound_table[raw_call_name] = secure_call_name
        
        @staticmethod
        def get_subroutines() -> MappingProxyType[str, Subroutine]:
            return MappingProxyType(_subroutine_mapping)
        
        @staticmethod
        def remap_to_secure_subroutine_name():
            nonlocal _subroutine_mapping
            _subroutine_mapping = _secure_subroutine_mapping
        
        @staticmethod
        def remap_to_raw_subroutine_name():
            nonlocal _subroutine_mapping
            _subroutine_mapping = _raw_subroutine_mapping
        
        @staticmethod
        def translate_raw_to_secure_name(raw_call_name: Optional[str]) -> Optional[str]:
            if raw_call_name is None:
                return None
            return _subroutine_name_correspound_table.get(raw_call_name)
            
    
        @staticmethod
        def cleanup() -> None:
            _secure_subroutine_mapping.clear()
            _raw_subroutine_mapping.clear()
    
    return _Imple()

