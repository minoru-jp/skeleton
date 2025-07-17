
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class _NoRecorded:
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
    
    @staticmethod
    def get_snapshot() -> ProcessRecordReader:
        ...

def _setup_sentinel() -> ProcessRecordReader:

    _NO_RECORDED = _NoRecorded()
    
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
        
        @staticmethod
        def get_snapshot() -> ProcessRecordReader:
            return NO_RECORDED_SENTINEL
    
    return _Interface()


NO_RECORDED_SENTINEL = _setup_sentinel()


class ProcessRecordFull(Protocol):
    @staticmethod
    def get_reader() -> ProcessRecordReader:
        ...
    
    @staticmethod
    def set_result(proc_name: str, result: Any) -> None:
        ...

    @staticmethod
    def cleanup() -> None:
        ...

def setup_ProcessRecordFull() -> ProcessRecordFull:

    _NO_RECORDED = _NoRecorded()

    _last_recorded_process = str(_NO_RECORDED)
    _last_recorded_result = _NO_RECORDED

    _snapshots:list[ProcessRecordFull] = []

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
        
        @staticmethod
        def get_snapshot() -> ProcessRecordReader:
            new = setup_ProcessRecordFull()
            new.set_result(_last_recorded_process, _last_recorded_result)
            _snapshots.append(new)
            return new.get_reader()
    
    _reader = _Reader()

    class _Interface(ProcessRecordFull):
        @staticmethod
        def get_reader() -> ProcessRecordReader:
            return _reader
        
        @staticmethod
        def set_result(proc_name: str, result: Any) -> None:
            nonlocal _last_recorded_process, _last_recorded_result
            _last_recorded_process = proc_name
            _last_recorded_result = result

        @staticmethod
        def cleanup() -> None:
            nonlocal _last_recorded_process, _last_recorded_result
            _last_recorded_process = str(_NO_RECORDED)
            _last_recorded_result = _NO_RECORDED
            for s in _snapshots:
                s.cleanup()
            _snapshots.clear()

    return _Interface()
