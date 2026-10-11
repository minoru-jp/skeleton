"""The result of a run, `Result`, and the record of a node, `NodeRecord` (RESULT_001, RESULT_005)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from honehone._errors import SkeletonFailed

Outcome = Literal["completed", "failed", "stopped"]

NodeState = Literal[
    "pending",
    "running",
    "pausing",
    "paused",
    "ready",
    "succeeded",
    "failed",
    "stopped",
    "skipped",
    "stuck",
]

NODE_STATES: tuple[str, ...] = (
    "pending",
    "running",
    "pausing",
    "paused",
    "ready",
    "succeeded",
    "failed",
    "stopped",
    "skipped",
    "stuck",
)

TERMINAL_STATES: frozenset[str] = frozenset(
    ("succeeded", "failed", "stopped", "skipped", "stuck")
)


@dataclass(frozen=True, slots=True)
class NodeRecord:
    """The record of one node (RESULT_005)."""

    state: NodeState
    errors: tuple[Exception, ...]
    calls: int
    value: object
    duration: float | None


@dataclass(frozen=True, slots=True)
class Result:
    """The result of one run (RESULT_001)."""

    outcome: Outcome
    nodes: Mapping[str, NodeRecord]
    cleanup_errors: tuple[Exception, ...]
    stuck: tuple[str, ...]
    _failures: tuple[Exception, ...] = ()

    def raise_if_failed(self) -> None:
        """Raise `SkeletonFailed` if `outcome` is `"failed"` (RESULT_008)."""
        if self.outcome != "failed":
            return
        failures = list(self._failures)
        if (
            not failures
        ):  # a safeguard in case the outcome and the gathered exceptions disagree
            failures = [RuntimeError("the run failed")]
        raise SkeletonFailed("the honehone run failed", failures)

    def __repr__(self) -> str:
        return f"<honehone Result {self.outcome}>"
