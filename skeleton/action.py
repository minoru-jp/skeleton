
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
class Action(Protocol, Generic[T_in]):
    def __call__(self, context: Context[T_in]) -> Any:
        ...

class ActionCaller(Protocol):
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
class ActionFull(Protocol):
    @staticmethod
    def get_accessor(context: Context, step: StepSlot) -> CallerAccessor:
        ...
    
    @staticmethod
    def get_raw_accessor() -> FunctionAccessor:
        ...

    @staticmethod
    def append_action(action: Action, name: Optional[str] = None) -> None:
        ...
    
    @staticmethod
    def get_actions() -> MappingProxyType[str, Action]:
        ...
    
    @staticmethod
    def remap_to_secure_action_name():
        ...
    
    @staticmethod
    def remap_to_raw_action_name():
        ...
    
    @staticmethod
    def translate_raw_to_secure_name(raw_call_name) -> str:
        ...

    @staticmethod
    def cleanup() -> None:
        ...


def setup_ActionRegistry() -> ActionFull:

    def _get_wrapper(call_name: str, action: Action, context: Context, step: StepSlot):
        async_ = inspect.iscoroutinefunction(action)
        set_result = step.set_result
        if async_:
            async def calla():
                set_result(call_name, await action(context))
            return calla
        else:
            def call():
                set_result(call_name, action(context))
            return call
    
    # _cast() applied to accessor __call__
    def _cast(self, proto: Type[CAST]) -> CAST:
        if not isinstance(proto, type):
            raise TypeError(f"Expected a type, got {type(proto).__name__}")
        if isinstance(self, proto):
            return cast(CAST, self)
        else:
            raise TypeError(f"Object of type {type(self).__name__} does not implement {proto.__name__}")
    

    _secure_action_mapping = {}
    _raw_action_mapping = {}

    # mapped raw action name to secure action name
    _action_name_correspound_table: dict[str, str] = {}

    _action_mapping = _raw_action_mapping

    class _Imple(ActionFull):
        __slots__ = ()
        @staticmethod
        def get_accessor(context: Context, step: StepSlot) -> CallerAccessor:

            _wrapped_actions = {} # call name: wrapped action

            for call_name, action in _action_mapping.items():
                _wrapped_actions[call_name] = _get_wrapper(call_name, action, context, step)
            
            ns: dict[str, Callable] = {k: staticmethod(v) for k, v in _wrapped_actions.items()}
            ns["__call__"] = _cast

            _Accessor = type('_ActionAccessor', (CallerAccessor,), ns)
            
            return _Accessor()
        
        @staticmethod
        def get_raw_accessor() -> FunctionAccessor:

            _raw_actions = {k: v for k, v in _action_mapping.items()}
            
            ns: dict[str, Callable] = {k: staticmethod(v) for k, v in _raw_actions.items()}
            ns["__call__"] = _cast

            _Accessor = type('_ActionRawAccessor', (FunctionAccessor,), ns)
            
            return _Accessor()
            
        @staticmethod
        def append_action(action: Action, name: Optional[str] = None) -> None:
            raw_call_name = name or getattr(action, '__name__', None)
            if not raw_call_name or not isinstance(raw_call_name, str) or not raw_call_name.isidentifier():
                raise ValueError(f"Action name must be defined as valid python identifier. Not '{raw_call_name}'")
            if raw_call_name in _action_mapping:
                raise ValueError(f"Action name is duplicated '{raw_call_name}'.")
            _raw_action_mapping[raw_call_name] = action
            secure_call_name = f"action{len(_secure_action_mapping)}"
            _secure_action_mapping[secure_call_name] = action
            _action_name_correspound_table[raw_call_name] = secure_call_name
        
        @staticmethod
        def get_actions() -> MappingProxyType[str, Action]:
            return MappingProxyType(_action_mapping)
        
        @staticmethod
        def remap_to_secure_action_name():
            nonlocal _action_mapping
            _action_mapping = _secure_action_mapping
        
        @staticmethod
        def remap_to_raw_action_name():
            nonlocal _action_mapping
            _action_mapping = _raw_action_mapping
        
        @staticmethod
        def translate_raw_to_secure_name(raw_call_name: Optional[str]) -> Optional[str]:
            if raw_call_name is None:
                return None
            return _action_name_correspound_table.get(raw_call_name)
            
    
        @staticmethod
        def cleanup() -> None:
            _secure_action_mapping.clear()
            _raw_action_mapping.clear()
    
    return _Imple()

