<!-- Published from devdocs/canonical_documents/specification/report.md sha256:abc070299c1b8f37256b60e4e5f76f57c2b5823b7b6646d72feb2d40520f6734. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Report

Rules on the sending point of reports, connecting the listener, and the vocabulary and order of reports.

## REPORT_001

Events of a run must be reported through `Port`, the sending point of fport. Reporting does not change how the run behaves. An exception raised by the listener does not reach the run, and the run proceeds the same way whether or not a listener is connected. The roles are separated: observation is done by reports, and changing behavior by overriding methods.

title: Reporting does not change behavior

level: MUST

## REPORT_002

The listener `listener` passed to `honehone.run()`, `honehone.start()` or `honehone.gpframe.routine` must be connected before the first report and disconnected after the last report. Reports are never missed by connecting in the middle of a run.

title: Connecting the listener

level: MUST

related: [CTRL_001](control.md#ctrl_001), [CTRL_002](control.md#ctrl_002), [CTRL_014](control.md#ctrl_014)

## REPORT_003

The reports sent by the skeleton must be the following. The listener receives them in the form `listener(tag, *args, **kwargs)`, as fport promises.

| Tag | Arguments | When |
| --- | --- | --- |
| `run.started` | None | When the run starts |
| `node.changed` | `name=`, `path=`, `state=`, `error=` | Every time the state of a node changes. `error` is the exception when `failed`, otherwise `None` |
| `node.called` | `name=`, `path=`, `count=` | Every time one round of calling a worker ends. `count` is the number of calls so far |
| `run.finished` | `result=` | When the result is settled. The last report |

title: Report vocabulary

level: MUST

related: [RESULT_002](result.md#result_002)

## REPORT_004

The vocabulary of reports (tags, argument names, state names) is a public promise. Changes must be treated as backward-incompatible changes, because listeners such as progress displays and log screens depend on this vocabulary.

title: The vocabulary is a public contract

level: MUST

## REPORT_005

The reports of one node must arrive in the order its state changed. The order of reports between nodes running on different threads is not defined. A report is handed to the listener right there, on the thread that sent it (as fport promises).

title: Order of reports

level: MUST

## REPORT_006

A worker can send its own reports with `ctx.report(*args, **kwargs)`. Such a report must have the tag `worker.report`, put `name` as the first positional argument, and then send the arguments passed to `ctx.report()` as they are. It is for telling the listener information only the worker knows, such as the ratio of progress.

title: Reports from workers

level: MUST

## REPORT_007

Reports and `Run.state()` are two views of the same state changes. Reports push changes out, and `Run.state()` pulls the current state. Seen from either side, the order of state changes is the same.

title: Reports and Run.state

level: INFORMATIVE
