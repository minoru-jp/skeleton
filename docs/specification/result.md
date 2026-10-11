<!-- Published from devdocs/canonical_documents/specification/result.md sha256:f6548f2e6a32abaa15a2fcf25177ec22c598813248ecf2c67ab7d1bf54e286ec. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Result

Rules on Result, judging the whole run, node states and records, and raising exceptions.

## RESULT_001

When a run ends, its result `Result` is settled. `Result` must have the following.

| Name | Content |
| --- | --- |
| `outcome` | The judgement of the whole run. One of `"completed"`, `"failed"` and `"stopped"` (RESULT_003) |
| `nodes` | A read-only mapping from node names to records `NodeRecord` (RESULT_005) |
| `cleanup_errors` | The exceptions raised in `cleanup` (RESULT_007) |
| `stuck` | The names of the nodes that did not stop (RESULT_004) |
| `raise_if_failed()` | Raises an exception on failure (RESULT_008) |

`Result` is returned by `Run.wait()` and `honehone.run()`. Neither raises an exception; both always return a `Result`.

title: Result

level: MUST

related: [CTRL_001](control.md#ctrl_001), [CTRL_004](control.md#ctrl_004)

## RESULT_002

The state of a node must be one of the following.

| State | Meaning |
| --- | --- |
| `pending` | Not started yet |
| `running` | Running |
| `pausing` | Requested to pause, waiting for a boundary |
| `paused` | Stopped at a boundary |
| `ready` | A service that has finished getting ready and keeps running |
| `succeeded` / `failed` / `stopped` / `skipped` | Ended (COMB_001) |
| `stuck` | Requested to stop, but did not end by `stop_timeout` |

title: Node states

level: MUST

related: [COMB_001](combinators.md#comb_001)

## RESULT_003

`outcome` must be judged in the following order.

1. `"failed"` if there is a final `failed` in any of `boot`, the body and `cleanup`
2. Otherwise, `"stopped"` if a stop was requested for the run
3. Otherwise, `"completed"`

A failure takes precedence over a stop. A failure that happens while stopping is `"failed"` too. Failures accepted by the parent through `@optional` or `until="first_success"` are not counted as a final `failed`.

title: Judging the outcome

level: MUST

## RESULT_004

A node that did not stop becomes `stuck`, its name must be put in `Result.stuck`, and it must be reported with the warning `SkeletonWarning`. The warning is given only once, on the thread that receives the result (the thread that called `honehone.run()`, or the thread that called the `Run.wait()` that first returned the result). Not stopping does not itself change `outcome`. The skeleton does not forcibly stop threads, and its responsibility ends at reporting.

title: Nodes that did not stop

level: MUST

## RESULT_005

`NodeRecord` is the record of one node and must have the following.

| Name | Content |
| --- | --- |
| `state` | The final state |
| `errors` | The exceptions that happened in that node, including those of `@retry` retries, failures accepted by `@optional`, and failures of children that lost under `until="first_success"` |
| `calls` | How many times the worker was called (counting each round of `@repeat` and each retry of `@retry`) |
| `value` | The last return value of the worker. `None` for groups and for workers that never returned |
| `duration` | The seconds from start to end. `None` for nodes that did not start |

title: Node records

level: MUST

## RESULT_006

`boot` and `cleanup` are also nodes with names, and must have records in `Result.nodes`.

title: Boot and cleanup are recorded

level: MUST

## RESULT_007

`Result.cleanup_errors` must hold the exceptions raised in `cleanup`, in the order they happened. A failure in `cleanup` makes `outcome` `"failed"` (RESULT_003).

title: Errors in cleanup

level: MUST

related: [LIFE_007](lifecycle.md#life_007)

## RESULT_008

`Result.raise_if_failed()` must raise `SkeletonFailed` if `outcome` is `"failed"`, and must do nothing otherwise. `SkeletonFailed` is an `ExceptionGroup` holding the exceptions of the nodes that finally became `failed` and the `cleanup_errors`. It can be received per exception type with `except*`.

title: Raising on failure

level: MUST

## RESULT_009

`Result` and `NodeRecord` must not contain gpframe types. Exceptions are held as the workers raised them.

title: No gpframe types in results

level: MUST NOT

related: [CTRL_014](control.md#ctrl_014)

## RESULT_010

Starting threads and propagating stop requests are owned by honehone itself, and follow the same principles as gpframe. Stopping is cooperative, threads that did not stop are reported rather than stopped forcibly, and threads are started as daemon threads so they do not prevent the process from exiting. gpframe frames are not used because stops must be requested per node, for example to stop services one at a time. Users do not need to be aware of this mechanism; they only need to look at the `Result`.

title: Relation to gpframe

level: INFORMATIVE
