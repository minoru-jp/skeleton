
from asyncio import Protocol
from typing import Any


class LastProcessReader(Protocol):
    @property
    def recorded_last_process(_) -> str:
        ...
    
    @property
    def recorded_last_result(_) -> Any:
        ...

class ResultReader(Protocol):
    @property
    def result(_) -> Any:
        ...
    
    @property
    def outcome(_) -> str:
        ...

    @property
    def error(_) -> Exception:
        ...

    @property
    def subroutine(_) -> LastProcessReader:
        ...

class ResultFull(Protocol):
    @staticmethod
    def get_result_reader(
        result: Any,
        outcome: str,
        last_recorded_process: Any,
        last_recorded_result: Any,
    ) -> ResultReader:
        ...

def setup_ResultFull() -> ResultFull:

    class _NoResult:
        __slots__ = ()
        def __repr__(self):
            return "no result"
        
    _NO_RESULT = _NoResult()

    _result = _NO_RESULT
    _outcome = str(_NO_RESULT)
    _error = None

    class _LastProcessReader(LastProcessReader):
        @property
        def recorded_last_process(_) -> str:
            ...
    
        @property
        def recorded_last_result(_) -> Any:
            ...

    class _ReaderInterface(ResultReader):
        @property
        def result(_) -> Any:
            return _result
        
        @property
        def outcome(_) -> str:
            return _outcome
            
        @property
        def error(_) -> Exception | None:
            return _error

        @property
        def subroutine(_) -> LastProcessReader:
            ...
        
    class _Interface(ResultFull):
        @staticmethod
        def get_result_reader(
            result: Any,
            outcome: str,
            last_recorded_process: Any,
            last_recorded_result: Any,
        ) -> ResultReader:
            ...

    return _Interface()

