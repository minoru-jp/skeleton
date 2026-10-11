"""Specification: joining gpframe in Control (CTRL_014). Checked in combination with gpframe itself."""

from __future__ import annotations

import time
from typing import Any

import gpframe
import pytest

import honehone
import honehone.gpframe
from honehone import Context, Sequence, Skeleton, repeat
from tests.conftest import Recorder


class Ticking(Skeleton):
    main = Sequence()

    @main
    @repeat(every=0.01)
    def tick(self, ctx: Context) -> None: ...


class Failing(Skeleton):
    main = Sequence()

    @main
    def bad(self, ctx: Context) -> None:
        raise ValueError("bad")


def test_ctrl_014_a_frame_stop_stops_the_run(recorder: Recorder) -> None:
    obj = Ticking()
    with gpframe.session(timeout=5) as s:
        frame = s.spawn(honehone.gpframe.routine, obj, recorder)
        deadline = time.monotonic() + 5
        while not _started(obj) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert honehone.control(obj).wait_until("tick", "running", 5)
        s.stop()
    result = frame.result()
    assert result.outcome == "stopped"
    assert recorder.tags()[-1] == "run.finished"


def _started(obj: Skeleton) -> bool:
    try:
        _ = honehone.control(obj)
    except honehone.SkeletonStateError:
        return False
    return True


def test_ctrl_014_a_failed_run_fails_the_frame() -> None:
    with gpframe.session(timeout=5) as s:
        frame = s.spawn(honehone.gpframe.routine, Failing())
        s.wait()
        broken = s.broken()
        assert broken == [frame]
        assert isinstance(frame.error, honehone.SkeletonFailed)
        frame.ignore()


def test_ctrl_014_gpframe_is_not_part_of_the_core_surface() -> None:
    for name in honehone.__all__:
        if name in ("Channel", "Shared"):
            continue  # re-exported as tools for passing data (EXEC_009)
        value = getattr(honehone, name)
        module = getattr(value, "__module__", "") or ""
        assert not module.startswith("gpframe"), name


def test_ctrl_014_routine_runs_on_the_frame_thread() -> None:
    import threading

    seen: list[str] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        def where(self, ctx: Context) -> None:
            seen.append(threading.current_thread().name)

    with gpframe.session(timeout=5) as s:
        frame = s.spawn(honehone.gpframe.routine, Shape(), name="home")
        s.wait()
    assert frame.succeeded
    assert seen == ["gpframe:home"]


@pytest.mark.parametrize("bad", [object(), None])
def test_ctrl_014_routine_rejects_non_skeletons(bad: Any) -> None:
    with gpframe.session(timeout=5) as s:
        frame = s.spawn(honehone.gpframe.routine, bad)
        s.wait()
        assert isinstance(frame.error, TypeError)
        frame.ignore()
