"""The exceptions and warnings raised by honehone."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Self


class SkeletonError(Exception):
    """The base of the exceptions raised by honehone."""


class SkeletonDefinitionError(SkeletonError, TypeError):
    """An error in the shape of a skeleton. Raised when the class is defined (STRUCT_015)."""


class SkeletonStateError(SkeletonError, RuntimeError):
    """An operation not possible at that point (a second run, `ready()` outside a service, and so on)."""


class FrozenSkeletonError(SkeletonError, AttributeError):  # pyright: ignore[reportUnsafeMultipleInheritance] - like FrozenInstanceError of dataclasses, a failed attribute write is an AttributeError
    """An attribute of the instance was written while the body is running (LIFE_005)."""


class ThreadAffinityError(SkeletonError, RuntimeError):
    """The content of a `ThreadBound` was touched from a thread other than the home thread (EXEC_007)."""


class WorkerTimeout(SkeletonError, TimeoutError):
    """The time of `@timeout` was exceeded (COMB_015)."""


class SkeletonFailed(ExceptionGroup[Exception]):
    """An `ExceptionGroup` gathering the exceptions of a failed run (RESULT_008)."""

    def __new__(cls, message: str, exceptions: Sequence[Exception]) -> Self:
        return super().__new__(cls, message, exceptions)

    def __init__(self, message: str, exceptions: Sequence[Exception]) -> None:
        super().__init__(message, exceptions)

    def derive(self, excs: Sequence[Exception]) -> SkeletonFailed:  # pyright: ignore[reportIncompatibleMethodOverride] - parts split by except* are returned as the same type
        return SkeletonFailed(self.message, excs)


class SkeletonWarning(UserWarning):
    """A warning that some node did not stop (RESULT_004)."""
