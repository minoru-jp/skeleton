

import logging
from typing import Protocol, runtime_checkable


@runtime_checkable
class Log(Protocol):
    @property
    def role(_) -> str:
        ...
    
    @property
    def logger(_) -> logging.Logger:
        ...

@runtime_checkable
class LogFull(Protocol):
    @staticmethod
    def get_reader() -> Log:
        ...

    @staticmethod
    def set_role(role: str) -> None:
        ...
    
    @staticmethod
    def set_logger(logger: logging.Logger) -> None:
        ...
    
    @property
    def role(_) -> str:
        ...
    
    @property
    def logger(_) -> logging.Logger:
        ...


def setup_LogFull() -> LogFull:
    
    _role = 'loop'
    _logger = logging.Logger(__name__ + '_default_logger')

    class _Reader(Log):
        @property
        def role(_) -> str:
            return _role
        @property
        def logger(_) -> logging.Logger:
            return _logger
    
    _reader = _Reader()

    class _Imple(LogFull):
        @staticmethod
        def get_reader() -> Log:
            return _reader

        @staticmethod
        def set_role(role: str) -> None:
            nonlocal _role
            _role = role
        
        @staticmethod
        def set_logger(logger: logging.Logger) -> None:
            nonlocal _logger
            _logger = logger
        
        @property
        def role(_) -> str:
            return _reader.role
        
        @property
        def logger(_) -> logging.Logger:
            return _reader.logger
    
    return _Imple()
