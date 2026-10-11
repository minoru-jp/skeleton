<!-- Published from devdocs/canonical_documents/specification/lifecycle.md sha256:7024bd72e2348368d992c42f220de9680c848ab2e8d3b8d042a053d0fdb8dfca. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Lifecycle

Rules on the relation between instances and runs, the flow of boot, body and cleanup, freezing, and services.

## LIFE_001

One instance corresponds to one run. If an instance that has started running is run again, `SkeletonStateError` must be raised. To run several times, create the instance again.

title: One instance, one run

level: MUST

## LIFE_002

`__init__` should only receive settings and should not acquire resources such as connections or files. `__init__` runs outside the run, so neither stop requests nor `cleanup` apply to it. Resources are prepared in `boot`.

title: What __init__ is for

level: SHOULD

condition: When writing `__init__` in a skeleton class or an implementation class.

## LIFE_003

One run must proceed in the following order.

1. `boot`, one at a time in the order of definition
2. The body (the root group)
3. `cleanup`, one at a time in the reverse order of definition
4. Settling the result (RESULT_001)

`boot` and `cleanup` run on the home thread (EXEC_002).

title: The flow of a run

level: MUST

## LIFE_004

When a `boot` ends `failed`, the remaining `boot`s and all nodes of the body must become `skipped`, and the run must go on to `cleanup`. In the same way, when a stop is requested in the middle of `boot`, the rest become `skipped` and the run goes on to `cleanup`.

title: When boot fails

level: MUST

## LIFE_005

While the body is running, assigning to or deleting attributes of the instance must be refused with `FrozenSkeletonError`. Attributes can be assigned during `boot` and `cleanup`, because both run one at a time on the home thread and never in parallel with other workers.

title: The instance is frozen while the body runs

level: MUST

## LIFE_006

To exchange values between workers of the body, prepare a `Channel` or `Shared` in `boot`, put it in an attribute, and pass values through it. Since attributes themselves cannot be rewritten (LIFE_005), sharing always goes through an explicit tool.

title: Sharing between workers

level: INFORMATIVE

## LIFE_007

`cleanup` must run however the body ended (`succeeded`, `failed`, `stopped`, or `skipped` because of a failed `boot`). They run one at a time in the reverse order of definition, and even if one ends `failed`, the rest still run. Exceptions from `cleanup` are collected in `Result.cleanup_errors` (RESULT_007).

title: Cleanup always runs

level: MUST

## LIFE_008

A `cleanup` can be paired with a particular `boot`. A `cleanup` paired as in `@cleanup(of=connect)` must run only when the corresponding `boot` ended `succeeded`. A `@cleanup` that is not paired always runs.

```python
@boot
def connect(self, ctx): ...


@cleanup(of=connect)
def disconnect(self, ctx): ...  # runs only when connect succeeded
```

`@boot` and `@cleanup` must return the function as it is. This lets implementation classes override the content of `boot` and `cleanup` as plain methods, and lets type checkers treat that as an ordinary method override.

title: Pairing cleanup with boot

level: MUST

## LIFE_009

Inside `cleanup`, `ctx.stopping` must be false, so that cleaning up is not interrupted by the stop request that caused it. However, when a second stop is requested for the run, a stop is requested from the running `cleanup`, and the remaining `cleanup`s become `skipped`.

title: Cleanup is not interrupted by the first stop

level: MUST

## LIFE_010

A worker with `@service` is a component that keeps running after it is ready (a server, monitoring of a device, and so on). When the worker calls `ctx.ready()`, the node becomes `ready`.

- If the parent is a `Sequence`, it moves on to the next child as soon as the service becomes `ready`. The service itself keeps running
- If the parent is a `Parallel`, `ready` is counted as done when judging how it ends
- If it returns without calling `ctx.ready()`, it becomes `ready` when it returns, and then `succeeded`
- If it ends `failed` before becoming `ready`, it becomes `failed` like an ordinary worker

title: Services

level: MUST

## LIFE_011

A service that has become `ready` is stopped by the skeleton when all of the rest of the body (the nodes other than services) has ended. The end caused by this stop must make the service `succeeded`. It is a planned way to end, distinguished from `stopped` caused by a stop request.

title: When services are stopped

level: MUST

## LIFE_012

When a service that has become `ready` ends `failed`, it must be handled as a failure of the whole body, and a stop must be requested from the body.

title: A service that fails after ready

level: MUST

## LIFE_013

When stopping services, a stop must be requested from them one at a time in the reverse order in which they became `ready`, waiting for each to end before moving on to the next. This is to clean up what was prepared later first (stopping the API before stopping the DB). Nodes that are not services are requested to stop at the same time.

title: Order of stopping services

level: MUST

## LIFE_014

`@service` cannot be combined with modifiers other than `@optional` and `@isolated`. If it is combined with `@repeat`, `@retry`, `@timeout` or `@pinned`, or if `@service` is given to a child of `Parallel(lockstep=True)`, `SkeletonDefinitionError` must be raised when the class is defined. A service runs on its own thread (EXEC_002) and keeps running after it is ready, so these modifiers do not fit its meaning.

title: Conflicting service declarations

level: MUST

related: [STRUCT_015](structure.md#struct_015), [COMB_008](combinators.md#comb_008)

## LIFE_015

A stop request does not reach a service from its parent group. Even when a stop is requested for the whole run, the nodes of the body that are not services stop first, and after the body has ended, the services are stopped in the order of LIFE_013. However, a service that has not yet become `ready` is stopped as soon as the parent waiting for it is stopped (so that the body's stop does not wait for a service in the middle of getting ready).

title: Services are stopped after the body

level: MUST
