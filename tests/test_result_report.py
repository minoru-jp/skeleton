"""Specification: Result (RESULT_*) and Report (REPORT_*)."""

from __future__ import annotations

import pytest

import honehone
from honehone import Context, Parallel, Sequence, Skeleton, boot, cleanup
from tests.conftest import Recorder, finish


class KeyProblem(KeyError):
    pass


class ValueProblem(ValueError):
    pass


def test_result_001_run_returns_a_result_even_on_failure() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def bad(self, ctx: Context) -> None:
            raise ValueProblem("bad")

    result = honehone.run(Shape())  # raises no exception
    assert result.outcome == "failed"


def test_result_003_failure_wins_over_stop() -> None:
    class Shape(Skeleton):
        main = Parallel()

        @main
        def waits(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)

        @main
        def fails_on_stop(self, ctx: Context) -> None:
            _ = ctx.wait_stop(5)
            raise ValueProblem("while stopping")

    run = honehone.start(Shape())
    assert run.wait_until("fails_on_stop", "running", 5)
    run.stop()
    assert finish(run).outcome == "failed"


def test_result_005_node_records() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def first(self, ctx: Context) -> int:
            return 7

        @main
        def second(self, ctx: Context) -> None:
            raise ValueProblem("x")

        @main
        def third(self, ctx: Context) -> None: ...

    result = honehone.run(Shape())
    first, second, third = (result.nodes[n] for n in ("first", "second", "third"))
    assert (first.state, first.value, first.calls) == ("succeeded", 7, 1)
    assert first.duration is not None
    assert second.state == "failed"
    assert isinstance(second.errors[0], ValueProblem)
    assert (third.state, third.calls, third.duration) == ("skipped", 0, None)
    assert result.nodes["main"].state == "failed"


def test_result_006_boot_and_cleanup_are_recorded() -> None:
    class Shape(Skeleton):
        @boot
        def prepare(self, ctx: Context) -> str:
            return "ready"

        @cleanup
        def tidy(self, ctx: Context) -> None: ...

    result = honehone.run(Shape())
    assert result.nodes["prepare"].value == "ready"
    assert result.nodes["tidy"].state == "succeeded"


def test_result_008_raise_if_failed_supports_except_star() -> None:
    class Shape(Skeleton):
        main = Parallel()

        @main
        def a(self, ctx: Context) -> None:
            raise KeyProblem("a")

        @cleanup
        def tidy(self, ctx: Context) -> None:
            raise ValueProblem("tidy")

    result = honehone.run(Shape())
    caught: list[type[BaseException]] = []
    try:
        result.raise_if_failed()
    except* KeyProblem as group:
        caught.extend(type(e) for e in group.exceptions)
    except* ValueProblem as group:
        caught.extend(type(e) for e in group.exceptions)
    assert sorted(t.__name__ for t in caught) == ["KeyProblem", "ValueProblem"]


def test_result_008_raise_if_failed_does_nothing_otherwise() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def ok(self, ctx: Context) -> None: ...

    honehone.run(Shape()).raise_if_failed()


def test_result_009_errors_are_the_original_exceptions() -> None:
    problem = ValueProblem("original")

    class Shape(Skeleton):
        main = Sequence()

        @main
        def bad(self, ctx: Context) -> None:
            raise problem

    result = honehone.run(Shape())
    assert result.nodes["bad"].errors == (problem,)
    assert "gpframe" not in type(result).__module__


def test_report_001_listener_failures_do_not_change_the_run() -> None:
    def broken(tag: str, *args: object, **kwargs: object) -> None:
        raise RuntimeError("listener broke")

    class Shape(Skeleton):
        main = Sequence()

        @main
        def ok(self, ctx: Context) -> None: ...

    assert honehone.run(Shape(), listener=broken).outcome == "completed"


def test_report_002_003_vocabulary_and_bounds(recorder: Recorder) -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def ok(self, ctx: Context) -> int:
            return 1

    result = honehone.run(Shape(), listener=recorder)
    tags = recorder.tags()
    assert tags[0] == "run.started"
    assert tags[-1] == "run.finished"
    assert recorder.events[-1][2] == {"result": result}
    assert set(tags) == {"run.started", "node.changed", "node.called", "run.finished"}
    changed = [kw for tag, _, kw in recorder.events if tag == "node.changed"]
    assert all(set(kw) == {"name", "path", "state", "error"} for kw in changed)
    called = [kw for tag, _, kw in recorder.events if tag == "node.called"]
    assert called == [{"name": "ok", "path": "main.ok", "count": 1}]


def test_report_003_failed_state_carries_the_error(recorder: Recorder) -> None:
    problem = ValueProblem("bad")

    class Shape(Skeleton):
        main = Sequence()

        @main
        def bad(self, ctx: Context) -> None:
            raise problem

    _ = honehone.run(Shape(), listener=recorder)
    failed = [
        kw
        for tag, _, kw in recorder.events
        if tag == "node.changed" and kw["name"] == "bad" and kw["state"] == "failed"
    ]
    assert failed[0]["error"] is problem


def test_report_005_states_of_one_node_arrive_in_order(recorder: Recorder) -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def a(self, ctx: Context) -> None: ...

    _ = honehone.run(Shape(), listener=recorder)
    assert recorder.states("a") == ["running", "succeeded"]
    assert recorder.states("main") == ["running", "succeeded"]


def test_report_006_reports_from_workers(recorder: Recorder) -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def a(self, ctx: Context) -> None:
            ctx.report("progress", 50, unit="%")

    _ = honehone.run(Shape(), listener=recorder)
    reports = [
        (args, kw) for tag, args, kw in recorder.events if tag == "worker.report"
    ]
    assert reports == [(("a", "progress", 50), {"unit": "%"})]


def test_report_listener_must_be_callable() -> None:
    class Shape(Skeleton):
        main = Sequence()

        @main
        def a(self, ctx: Context) -> None: ...

    with pytest.raises(TypeError):
        _ = honehone.run(Shape(), listener="print")  # pyright: ignore[reportArgumentType] - checks an invalid listener
