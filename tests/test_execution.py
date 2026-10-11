"""Specification: Execution(EXEC_*)。"""

from __future__ import annotations

import threading
import time

import pytest

import honehone
from honehone import (
    Channel,
    Context,
    Parallel,
    Sequence,
    Skeleton,
    SkeletonDefinitionError,
    SkeletonWarning,
    ThreadAffinityError,
    ThreadBound,
    boot,
    cleanup,
    isolated,
    pinned,
)
from tests.conftest import finish


def test_exec_002_sequence_runs_on_the_parent_thread_and_parallel_on_others() -> None:
    seen: dict[str, int] = {}
    # Thread identifiers are reused once a thread ends, so both are kept alive together
    together = threading.Barrier(2)

    class Shape(Skeleton):
        main = Sequence()

        @boot
        def prepare(self, ctx: Context) -> None:
            seen["boot"] = threading.get_ident()

        @main
        def step(self, ctx: Context) -> None:
            seen["step"] = threading.get_ident()

        side = main.parallel()

        @side
        def left(self, ctx: Context) -> None:
            seen["left"] = threading.get_ident()
            _ = together.wait(5)  # checks that the two run at the same time

        @side
        def right(self, ctx: Context) -> None:
            seen["right"] = threading.get_ident()
            _ = together.wait(5)

        @cleanup
        def tidy(self, ctx: Context) -> None:
            seen["cleanup"] = threading.get_ident()

    home = threading.get_ident()
    assert honehone.run(Shape()).outcome == "completed"
    assert seen["boot"] == seen["step"] == seen["cleanup"] == home
    assert len({seen["left"], seen["right"], home}) == 3


def test_exec_003_pinned_runs_on_the_home_thread() -> None:
    seen: dict[str, int] = {}

    class Shape(Skeleton):
        main = Parallel()

        @main
        @pinned
        def local(self, ctx: Context) -> None:
            seen["local"] = threading.get_ident()

        @main
        def other(self, ctx: Context) -> None:
            seen["other"] = threading.get_ident()

    home = threading.get_ident()
    assert honehone.run(Shape()).outcome == "completed"
    assert seen["local"] == home
    assert seen["other"] != home


def test_exec_003_pinned_child_sees_a_sibling_failure() -> None:
    class Shape(Skeleton):
        main = Parallel()

        @main
        @pinned
        def local(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)  # a sibling's failure requests a stop

        @main
        def other(self, ctx: Context) -> None:
            time.sleep(0.05)
            raise RuntimeError("other failed")

    begin = time.monotonic()
    result = honehone.run(Shape())
    assert time.monotonic() - begin < 2
    assert result.nodes["local"].state == "stopped"
    assert result.outcome == "failed"


def test_exec_003_two_pinned_children_in_one_parallel_are_rejected() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            main = Parallel()

            @main
            @pinned
            def a(self, ctx: Context) -> None: ...

            @main
            @pinned
            def b(self, ctx: Context) -> None: ...


def test_exec_004_isolated_runs_on_its_own_thread() -> None:
    seen: dict[str, int] = {}

    class Shape(Skeleton):
        main = Sequence()

        @main
        @isolated
        def alone(self, ctx: Context) -> None:
            seen["alone"] = threading.get_ident()

    assert honehone.run(Shape()).outcome == "completed"
    assert seen["alone"] != threading.get_ident()


def test_exec_004_isolated_worker_that_does_not_stop_is_abandoned() -> None:
    release = threading.Event()
    cleaned: list[bool] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        @isolated
        def stubborn(self, ctx: Context) -> None:
            _ = release.wait(10)  # ignores the stop request

        @cleanup
        def tidy(self, ctx: Context) -> None:
            cleaned.append(True)

    run = honehone.start(Shape(), stop_timeout=0.1)
    assert run.wait_until("stubborn", "running", 5)
    run.stop()
    with pytest.warns(SkeletonWarning):
        result = finish(run)
    release.set()
    assert result.stuck == ("stubborn",)
    assert result.nodes["stubborn"].state == "stuck"
    assert cleaned == [True]
    assert (
        result.outcome == "stopped"
    )  # not stopping does not change the outcome (RESULT_004)


def test_exec_007_thread_bound() -> None:
    errors: list[BaseException] = []

    class Shape(Skeleton):
        main = Parallel()

        @boot
        def prepare(self, ctx: Context) -> None:
            self.resource = ThreadBound(object())

        @main
        @pinned
        def local(self, ctx: Context) -> None:
            _ = self.resource.get()

        @main
        def other(self, ctx: Context) -> None:
            try:
                _ = self.resource.get()
            except ThreadAffinityError as exc:
                errors.append(exc)

    assert honehone.run(Shape()).outcome == "completed"
    assert len(errors) == 1


def test_exec_009_channel_works_with_the_worker_context() -> None:
    class Shape(Skeleton):
        main = Parallel()

        @boot
        def prepare(self, ctx: Context) -> None:
            self.numbers = Channel(int)

        @main
        def produce(self, ctx: Context) -> None:
            for n in range(1, 5):
                self.numbers.put(n)
            self.numbers.close()

        @main
        def consume(self, ctx: Context) -> int:
            return sum(self.numbers.receive(ctx))

    result = honehone.run(Shape())
    assert result.nodes["consume"].value == 10


def test_exec_009_channel_receive_ends_on_stop() -> None:
    class Shape(Skeleton):
        main = Parallel()

        @boot
        def prepare(self, ctx: Context) -> None:
            self.numbers = Channel(int)

        @main
        def consume(self, ctx: Context) -> int:
            return sum(self.numbers.receive(ctx))

    run = honehone.start(Shape())
    assert run.wait_until("consume", "running", 5)
    run.stop()
    assert finish(run).nodes["consume"].state == "stopped"


def test_exec_010_context_members() -> None:
    called = threading.Event()
    registered = threading.Event()

    class Shape(Skeleton):
        main = Sequence()

        @main
        def worker(self, ctx: Context) -> str:
            _ = ctx.on_stop(called.set)
            registered.set()
            _ = ctx.wait_stop(5)
            return ctx.name

    run = honehone.start(Shape())
    assert registered.wait(5)
    run.stop()
    result = finish(run)
    assert called.wait(5)
    assert result.nodes["worker"].value == "worker"


def test_exec_010_cancelled_stop_callback_is_not_called() -> None:
    called: list[bool] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        def worker(self, ctx: Context) -> None:
            handle = ctx.on_stop(lambda: called.append(True))
            handle.cancel()
            _ = ctx.wait_stop(5)

    run = honehone.start(Shape())
    assert run.wait_until("worker", "running", 5)
    run.stop()
    _ = finish(run)
    time.sleep(0.05)
    assert called == []


def test_exec_010_failing_stop_callback_fails_the_node() -> None:
    def bad() -> None:
        raise RuntimeError("callback failed")

    class Shape(Skeleton):
        main = Sequence()

        @main
        def worker(self, ctx: Context) -> None:
            _ = ctx.on_stop(bad)
            registered.set()
            _ = ctx.wait_stop(5)
            time.sleep(0.05)  # waits for the callback to finish

    registered = threading.Event()
    run = honehone.start(Shape())
    assert registered.wait(5)
    run.stop()
    result = finish(run)
    assert result.nodes["worker"].state == "failed"
    assert str(result.nodes["worker"].errors[0]) == "callback failed"
