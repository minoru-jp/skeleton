"""Specification: Lifecycle(LIFE_*)。"""

from __future__ import annotations

import threading
import time

import pytest

import honehone
from honehone import (
    Context,
    FrozenSkeletonError,
    Parallel,
    Sequence,
    Skeleton,
    SkeletonDefinitionError,
    SkeletonStateError,
    boot,
    cleanup,
    repeat,
    service,
)
from tests.conftest import Recorder, finish


class Boom(Exception):
    pass


class Simple(Skeleton):
    main = Sequence()

    @main
    def a(self, ctx: Context) -> None: ...


def test_life_001_one_instance_one_run() -> None:
    obj = Simple()
    assert honehone.run(obj).outcome == "completed"
    with pytest.raises(SkeletonStateError):
        _ = honehone.run(obj)
    with pytest.raises(SkeletonStateError):
        _ = honehone.start(obj)


def test_life_003_flow_order() -> None:
    order: list[str] = []

    class Shape(Skeleton):
        main = Sequence()

        @boot
        def b1(self, ctx: Context) -> None:
            order.append("b1")

        @boot
        def b2(self, ctx: Context) -> None:
            order.append("b2")

        @main
        def body(self, ctx: Context) -> None:
            order.append("body")

        @cleanup
        def c1(self, ctx: Context) -> None:
            order.append("c1")

        @cleanup
        def c2(self, ctx: Context) -> None:
            order.append("c2")

    assert honehone.run(Shape()).outcome == "completed"
    assert order == ["b1", "b2", "body", "c2", "c1"]


def test_life_003_implementation_classes_override_boot_and_cleanup() -> None:
    seen: list[str] = []

    class Shape(Skeleton):
        main = Sequence()

        @boot
        def connect(self, ctx: Context) -> None: ...

        @cleanup(of=connect)
        def disconnect(self, ctx: Context) -> None: ...

        @main
        def body(self, ctx: Context) -> None: ...

    class Impl(Shape):
        def connect(self, ctx: Context) -> None:  # overrides only the content
            seen.append("connect")

        def disconnect(self, ctx: Context) -> None:
            seen.append("disconnect")

    assert honehone.run(Impl()).outcome == "completed"
    assert seen == ["connect", "disconnect"]


def test_life_004_failed_boot_skips_the_rest() -> None:
    order: list[str] = []

    class Shape(Skeleton):
        main = Sequence()

        @boot
        def b1(self, ctx: Context) -> None:
            raise Boom

        @boot
        def b2(self, ctx: Context) -> None:
            order.append("b2")

        @main
        def body(self, ctx: Context) -> None:
            order.append("body")

        @cleanup
        def tidy(self, ctx: Context) -> None:
            order.append("cleanup")

    result = honehone.run(Shape())
    assert result.outcome == "failed"
    assert order == ["cleanup"]
    assert result.nodes["b2"].state == "skipped"
    assert result.nodes["body"].state == "skipped"


def test_life_005_frozen_while_the_body_runs() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @boot
        def prepare(self, ctx: Context) -> None:
            self.value = 1  # writable during boot

        @main
        def body(self, ctx: Context) -> None:
            self.value = 2

        @cleanup
        def tidy(self, ctx: Context) -> None:
            self.value = 3  # writable during cleanup too

    obj = Shape()
    result = honehone.run(obj)
    assert isinstance(result.nodes["body"].errors[0], FrozenSkeletonError)
    assert obj.value == 3


def test_life_007_cleanup_always_runs_and_collects_errors() -> None:
    seen: list[str] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        def body(self, ctx: Context) -> None:
            raise Boom("body")

        @cleanup
        def first(self, ctx: Context) -> None:
            seen.append("first")

        @cleanup
        def second(self, ctx: Context) -> None:
            seen.append("second")
            raise Boom("cleanup")

    result = honehone.run(Shape())
    assert seen == ["second", "first"]
    assert result.outcome == "failed"
    assert [str(e) for e in result.cleanup_errors] == ["cleanup"]


def test_life_008_paired_cleanup_runs_only_after_its_boot_succeeded() -> None:
    seen: list[str] = []

    class Shape(Skeleton):
        @boot
        def connect(self, ctx: Context) -> None:
            seen.append("connect")

        @cleanup(of=connect)
        def disconnect(self, ctx: Context) -> None:
            seen.append("disconnect")

        @boot
        def broken(self, ctx: Context) -> None:
            raise Boom

        @cleanup(of=broken)
        def unbreak(self, ctx: Context) -> None:
            seen.append("unbreak")

        @cleanup
        def always(self, ctx: Context) -> None:
            seen.append("always")

    result = honehone.run(Shape())
    assert seen == ["connect", "always", "disconnect"]
    assert result.nodes["unbreak"].state == "skipped"


def test_life_008_cleanup_of_must_name_a_boot() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            def plain(self, ctx: Context) -> None: ...

            @cleanup(of=plain)
            def tidy(self, ctx: Context) -> None: ...


def test_life_008_boot_and_cleanup_take_no_modifiers() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            @repeat(times=2)
            @boot
            def prepare(self, ctx: Context) -> None: ...

    with pytest.raises(SkeletonDefinitionError):

        class Bad2(Skeleton):
            @boot
            @repeat(times=2)
            def prepare(self, ctx: Context) -> None: ...


def test_life_009_cleanup_is_not_interrupted_by_the_first_stop() -> None:
    observed: list[bool] = []
    release = threading.Event()

    class Shape(Skeleton):
        main = Sequence()

        @main
        def body(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)

        @cleanup
        def tidy(self, ctx: Context) -> None:
            observed.append(ctx.stopping)
            _ = release.wait(5)
            observed.append(ctx.stopping)

    run = honehone.start(Shape())
    assert run.wait_until("body", "running", 5)
    run.stop()
    assert run.wait_until("tidy", "running", 5)
    release.set()
    result = finish(run)
    assert observed == [False, False]
    assert result.nodes["tidy"].state == "succeeded"


def test_life_009_second_stop_interrupts_cleanup() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def body(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)

        @cleanup
        def runs_after_tidy(
            self, ctx: Context
        ) -> None: ...  # reverse order, so after tidy

        @cleanup
        def tidy(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)

    run = honehone.start(Shape())
    assert run.wait_until("body", "running", 5)
    run.stop()
    assert run.wait_until("tidy", "running", 5)
    run.stop()
    result = finish(run)
    assert result.nodes["tidy"].state == "stopped"
    assert result.nodes["runs_after_tidy"].state == "skipped"


def test_life_010_sequence_moves_on_when_a_service_is_ready() -> None:
    order: list[str] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        @service
        def server(self, ctx: Context) -> None:
            order.append("server ready")
            ctx.ready()
            _ = ctx.wait_stop(5)
            order.append("server stopped")

        @main
        def client(self, ctx: Context) -> None:
            order.append("client")

    result = honehone.run(Shape())
    assert result.outcome == "completed"
    assert order == ["server ready", "client", "server stopped"]
    assert result.nodes["server"].state == "succeeded"  # LIFE_011


def test_life_010_service_that_returns_without_ready(recorder: Recorder) -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        @service
        def quick(self, ctx: Context) -> None: ...

    result = honehone.run(Shape(), listener=recorder)
    assert result.nodes["quick"].state == "succeeded"
    assert recorder.states("quick") == ["running", "ready", "succeeded"]


def test_life_010_ready_outside_a_service_is_an_error() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def plain(self, ctx: Context) -> None:
            ctx.ready()

    result = honehone.run(Shape())
    assert isinstance(result.nodes["plain"].errors[0], SkeletonStateError)


def test_life_010_parallel_counts_ready_as_done() -> None:
    class Shape(Skeleton):
        main = Sequence()
        services = main.parallel()

        @services
        @service
        def db(self, ctx: Context) -> None:
            ctx.ready()
            _ = ctx.wait_stop(5)

        @services
        @service
        def api(self, ctx: Context) -> None:
            ctx.ready()
            _ = ctx.wait_stop(5)

        @main
        def client(self, ctx: Context) -> str:
            return "done"

    result = honehone.run(Shape())
    assert result.outcome == "completed"
    assert result.nodes["services"].state == "succeeded"
    assert result.nodes["client"].value == "done"


def test_life_012_a_service_failing_after_ready_fails_the_body() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        @service
        def server(self, ctx: Context) -> None:
            ctx.ready()
            time.sleep(0.05)
            raise Boom("crash")

        @main
        @repeat(every=0.01)
        def watch(self, ctx: Context) -> None: ...

    result = honehone.run(Shape())
    assert result.outcome == "failed"
    assert result.nodes["watch"].state == "stopped"
    with pytest.raises(honehone.SkeletonFailed) as info:
        result.raise_if_failed()
    assert [str(e) for e in info.value.exceptions] == ["crash"]


def test_life_013_services_stop_in_reverse_ready_order() -> None:
    stopped: list[str] = []
    lock = threading.Lock()

    class Shape(Skeleton):
        main = Sequence()

        @main
        @service
        def db(self, ctx: Context) -> None:
            ctx.ready()
            _ = ctx.wait_stop(5)
            with lock:
                stopped.append("db")

        @main
        @service
        def api(self, ctx: Context) -> None:
            ctx.ready()
            _ = ctx.wait_stop(5)
            time.sleep(0.05)  # even if it stops late, db is not stopped until api ends
            with lock:
                stopped.append("api")

        @main
        @repeat(every=0.01)
        def watch(self, ctx: Context) -> None: ...

    run = honehone.start(Shape())
    assert run.wait_until("watch", "running", 5)
    run.stop()
    result = finish(run)
    assert stopped == ["api", "db"]
    assert result.outcome == "stopped"
    assert result.nodes["api"].state == "stopped"


@pytest.mark.parametrize(
    "modifier", [repeat(times=2), honehone.retry(1), honehone.timeout(1)]
)
def test_life_014_service_conflicts(modifier: honehone.Modifier) -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            main = Sequence()

            @main
            @service
            @modifier
            def s(self, ctx: Context) -> None: ...


def test_life_014_service_in_lockstep_is_rejected() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            main = Parallel(lockstep=True)

            @main
            @repeat()
            def a(self, ctx: Context) -> None: ...

            @main
            @service
            def s(self, ctx: Context) -> None: ...
