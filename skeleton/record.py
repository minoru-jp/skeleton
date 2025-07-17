
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class _NoRecoded:
    __slots__ = ()
    def __repr__(self):
        return "no recoded"

class ProcessRecordReader(Protocol):
    @property
    def NO_RECORDED(_) -> object:
        ...

    @property
    def last_recorded_process(_) -> str:
        ...
    
    @property
    def last_recorded_result(_) -> Any:
        ...

def _setup_sentinel() -> ProcessRecordReader:

    _NO_RECORDED = _NoRecoded()
    
    class _Interface(ProcessRecordReader):
        @property
        def NO_RECORDED(_) -> object:
            return _NO_RECORDED

        @property
        def last_recorded_process(_) -> str:
            return str(_NO_RECORDED)
        
        @property
        def last_recorded_result(_) -> Any:
            return _NO_RECORDED
    
    return _Interface()


NO_RECORDED_SENTINEL = _setup_sentinel()


class ProcessRecordFull(Protocol):
    @staticmethod
    def get_process_record_reader() -> ProcessRecordReader:
        ...
    
    @staticmethod
    def set_result(proc_name: str, result: Any) -> None:
        ...
    
    @staticmethod
    def get_snapshot() -> ProcessRecordFull:
        ...

    @staticmethod
    def cleanup() -> None:
        ...

def setup_ProcessRecordFull() -> ProcessRecordFull:

    _NO_RECORDED = _NoRecoded()

    _last_recorded_process = str(_NO_RECORDED)
    _last_recorded_result = _NO_RECORDED


    class _Reader(ProcessRecordReader):
        @property
        def NO_RECORDED(_) -> object:
            return _NO_RECORDED
        
        @property
        def last_recorded_process(_) -> str:
            return _last_recorded_process
    
        @property
        def last_recorded_result(_) -> Any:
            return _last_recorded_result
    
    _reader = _Reader()

    class _Interface(ProcessRecordFull):
        @staticmethod
        def get_process_record_reader() -> ProcessRecordReader:
            return _reader
        
        @staticmethod
        def set_result(proc_name: str, result: Any) -> None:
            nonlocal _last_recorded_process, _last_recorded_result
            _last_recorded_process = proc_name
            _last_recorded_result = result
        
        @staticmethod
        def get_snapshot() -> ProcessRecordFull:
            new = setup_ProcessRecordFull()
            new.set_result(_last_recorded_process, _last_recorded_result)
            return new

        @staticmethod
        def cleanup() -> None:
            nonlocal _last_recorded_process, _last_recorded_result
            _last_recorded_process = str(_NO_RECORDED)
            _last_recorded_result = _NO_RECORDED

    return _Interface()




