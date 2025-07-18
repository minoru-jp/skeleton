

from typing import Generic, Protocol, runtime_checkable

from .context import Context, T

@runtime_checkable
class Routine(Protocol, Generic[T]):
    async def __call__(self, context: Context[T]):
        ...