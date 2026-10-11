<!-- Published from devdocs/canonical_documents/specification/execution.md sha256:e181109aeff2bbfba888e1c2efab3cbd05d80122d2371a3b253cfa2a7554f272. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Execution

Rules on the home thread, the default unit of execution, pinned and isolated, passing data, and Context.

## EXEC_001

Workers run on threads. One run has one **home thread**. With `honehone.run()` the thread that called it, and with `honehone.start()` a thread prepared for the run, becomes the home thread (CTRL_001, CTRL_002).

Which worker runs on which thread is not chosen by the user leaf by leaf; it is decided by the structure and by the constraints attached to leaves (`@pinned`, `@isolated`).

title: Threads and the home thread

level: INFORMATIVE

## EXEC_002

By default, threads must be decided by the following rules.

- What runs in order (`boot`, `cleanup`, the children of a `Sequence`, each round of `@repeat`, the retries of `@retry`) is called on the same thread as its parent
- The children of a `Parallel` each run on a thread of their own, except the child that inherits the home thread by EXEC_003
- A `@service` worker always runs on a thread of its own, even when its parent is a `Sequence`, because it keeps running after it is ready while the parent moves on to the next child

Threads are started only where concurrency is needed, and no threads are added where things run in order.

title: Default threading

level: MUST

## EXEC_003

A worker with `@pinned` must always run on the home thread. It is for workers that handle resources that cannot be used across threads, such as an sqlite connection.

The home thread is inherited along the path from the root to the `@pinned` worker. A `Parallel` runs the child that contains `@pinned` among its descendants on the home thread, and the other children on threads of their own. If two or more children of the same `Parallel` contain `@pinned` among their descendants, `SkeletonDefinitionError` must be raised when the class is defined.

title: Pinned workers

level: MUST

related: [STRUCT_015](structure.md#struct_015)

## EXEC_004

A worker with `@isolated` must always run on a thread of its own, even when it is a child of a `Sequence`. If it does not stop, the parent gives up on it as a node that did not stop (RESULT_004) and moves on. It is for work that might hang.

title: Isolated workers

level: MUST

## EXEC_005

If a worker is given both `@pinned` and `@isolated`, `SkeletonDefinitionError` must be raised when the class is defined.

title: Pinned and isolated conflict

level: MUST

related: [STRUCT_015](structure.md#struct_015)

## EXEC_006

If a worker called on the same thread as its parent does not return, the work that follows on that thread (including `cleanup`) cannot proceed either. The skeleton cannot give up on it. Attach `@isolated` to work that might not stop.

title: Workers on a shared thread cannot be abandoned

level: INFORMATIVE

## EXEC_007

`honehone.ThreadBound(obj)` is a holder that wraps `obj` and binds it to the thread that created it. The holder's `get()` must return `obj` only when called from the thread that created it, and must raise `ThreadAffinityError` when called from another thread. If it is created inside `boot`, it is bound to the home thread. Use it in `boot` like `self.db = honehone.ThreadBound(sqlite3.connect(path))`.

title: Holding thread-bound resources

level: MUST

## EXEC_008

Passing data between workers follows these rules.

- Exchanges across threads go through `Channel` or `Shared`
- A resource bound to a thread is wrapped in `honehone.ThreadBound` and used from a `@pinned` worker
- Attributes of the instance can be written only during `boot` and `cleanup` (LIFE_005)

Workers that run in order on the same thread can exchange data freely within these rules.

title: Rules for passing data

level: INFORMATIVE

related: [LIFE_005](lifecycle.md#life_005), [LIFE_006](lifecycle.md#life_006)

## EXEC_009

`honehone` must expose `Channel`, the tool for passing values, and `Shared`, a shared cell with a fixed type, as `honehone.Channel` and `honehone.Shared`. A worker's `ctx` can be passed as it is to the waits of these, such as `Channel.receive(ctx)`.

title: Channel and Shared

level: MUST

## EXEC_010

The `Context` received by workers, `boot` and `cleanup` must have the following.

| Name | Content |
| --- | --- |
| `name` | The name of the node |
| `stopping` | True if a stop has been requested (in `cleanup`, by LIFE_009) |
| `wait_stop(timeout)` | Waits for a stop request. Returns true if there was a request |
| `on_stop(callback)` | Registers a callback called on a stop request |
| `checkpoint()` | If a pause has been requested, waits until resumed (CTRL_007) |
| `ready()` | Tells that a service is ready (LIFE_010). `SkeletonStateError` outside a service |
| `report(*args, **kwargs)` | Sends the worker's own report (REPORT_006) |

title: Context

level: MUST

## EXEC_011

A callback registered with `ctx.on_stop(callback)` must be called once, when a stop is requested, on a thread that is neither the thread that requested the stop nor the worker's thread. A callback registered when a stop has already been requested is called in the same way right after registration. After `cancel()` of the returned `StopHandle`, and after the call has ended, callbacks that have not yet been decided to be called are not called. A callback that has been decided to be called because a stop was requested before the call ended is called even after the call has returned, and the call waits for it to end before ending (at most `stop_timeout`). If a callback raises an exception, that call becomes `failed` and the exception remains in the record.

title: Stop callbacks

level: MUST
