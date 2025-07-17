
from asyncio import Protocol
from typing import Any


class LastProcessReader(Protocol):
    @property
    def NO_RECORDED(_) -> object:
        ...

    @property
    def recorded_last_process(_) -> str:
        ...
    
    @property
    def recorded_last_result(_) -> Any:
        ...

class ResultReader(Protocol):
    @property
    def NO_RESULT(_) -> object:
        ...
        
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
    def process(_) -> LastProcessReader:
        ...

class ResultFull(Protocol):
    @staticmethod
    def set_recorded_last_process(name: str) -> None:
        ...
    
    @staticmethod
    def set_recorded_last_result(obj: Any) -> None:
        ...
    
    @staticmethod
    def set_result(outcome: str, obj: Any) -> None:
        ...
    
    @staticmethod
    def get_result_reader() -> ResultReader:
        ...

def setup_ResultFull() -> ResultFull:

    class _NoResult:
        __slots__ = ()
        def __repr__(self):
            return "no result"
    
    class _NoRecoded:
        __slots__ = ()
        def __repr__(self):
            return "no recoded"
        
    _NO_RESULT = _NoResult()
    _NO_RECORDED = _NoRecoded()

    _result = _NO_RESULT
    _outcome = str(_NO_RESULT)
    _error = None

    _last_recorded_process = str(_NO_RECORDED)
    _last_recorded_result = _NO_RECORDED

    class _LastProcessReader(LastProcessReader):
        @property
        def NO_RECORDED(_) -> object:
            return _NO_RECORDED
        
        @property
        def recorded_last_process(_) -> str:
            return _last_recorded_process
    
        @property
        def recorded_last_result(_) -> Any:
            return _last_recorded_result
    
    _last_process_reader = _LastProcessReader()

    class _ResultReaderInterface(ResultReader):
        @property
        def NO_RESULT(_) -> object:
            return _NO_RESULT
        
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
        def process(_) -> LastProcessReader:
            return _last_process_reader
    
    _result_reader = _ResultReaderInterface()

    class _Interface(ResultFull):
        @staticmethod
        def set_recorded_last_process(name: str) -> None:
            nonlocal _last_recorded_process
            _last_recorded_process = name
        
        @staticmethod
        def set_recorded_last_result(obj: Any) -> None:
            nonlocal _last_recorded_result
            _last_recorded_result = obj
        
        @staticmethod
        def set_result(outcome: str, obj: Any) -> None:
            nonlocal _outcome, _result
            _outcome = outcome
            _result = obj
        
        @staticmethod
        def get_result_reader() -> ResultReader:
            return _result_reader

    return _Interface()

