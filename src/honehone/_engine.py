"""The machinery that drives one run.

All state is guarded by one `Condition` per run (a reentrant lock). A state change and
its report happen under the same lock, so reports and `Run.state()` never disagree
(REPORT_005, REPORT_007).
"""

from __future__ import annotations

import signal
import threading
import time
import warnings
from collections.abc import Callable, Generator
from contextlib import contextmanager
from types import MappingProxyType
from typing import Generic, TypeVar, cast, final

import fport

from honehone._define import _EXECUTION_ATTR, NodeDef, Plan, Skeleton, _namespace
from honehone._errors import (
    SkeletonStateError,
    SkeletonWarning,
    ThreadAffinityError,
    WorkerTimeout,
)
from honehone._result import (
    NODE_STATES,
    TERMINAL_STATES,
    NodeRecord,
    NodeState,
    Outcome,
    Result,
)

Listener = Callable[..., object]

T = TypeVar("T")


@final
class _Keep:
    """The marker meaning "leave unchanged" in `set_state()`."""


_KEEP = _Keep()


def _as_exception(exc: BaseException) -> Exception:
    """Normalize a recorded exception to `Exception` (`SkeletonFailed` can hold only `Exception`)."""
    if isinstance(exc, Exception):
        return exc
    wrapped = RuntimeError(f"a worker raised {type(exc).__name__}")
    wrapped.__cause__ = exc
    return wrapped


# ---------------------------------------------------------------------------
# Stop scopes
# ---------------------------------------------------------------------------


class StopHandle:
    """A registered stop callback. `cancel()` withdraws it."""

    __slots__: tuple[str, ...] = ("_callback", "_scope", "_state")

    def __init__(self, scope: _Scope, callback: Callable[[], object]) -> None:
        self._scope: _Scope = scope
        self._callback: Callable[[], object] = callback
        # registered -> fired (committed to be called) -> running -> done, or cancelled
        self._state: str = "registered"

    def cancel(self) -> None:
        """Withdraw the registration. Does nothing once called or already withdrawn."""
        scope = self._scope
        with scope.ex.cond:
            if self._state == "registered":
                self._state = "cancelled"
                if self in scope.callbacks:
                    scope.callbacks.remove(self)
            elif self._state == "fired":
                self._state = (
                    "cancelled"  # the caller sees it, skips it, and lowers the count
                )


class _Scope:
    """The range a stop request reaches. Requests propagate from parent to child."""

    __slots__: tuple[str, ...] = (
        "callback_errors",
        "callbacks",
        "children",
        "closed",
        "ex",
        "inflight",
        "parent",
        "stopped_at",
        "stopping",
    )

    def __init__(self, ex: _Execution, parent: _Scope | None) -> None:
        self.ex: _Execution = ex
        self.parent: _Scope | None = parent
        self.stopping: bool = False
        self.stopped_at: float | None = None
        self.children: list[_Scope] = []
        self.callbacks: list[StopHandle] = []
        self.callback_errors: list[Exception] = []
        self.inflight: int = 0
        self.closed: bool = False
        if parent is not None:
            with ex.cond:
                parent.children.append(self)
                if parent.stopping:
                    self.stopping = True
                    self.stopped_at = time.monotonic()

    def child(self) -> _Scope:
        return _Scope(self.ex, self)

    def request(self) -> None:
        """Request a stop. Propagates to children and calls callbacks on another thread (EXEC_011)."""
        with self.ex.cond:
            pending: list[StopHandle] = []
            self._request(pending)
            self.ex.cond.notify_all()
        if pending:
            _start_dispatch(self.ex, pending)

    def _request(self, pending: list[StopHandle]) -> None:
        if self.stopping:
            return
        self.stopping = True
        self.stopped_at = time.monotonic()
        for handle in self.callbacks:
            handle._state = "fired"
            self.inflight += 1
            pending.append(handle)
        self.callbacks.clear()
        for child in list(self.children):
            child._request(pending)

    def on_stop(self, callback: Callable[[], object]) -> StopHandle:
        handle = StopHandle(self, callback)
        with self.ex.cond:
            if self.closed:
                handle._state = "done"
                return handle
            if not self.stopping:
                self.callbacks.append(handle)
                return handle
            handle._state = "fired"  # a stop is already requested; call it right away
            self.inflight += 1
        _start_dispatch(self.ex, [handle])
        return handle

    def wait_stop(self, timeout: float | None) -> bool:
        with self.ex.cond:
            return self.ex.cond.wait_for(lambda: self.stopping, timeout)

    def close(self) -> None:
        """The call has ended. Wait for callbacks already committed to be called to finish,
        and do not call those not yet committed."""
        with self.ex.cond:
            limit = self.ex.stop_timeout
            _ = self.ex.cond.wait_for(lambda: self.inflight == 0, limit)
            self.closed = True
            for handle in self.callbacks:
                handle._state = "cancelled"
            self.callbacks.clear()
            if self.parent is not None and self in self.parent.children:
                self.parent.children.remove(self)


def _start_dispatch(ex: _Execution, handles: list[StopHandle]) -> None:
    threading.Thread(
        target=_dispatch, args=(ex, handles), name="honehone:on_stop", daemon=True
    ).start()


def _dispatch(ex: _Execution, handles: list[StopHandle]) -> None:
    """Call the callbacks one at a time in registration order. A failure is recorded as a failure of the call."""
    for handle in handles:
        scope = handle._scope
        with ex.cond:
            if handle._state != "fired":
                scope.inflight -= 1
                ex.cond.notify_all()
                continue
            handle._state = "running"
        error: Exception | None = None
        try:
            _ = handle._callback()
        except BaseException as exc:  # noqa: BLE001 - a callback failure is recorded as a node failure
            error = _as_exception(exc)
        with ex.cond:
            handle._state = "done"
            if error is not None:
                scope.callback_errors.append(error)
            scope.inflight -= 1
            ex.cond.notify_all()


# ---------------------------------------------------------------------------
# Context and ThreadBound
# ---------------------------------------------------------------------------


class Context:
    """The environment received by workers, `boot` and `cleanup` (EXEC_010)."""

    __slots__: tuple[str, ...] = ("_ex", "_rt", "_scope")

    def __init__(self, ex: _Execution, rt: _NodeRT, scope: _Scope) -> None:
        self._ex: _Execution = ex
        self._rt: _NodeRT = rt
        self._scope: _Scope = scope

    @property
    def name(self) -> str:
        """The name of the node."""
        return self._rt.node.name

    @property
    def stopping(self) -> bool:
        """`True` if a stop has been requested."""
        return self._scope.stopping

    def wait_stop(self, timeout: float | None = None) -> bool:
        """Wait up to `timeout` seconds for a stop request. Return `True` if there is one."""
        return self._scope.wait_stop(timeout)

    def on_stop(self, callback: Callable[[], object]) -> StopHandle:
        """Register a callback called once, from another thread, on a stop request."""
        if not callable(callback):
            raise TypeError("callback must be callable")  # pyright: ignore[reportUnreachable] - runtime check for calls that ignore the type annotations
        return self._scope.on_stop(callback)

    def checkpoint(self) -> None:
        """If a pause is requested, wait until resumed or a stop is requested (CTRL_007)."""
        self._ex.boundary(self._rt, self._scope)

    def ready(self) -> None:
        """Signal that the service is ready (LIFE_010)."""
        self._ex.mark_ready(self._rt)

    def report(self, *args: object, **kwargs: object) -> None:
        """Send the worker's own report (REPORT_006)."""
        self._ex.port.send("worker.report", self._rt.node.name, *args, **kwargs)

    def __repr__(self) -> str:
        return f"<honehone Context {self.name}>"


class ThreadBound(Generic[T]):
    """A holder bound to the thread that created it. Created in `boot`, it is bound to the home thread (EXEC_007)."""

    __slots__: tuple[str, ...] = ("_ident", "_value")

    def __init__(self, value: T) -> None:
        self._value: T = value
        self._ident: int = threading.get_ident()

    def get(self) -> T:
        """Return the content only when called from the bound thread."""
        if threading.get_ident() != self._ident:
            raise ThreadAffinityError(
                "this resource belongs to another thread; use it from a @pinned worker"
            )
        return self._value

    def __repr__(self) -> str:
        return f"<honehone ThreadBound {type(self._value).__name__}>"


# ---------------------------------------------------------------------------
# Runtime state of nodes
# ---------------------------------------------------------------------------


class _NodeRT:
    __slots__: tuple[str, ...] = (
        "base",
        "calls",
        "ended",
        "errors",
        "node",
        "phase",
        "planned_stop",
        "reached",
        "settle_seq",
        "started",
        "tolerated",
        "value",
    )

    def __init__(self, node: NodeDef) -> None:
        self.node: NodeDef = node
        self.base: str = "pending"
        self.phase: str | None = None
        self.errors: list[Exception] = []
        self.calls: int = 0
        self.value: object = None
        self.started: float | None = None
        self.ended: float | None = None
        self.reached: set[str] = {"pending"}
        self.tolerated: bool = False
        self.planned_stop: bool = False
        self.settle_seq: int | None = None

    @property
    def display(self) -> str:
        if self.base in TERMINAL_STATES or self.base == "pending":
            return self.base
        return self.phase or self.base

    @property
    def effective(self) -> str:
        """How the node ended, as seen by its parent. A failure accepted by `@optional` and ready both count as success."""
        if self.base == "failed" and self.tolerated:
            return "succeeded"
        if self.base == "ready":
            return "succeeded"
        return self.base

    @property
    def settled(self) -> bool:
        return self.base in TERMINAL_STATES or self.base == "ready"


Round = tuple[str, object, list[Exception]]
"""The outcome of one call: (how it ended, return value, exception)."""


class _Lockstep:
    """The lockstep of `Parallel(lockstep=True)` (COMB_008)."""

    def __init__(self, ex: _Execution, names: list[str]) -> None:
        self.ex: _Execution = ex
        self.counts: dict[str, int] = dict.fromkeys(names, 0)
        self.ended: bool = False

    def turn(self, name: str, scope: _Scope) -> bool:
        completed = self.counts[name]
        with self.ex.cond:
            _ = self.ex.cond.wait_for(
                lambda: (
                    self.ended
                    or scope.stopping
                    or all(c >= completed for c in self.counts.values())
                )
            )
            return not self.ended

    def done(self, name: str) -> None:
        with self.ex.cond:
            self.counts[name] += 1
            self.ex.cond.notify_all()

    def end(self) -> None:
        with self.ex.cond:
            self.ended = True
            self.ex.cond.notify_all()


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class _Execution:
    def __init__(
        self, obj: Skeleton, listener: Listener | None, stop_timeout: float | None
    ) -> None:
        if stop_timeout is not None and stop_timeout < 0:
            raise ValueError("stop_timeout must be None or a non-negative number")
        plan: Plan = type(obj).__skeleton_plan__
        self.obj: Skeleton = obj
        self.plan: Plan = plan
        self.stop_timeout: float | None = stop_timeout
        self.cond: threading.Condition = threading.Condition(threading.RLock())
        self.port: fport.Port = fport.Port()
        self.connection: fport.Connection | None = (
            None if listener is None else self.port.connect(listener)
        )
        self.nodes: dict[str, _NodeRT] = {n: _NodeRT(d) for n, d in plan.nodes.items()}
        self.pause_requests: set[str] = set()
        self.stop_count: int = 0
        self.run_scope: _Scope = _Scope(self, None)
        self.cleanup_scope: _Scope = _Scope(self, None)
        self.frozen: bool = False
        self.started: bool = False
        self.finished: bool = False
        self.result: Result | None = None
        self.delivered: bool = False
        self.services: list[tuple[_NodeRT, _Scope]] = []
        self.ready_order: list[str] = []
        self.service_failures: list[Exception] = []
        self.lockstep_of: dict[str, _Lockstep] = {}
        self.settle_counter: int = 0
        self.internal_errors: list[Exception] = []
        self.handle: Run = Run(self)

    # -- state and reports ----------------------------------------------------

    def set_state(
        self, rt: _NodeRT, base: str | _Keep = _KEEP, phase: str | None | _Keep = _KEEP
    ) -> None:
        with self.cond:
            before = rt.display
            if not isinstance(base, _Keep):
                if (
                    rt.base == "stuck"
                ):  # a late end of a node given up on is not recorded
                    return
                rt.base = base
                if base == "running" and rt.started is None:
                    rt.started = time.monotonic()
                if base in TERMINAL_STATES:
                    rt.ended = time.monotonic()
                    rt.phase = None
                elif base in ("running", "ready") and self.affected(rt.node.name):
                    rt.phase = rt.phase or "pausing"
            if not isinstance(phase, _Keep):
                rt.phase = phase
            if rt.settled and rt.settle_seq is None:
                self.settle_counter += 1
                rt.settle_seq = self.settle_counter
            elif rt.base == "pending":
                rt.settle_seq = None
            after = rt.display
            if after != before:
                rt.reached.add(after)
                error = rt.errors[-1] if after == "failed" and rt.errors else None
                self.port.send(
                    "node.changed",
                    name=rt.node.name,
                    path=rt.node.path,
                    state=after,
                    error=error,
                )
                self.refresh_parent(rt)
            self.cond.notify_all()

    def refresh_parent(self, rt: _NodeRT) -> None:
        """Recompute pausing / paused of the parent groups from how their children are paused."""
        parent_name = self.plan.parents.get(rt.node.name)
        if parent_name is None:
            return
        parent = self.nodes[parent_name]
        if parent.base not in ("running", "ready") or not self.affected(parent_name):
            return
        active = [
            self.nodes[c.name]
            for c in parent.node.children
            if self.nodes[c.name].base in ("running", "ready")
        ]
        if not active:
            return
        phase = "paused" if all(c.phase == "paused" for c in active) else "pausing"
        if parent.phase != phase:
            self.set_state(parent, phase=phase)

    def affected(self, name: str) -> bool:
        return any(a in self.pause_requests for a in self.plan.ancestors(name))

    def skip_subtree(self, node: NodeDef) -> None:
        for n in node.walk():
            rt = self.nodes[n.name]
            if rt.base == "pending":
                self.set_state(rt, base="skipped")

    def reset_subtree(self, node: NodeDef) -> None:
        """Reset the descendants to pending for the next round of a repeating group."""
        for child in node.children:
            for n in child.walk():
                rt = self.nodes[n.name]
                if rt.base in TERMINAL_STATES and rt.base != "stuck":
                    with self.cond:
                        rt.tolerated = False
                    self.set_state(rt, base="pending")

    # -- operations -----------------------------------------------------------

    def request_stop(self) -> None:
        with self.cond:
            self.stop_count = min(self.stop_count + 1, 2)
            count = self.stop_count
        if count == 1:
            self.run_scope.request()
        else:
            self.run_scope.request()
            self.cleanup_scope.request()

    def pause(self, name: str | None) -> None:
        target = self.target(name)
        if target is None:
            return
        with self.cond:
            if target in self.pause_requests:
                return
            self.pause_requests.add(target)
            for n in self.plan.nodes[target].walk():
                rt = self.nodes[n.name]
                if rt.base in ("running", "ready") and rt.phase is None:
                    self.set_state(rt, phase="pausing")
            self.cond.notify_all()

    def resume(self, name: str | None) -> None:
        target = self.target(name)
        if target is None:
            return
        with self.cond:
            self.pause_requests.discard(target)
            for n in self.plan.nodes[target].walk():
                rt = self.nodes[n.name]
                if rt.phase is not None and not self.affected(n.name):
                    self.set_state(rt, phase=None)
            self.cond.notify_all()

    def target(self, name: str | None) -> str | None:
        if name is None:
            return None if self.plan.root is None else self.plan.root.name
        if name not in self.plan.nodes:
            raise KeyError(name)
        return name

    def boundary(self, rt: _NodeRT, scope: _Scope) -> None:
        """A boundary. If a pause is requested, wait until resumed or a stop is requested (CTRL_005)."""
        with self.cond:
            if scope.stopping or not self.affected(rt.node.name):
                return
            self.set_state(rt, phase="paused")
            _ = self.cond.wait_for(
                lambda: scope.stopping or not self.affected(rt.node.name)
            )
            if rt.phase is not None:
                self.set_state(
                    rt, phase="pausing" if self.affected(rt.node.name) else None
                )

    def mark_ready(self, rt: _NodeRT) -> None:
        if not rt.node.mods.service:
            raise SkeletonStateError(f"{rt.node.name!r} is not a @service (LIFE_010)")
        with self.cond:
            if rt.base == "running":
                self.ready_order.append(rt.node.name)
                self.set_state(rt, base="ready")

    # -- waiting --------------------------------------------------------------

    def await_settled(self, rts: list[_NodeRT], scopes: dict[str, _Scope]) -> None:
        """Wait until the nodes settle (end or become ready).

        A node asked to stop that does not settle within `stop_timeout` is given up on
        as a node that did not stop (stuck) (RESULT_004).
        """
        with self.cond:
            while True:
                waiting = [rt for rt in rts if not rt.settled]
                if not waiting:
                    return
                deadline: float | None = None
                for rt in waiting:
                    scope = scopes[rt.node.name]
                    if not scope.stopping or self.stop_timeout is None:
                        continue
                    assert scope.stopped_at is not None
                    limit = scope.stopped_at + self.stop_timeout
                    if time.monotonic() >= limit:
                        self.mark_stuck(rt.node)
                    elif deadline is None or limit < deadline:
                        deadline = limit
                if all(rt.settled for rt in rts):
                    return
                timeout = (
                    None if deadline is None else max(0.0, deadline - time.monotonic())
                )
                _ = self.cond.wait(timeout)

    def mark_stuck(self, node: NodeDef) -> None:
        for n in node.walk():
            rt = self.nodes[n.name]
            if rt.base not in TERMINAL_STATES:
                self.set_state(rt, base="stuck")

    # -- running nodes --------------------------------------------------------

    def run_node(self, node: NodeDef, scope: _Scope) -> str:
        """Run one node to the end on the calling thread. Return how it ended, as seen by its parent."""
        rt = self.nodes[node.name]
        self.set_state(rt, base="running")
        final, errors = self.run_rounds(rt, scope)
        with self.cond:
            rt.errors.extend(e for e in errors if e not in rt.errors)
            if final == "failed" and node.mods.optional:
                rt.tolerated = True
        self.set_state(rt, base=final)
        return rt.effective

    def run_rounds(self, rt: _NodeRT, scope: _Scope) -> tuple[str, list[Exception]]:
        """Run with the modifiers applied from the inside: timeout, retry, then repeat (COMB_017)."""
        node = rt.node
        spec = node.mods.repeat
        lock = self.lockstep_of.get(node.name)
        errors: list[Exception] = []
        next_start: float | None = None
        count = 0
        try:
            while True:
                if scope.stopping:
                    return "stopped", errors
                if lock is not None and count > 0 and not lock.turn(node.name, scope):
                    return ("stopped" if scope.stopping else "succeeded"), errors
                self.boundary(rt, scope)
                if scope.stopping:
                    return "stopped", errors
                if next_start is not None:
                    remaining = next_start - time.monotonic()
                    if remaining > 0 and scope.wait_stop(remaining):
                        return "stopped", errors
                started = time.monotonic()
                if count > 0 and node.is_group:
                    self.reset_subtree(node)
                state, value, round_errors = self.run_with_retry(rt, scope)
                errors.extend(round_errors)
                count += 1
                if lock is not None:
                    lock.done(node.name)
                if state != "succeeded":
                    return state, errors
                if spec is None:
                    return "succeeded", errors
                if spec.times is not None and count >= spec.times:
                    return "succeeded", errors
                if spec.until is not None:
                    try:
                        finished = bool(spec.until(value))
                    except Exception as exc:  # noqa: BLE001 - a failure of until is a failure of the node
                        errors.append(exc)
                        return "failed", errors
                    if finished:
                        return "succeeded", errors
                if spec.every is not None:
                    next_start = started + spec.every
        finally:
            if lock is not None:
                lock.end()

    def run_with_retry(self, rt: _NodeRT, scope: _Scope) -> Round:
        spec = rt.node.mods.retry
        attempts = 1 + (spec.times if spec is not None else 0)
        errors: list[Exception] = []
        state, value = "stopped", None
        for attempt in range(attempts):
            if attempt > 0:
                self.boundary(rt, scope)
                if scope.stopping:
                    return "stopped", None, errors
                if spec is not None and spec.backoff and scope.wait_stop(spec.backoff):
                    return "stopped", None, errors
            state, value, round_errors = self.run_once(rt, scope)
            errors.extend(round_errors)
            if state != "failed" or scope.stopping:
                break
        return state, value, errors

    def run_once(self, rt: _NodeRT, scope: _Scope) -> Round:
        """Run one call, applying `@timeout` (COMB_015)."""
        node = rt.node
        call_scope = scope.child()
        timed_out = threading.Event()
        timer: threading.Timer | None = None
        if node.mods.timeout is not None:

            def expire() -> None:
                timed_out.set()
                call_scope.request()

            timer = threading.Timer(node.mods.timeout, expire)
            timer.daemon = True
            timer.start()
        try:
            if node.is_group:
                state, value, errors = self.run_group(rt, call_scope)
            else:
                state, value, errors = self.invoke(rt, call_scope)
        finally:
            if timer is not None:
                timer.cancel()
            call_scope.close()
        with self.cond:
            errors = [*errors, *call_scope.callback_errors]
        if timed_out.is_set() and not scope.stopping:
            error = WorkerTimeout(
                f"{node.name!r} took longer than {node.mods.timeout}s"
            )
            if errors:
                error.__cause__ = errors[-1]
            return "failed", None, [*errors, error]
        if errors:
            return "failed", None, errors
        return state, value, errors

    def invoke(self, rt: _NodeRT, scope: _Scope) -> Round:
        """Call the worker once. With `@isolated`, call it on a dedicated thread (EXEC_004)."""
        node = rt.node
        method = cast("Callable[[Context], object]", getattr(self.obj, node.name))
        ctx = Context(self, rt, scope)
        outcome: list[Round] = []

        def call() -> None:
            try:
                value = method(ctx)
            except BaseException as exc:  # noqa: BLE001 - a worker failure is recorded as a node failure
                result: Round = ("failed", None, [_as_exception(exc)])
            else:
                result = ("stopped" if scope.stopping else "succeeded", value, [])
            with self.cond:
                outcome.append(result)
                rt.calls += 1
                if result[0] != "failed":
                    rt.value = result[1]
                self.port.send(
                    "node.called", name=node.name, path=node.path, count=rt.calls
                )
                self.cond.notify_all()

        if node.mods.isolated and not node.mods.service:
            thread = threading.Thread(
                target=call, name=f"honehone:{node.path}", daemon=True
            )
            thread.start()
            with self.cond:
                while not outcome:
                    if scope.stopping and self.stop_timeout is not None:
                        assert scope.stopped_at is not None
                        remaining = (
                            scope.stopped_at + self.stop_timeout - time.monotonic()
                        )
                        if remaining <= 0:
                            self.mark_stuck(node)
                            return "stopped", None, []
                        _ = self.cond.wait(remaining)
                    else:
                        _ = self.cond.wait()
        else:
            call()
        return outcome[0]

    # -- groups ---------------------------------------------------------------

    def run_group(self, rt: _NodeRT, scope: _Scope) -> Round:
        node = rt.node
        if node.kind == "sequence":
            return self.run_sequence(rt, scope)
        return self.run_parallel(rt, scope)

    def causes_of(self, rt: _NodeRT) -> list[Exception]:
        if rt.node.is_group:
            return list(rt.errors)
        return rt.errors[-1:]

    def start_child(
        self, child: NodeDef, scope: _Scope
    ) -> tuple[_Scope, threading.Thread | None]:
        """Start a child. Services and children with a dedicated thread run on a thread."""
        if child.mods.service:
            child_scope = _Scope(
                self, None
            )  # services are stopped LIFO, so they are detached from the parent's stop
            rt = self.nodes[child.name]
            with self.cond:
                self.services.append((rt, child_scope))
            thread = threading.Thread(
                target=self.run_service,
                args=(child, child_scope),
                name=f"honehone:{child.path}",
                daemon=True,
            )
            thread.start()
            return child_scope, thread
        child_scope = scope.child()
        thread = threading.Thread(
            target=self.run_node,
            args=(child, child_scope),
            name=f"honehone:{child.path}",
            daemon=True,
        )
        thread.start()
        return child_scope, thread

    def run_service(self, node: NodeDef, scope: _Scope) -> None:
        rt = self.nodes[node.name]
        self.set_state(rt, base="running")
        state, _, errors = self.run_once(rt, scope)
        with self.cond:
            was_ready = rt.base == "ready"
            rt.errors.extend(errors)
            if not was_ready and state != "failed":
                self.ready_order.append(node.name)
                self.set_state(
                    rt, base="ready"
                )  # returned without calling ready() (LIFE_010)
            if state == "failed" and node.mods.optional:
                rt.tolerated = True
            if state == "stopped" and rt.planned_stop:
                state = "succeeded"  # the stop that comes with the end of the body (LIFE_011)
            self.set_state(rt, base=state)
            if was_ready and state == "failed" and not rt.tolerated:
                self.service_failures.extend(
                    errors[-1:]
                )  # a failure after ready (LIFE_012)
                failed = True
            else:
                failed = False
        if failed:
            self.run_scope.request()
        scope.close()

    def run_sequence(self, rt: _NodeRT, scope: _Scope) -> Round:
        node = rt.node
        causes: list[Exception] = []
        any_success = False
        for index, child in enumerate(node.children):
            if not scope.stopping:
                self.boundary(rt, scope)
            if scope.stopping:
                for rest in node.children[index:]:
                    self.skip_subtree(rest)
                return (
                    ("failed" if causes and node.until == "all" else "stopped"),
                    None,
                    causes,
                )
            child_rt = self.nodes[child.name]
            if child.mods.service:
                child_scope, _ = self.start_child(child, scope)
                self.await_service(child_rt, child_scope, scope)
                effective = child_rt.effective if child_rt.settled else "stopped"
            else:
                child_scope = scope.child()
                effective = self.run_node(child, child_scope)
                child_scope.close()
            if child_rt.base == "stuck":
                effective = "stopped"
            if effective == "failed":
                causes.extend(self.causes_of(child_rt))
                if node.until == "all":
                    for rest in node.children[index + 1 :]:
                        self.skip_subtree(rest)
                    return "failed", None, causes
                continue
            if effective == "succeeded":
                any_success = True
                if node.until == "first_success":
                    for rest in node.children[index + 1 :]:
                        self.skip_subtree(rest)
                    return "succeeded", None, []
                continue
            # stopped / skipped
            for rest in node.children[index + 1 :]:
                self.skip_subtree(rest)
            return "stopped", None, causes if node.until == "all" else []
        if node.until == "first_success" and not any_success:
            return "failed", None, causes
        return "succeeded", None, []

    def await_service(self, rt: _NodeRT, child_scope: _Scope, scope: _Scope) -> None:
        """Wait until the service is ready or ends. If the waiting side is stopped, stop the service too."""
        with self.cond:
            while not rt.settled:
                if scope.stopping and not child_scope.stopping:
                    child_scope.request()
                if child_scope.stopping:
                    break
                _ = self.cond.wait()
        if not rt.settled:
            self.await_settled([rt], {rt.node.name: child_scope})

    def run_parallel(self, rt: _NodeRT, scope: _Scope) -> Round:
        node = rt.node
        self.boundary(rt, scope)
        if scope.stopping:
            for child in node.children:
                self.skip_subtree(child)
            return "stopped", None, []
        if node.lockstep:
            lock = _Lockstep(self, [c.name for c in node.children])
            with self.cond:
                for child in node.children:
                    self.lockstep_of[child.name] = lock
        holder = next((c for c in node.children if c.contains_pinned), None)
        rts = [self.nodes[c.name] for c in node.children]
        holder_rt = None if holder is None else self.nodes[holder.name]
        scopes: dict[str, _Scope] = {}
        if holder is not None:
            scopes[holder.name] = scope.child()
        winner: list[_NodeRT] = []

        def judge() -> None:
            """Look at children in the order they settle, and stop the rest depending on how they ended (COMB_004, COMB_005, COMB_009)."""
            if winner:
                return
            settled = sorted(
                (r for r in rts if r.settled), key=lambda r: r.settle_seq or 0
            )
            for child_rt in settled:
                eff = "stopped" if child_rt.base == "stuck" else child_rt.effective
                stop_rest = (
                    (node.until == "all" and eff == "failed")
                    or (node.until == "first_success" and eff == "succeeded")
                    or node.until == "first_done"
                )
                if stop_rest:
                    winner.append(child_rt)
                    for other in rts:
                        other_scope = scopes.get(other.node.name)
                        if (
                            other is not child_rt
                            and not other.settled
                            and other_scope is not None
                        ):
                            other_scope.request()
                    return

        def watch() -> None:
            with self.cond:
                while not all(r.settled for r in rts):
                    judge()
                    if scope.stopping:
                        for other in rts:
                            other_scope = scopes.get(other.node.name)
                            if not other.settled and other_scope is not None:
                                other_scope.request()
                    if any(
                        scopes[r.node.name].stopping
                        for r in rts
                        if not r.settled
                        and r.node.name in scopes
                        and r is not holder_rt
                    ):
                        break
                    _ = self.cond.wait()
                judge()
            # A child on the home thread cannot be given up on (EXEC_006). Wait for the others, giving up on those that do not stop.
            self.await_settled([r for r in rts if r is not holder_rt], scopes)
            with self.cond:
                judge()

        for child in node.children:
            if child is not holder:
                scopes[child.name], _ = self.start_child(child, scope)
        if holder is not None:
            watcher = threading.Thread(
                target=watch, name=f"honehone:{node.path}:watch", daemon=True
            )
            watcher.start()
            _ = self.run_node(
                holder, scopes[holder.name]
            )  # the child that inherits the home thread (EXEC_003)
            watcher.join()
        else:
            watch()
        for child in node.children:
            if not child.mods.service:
                scopes[child.name].close()
        with self.cond:
            for child in node.children:
                _ = self.lockstep_of.pop(child.name, None)
        return self.judge_parallel(rt, rts, winner)

    def judge_parallel(
        self, rt: _NodeRT, rts: list[_NodeRT], winner: list[_NodeRT]
    ) -> Round:
        node = rt.node

        def eff(r: _NodeRT) -> str:
            return "stopped" if r.base == "stuck" else r.effective

        failed = [r for r in rts if eff(r) == "failed"]
        causes = [e for r in failed for e in self.causes_of(r)]
        if node.until == "all":
            if failed:
                return "failed", None, causes
            if any(eff(r) != "succeeded" for r in rts):
                return "stopped", None, []
            return "succeeded", None, []
        if node.until == "first_success":
            if any(eff(r) == "succeeded" for r in rts):
                return "succeeded", None, []
            if len(failed) == len(rts):
                return "failed", None, causes
            return "stopped", None, []
        first = winner[0] if winner else None
        if first is None:
            return "stopped", None, []
        state = eff(first)
        if state == "skipped":
            state = "stopped"
        return state, None, self.causes_of(first) if state == "failed" else []

    # -- one run --------------------------------------------------------------

    def execute(self) -> None:
        """Run boot -> body -> cleanup on the home thread (LIFE_003)."""
        try:
            self.execute_phases()
        except BaseException as exc:  # noqa: BLE001 - even an internal error ends the run so that waiters are not left hanging
            with self.cond:
                self.internal_errors.append(_as_exception(exc))
                self.frozen = False
        self.finish()

    def execute_phases(self) -> None:
        self.port.send("run.started")
        boot_ok = True
        for boot_def in self.plan.boots:
            rt = self.nodes[boot_def.name]
            if not boot_ok or self.run_scope.stopping:
                self.set_state(rt, base="skipped")
                continue
            boot_scope = self.run_scope.child()
            effective = self.run_node(boot_def, boot_scope)
            boot_scope.close()
            if effective != "succeeded":
                boot_ok = False
        root = self.plan.root
        if root is not None:
            if boot_ok and not self.run_scope.stopping:
                with self.cond:
                    self.frozen = True
                body_scope = self.run_scope.child()
                _ = self.run_node(root, body_scope)
                body_scope.close()
                self.stop_services()
                with self.cond:
                    self.frozen = False
            else:
                self.skip_subtree(root)
        for cleanup_def in reversed(self.plan.cleanups):
            rt = self.nodes[cleanup_def.name]
            paired = cleanup_def.paired_boot
            if self.cleanup_scope.stopping or (
                paired is not None and self.nodes[paired].base != "succeeded"
            ):
                self.set_state(rt, base="skipped")
                continue
            cleanup_scope = self.cleanup_scope.child()
            _ = self.run_node(cleanup_def, cleanup_scope)
            cleanup_scope.close()

    def stop_services(self) -> None:
        """After the rest of the body ends, stop the services in the reverse order they became ready (LIFE_011, LIFE_013)."""
        with self.cond:
            planned = self.stop_count == 0 and not self.service_failures
            services = list(self.services)
            order = {name: i for i, name in enumerate(self.ready_order)}
        not_ready = [s for s in services if s[0].node.name not in order]
        ready = sorted(
            (s for s in services if s[0].node.name in order),
            key=lambda s: order[s[0].node.name],
            reverse=True,
        )
        for rt, scope in [*not_ready, *ready]:
            with self.cond:
                if rt.base in TERMINAL_STATES:
                    continue
                rt.planned_stop = planned
            scope.request()
            self.await_settled_terminal(rt, scope)

    def await_settled_terminal(self, rt: _NodeRT, scope: _Scope) -> None:
        with self.cond:
            while rt.base not in TERMINAL_STATES:
                if self.stop_timeout is not None:
                    assert scope.stopped_at is not None
                    remaining = scope.stopped_at + self.stop_timeout - time.monotonic()
                    if remaining <= 0:
                        self.mark_stuck(rt.node)
                        return
                    _ = self.cond.wait(remaining)
                else:
                    _ = self.cond.wait()

    def finish(self) -> None:
        with self.cond:
            failures: list[Exception] = []
            failed = False
            for boot_def in self.plan.boots:
                rt = self.nodes[boot_def.name]
                if rt.effective == "failed":
                    failed = True
                    failures.extend(self.causes_of(rt))
            root = self.plan.root
            if root is not None:
                rt = self.nodes[root.name]
                if rt.effective == "failed":
                    failed = True
                    failures.extend(self.causes_of(rt))
            if self.service_failures:
                failed = True
                failures.extend(self.service_failures)
            cleanup_errors: list[Exception] = []
            for cleanup_def in self.plan.cleanups:
                rt = self.nodes[cleanup_def.name]
                if rt.base == "failed":
                    cleanup_errors.extend(rt.errors)
            if cleanup_errors:
                failed = True
                failures.extend(cleanup_errors)
            if self.internal_errors:
                failed = True
                failures.extend(self.internal_errors)
            outcome: Outcome = (
                "failed" if failed else "stopped" if self.stop_count else "completed"
            )
            now = time.monotonic()
            records = {
                name: NodeRecord(
                    state=_node_state(rt.display),
                    errors=tuple(rt.errors),
                    calls=rt.calls,
                    value=rt.value,
                    duration=None
                    if rt.started is None
                    else (rt.ended if rt.ended is not None else now) - rt.started,
                )
                for name, rt in self.nodes.items()
            }
            self.result = Result(
                outcome=outcome,
                nodes=MappingProxyType(records),
                cleanup_errors=tuple(cleanup_errors),
                stuck=tuple(n for n, rt in self.nodes.items() if rt.base == "stuck"),
                _failures=tuple(failures),
            )
            self.finished = True
            self.port.send("run.finished", result=self.result)
            self.cond.notify_all()
        if self.connection is not None:
            self.connection.disconnect()

    def deliver(self) -> Result:
        """Return the result. If a node did not stop, warn once on the receiving thread."""
        with self.cond:
            result = self.result
            assert result is not None
            first = not self.delivered
            self.delivered = True
        if first and result.stuck:
            warnings.warn(
                f"nodes did not stop: {', '.join(result.stuck)}",
                SkeletonWarning,
                stacklevel=3,
            )
        return result


def _node_state(state: str) -> NodeState:
    if state not in NODE_STATES:
        raise AssertionError(state)
    return state  # pyright: ignore[reportReturnType] - checked against NODE_STATES


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


class Run:
    """The handle for operating a running skeleton (CTRL_004)."""

    __slots__: tuple[str, ...] = ("_ex",)

    def __init__(self, ex: _Execution) -> None:
        self._ex: _Execution = ex

    def pause(self, name: str | None = None) -> None:
        """Request a pause. Returns without waiting for it to take effect (CTRL_005)."""
        self._ex.pause(name)

    def resume(self, name: str | None = None) -> None:
        """Withdraw the pause request (CTRL_008)."""
        self._ex.resume(name)

    def stop(self) -> None:
        """Request a stop of the whole run. A second request stops the cleanup too (CTRL_009)."""
        self._ex.request_stop()

    def wait(self, timeout: float | None = None) -> Result | None:
        """Wait for the run to end and return the `Result`. `None` on timeout."""
        ex = self._ex
        with ex.cond:
            if not ex.cond.wait_for(lambda: ex.finished, timeout):
                return None
        return ex.deliver()

    def wait_until(
        self, name: str, state: NodeState, timeout: float | None = None
    ) -> bool:
        """Wait until the node reaches `state` (CTRL_010)."""
        ex = self._ex
        if name not in ex.plan.nodes:
            raise KeyError(name)
        if state not in NODE_STATES:
            raise ValueError(f"unknown state {state!r}")
        rt = ex.nodes[name]
        with ex.cond:
            _ = ex.cond.wait_for(lambda: state in rt.reached or ex.finished, timeout)
            return state in rt.reached

    def state(self, name: str) -> NodeState:
        """Return the current state of the node (RESULT_002)."""
        ex = self._ex
        if name not in ex.plan.nodes:
            raise KeyError(name)
        with ex.cond:
            return _node_state(ex.nodes[name].display)

    def __repr__(self) -> str:
        return f"<honehone Run {'finished' if self._ex.finished else 'running'}>"


def _prepare(
    obj: Skeleton, listener: Listener | None, stop_timeout: float | None
) -> _Execution:
    if not isinstance(obj, Skeleton):  # pyright: ignore[reportUnnecessaryIsInstance] - runtime check for calls that ignore the type annotations
        raise TypeError(f"expected a Skeleton instance, not {type(obj).__name__}")  # pyright: ignore[reportUnreachable] - runtime check for calls that ignore the type annotations
    if listener is not None and not callable(listener):
        raise TypeError("listener must be callable")  # pyright: ignore[reportUnreachable] - runtime check for calls that ignore the type annotations
    if _namespace(obj).get(_EXECUTION_ATTR) is not None:
        raise SkeletonStateError(
            "this instance has already run; create a new one (LIFE_001)"
        )
    ex = _Execution(obj, listener, stop_timeout)
    object.__setattr__(obj, _EXECUTION_ATTR, ex)
    return ex


@contextmanager
def _sigint_to_stop(ex: _Execution) -> Generator[None]:
    """On the main thread, turn Ctrl+C into a stop request (CTRL_001)."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def handler(_signum: int, _frame: object) -> None:
        # A signal handler may interrupt code holding the lock, so the request is made on another thread.
        threading.Thread(target=ex.request_stop, daemon=True).start()

    previous = signal.signal(signal.SIGINT, handler)
    try:
        yield
    finally:
        _ = signal.signal(signal.SIGINT, previous)


def run(
    obj: Skeleton,
    *,
    listener: Listener | None = None,
    stop_timeout: float | None = None,
) -> Result:
    """Run with the calling thread as the home thread, wait until it ends, and return the result (CTRL_001)."""
    ex = _prepare(obj, listener, stop_timeout)
    with _sigint_to_stop(ex):
        ex.execute()
    return ex.deliver()


def start(
    obj: Skeleton,
    *,
    listener: Listener | None = None,
    stop_timeout: float | None = None,
) -> Run:
    """Prepare a home thread, start the run, and return its handle without waiting (CTRL_002)."""
    ex = _prepare(obj, listener, stop_timeout)
    thread = threading.Thread(
        target=ex.execute, name=f"honehone:{type(obj).__name__}", daemon=True
    )
    thread.start()
    return ex.handle


def control(obj: Skeleton) -> Run:
    """Return the handle of the run started for the instance (CTRL_013)."""
    ex = _namespace(obj).get(_EXECUTION_ATTR)
    if not isinstance(ex, _Execution):
        raise SkeletonStateError("this instance has not started running")
    return ex.handle
