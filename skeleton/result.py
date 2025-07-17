
from __future__ import annotations

from typing import Any, Protocol

from .log import Log
from .record import ProcessRecordReader, NO_RECORDED_SENTINEL



class ResultReader(Protocol):
    @property
    def NO_RESULT(_) -> object:
        ...

    @property
    def log(_) -> Log:
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
    def evnet(_) -> ProcessRecordReader:
        ...
    
    @property
    def routine(_) -> ProcessRecordReader:
        ...

class ResultFull(Protocol):
    @staticmethod
    def set_event_process_record(record: ProcessRecordReader) -> None:
        ...
    
    @staticmethod
    def set_routine_process_record(record: ProcessRecordReader) -> None:
        ...
    
    @staticmethod
    def set_graceful(obj: Any) -> None:
        ...
    
    @staticmethod
    def set_resigned(obj: Any) -> None:
        ...
    
    @staticmethod
    def set_error(e: Exception) -> None:
        ...
    
    @staticmethod
    def get_reader() -> ResultReader:
        ...

def setup_ResultFull(log: Log) -> ResultFull:

    class _NoResult:
        __slots__ = ()
        def __repr__(self):
            return "no result"
    
    _NO_RESULT = _NoResult()

    _result = _NO_RESULT
    _outcome = str(_NO_RESULT)
    _error = None

    _event_process_record = NO_RECORDED_SENTINEL
    _routine_process_record = NO_RECORDED_SENTINEL

    class _Reader(ResultReader):
        @property
        def NO_RESULT(_) -> object:
            return _NO_RESULT
        
        @property
        def log(_) -> Log:
            return log
        
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
        def evnet(_) -> ProcessRecordReader:
            return _event_process_record
        
        @property
        def routine(_) -> ProcessRecordReader:
            return _routine_process_record

    
    _reader = _Reader()

    class _Interface(ResultFull):
        @staticmethod
        def set_event_process_record(record: ProcessRecordReader) -> None:
            nonlocal _event_process_record
            _event_process_record = record.get_snapshot()
            
        @staticmethod
        def set_routine_process_record(record: ProcessRecordReader) -> None:
            nonlocal _routine_process_record
            _routine_process_record = record.get_snapshot()
        
        @staticmethod
        def set_graceful(obj: Any) -> None:
            nonlocal _outcome, _result
            _outcome = 'graceful'
            _result = obj
        
        @staticmethod
        def set_resigned(obj: Any) -> None:
            nonlocal _outcome, _result
            _outcome = 'resigned'
            _result = obj
        
        @staticmethod
        def set_error(e: Exception) -> None:
            nonlocal _error
            _error = e
        
        @staticmethod
        def get_reader() -> ResultReader:
            return _reader

    return _Interface()

