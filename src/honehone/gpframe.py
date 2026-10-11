"""A part for putting a skeleton into a gpframe tree (CTRL_014).

The public surface of honehone itself shows no gpframe types. The part here, too,
assumes only the operation of gpframe's `Context` (`ctx.on_stop()`) and does not
import gpframe.

    with gpframe.session(timeout=5) as s:
        s.spawn(honehone.gpframe.routine, MySkeleton())
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from honehone._define import Skeleton
from honehone._engine import Listener, _prepare
from honehone._result import Result


class StopHandle(Protocol):
    """A registered stop callback. gpframe's `StopHandle` satisfies it."""

    def cancel(self) -> object: ...


class StopSource(Protocol):
    """Something that signals stop requests. gpframe's `Context` satisfies it."""

    def on_stop(self, callback: Callable[[], object], /) -> StopHandle: ...


def routine(ctx: StopSource, obj: Skeleton, listener: Listener | None = None) -> Result:
    """A gpframe frame routine that runs `obj` on the thread of this frame.

    A stop request to the frame becomes a stop request to the run. If the run ends as
    `"failed"`, `SkeletonFailed` is raised to fail the frame; otherwise the `Result`
    is returned. The handle can be taken out with `honehone.control(obj)`.
    """
    ex = _prepare(obj, listener, None)
    handle = ctx.on_stop(ex.request_stop)
    try:
        ex.execute()
    finally:
        _ = handle.cancel()
    result = ex.deliver()
    result.raise_if_failed()
    return result


__all__ = ("StopHandle", "StopSource", "routine")
