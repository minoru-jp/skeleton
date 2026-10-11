<!-- Published from devdocs/canonical_documents/specification/control.md sha256:b5137d3165ec3338ea85960e331290f30734e68b32f549050635ddc0e936b350. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Control

Rules on run and start, the Run handle, pausing at boundaries, waiting, and joining gpframe.

## CTRL_001

`honehone.run(obj, *, listener=None, stop_timeout=None)` must run with the calling thread as the home thread, wait until the run ends, and return a `Result`. When called from the main thread, it turns `KeyboardInterrupt` (Ctrl+C) during the run into a stop request. A second Ctrl+C becomes a second stop request (LIFE_009).

title: run

level: MUST

related: [LIFE_009](lifecycle.md#life_009)

## CTRL_002

`honehone.start(obj, *, listener=None, stop_timeout=None)` must prepare a home thread for the run, start the run, and return the `Run` handle without waiting.

title: start

level: MUST

## CTRL_003

`stop_timeout` is the upper limit, in seconds, of waiting for a node requested to stop to end. A node that has not ended after the limit is given up on as a node that did not stop (RESULT_004). With `None`, it waits until the node ends.

title: stop_timeout

level: MUST

## CTRL_004

`Run` must have the following operations. Nodes are referred to by name (STRUCT_011), and a name that does not exist raises `KeyError`.

| Operation | Content |
| --- | --- |
| `pause(name=None)` | Requests a pause (CTRL_005) |
| `resume(name=None)` | Withdraws a pause request (CTRL_008) |
| `stop()` | Requests a stop for the whole run (CTRL_009) |
| `wait(timeout=None)` | Waits for the run to end and returns the `Result`. `None` on timeout |
| `wait_until(name, state, timeout=None)` | Waits until a node reaches the given state (CTRL_010) |
| `state(name)` | Returns the current state of a node (RESULT_002) |

Every operation can be called from any thread.

title: The Run handle

level: MUST

## CTRL_005

`pause(name)` must request a pause and return without waiting for anything to stop. The named node and its descendants stop at the next **boundary**. If `name` is omitted, the whole body is the target. Boundaries are the following points that the skeleton holds between calls.

- Before starting the next round of `@repeat`
- Before starting the next child of a `Sequence`
- Before a `Parallel` starts its children
- Before a retry of `@retry`
- When a worker calls `ctx.checkpoint()`

A node between receiving the request and stopping at a boundary is `pausing`, and a node stopped at a boundary is `paused`.

title: Pausing at boundaries

level: MUST

## CTRL_006

A pause must not interrupt a call in progress, because there is no way to freeze a thread safely from outside. Since the skeleton owns the loops and the transitions between steps, nodes reliably stop at boundaries even if the worker does nothing to cooperate.

title: A call in progress is not interrupted

level: MUST

## CTRL_007

A service has no boundaries. To pause a service that keeps running after `ready`, the worker itself needs to call `ctx.checkpoint()`. `ctx.checkpoint()` must wait until it is resumed or a stop is requested, if a pause has been requested for itself or an ancestor. Only here is pausing cooperative.

title: Checkpoints in services

level: MUST

related: [LIFE_010](lifecycle.md#life_010)

## CTRL_008

Pause requests must be recorded per name. A node stops if there is a request for itself or for any of its ancestors. `resume(name)` withdraws only the request for that name, and if no other request remains, the node returns to `running`. Calling `pause(name)` twice still makes one request.

title: Resuming

level: MUST

## CTRL_009

`stop()` must request a stop for the whole run and return without waiting for it to end. A stop request takes precedence over a pause, and wakes and stops `paused` and `pausing` nodes too. A stop request cannot be withdrawn. A second `stop()` becomes a second stop request (LIFE_009).

title: Stopping

level: MUST

related: [LIFE_009](lifecycle.md#life_009)

## CTRL_010

`wait_until(name, state, timeout=None)` must return `True` as soon as the node reaches `state`. If it has already passed through that state (for example a service that has once become `ready`), it returns `True` at once. It returns `False` when the run has ended and the state can no longer be reached, and on timeout.

title: Waiting for a node

level: MUST

## CTRL_011

When one child of `Parallel(lockstep=True)` stops, the other children cannot start their next round either, so the whole group stops in step.

title: Pausing in lockstep

level: INFORMATIVE

related: [COMB_008](combinators.md#comb_008)

## CTRL_012

A worker should not call `Run.wait()` or `Run.wait_until()` of its own run from inside the worker. It would be waiting for its own end, and would never end.

title: Waiting from inside a run

level: SHOULD NOT

condition: When using `Run` inside a worker.

## CTRL_013

`honehone.control(obj)` must return the `Run` of an instance `obj` that is running or has finished running. Since one instance corresponds to one run (LIFE_001), the instance is the key that refers to the run. For an instance that has not started running, `SkeletonStateError` is raised.

title: Finding the Run of an instance

level: MUST

related: [LIFE_001](lifecycle.md#life_001)

## CTRL_014

The component for putting a skeleton into a gpframe tree must be placed in `honehone.gpframe`, a module separate from the core. gpframe types must not appear on the public surface of the `honehone` core.

`honehone.gpframe.routine` is a routine for a gpframe frame. Use it as `s.spawn(honehone.gpframe.routine, obj)`, and to pass a listener for reports, `s.spawn(honehone.gpframe.routine, obj, listener)`. The home thread is the thread of that frame. A stop request to the frame becomes a stop request to the run, and when the run ends `failed`, the frame fails with `SkeletonFailed` (RESULT_008). The handle can be obtained with `honehone.control(obj)`.

title: Joining a gpframe tree

level: MUST

## CTRL_015

A group that has been requested to pause must be `paused` when it is stopped at its own boundary, or when all of its running children (children that are `running` or `ready`) have become `paused`, and `pausing` otherwise. This is so that the state of a group shows whether everything below it has stopped.

title: Pausing groups

level: MUST
