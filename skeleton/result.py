
from __future__ import annotations

from typing import Any, Protocol

from .log import Log
from .record import ProcessRecordReader, NO_RECORDED_SENTINEL


def DEAULT_RESULT_HANDLER(result: ResultReader):
    log = result.log
    log.logger.info(
        f"[{log.role}] loop result \n"
        f"    outcome: {result.outcome}"
        f"    return value: {result.return_value}\n"
        f"    recorded last event process: {result.event.last_recorded_process}\n"
        f"    recorded last event result: {result.event.last_recorded_result}\n"
        f"    recorded last routine process: {result.routine.last_recorded_process}\n"
        f"    recorded last routine result: {result.routine.last_recorded_result}\n"
        f"    error: {result.error}\n"
        )
    
    return False # rethrow if exception has raised


class ResultHandler(Protocol):
    def __call__(self, result: ResultReader) -> bool:
        ...

class ResultReader(Protocol):
    @property
    def NO_RESULT(_) -> object:
        ...

    @property
    def log(_) -> Log:
        ...
        
    @property
    def return_value(_) -> Any:
        ...
    
    @property
    def outcome(_) -> str:
        ...

    @property
    def error(_) -> Exception:
        ...

    @property
    def event(_) -> ProcessRecordReader:
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
    def set_error(e: BaseException) -> None:
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

    _return_value = _NO_RESULT
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
        def return_value(_) -> Any:
            return _return_value
        
        @property
        def outcome(_) -> str:
            return _outcome
            
        @property
        def error(_) -> BaseException | None:
            return _error

        @property
        def event(_) -> ProcessRecordReader:
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
            nonlocal _outcome, _return_value
            _outcome = 'graceful'
            _return_value = obj
        
        @staticmethod
        def set_resigned(obj: Any) -> None:
            nonlocal _outcome, _return_value
            _outcome = 'resigned'
            _return_value = obj
        
        @staticmethod
        def set_error(e: BaseException) -> None:
            nonlocal _outcome, _error
            _outcome = 'fail'
            _error = e
        
        @staticmethod
        def get_reader() -> ResultReader:
            return _reader

    return _Interface()

