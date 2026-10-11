<!-- Published from devdocs/canonical_documents/specification/combinators.md sha256:4ebea6d2214d5c52da193c4015bf21f994bac98e620f493f5a5dfce2c04ee8c4. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Combinators

Rules on how nodes end, how Sequence and Parallel end, and modifiers.

## COMB_001

Every node ends in one of the following.

| How it ends | Meaning |
| --- | --- |
| `succeeded` | It succeeded |
| `failed` | It ended with an exception |
| `stopped` | It ended after a stop was requested. Not a failure. If it ended with an exception, it is `failed` |
| `skipped` | It did not start, because of an earlier failure or a stop request. Not a failure |

A group only has rules that decide how it ends from how its children ended. Since every node ends in the same ways, groups can be nested as deeply as needed. Nodes that did not stop are handled by RESULT_004.

title: How nodes end

level: INFORMATIVE

## COMB_002

The kind of a group is decided by the combination of how its children are **arranged** (`Sequence` one at a time in order, `Parallel` at the same time) and how it **completes**, `until`.

| | `until="all"` (default) | `until="first_success"` | `until="first_done"` |
| --- | --- | --- | --- |
| `Sequence` | All, in order (COMB_003) | Try in order until the first success (COMB_006) | Error at definition (COMB_007) |
| `Parallel` | All, at the same time (COMB_004) | Run at the same time, first success wins (COMB_005) | Run at the same time, first to end wins (COMB_009) |

`sequence()` / `parallel()`, which make child groups, take the same `until`.

title: Arrangement and completion

level: INFORMATIVE

## COMB_003

`Sequence(until="all")` must run its children one at a time in the order of definition. When a child ends `succeeded`, it moves on to the next child, and if all children are `succeeded`, it becomes `succeeded` itself. When a child ends `failed`, the remaining children become `skipped` and it becomes `failed` itself.

title: Sequence

level: MUST

## COMB_004

`Parallel(until="all")` must start all of its children at the same time. If all children are `succeeded`, it becomes `succeeded` itself. When a child ends `failed`, it requests a stop from the remaining children, waits for them to end, and then becomes `failed` itself. The children requested to stop end `stopped` and are not counted as failures.

title: Parallel

level: MUST

## COMB_005

`Parallel(until="first_success")` must start all of its children at the same time, and request a stop from the remaining children as soon as a child ends `succeeded`. It becomes `succeeded` itself. Children that ended `failed` before then are not its failure, but they remain in the record (RESULT_005). If all children are `failed`, it becomes `failed` itself.

title: Race

level: MUST

## COMB_006

`Sequence(until="first_success")` must try its children one at a time in the order of definition. When a child ends `succeeded`, the rest become `skipped` and it becomes `succeeded` itself. When a child is `failed`, it tries the next child. If all children are `failed`, it becomes `failed` itself. Children that ended `failed` remain in the record (RESULT_005).

title: Fallback

level: MUST

## COMB_007

`Sequence(until="first_done")` has no meaning, since it is the same as running only the first child, so `SkeletonDefinitionError` must be raised when the class is defined.

title: Sequence cannot end at the first done

level: MUST

related: [STRUCT_015](structure.md#struct_015)

## COMB_008

The children of `Parallel(lockstep=True)` must all be `@repeat` workers; otherwise `SkeletonDefinitionError` is raised when the class is defined. No child must start its next round until one round of every child has ended. When the repetition of any child ends, the other children end without starting their next round.

title: Lockstep

level: MUST

related: [STRUCT_015](structure.md#struct_015)

## COMB_009

`Parallel(until="first_done")` must start all of its children at the same time, and as soon as a child ends, however it ends, request a stop from the remaining children. It ends the same way as the first child that ended. It is for work where the whole ends when either part ends, such as reading and writing on one connection.

title: First done

level: MUST

## COMB_010

A group that receives a stop request must make the children that have not started yet `skipped`, pass the stop on to the running children, and wait for them to end. It ends `stopped` itself. However, if any child is `failed`, it ends `failed` (a failure takes precedence over a stop).

A stop request travels from a group to its children, and further down below them.

title: Groups and stop requests

level: MUST

## COMB_011

Modifiers are attached to workers as decorators and change how they are called. The modifiers of this version are the four `@repeat`, `@retry`, `@timeout` and `@optional`, plus `@service` (LIFE_010) and `@pinned` / `@isolated` (EXEC_003, EXEC_004).

Groups can also be given `repeat`, `retry`, `timeout` and `optional` with the argument `modifiers` at creation (for example `Sequence(modifiers=(repeat(every=5.0),))`). In that case, one round of the whole group corresponds to one round of calling a worker.

title: Modifiers

level: INFORMATIVE

## COMB_012

For a node with `@repeat(times=None, every=None, until=None)`, the skeleton must repeat the call. The skeleton owns the outside of the loop, and the worker only writes the work of one round.

- If `times` is given, it ends after that many rounds
- `until` is a function that receives the return value of each round, and it ends when that returns true
- If `every` is given, the interval between the starts of rounds is `every` seconds. If the previous round took longer than `every` seconds, the next round starts without waiting, and it does not call several times in a row to catch up. Waiting for the interval is released by a stop request
- It becomes `succeeded` if it ends by the given condition, and `stopped` if it ends by a stop request

If none is given, it repeats until a stop request. If `until` raises an exception, the node ends `failed`.

title: Repeat

level: MUST

## COMB_013

When one round of a `@repeat` node ends `failed`, the whole node must end `failed` without starting the next round. To call a failed round again, also attach `@retry`.

title: A failed round ends the repeat

level: MUST

## COMB_014

When one round of calling a node with `@retry(times, backoff=None)` ends `failed`, it must be called again up to `times` times. `backoff` is the number of seconds to wait before calling again, and the wait is released by a stop request. When the retries run out, the node becomes `failed` with the last failure. The exceptions of the failures before that also remain in the record (RESULT_005).

title: Retry

level: MUST

## COMB_015

When one round of calling a node with `@timeout(seconds)` goes over `seconds` seconds, a stop must be requested from that node, and it must be made `failed` with the exception `WorkerTimeout`. Since stopping is cooperative, if the call does not return even after the request, the node is handled as a node that did not stop (RESULT_004).

title: Timeout

level: MUST

## COMB_016

A node with `@optional` must be handled by its parent as `succeeded` even if it ends `failed`. The failure and the exception remain in the record (RESULT_005). It is for work that may fail, when the rest should continue without stopping.

title: Optional

level: MUST

## COMB_017

Modifiers must be applied, regardless of the order in which the decorators are stacked, from the inside in the order `timeout`, `retry`, `repeat`, `optional`. That is, `timeout` applies to one call, `retry` to calling it again, `repeat` to repeating a round including the retries, and `optional` to how it finally ends.

title: Order of modifiers

level: MUST
