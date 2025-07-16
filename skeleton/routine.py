

from typing import Generic, Protocol, runtime_checkable

from .context import Context, T_in

@runtime_checkable
class Routine(Protocol, Generic[T_in]):
    async def __call__(self, context: Context[T_in]):
        ...

