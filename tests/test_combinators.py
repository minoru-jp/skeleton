"""Specification: Combinators(COMB_*)。"""

from __future__ import annotations

import threading
import time

import pytest

import honehone
from honehone import (
    Context,
    Parallel,
    Sequence,
    Skeleton,
    SkeletonDefinitionError,
    WorkerTimeout,
    optional,
    repeat,
    retry,
    timeout,
)
from tests.conftest import finish


class Boom(Exception):
    pass


def test_comb_003_sequence_skips_the_rest_after_a_failure() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def a(self, ctx: Context) -> None: ...

        @main
        def b(self, ctx: Context) -> None:
            raise Boom

        @main
        def c(self, ctx: Context) -> None: ...

    result = honehone.run(Shape())
    assert result.outcome == "failed"
    assert [result.nodes[n].state for n in ("a", "b", "c", "main")] == [
        "succeeded",
        "failed",
        "skipped",
        "failed",
    ]


def test_comb_004_parallel_stops_siblings_after_a_failure() -> None:
    class Shape(Skeleton):
        main = Parallel()

        @main
        def slow(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)

        @main
        def bad(self, ctx: Context) -> None:
            time.sleep(0.05)
            raise Boom

    result = honehone.run(Shape())
    assert result.outcome == "failed"
    assert result.nodes["slow"].state == "stopped"
    assert result.nodes["bad"].state == "failed"
    assert result.nodes["main"].state == "failed"


def test_comb_005_race_takes_the_first_success() -> None:
    class Shape(Skeleton):
        main = Parallel(until="first_success")

        @main
        def fails(self, ctx: Context) -> None:
            raise Boom

        @main
        def fast(self, ctx: Context) -> str:
            time.sleep(0.05)
            return "fast"

        @main
        def slow(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)

    result = honehone.run(Shape())
    assert result.outcome == "completed"
    assert result.nodes["fast"].state == "succeeded"
    assert result.nodes["slow"].state == "stopped"
    assert result.nodes["fails"].state == "failed"  # still in the record
    assert isinstance(result.nodes["fails"].errors[0], Boom)


def test_comb_005_race_fails_when_all_fail() -> None:
    class Shape(Skeleton):
        main = Parallel(until="first_success")

        @main
        def a(self, ctx: Context) -> None:
            raise Boom("a")

        @main
        def b(self, ctx: Context) -> None:
            raise Boom("b")

    result = honehone.run(Shape())
    assert result.outcome == "failed"
    with pytest.raises(honehone.SkeletonFailed) as info:
        result.raise_if_failed()
    assert len(info.value.exceptions) == 2


def test_comb_006_fallback_tries_in_order() -> None:
    class Shape(Skeleton):
        main = Sequence(until="first_success")

        @main
        def primary(self, ctx: Context) -> None:
            raise Boom

        @main
        def secondary(self, ctx: Context) -> str:
            return "ok"

        @main
        def tertiary(self, ctx: Context) -> None: ...

    result = honehone.run(Shape())
    assert result.outcome == "completed"
    assert [result.nodes[n].state for n in ("primary", "secondary", "tertiary")] == [
        "failed",
        "succeeded",
        "skipped",
    ]


def test_comb_007_sequence_first_done_is_rejected() -> None:
    with pytest.raises(SkeletonDefinitionError):
        _ = Sequence(until="first_done")


def test_comb_008_lockstep_rounds_move_together() -> None:
    log: list[tuple[str, int]] = []
    lock = threading.Lock()

    class Shape(Skeleton):
        main = Parallel(lockstep=True)

        @main
        @repeat(times=3)
        def fast(self, ctx: Context) -> None:
            with lock:
                log.append(("fast", sum(1 for n, _ in log if n == "fast")))

        @main
        @repeat(times=3)
        def slow(self, ctx: Context) -> None:
            time.sleep(0.03)
            with lock:
                log.append(("slow", sum(1 for n, _ in log if n == "slow")))

    assert honehone.run(Shape()).outcome == "completed"
    # At any point, the call counts of the two children differ by at most 1
    counts = {"fast": 0, "slow": 0}
    for name, _ in log:
        counts[name] += 1
        assert abs(counts["fast"] - counts["slow"]) <= 1


def test_comb_008_lockstep_requires_repeat_workers() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            main = Parallel(lockstep=True)

            @main
            def once(self, ctx: Context) -> None: ...


def test_comb_009_first_done_ends_with_the_first_child() -> None:
    class Shape(Skeleton):
        main = Parallel(until="first_done")

        @main
        def reader(self, ctx: Context) -> None:
            time.sleep(0.05)
            raise Boom

        @main
        def writer(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)

    result = honehone.run(Shape())
    assert result.nodes["main"].state == "failed"
    assert result.nodes["writer"].state == "stopped"


def test_comb_010_stopped_group_skips_pending_children() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def first(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)

        @main
        def second(self, ctx: Context) -> None: ...

    run = honehone.start(Shape())
    assert run.wait_until("first", "running", 5)
    run.stop()
    result = finish(run)
    assert result.outcome == "stopped"
    assert result.nodes["first"].state == "stopped"
    assert result.nodes["second"].state == "skipped"
    assert result.nodes["main"].state == "stopped"


def test_comb_011_group_modifiers() -> None:
    calls: list[str] = []

    class Shape(Skeleton):
        main = Sequence(modifiers=(repeat(times=2),))

        @main
        def a(self, ctx: Context) -> None:
            calls.append("a")

        @main
        def b(self, ctx: Context) -> None:
            calls.append("b")

    assert honehone.run(Shape()).outcome == "completed"
    assert calls == ["a", "b", "a", "b"]


def test_comb_011_service_cannot_be_given_to_a_group() -> None:
    with pytest.raises(SkeletonDefinitionError):
        _ = Parallel(modifiers=(honehone.service,))


def test_comb_012_repeat_until_and_every() -> None:
    values = iter(range(1, 100))

    class Counting(Skeleton):
        main = Sequence()

        @main
        @repeat(until=lambda value: value >= 3)
        def counter(self, ctx: Context) -> int:
            return next(values)

    result = honehone.run(Counting())
    assert result.nodes["counter"].calls == 3
    assert result.nodes["counter"].value == 3

    class Timed(Skeleton):
        main = Sequence()

        @main
        @repeat(times=3, every=0.05)
        def tick(self, ctx: Context) -> None: ...

    begin = time.monotonic()
    result = honehone.run(Timed())
    assert result.nodes["tick"].calls == 3
    assert time.monotonic() - begin >= 0.09  # start interval 0.05 s x 2


def test_comb_012_repeat_until_stop() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        @repeat(every=0.01)
        def tick(self, ctx: Context) -> None: ...

    run = honehone.start(Shape())
    assert run.wait_until("tick", "running", 5)
    time.sleep(0.05)
    run.stop()
    result = finish(run)
    assert result.nodes["tick"].state == "stopped"
    assert result.nodes["tick"].calls >= 1


def test_comb_013_a_failed_round_ends_the_repeat() -> None:
    rounds: list[int] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        @repeat(times=5)
        def flaky(self, ctx: Context) -> None:
            rounds.append(len(rounds))
            if len(rounds) == 2:
                raise Boom

    result = honehone.run(Shape())
    assert result.nodes["flaky"].state == "failed"
    assert rounds == [0, 1]


def test_comb_014_retry() -> None:
    attempts: list[int] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        @retry(2, backoff=0.01)
        def flaky(self, ctx: Context) -> str:
            attempts.append(1)
            if len(attempts) < 3:
                raise Boom(len(attempts))
            return "ok"

    result = honehone.run(Shape())
    assert result.outcome == "completed"
    record = result.nodes["flaky"]
    assert record.calls == 3
    assert record.value == "ok"
    assert len(record.errors) == 2  # the failure before the retry is kept too


def test_comb_014_retry_exhausted() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        @retry(1)
        def bad(self, ctx: Context) -> None:
            raise Boom

    result = honehone.run(Shape())
    assert result.nodes["bad"].state == "failed"
    assert result.nodes["bad"].calls == 2


def test_comb_015_timeout() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        @timeout(0.05)
        def slow(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)  # woken by the stop request of the timeout

    result = honehone.run(Shape())
    assert result.outcome == "failed"
    assert isinstance(result.nodes["slow"].errors[-1], WorkerTimeout)


def test_comb_016_optional() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        @optional
        def may_fail(self, ctx: Context) -> None:
            raise Boom

        @main
        def after(self, ctx: Context) -> None: ...

    result = honehone.run(Shape())
    assert result.outcome == "completed"
    assert result.nodes["may_fail"].state == "failed"
    assert isinstance(result.nodes["may_fail"].errors[0], Boom)
    assert result.nodes["after"].state == "succeeded"


def test_comb_017_modifier_order_does_not_depend_on_stacking() -> None:
    calls: list[str] = []

    class A(Skeleton):
        main = Sequence()

        @main
        @optional
        @repeat(times=2)
        @retry(1)
        def w(self, ctx: Context) -> None:
            calls.append("A")
            raise Boom

    class B(Skeleton):
        main = Sequence()

        @main
        @retry(1)
        @repeat(times=2)
        @optional
        def w(self, ctx: Context) -> None:
            calls.append("B")
            raise Boom

    ra = honehone.run(A())
    rb = honehone.run(B())
    # retry calls again within one round, repeat ends on the failure, and optional accepts it last
    assert calls.count("A") == calls.count("B") == 2
    assert ra.outcome == rb.outcome == "completed"
