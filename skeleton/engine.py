
from __future__ import annotations
import asyncio
import threading
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol, Type, runtime_checkable

if TYPE_CHECKING:
    from .log import Log
    from .context import Context
    from .result import ResultFull
    from .control import ControlFull

def boot_sync_routine_with_thread(
        routine,
        exception_marker: ExceptionMarker,
        log: Log,
        context: Context,
        result_full: ResultFull,
        on_redo_processor: Callable[[], Any],
        on_end_processor: Callable[[], bool],
    ):
    def worker():
        role = log.role
        log.logger.debug(f"[{role}] routine start")
        try:
            while True:
                try:
                    result = routine(context)
                    result_full.set_graceful(result)
                    log.logger.debug(f"[{log.role}] routine end")
                    redo = on_end_processor()
                    if redo:
                        raise context.signal.Redo
                    break
                except context.signal.Redo:
                    on_redo_processor()
                    log.logger.debug(f"[{role}] routine redo")
                    continue
                except context.signal.Graceful as e:
                    result_full.set_graceful(e.result)
                    break
                except context.signal.Resigned as e:
                    result_full.set_resigned(e.result)
                    break
                except Exception as e:
                    log.logger.exception(f"[{log.role}] routine raises exception")
                    raise exception_marker.RoutineError('routine', e)
        except Exception as e:
            result_full.set_error(e)
    
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join()

async def boot_async_routine(
        routine,
        exception_marker: ExceptionMarker,
        log: Log,
        context: Context,
        result_full: ResultFull,
        control_full: ControlFull,
        on_redo_processor: Callable[[], Awaitable[bool]],
        on_end_processor: Callable[[], Awaitable[bool]],
    ):
    role = log.role
    log.logger.debug(f"[{role}] routine start")
    try:
        while True:
            try:
                result = await routine(context)
                result_full.set_graceful(result)
                log.logger.debug(f"[{log.role}] routine end")
                redo = await on_end_processor()
                if redo:
                    raise context.signal.Redo
                break
            except context.signal.Redo:
                await on_redo_processor()
                control_full.reset()
                log.logger.debug(f"[{role}] routine redo")
                continue
            except context.signal.Graceful as e:
                result_full.set_graceful(e.result)
                break
            except context.signal.Resigned as e:
                result_full.set_resigned(e.result)
                break
            except asyncio.CancelledError as e:
                raise exception_marker.RoutineError('routine', e)
            except Exception as e:
                log.logger.exception(f"[{log.role}] routine raises exception")
                raise exception_marker.RoutineError('routine', e)
    except Exception as e:
        result_full.set_error(e)


class MarkedException(Exception):
    def __init__(self, process: str, e: BaseException):
        self.process: str = process
        self.orig_exception: BaseException = e

class ExceptionMarker(Protocol):
    @property
    def RoutineError(_) -> Type[MarkedException]:
        ...

    @property
    def EventHandlerError(_) -> Type[MarkedException]:
        ...
    
    @property
    def ResultHandlerError(_) -> Type[MarkedException]:
        ...

def create_ExceptionMarker() -> ExceptionMarker:
    class RoutineError(MarkedException):
        pass
    
    class EventHandlerError(MarkedException):
        pass
    
    class ResultHandlerError(MarkedException):
        pass

    class _ExceptionMarker(ExceptionMarker):
        @property
        def RoutineError(_) -> Type[MarkedException]:
            return RoutineError
        
        @property
        def EventHandlerError(_) -> Type[MarkedException]:
            return EventHandlerError
        
        @property
        def ResultHandlerError(_) -> Type[MarkedException]:
            return ResultHandlerError
    
    return _ExceptionMarker()
    
