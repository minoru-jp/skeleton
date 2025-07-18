
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .context import Context, T

@runtime_checkable
class Routine(Protocol, Generic[T]):
    def __call__(self, context: Context[T]) -> Any:
        ...