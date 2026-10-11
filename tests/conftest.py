"""Tools shared by the tests."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import pytest

import honehone

WAIT = 5.0
"""The longest a test waits, in seconds. Going past it fails the test as a bug."""


@dataclass
class Recorder:
    """A listener that records every report."""

    events: list[tuple[str, tuple[object, ...], dict[str, object]]] = field(
        default_factory=list
    )
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __call__(self, tag: str, *args: object, **kwargs: object) -> None:
        with self.lock:
            self.events.append((tag, args, kwargs))

    def states(self, name: str) -> list[object]:
        with self.lock:
            return [
                kw["state"]
                for tag, _, kw in self.events
                if tag == "node.changed" and kw["name"] == name
            ]

    def tags(self) -> list[str]:
        with self.lock:
            return [tag for tag, _, _ in self.events]


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


def finish(run: honehone.Run) -> honehone.Result:
    """Wait for the run to end; fail if it does not."""
    result = run.wait(WAIT)
    assert result is not None, "the run did not finish in time"
    return result
