"""Specification: Structure(STRUCT_*)。"""

from __future__ import annotations

from abc import abstractmethod

import pytest

import honehone
from honehone import (
    Context,
    Parallel,
    Sequence,
    Skeleton,
    SkeletonDefinitionError,
    boot,
    cleanup,
    repeat,
)
from tests.conftest import Recorder, finish


def test_struct_002_implementation_class_cannot_declare_groups() -> None:
    class Base(Skeleton):
        main = Sequence()

        @main
        def a(self, ctx: Context) -> None: ...

    with pytest.raises(SkeletonDefinitionError):

        class Impl(Base):
            extra = Sequence()


def test_struct_002_implementation_class_cannot_use_worker_decorators() -> None:
    class Base(Skeleton):
        main = Sequence()

        @main
        def a(self, ctx: Context) -> None: ...

    with pytest.raises(SkeletonDefinitionError):

        class Impl(Base):
            @Base.main
            def b(self, ctx: Context) -> None: ...

    with pytest.raises(SkeletonDefinitionError):

        class Impl2(Base):
            @boot
            def prepare(self, ctx: Context) -> None: ...

    with pytest.raises(SkeletonDefinitionError):

        class Impl3(Base):
            @cleanup
            def tidy(self, ctx: Context) -> None: ...


def test_struct_003_override_keeps_role_and_modifiers() -> None:
    class Base(Skeleton):
        main = Sequence()

        @main
        @repeat(times=3)
        def tick(self, ctx: Context) -> None: ...

    class Impl(Base):
        def __init__(self) -> None:
            self.seen: list[int] = []

        def tick(self, ctx: Context) -> None:
            self.seen.append(1)

    obj = Impl()
    result = honehone.run(obj)
    assert result.outcome == "completed"
    assert obj.seen == [1, 1, 1]
    assert result.nodes["tick"].calls == 3


def test_struct_003_override_replaces_a_group_is_rejected() -> None:
    class Base(Skeleton):
        main = Sequence()

        @main
        def a(self, ctx: Context) -> None: ...

    with pytest.raises(SkeletonDefinitionError):

        class Impl(Base):
            main = None  # checks an invalid override


def test_struct_004_async_workers_are_rejected() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            main = Sequence()

            @main
            async def a(self, ctx: Context) -> None: ...

    class Base(Skeleton):
        main = Sequence()

        @main
        def a(self, ctx: Context) -> None: ...

    with pytest.raises(SkeletonDefinitionError):

        class Impl(Base):
            async def a(self, ctx: Context) -> None: ...  # pyright: ignore[reportIncompatibleMethodOverride] - checks an invalid override


def test_struct_006_a_worker_belongs_to_one_group() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            main = Sequence()
            other = main.parallel()

            @main
            @other
            def a(self, ctx: Context) -> None: ...


def test_struct_007_children_run_in_definition_order() -> None:
    order: list[str] = []

    class Shape(Skeleton):
        main = Sequence()

        @main
        def first(self, ctx: Context) -> None:
            order.append("first")

        inner = main.sequence()

        @inner
        def nested(self, ctx: Context) -> None:
            order.append("nested")

        @main
        def last(self, ctx: Context) -> None:
            order.append("last")

    assert honehone.run(Shape()).outcome == "completed"
    assert order == ["first", "nested", "last"]


def test_struct_008_more_than_one_root_is_rejected() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            one = Sequence()
            two = Parallel()

            @one
            def a(self, ctx: Context) -> None: ...

            @two
            def b(self, ctx: Context) -> None: ...


def test_struct_008_no_root_runs_only_boot_and_cleanup() -> None:
    seen: list[str] = []

    class Only(Skeleton):
        @boot
        def prepare(self, ctx: Context) -> None:
            seen.append("boot")

        @cleanup
        def tidy(self, ctx: Context) -> None:
            seen.append("cleanup")

    assert honehone.run(Only()).outcome == "completed"
    assert seen == ["boot", "cleanup"]


def test_struct_009_empty_groups_are_rejected() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            main = Sequence()
            empty = main.parallel()

            @main
            def a(self, ctx: Context) -> None: ...


def test_struct_009_modifier_without_group_is_rejected() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            @repeat(times=2)
            def a(self, ctx: Context) -> None: ...


def test_struct_010_plain_methods_are_not_workers() -> None:
    class Shape(Skeleton):
        main = Sequence()

        def helper(self) -> int:
            return 41

        @main
        def a(self, ctx: Context) -> int:
            return self.helper() + 1

    result = honehone.run(Shape())
    assert "helper" not in result.nodes
    assert result.nodes["a"].value == 42


def test_struct_011_names_and_paths(recorder: Recorder) -> None:
    class Shape(Skeleton):
        main = Sequence()
        services = main.parallel()

        @services
        def db(self, ctx: Context) -> None: ...

    _ = honehone.run(Shape(), listener=recorder)
    paths = {
        kw["name"]: kw["path"]
        for tag, _, kw in recorder.events
        if tag == "node.changed"
    }
    assert paths == {
        "main": "main",
        "services": "main.services",
        "db": "main.services.db",
    }


def test_struct_012_required_workers_use_abstractmethod() -> None:
    class Base(Skeleton):
        main = Sequence()

        @main
        @abstractmethod
        def must(self, ctx: Context) -> None: ...

    with pytest.raises(TypeError):
        _ = Base()  # pyright: ignore[reportAbstractUsage] - checks that instantiating an abstract class is refused

    class Impl(Base):
        def must(self, ctx: Context) -> None: ...

    assert honehone.run(Impl()).outcome == "completed"


def test_struct_013_default_behavior_runs_and_stops() -> None:
    class Shape(Skeleton):
        main = Parallel()

        @main
        @repeat(every=0.01)
        def watch(self, ctx: Context) -> None: ...

        @main
        def once(self, ctx: Context) -> None: ...

    run = honehone.start(Shape())
    assert run.wait_until("watch", "running", 5)
    run.stop()
    assert finish(run).outcome == "stopped"


def test_struct_015_conflicts_are_found_at_definition_time() -> None:
    with pytest.raises(SkeletonDefinitionError):

        class Bad(Skeleton):
            main = Sequence()

            @main
            @honehone.pinned
            @honehone.isolated
            def a(self, ctx: Context) -> None: ...
