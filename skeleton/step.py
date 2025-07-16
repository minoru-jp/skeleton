

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StepSlot(Protocol):
    @property
    def UNSET(self) -> object:
        ...

    @staticmethod
    def set_result(proc_name: str, result: Any) -> None:
        ...

    @property
    def prev_proc(_) -> str:
        ...

    @property
    def prev_result(_) -> Any:
        ...

    @staticmethod
    def cleanup() -> None:
        ...

def setup_StepSlot() -> StepSlot:

    _UNSET = object()

    _prev_proc: str = '<unset>'
    _prev_result: Any = _UNSET

    class _Interface(StepSlot):
        __slots__ = ()
        @property
        def UNSET(_):
            return _UNSET
        @staticmethod
        def set_result(proc_name: str, result: Any):
            nonlocal _prev_proc, _prev_result
            _prev_proc = proc_name
            _prev_result = result
        @property
        def prev_proc(_):
            return _prev_proc
        @property
        def prev_result(_):
            return _prev_result
        @staticmethod
        def cleanup() -> None:
            nonlocal _prev_proc, _prev_result
            _prev_proc = '<unset>'
            _prev_result = _UNSET

    return _Interface()
