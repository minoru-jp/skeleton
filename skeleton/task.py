
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .state import UsageStateFull

@runtime_checkable
class TaskControl(Protocol):
    @staticmethod
    def start(
        fn: Callable[..., Any], *fn_args: Any, **fn_kwargs: Any
    ) -> Optional[asyncio.Task]:
        ...
    
    @property
    def is_running(_) -> bool:
        ...
    
    @staticmethod
    def stop() -> None:
        ...

def setup_TaskControl(state: UsageStateFull) -> TaskControl:

    _task:Optional[asyncio.Task] = None

    def _is_running():
        return _task is not None and not _task.done()

    class _Interface(TaskControl):
        __slots__ = ()
        @staticmethod
        def start(fn, *fn_args, **fn_kwargs):

            def create_task():
                nonlocal _task
                result = fn(*fn_args, **fn_kwargs)
                if isinstance(result, Coroutine):
                    # create_task validates result
                    _task = asyncio.create_task(result)
                    return _task
                return None
            
            return state.maintain_state(state.ACTIVE, create_task)
        
        @property
        def is_running(_):
            return _is_running()
        
        @staticmethod
        def stop():
            def cancel_task():
                if _task and _is_running():
                    _task.cancel()
            state.maintain_state(state.ACTIVE, cancel_task)
    
    return _Interface()
