"""Checks the Specification rules not covered by the other files."""

from __future__ import annotations

import threading
import warnings

import pytest

import honehone
from honehone import (
    Context,
    Sequence,
    Skeleton,
    SkeletonWarning,
    cleanup,
    repeat,
    service,
)
from tests.conftest import finish


def test_exec_002_services_run_on_their_own_thread() -> None:
    seen: dict[str, int] = {}

    class Shape(Skeleton):
        main = Sequence()

        @main
        @service
        def server(self, ctx: Context) -> None:
            seen["server"] = threading.get_ident()

        @main
        def after(self, ctx: Context) -> None:
            seen["after"] = threading.get_ident()

    assert honehone.run(Shape()).outcome == "completed"
    assert seen["after"] == threading.get_ident()
    assert seen["server"] != threading.get_ident()


def test_life_015_a_service_not_yet_ready_stops_with_its_parent() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        @service
        def slow_start(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)  # waits without becoming ready

        @main
        def after(self, ctx: Context) -> None: ...

    run = honehone.start(Shape())
    assert run.wait_until("slow_start", "running", 5)
    run.stop()
    result = finish(run)
    assert result.nodes["slow_start"].state == "stopped"
    assert result.nodes["after"].state == "skipped"
    assert result.outcome == "stopped"


def test_life_015_services_are_not_stopped_by_their_parent_group() -> None:
    order: list[str] = []
    lock = threading.Lock()

    class Shape(Skeleton):
        main = Sequence()

        @main
        @service
        def server(self, ctx: Context) -> None:
            ctx.ready()
            _ = ctx.wait_stop(5)
            with lock:
                order.append("server")

        @main
        @repeat(every=0.01)
        def watch(self, ctx: Context) -> None: ...

        @cleanup
        def tidy(self, ctx: Context) -> None:
            with lock:
                order.append("cleanup")

    run = honehone.start(Shape())
    assert run.wait_until("watch", "running", 5)
    run.stop()
    result = finish(run)
    # watch stops, the body ends, then server is stopped, then cleanup
    assert order == ["server", "cleanup"]
    assert result.nodes["watch"].state == "stopped"


def test_exec_011_callback_registered_after_a_stop_runs_at_once() -> None:
    called = threading.Event()

    class Shape(Skeleton):
        main = Sequence()

        @main
        def worker(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)
            _ = ctx.on_stop(called.set)  # a stop is already requested
            _ = called.wait(5)

    run = honehone.start(Shape())
    assert run.wait_until("worker", "running", 5)
    run.stop()
    _ = finish(run)
    assert called.is_set()


def test_result_004_a_stuck_service_is_reported_once() -> None:
    release = threading.Event()
    cleaned: list[bool] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        @service
        def stubborn(self, ctx: Context) -> None:
            ctx.ready()
            _ = release.wait(10)  # ignores the stop request

        @cleanup
        def tidy(self, ctx: Context) -> None:
            cleaned.append(True)

    run = honehone.start(Shape(), stop_timeout=0.1)
    with pytest.warns(SkeletonWarning):
        result = finish(run)
    release.set()
    assert result.stuck == ("stubborn",)
    assert cleaned == [True]
    assert result.outcome == "completed"
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert run.wait(0) is result  # no warning the second time
