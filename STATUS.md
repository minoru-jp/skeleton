<!-- Published from devdocs/canonical_documents/STATUS.md sha256:477e5bb90f33b610266fa5adf52c708947e16910e32c0227e9ad4bc8d93e45c3. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# honehone Project Status

This document describes the current state of `honehone` and its future direction as seen from now.
Changes that actually happened in the past belong to the CHANGELOG.

## STATUS_001

The current development stage is Alpha. The current version is `2.0.0`, the first version rebuilt from the design. It is not compatible with the old implementation `1.0.0`.

title: Development stage

## STATUS_002

The supported Python version range is `>=3.11`, because `SkeletonFailed` uses the standard `ExceptionGroup`.

There are the following two runtime dependencies, and both are intended. This is because the rebuild hands passing data and reporting, which the old implementation held by itself, to a dedicated package each.

- `gpframe`: borrows the tools for passing data between workers (`Channel`, `Shared`), and joins a gpframe tree with `honehone.gpframe`. Starting threads and propagating stop requests are owned by honehone itself, on the same principles as gpframe (RESULT_010)
- `fport`: the sending point for the reports of a run

title: Supported Python and dependencies

## STATUS_003

The following is provided.

- Declaring the shape with a skeleton class that inherits `Skeleton` directly, and overriding the content with an implementation class that inherits it. Errors in the shape are detected when the class is defined
- The groups `Sequence` / `Parallel`, the completion `until` (`all`, `first_success`, `first_done`), and `Parallel(lockstep=True)`
- The modifiers `@repeat`, `@retry`, `@timeout`, `@optional`, `@service`, `@pinned` and `@isolated`
- Using the standard `abc.abstractmethod` to require overriding
- The flow of `boot`, body and `cleanup`, `cleanup` paired with a `boot`, and freezing during the body
- Assigning threads as decided by the structure, and binding resources with `ThreadBound`
- `honehone.run()` (which turns Ctrl+C into a stop request), `honehone.start()` with the `Run` handle (`pause`, `resume`, `stop`, `wait`, `wait_until`, `state`), and `honehone.control()`
- The result `Result`, which contains no gpframe types, and reports through fport
- `honehone.gpframe.routine` for joining a gpframe tree

Execution covers threads (the synchronous version) only.

title: Scope

## STATUS_004

The Specification is the authoritative source for rules of behavior, placed in `devdocs/canonical_sources/specification/`. The tests are split into a file per Specification document (`tests/test_structure.py`, `test_combinators.py`, `test_lifecycle.py`, `test_execution.py`, `test_control.py`, `test_result_report.py`, `test_gpframe.py`, and `test_cross_cutting.py` for rules spanning documents), and the name of each test includes the identifier of the rule it checks. The examples are checked by `tests/test_examples.py`. The combination with gpframe is checked using gpframe itself.

`tests/test_devdocs.py` checks that the canonical documents match the ones generated again from the canonical sources, that the code examples of the README actually work, and that the version injected into the documents matches `pyproject.toml`.

pytest treats every warning as an error.

title: Specification and tests

## STATUS_005

The relation to the old implementation is as follows. The implementation of the old one is not carried over; only some of its ideas are.

- The old EventHandler served both for observation and for changing behavior (such as Redo when `on_end` was true). In the new design, observation goes to fport reports and changing behavior to overriding methods
- The old Redo became `@repeat`, with the skeleton owning the outside of the loop
- The old two-level pause (a super pause from the driver and the Routine's own pause) was reorganized into pausing at boundaries (`Run.pause()`) and the worker's own `ctx.checkpoint()`. Since the skeleton owns the loops and the transitions between steps, nodes stop at boundaries without the worker's cooperation
- The old `Context.field` became attributes of the instance, prepared in `boot` and frozen
- The old code generation mode and trial execution (`exec`) are not carried over, because the shape is the declaration itself and does not need to be generated

title: Relation to the old implementation

## STATUS_006

`examples/` holds three examples. All of them run with the standard library only.

- `cooking.py`: a cooking timer. It shows two recipes reusing the shape of one recipe, pausing in the middle of work with `ctx.checkpoint()`, and a display made by the listener of reports
- `instrument.py`: controlling a measuring instrument. It shows a service, a `cleanup` paired with a `boot`, recording to sqlite with `@pinned` and `ThreadBound`, and that the order of cleanup is kept whether the run ends normally, fails, or is stopped with Ctrl+C
- `console.py`: a CLI as a control panel. It operates work running in the background with commands accepted by an input worker. It separates the managing side that receives Ctrl+C (the home thread) from the input worker placed on another thread with `@isolated`

`tests/test_examples.py` checks that the examples work as written. For the cooking timer it checks that nothing advances while paused, and for the instrument that, even when stopped with Ctrl+C, it closes the recording and stops the watching before disconnecting. For the CLI, it also runs the example itself on a pseudo terminal and checks that it ends on Ctrl+C while waiting for input.

Writing two of the examples revealed the following about making a listener of reports. A report arrives right there, on the thread of the worker that sent it, so a listener that receives reports from several workers and displays them needs to take a lock itself so that the output does not get mixed. The listener of every example does so.

Writing the CLI example led to the following view of waiting for input. `input()` cannot release its wait on a stop request, but while input is being typed it is the person's turn, so waiting until the line is finished is the natural behavior. This is a plain instance of "a call in progress is not interrupted" (CTRL_006), and the library needs no special handling. The `KeyboardInterrupt` of Ctrl+C appears only on the main thread, but if the managing side that receives Ctrl+C (the home thread) is separated from the input worker, no `KeyboardInterrupt` appears, and Ctrl+C takes effect at a boundary as a stop request. Right after `input()` returns, the input worker checks `ctx.stopping` and does not run a line typed while stopping.

title: Examples

## STATUS_007

The distribution name and the import name are `honehone` (骨々, "bones"). The GitHub repository keeps the name `skeleton`, inherited from the old implementation.

The old name `skeleton` cannot be used as the distribution name, because another project already uses it on PyPI. PyPI also refuses, as "too similar", a name that matches an existing project after removing `.` `_` `-` and replacing `l` and `i` with `1` and `o` with `0`. The import name was made the same as the distribution name because `skeleton` is a common name that easily collides with the import names of other packages. The name of the base class `Skeleton`, and calling it a "skeleton" in the documents, are kept as words for the idea behind this mechanism.

title: Name

## STATUS_008

Every check is gathered in `tools/check.py`. There are seven: `docs` (the canonical documents are up to date, and the English published documents do not disagree with the canonical documents), `format`, `lint`, `types`, `types-tests`, `tests` and `dist` (build an sdist and a wheel, `twine check --strict`, inspect their contents, and confirm that the wheel works when installed with its dependencies in a clean venv). `python tools/check.py` runs all of them, and listing names runs only some. The versions of the tools used for checking are fixed by the extras in `pyproject.toml` (`dev` includes all of them).

GitHub Actions consists of two workflows.

- `ci.yml`: on every push and pull request, runs `python tools/check.py` on Python 3.11, 3.12 and 3.13
- `release.yml`: when a Release is published on GitHub, it first calls `ci.yml` as it is and passes the same checks. It then builds and checks the distributions with `python tools/check.py dist --tag <tag>` (also confirming that the tag matches `v<version>`), and publishes them with PyPI Trusted Publishing. No API token is used

For Trusted Publishing, this repository (`minoru-jp/skeleton`), the workflow `release.yml` and the environment `pypi` must be registered on PyPI as a Trusted Publisher of the project `honehone`.

title: Checks, CI and release

## STATUS_009

Static analysis is clean for `ruff format --check .`, `ruff check .`, and both BasedPyright configurations.

- Ruff is pinned to 0.16.10 with Python 3.11 as the target version. The generated canonical documents are excluded from formatting.
- BasedPyright 1.40.2 checks `src/honehone`, `scripts` and `tools` in `recommended` mode with 0 errors / 0 warnings. Only two diagnostics are disabled: `reportImplicitOverride`, because `typing.override` is available from Python 3.12; and `reportPrivateUsage`, because the package handles internal state across its own modules.
- `tests/pyrightconfig.json` checks the tests, the examples and the canonical sources of the documents as user code in `standard` mode, with 0 errors / 0 warnings. The examples are checked as user code so as not to demand rules meant for libraries (such as type annotations on class attributes) from the skeleton classes users write.

Explicit `Any` remains only as the argument type of the function passed to `repeat(until=...)`, so that a `lambda value: value >= 3` written by users passes type checking. Local suppressions needed to keep the runtime meaning (`pyright: ignore`) have their reasons written next to them.

Passing the type checker revealed that overriding a `@boot` method in an implementation class was reported by type checkers as an incompatible override, because `@boot` returned a descriptor. `@boot` and `@cleanup` were changed to return the function as it is, and pairing with a `boot` is now written as `@cleanup(of=connect)` (LIFE_008).

title: Static analysis

## STATUS_010

The English published documents are made by translating the Japanese canonical documents. README, STATUS and CHANGELOG are placed at the root of the repository, and the Specification in `docs/specification/`. The translation itself is not automated; `scripts/published_docs.py` checks the following mechanically (included in `tools/check.py docs`).

- Every canonical document has a published document, and there are no extra published documents
- The stamp at the top of each published document matches the SHA-256 of the current canonical document. When a canonical document changes, the check fails until it is re-translated and stamped again with `python scripts/published_docs.py stamp <published document>`
- The Python code examples are the same as in the canonical document, apart from comments and docstrings
- The rule headings of the Specification are the same, in the same order and number
- The targets of links exist

title: Published documents

## NOTICE_001

Making an asynchronous version on top of gpframe.aio, as an independent line that shares no types with the synchronous version, is being considered.

title: Async version

kind: General

condition: After the synchronous API has settled.

## NOTICE_002

An undo paired with a step (`.undo`, compensation) is being considered. When a later step fails, the completed steps are undone in reverse order. It needs to be decided up to which point the succeeded steps are undone, and how to report a failure of the undo itself.

title: Undo (compensation)

kind: General

condition: After the need is confirmed by actual uses.

## NOTICE_003

A way for a later worker in the body to receive the return value of an earlier worker is being considered. Currently, passing data within the body goes through a `Channel` / `Shared` prepared in `boot`, and from outside, the last return value can be seen with `Result.nodes[...].value`.

title: Passing results between workers

kind: General

condition: After the need is confirmed by actual uses.

## NOTICE_004

`Each`, which runs the same procedure in parallel for each item (with a limit on concurrency), and `Choice`, which selects only one child by a condition, are being considered. In the CLI example, dispatching commands was written plainly with a dictionary inside one worker and did not need to be expressed as a shape. `Choice` is thought to be needed where what is selected is itself a procedure with its own way to stop and its own cleanup.

title: Each and Choice

kind: General

condition: After the need is confirmed by actual uses.

## NOTICE_005

Whether the clocks of `@timeout` and `@repeat(every=)` advance or stop while paused has not been decided yet. In the current implementation, the clocks advance while paused.

title: Clocks while paused

kind: General

condition: After the need is confirmed by actual uses.

## NOTICE_006

Policies for restarting failed children (corresponding to Erlang supervisor strategies such as one_for_one and one_for_all) are not covered.

title: No restart strategies

kind: General

condition: Until the need is confirmed by actual uses.

## NOTICE_007

As validation (dogfooding), rewriting gpframe's `tools/devwatch.py` as a skeleton and comparing it with the version written directly with gpframe is planned. It will check whether the shape reads as a declaration and whether the wiring code disappears.

title: Dogfooding plan

kind: General

condition: After the synchronous API has settled.

## NOTICE_008

Following gpframe and fport, placing the promises kept by tests in `contract/` as `shikumi-contrace` contracts, and the shape of the public API as Protocols, is planned.

title: Contracts

kind: General

condition: After the synchronous API has settled.
