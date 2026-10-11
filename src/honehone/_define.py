"""The tools that declare the shape of a skeleton, and checking and compiling it at class definition.

In the body of a skeleton class (a class that inherits `Skeleton` directly), groups,
modifiers, `boot` and `cleanup` put marks on functions and class attributes.
`Skeleton.__init_subclass__` reads those marks, checks the shape, and compiles it into
the `Plan` used for running (STRUCT_015).
"""

from __future__ import annotations

import inspect
from abc import ABC
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import (
    Any,
    ClassVar,
    Literal,
    TypeVar,
    overload,
)

from honehone._errors import FrozenSkeletonError, SkeletonDefinitionError

F = TypeVar("F", bound=Callable[..., object])
S = TypeVar("S")
C = TypeVar("C")

UntilPredicate = Callable[[Any], object]  # pyright: ignore[reportExplicitAny] - the value is taken as any type so that `lambda value: value >= 3` written by users passes type checking

Until = Literal["all", "first_success", "first_done"]
_UNTIL: tuple[str, ...] = ("all", "first_success", "first_done")

_SPEC_ATTR = "__skeleton_spec__"
_EXECUTION_ATTR = "_skeleton_execution"


# ---------------------------------------------------------------------------
# Modifiers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepeatSpec:
    times: int | None
    every: float | None
    until: UntilPredicate | None


@dataclass(frozen=True, slots=True)
class RetrySpec:
    times: int
    backoff: float | None


@dataclass(frozen=True, slots=True)
class Mods:
    """The modifiers attached to a node."""

    repeat: RepeatSpec | None = None
    retry: RetrySpec | None = None
    timeout: float | None = None
    optional: bool = False
    service: bool = False
    pinned: bool = False
    isolated: bool = False


_GROUP_MODIFIERS = ("repeat", "retry", "timeout", "optional")


@dataclass(slots=True)
class _Spec:
    """The mark put on a function. Decorators write into it in layers."""

    role: Literal["worker", "boot", "cleanup"] = "worker"
    group: Group | None = None
    mods: Mods = field(default_factory=Mods)
    paired: object = None  # the boot function this is paired with


def _spec_of(obj: object) -> _Spec | None:
    spec = getattr(obj, _SPEC_ATTR, None)
    return spec if isinstance(spec, _Spec) else None


def _ensure_spec(fn: Callable[..., object]) -> _Spec:
    if not inspect.isfunction(fn):
        raise SkeletonDefinitionError(
            f"workers must be plain functions defined in the class body, not {type(fn).__name__}"
        )
    spec = _spec_of(fn)
    if spec is None:
        spec = _Spec()
        setattr(fn, _SPEC_ATTR, spec)
    return spec


class Modifier:
    """A modifier that changes how a worker is called. Used as a decorator; passed to groups with `modifiers`."""

    __slots__: tuple[str, ...] = ("_kind", "_value")

    def __init__(self, kind: str, value: object) -> None:
        self._kind: str = kind
        self._value: object = value

    @property
    def kind(self) -> str:
        """The kind of modifier."""
        return self._kind

    def _apply(self, mods: Mods, where: str) -> Mods:
        if self._kind in ("optional", "service", "pinned", "isolated"):
            if getattr(mods, self._kind):
                raise SkeletonDefinitionError(
                    f"@{self._kind} is given twice to {where}"
                )
            return replace(mods, **{self._kind: True})
        if getattr(mods, self._kind) is not None:
            raise SkeletonDefinitionError(f"@{self._kind} is given twice to {where}")
        return replace(mods, **{self._kind: self._value})

    def __call__(self, fn: F) -> F:
        spec = _ensure_spec(fn)
        if spec.role != "worker":
            raise SkeletonDefinitionError(
                f"{spec.role} {fn.__name__!r} cannot have modifiers"
            )
        spec.mods = self._apply(spec.mods, fn.__name__)
        return fn

    def __repr__(self) -> str:
        return f"<honehone modifier {self._kind}>"


def _check_positive(name: str, value: float | None) -> None:
    if value is not None and not value > 0:
        raise SkeletonDefinitionError(f"{name} must be positive, not {value!r}")


def repeat(
    *,
    times: int | None = None,
    every: float | None = None,
    until: UntilPredicate | None = None,
) -> Modifier:
    """The skeleton repeats the call (COMB_012)."""
    if times is not None and (not isinstance(times, int) or times < 1):  # pyright: ignore[reportUnnecessaryIsInstance] - runtime check for calls that ignore the type annotations
        raise SkeletonDefinitionError(f"times must be a positive int, not {times!r}")
    _check_positive("every", every)
    if until is not None and not callable(until):
        raise SkeletonDefinitionError("until must be callable")  # pyright: ignore[reportUnreachable] - runtime check for calls that ignore the type annotations
    return Modifier("repeat", RepeatSpec(times, every, until))


def retry(times: int, *, backoff: float | None = None) -> Modifier:
    """Call again a failed call, up to `times` times (COMB_014)."""
    if not isinstance(times, int) or times < 1:  # pyright: ignore[reportUnnecessaryIsInstance] - runtime check for calls that ignore the type annotations
        raise SkeletonDefinitionError(f"times must be a positive int, not {times!r}")
    if backoff is not None and backoff < 0:
        raise SkeletonDefinitionError(f"backoff must not be negative, not {backoff!r}")
    return Modifier("retry", RetrySpec(times, backoff))


def timeout(seconds: float) -> Modifier:
    """Limit the time of one call (COMB_015)."""
    _check_positive("seconds", seconds)
    return Modifier("timeout", float(seconds))


optional: Modifier = Modifier("optional", True)
"""Treated as a success by the parent even when it fails (COMB_016)."""

service: Modifier = Modifier("service", True)
"""A part that keeps running after it is ready (LIFE_010)."""

pinned: Modifier = Modifier("pinned", True)
"""Always runs on the home thread (EXEC_003)."""

isolated: Modifier = Modifier("isolated", True)
"""Always runs on a dedicated thread (EXEC_004)."""


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


class Group:
    """A node that bundles children. Declared as a class attribute and used as a decorator as it is."""

    _kind: ClassVar[Literal["sequence", "parallel"]]

    def __init__(
        self,
        *,
        until: Until = "all",
        modifiers: tuple[Modifier, ...] = (),
        lockstep: bool = False,
        _parent: Group | None = None,
    ) -> None:
        if until not in _UNTIL:
            raise SkeletonDefinitionError(
                f"until must be one of {_UNTIL}, not {until!r}"
            )
        mods = Mods()
        for modifier in modifiers:
            if not isinstance(modifier, Modifier):  # pyright: ignore[reportUnnecessaryIsInstance] - runtime check for calls that ignore the type annotations
                raise SkeletonDefinitionError(f"not a modifier: {modifier!r}")
            if modifier.kind not in _GROUP_MODIFIERS:
                raise SkeletonDefinitionError(
                    f"@{modifier.kind} cannot be given to a group (COMB_011)"
                )
            mods = modifier._apply(mods, "a group")
        self._until: Until = until
        self._mods: Mods = mods
        self._lockstep: bool = lockstep
        self._parent: Group | None = _parent
        self._name: str | None = None
        self._owner: type | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        if self._owner is not None:
            raise SkeletonDefinitionError(
                f"the group {self._name!r} is assigned to more than one name"
            )
        self._owner = owner
        self._name = name

    def sequence(
        self, *, until: Until = "all", modifiers: tuple[Modifier, ...] = ()
    ) -> Sequence:
        """Create a `Sequence` inside this group."""
        return Sequence(until=until, modifiers=modifiers, _parent=self)

    def parallel(
        self,
        *,
        until: Until = "all",
        lockstep: bool = False,
        modifiers: tuple[Modifier, ...] = (),
    ) -> Parallel:
        """Create a `Parallel` inside this group."""
        return Parallel(
            until=until, lockstep=lockstep, modifiers=modifiers, _parent=self
        )

    def __call__(self, fn: F) -> F:
        spec = _ensure_spec(fn)
        if spec.role != "worker":
            raise SkeletonDefinitionError(
                f"{spec.role} {fn.__name__!r} cannot belong to a group"
            )
        if spec.group is not None and spec.group is not self:
            raise SkeletonDefinitionError(
                f"{fn.__name__!r} belongs to more than one group (STRUCT_006)"
            )
        spec.group = self
        return fn

    def __repr__(self) -> str:
        return f"<honehone {type(self).__name__} {self._name or '?'}>"


class Sequence(Group):
    """A group that runs its children one at a time in definition order (COMB_003, COMB_006)."""

    _kind: ClassVar[Literal["sequence", "parallel"]] = "sequence"

    def __init__(
        self,
        *,
        until: Until = "all",
        modifiers: tuple[Modifier, ...] = (),
        _parent: Group | None = None,
    ) -> None:
        if until == "first_done":
            raise SkeletonDefinitionError(
                'Sequence(until="first_done") has no meaning (COMB_007)'
            )
        super().__init__(until=until, modifiers=modifiers, _parent=_parent)


class Parallel(Group):
    """A group that runs its children at the same time (COMB_004, COMB_005, COMB_009, COMB_008)."""

    _kind: ClassVar[Literal["sequence", "parallel"]] = "parallel"

    def __init__(
        self,
        *,
        until: Until = "all",
        lockstep: bool = False,
        modifiers: tuple[Modifier, ...] = (),
        _parent: Group | None = None,
    ) -> None:
        super().__init__(
            until=until, modifiers=modifiers, lockstep=lockstep, _parent=_parent
        )


# ---------------------------------------------------------------------------
# boot and cleanup
# ---------------------------------------------------------------------------


def boot(fn: F) -> F:
    """Preparation that runs first, on the home thread, in definition order (LIFE_003, LIFE_004).

    The function is returned as it is, so implementation classes can override its
    content as an ordinary method.
    """
    spec = _ensure_spec(fn)
    if spec.group is not None or spec.role != "worker" or spec.mods != Mods():
        raise SkeletonDefinitionError(
            f"{fn.__name__!r} cannot be both boot and a worker or cleanup"
        )
    spec.role = "boot"
    return fn


@overload
def cleanup(fn: F, /) -> F: ...
@overload
def cleanup(*, of: Callable[..., object]) -> Callable[[F], F]: ...
def cleanup(
    fn: F | None = None, /, *, of: Callable[..., object] | None = None
) -> F | Callable[[F], F]:
    """Cleanup that runs at the end of the run (LIFE_007).

    `@cleanup` always runs, however the run ended. `@cleanup(of=connect)` runs only if
    the `boot` named `connect` succeeded (LIFE_008).
    """
    if fn is not None:
        if of is not None:
            raise SkeletonDefinitionError("use either @cleanup or @cleanup(of=...)")
        return _mark_cleanup(fn, None)
    if of is None:
        raise SkeletonDefinitionError("@cleanup() needs of=<boot>")
    boot_spec = _spec_of(of)
    if boot_spec is None or boot_spec.role != "boot":
        raise SkeletonDefinitionError("of= must be a method decorated with @boot")
    paired = of

    def decorate(target: F) -> F:
        return _mark_cleanup(target, paired)

    return decorate


def _mark_cleanup(fn: F, paired: object) -> F:
    spec = _ensure_spec(fn)
    if spec.group is not None or spec.role != "worker" or spec.mods != Mods():
        raise SkeletonDefinitionError(
            f"{fn.__name__!r} cannot be both cleanup and a worker or boot"
        )
    spec.role = "cleanup"
    spec.paired = paired
    return fn


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

NodeKind = Literal["worker", "sequence", "parallel", "boot", "cleanup"]


@dataclass(frozen=True, slots=True, eq=False)
class NodeDef:
    """One node in the shape."""

    name: str
    path: str
    kind: NodeKind
    mods: Mods
    until: Until = "all"
    lockstep: bool = False
    children: tuple[NodeDef, ...] = ()
    paired_boot: str | None = None
    contains_pinned: bool = False

    @property
    def is_group(self) -> bool:
        return self.kind in ("sequence", "parallel")

    def walk(self) -> list[NodeDef]:
        """Return this node and its descendants in pre-order."""
        out: list[NodeDef] = [self]
        for child in self.children:
            out.extend(child.walk())
        return out


@dataclass(frozen=True, slots=True)
class Plan:
    """The shape of one skeleton class."""

    root: NodeDef | None
    boots: tuple[NodeDef, ...]
    cleanups: tuple[NodeDef, ...]
    nodes: Mapping[str, NodeDef]
    parents: Mapping[str, str | None]

    def ancestors(self, name: str) -> list[str]:
        """Return the names up to the root, including this node."""
        out: list[str] = []
        current: str | None = name
        while current is not None:
            out.append(current)
            current = self.parents.get(current)
        return out


def _namespace(obj: object) -> Mapping[str, object]:
    """Read the attribute dictionary of a class or instance without fixing the value type."""
    return vars(obj)


def _fail(message: str) -> SkeletonDefinitionError:
    return SkeletonDefinitionError(message)


def _check_sync(name: str, fn: object) -> None:
    if inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn):
        raise _fail(f"{name!r} is async; async workers are not supported (STRUCT_004)")


def _compile(cls: type) -> Plan:
    groups: dict[str, Group] = {}
    workers: dict[str, _Spec] = {}
    boots: list[str] = []
    cleanups: list[tuple[str, _Spec]] = []
    order: dict[str, int] = {}
    namespace = _namespace(cls)

    for index, (name, value) in enumerate(namespace.items()):
        order[name] = index
        if isinstance(value, Group):
            if value._owner is not cls:
                raise _fail(f"the group {name!r} was declared in another class")
            groups[name] = value
        else:
            spec = _spec_of(value)
            if spec is None:
                continue
            _check_sync(name, value)
            if spec.role == "boot":
                if spec.group is not None or spec.mods != Mods():
                    raise _fail(f"boot {name!r} cannot have modifiers or a group")
                boots.append(name)
            elif spec.role == "cleanup":
                cleanups.append((name, spec))
            elif spec.group is None:
                raise _fail(f"{name!r} has modifiers but belongs to no group")
            else:
                workers[name] = spec

    group_names = {id(g): n for n, g in groups.items()}

    def name_of(group: Group, user: str) -> str:
        found = group_names.get(id(group))
        if found is None:
            raise _fail(
                f"{user!r} refers to a group that is not declared in this class"
            )
        return found

    children: dict[str, list[str]] = {n: [] for n in groups}
    parents: dict[str, str | None] = {}
    for name, group in groups.items():
        parent = None if group._parent is None else name_of(group._parent, name)
        parents[name] = parent
        if parent is not None:
            children[parent].append(name)
    for name, spec in workers.items():
        assert spec.group is not None
        parent = name_of(spec.group, name)
        parents[name] = parent
        children[parent].append(name)
    for names in children.values():
        names.sort(key=order.__getitem__)  # definition order (STRUCT_007)

    roots = [n for n, g in groups.items() if g._parent is None]
    if len(roots) > 1:
        raise _fail(f"more than one root group: {', '.join(roots)} (STRUCT_008)")
    for name, names in children.items():
        if not names:
            raise _fail(f"the group {name!r} has no children (STRUCT_009)")

    def check_worker(name: str, mods: Mods) -> None:
        if mods.pinned and mods.isolated:
            raise _fail(f"{name!r} is both @pinned and @isolated (EXEC_005)")
        if mods.service:
            for other in ("repeat", "retry", "timeout"):
                if getattr(mods, other) is not None:
                    raise _fail(f"@service {name!r} cannot have @{other} (LIFE_014)")
            if mods.pinned:
                raise _fail(f"@service {name!r} cannot be @pinned (LIFE_014)")

    def build(name: str, path: str) -> NodeDef:
        if name in workers:
            mods = workers[name].mods
            check_worker(name, mods)
            return NodeDef(name, path, "worker", mods, contains_pinned=mods.pinned)
        group = groups[name]
        kids = tuple(build(c, f"{path}.{c}") for c in children[name])
        if group._lockstep:
            for kid in kids:
                if kid.kind != "worker" or kid.mods.repeat is None:
                    raise _fail(
                        f"every child of the lockstep group {name!r} must be a @repeat worker (COMB_008)"
                    )
                if kid.mods.service:
                    raise _fail(
                        f"@service {kid.name!r} cannot be in a lockstep group (LIFE_014)"
                    )
        if group._kind == "parallel":
            holders = [k.name for k in kids if k.contains_pinned]
            if len(holders) > 1:
                raise _fail(
                    f"more than one child of {name!r} needs the home thread: {', '.join(holders)} (EXEC_003)"
                )
        return NodeDef(
            name,
            path,
            group._kind,
            group._mods,
            until=group._until,
            lockstep=group._lockstep,
            children=kids,
            contains_pinned=any(k.contains_pinned for k in kids),
        )

    root = build(roots[0], roots[0]) if roots else None

    boot_defs = tuple(NodeDef(n, n, "boot", Mods()) for n in boots)
    boot_by_obj = {id(namespace[n]): n for n in boots}
    cleanup_defs: list[NodeDef] = []
    for name, spec in cleanups:
        paired: str | None = None
        if spec.paired is not None:
            paired = boot_by_obj.get(id(spec.paired))
            if paired is None:
                raise _fail(f"{name!r} is paired with a boot that is not in this class")
        cleanup_defs.append(NodeDef(name, name, "cleanup", Mods(), paired_boot=paired))
        parents[name] = None
    for name in boots:
        parents[name] = None

    nodes: dict[str, NodeDef] = {}
    for node in [*(root.walk() if root else []), *boot_defs, *cleanup_defs]:
        nodes[node.name] = node
    return Plan(
        root,
        boot_defs,
        tuple(cleanup_defs),
        MappingProxyType(nodes),
        MappingProxyType(parents),
    )


_EMPTY_PLAN = Plan(None, (), (), MappingProxyType({}), MappingProxyType({}))


def _check_implementation(cls: type, plan: Plan) -> None:
    namespace = _namespace(cls)
    for name, value in namespace.items():
        if isinstance(value, Group) or _spec_of(value) is not None:
            raise _fail(
                f"{cls.__qualname__} defines {name!r} as part of the shape; only classes "
                + "that inherit Skeleton directly can do that (STRUCT_002)"
            )
        node = plan.nodes.get(name)
        if node is None:
            continue
        if node.is_group:
            raise _fail(f"{cls.__qualname__} replaces the group {name!r} (STRUCT_002)")
        if not inspect.isfunction(value):
            raise _fail(
                f"{cls.__qualname__}.{name} must be a plain method to override a worker (STRUCT_003)"
            )
        _check_sync(name, value)


class Skeleton(ABC):
    """The base of classes whose processing has a fixed shape.

    A class that inherits it directly (a skeleton class) declares the shape, and classes
    that inherit that class (implementation classes) override the content (STRUCT_001).
    """

    __skeleton_plan__: ClassVar[Plan] = _EMPTY_PLAN

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if Skeleton in cls.__bases__:
            for base in cls.__bases__:
                if base is not Skeleton and issubclass(base, Skeleton):
                    raise _fail(
                        f"{cls.__qualname__} inherits Skeleton and another skeleton class"
                    )
            cls.__skeleton_plan__ = _compile(cls)
        else:
            _check_implementation(cls, cls.__skeleton_plan__)

    def __setattr__(self, name: str, value: object) -> None:
        _check_writable(self, name)
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        _check_writable(self, name)
        object.__delattr__(self, name)


def _check_writable(obj: Skeleton, name: str) -> None:
    execution = _namespace(obj).get(_EXECUTION_ATTR)
    if execution is not None and getattr(execution, "frozen", False) is True:
        raise FrozenSkeletonError(
            f"cannot set {name!r}: the instance is frozen while the body runs (LIFE_005)"
        )
