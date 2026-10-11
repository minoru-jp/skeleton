"""Specification: Control(CTRL_*)。"""

from __future__ import annotations

import os
import signal
import threading
import time

import pytest

import honehone
from honehone import (
    Context,
    Parallel,
    Sequence,
    Skeleton,
    SkeletonStateError,
    repeat,
    service,
)
from tests.conftest import Recorder, finish


class Ticking(Skeleton):
    main = Sequence()

    @main
    @repeat(every=0.01)
    def tick(self, ctx: Context) -> None: ...


def test_ctrl_001_run_turns_ctrl_c_into_a_stop_request() -> None:
    assert threading.current_thread() is threading.main_thread()
    before = signal.getsignal(signal.SIGINT)
    timer = threading.Timer(0.1, os.kill, (os.getpid(), signal.SIGINT))
    timer.start()
    result = honehone.run(Ticking())
    timer.join()
    assert result.outcome == "stopped"
    assert signal.getsignal(signal.SIGINT) is before  # restored


def test_ctrl_002_start_returns_without_waiting() -> None:
    run = honehone.start(Ticking())
    assert isinstance(run, honehone.Run)
    assert run.wait(0.05) is None
    run.stop()
    assert finish(run).outcome == "stopped"


def test_ctrl_004_unknown_names_and_states() -> None:
    run = honehone.start(Ticking())
    with pytest.raises(KeyError):
        run.pause("nope")
    with pytest.raises(KeyError):
        _ = run.state("nope")
    with pytest.raises(ValueError, match="unknown state"):
        _ = run.wait_until("tick", "sleeping", 0)  # pyright: ignore[reportArgumentType] - checks an invalid state
    run.stop()
    _ = finish(run)


def test_ctrl_005_pause_stops_at_the_next_boundary(recorder: Recorder) -> None:
    calls: list[int] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        @repeat(every=0.01)
        def tick(self, ctx: Context) -> None:
            calls.append(1)

    run = honehone.start(Shape(), listener=recorder)
    assert run.wait_until("tick", "running", 5)
    run.pause("tick")
    assert run.wait_until("tick", "paused", 5)
    paused_at = len(calls)
    time.sleep(0.1)
    assert len(calls) == paused_at  # not called while paused
    run.resume("tick")
    deadline = time.monotonic() + 5
    while len(calls) == paused_at and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(calls) > paused_at
    run.stop()
    _ = finish(run)
    states = recorder.states("tick")
    assert states.index("pausing") < states.index("paused")


def test_ctrl_005_pause_of_the_whole_body_reaches_the_root() -> None:
    class Shape(Skeleton):
        main = Parallel()

        @main
        @repeat(every=0.01)
        def a(self, ctx: Context) -> None: ...

        @main
        @repeat(every=0.01)
        def b(self, ctx: Context) -> None: ...

    run = honehone.start(Shape())
    assert run.wait_until("a", "running", 5)
    assert run.wait_until("b", "running", 5)
    run.pause()
    assert run.wait_until("a", "paused", 5)
    assert run.wait_until("b", "paused", 5)
    assert run.wait_until(
        "main", "paused", 5
    )  # once every active child is paused, the parent is paused too
    run.resume()
    deadline = time.monotonic() + 5
    while run.state("main") != "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert run.state("main") == "running"
    run.stop()
    assert finish(run).outcome == "stopped"


def test_ctrl_006_a_call_in_progress_is_not_interrupted() -> None:
    inside = threading.Event()
    release = threading.Event()

    class Shape(Skeleton):
        main = Sequence()

        @main
        @repeat()
        def long_call(self, ctx: Context) -> None:
            inside.set()
            _ = release.wait(5)

    run = honehone.start(Shape())
    assert inside.wait(5)
    run.pause("long_call")
    time.sleep(0.05)
    assert run.state("long_call") == "pausing"  # does not stop in the middle of a call
    release.set()
    assert run.wait_until("long_call", "paused", 5)
    run.stop()
    _ = finish(run)


def test_ctrl_007_services_pause_at_checkpoints() -> None:
    loops: list[int] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        @service
        def server(self, ctx: Context) -> None:
            ctx.ready()
            while not ctx.stopping:
                ctx.checkpoint()
                loops.append(1)
                _ = ctx.wait_stop(0.01)

        @main
        @repeat(every=0.01)
        def watch(self, ctx: Context) -> None: ...

    run = honehone.start(Shape())
    assert run.wait_until("server", "ready", 5)
    run.pause("server")
    assert run.wait_until("server", "paused", 5)
    count = len(loops)
    time.sleep(0.05)
    assert len(loops) == count
    run.resume("server")
    deadline = time.monotonic() + 5
    while run.state("server") != "ready" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert run.state("server") == "ready"
    run.stop()
    assert finish(run).outcome == "stopped"


def test_ctrl_008_resume_removes_only_that_request() -> None:
    run = honehone.start(Ticking())
    assert run.wait_until("tick", "running", 5)
    run.pause("main")
    run.pause("tick")
    assert run.wait_until("tick", "paused", 5)
    run.resume("tick")
    time.sleep(0.05)
    assert run.state("tick") == "paused"  # the request to main remains
    run.resume("main")
    deadline = time.monotonic() + 5
    while run.state("tick") != "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert run.state("tick") == "running"
    run.stop()
    _ = finish(run)


def test_ctrl_009_stop_wakes_paused_nodes() -> None:
    run = honehone.start(Ticking())
    assert run.wait_until("tick", "running", 5)
    run.pause()
    assert run.wait_until("tick", "paused", 5)
    run.stop()
    result = finish(run)
    assert result.outcome == "stopped"
    assert result.nodes["tick"].state == "stopped"


def test_ctrl_010_wait_until() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def a(self, ctx: Context) -> None: ...

    run = honehone.start(Shape())
    _ = finish(run)
    assert run.wait_until("a", "running", 0)  # a state already passed
    assert not run.wait_until("a", "paused", 1)  # already ended, so it is never reached


def test_ctrl_013_control_finds_the_run() -> None:
    obj = Ticking()
    with pytest.raises(SkeletonStateError):
        _ = honehone.control(obj)
    run = honehone.start(obj)
    assert honehone.control(obj) is run
    run.stop()
    _ = finish(run)
