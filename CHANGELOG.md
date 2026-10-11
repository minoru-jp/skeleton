<!-- Published from devdocs/canonical_documents/CHANGELOG.md sha256:2dd9c991d1679ac8f0f4c84e7b6564f80cd15a4f16d66697da3415ddb16c4966. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# honehone Changelog

Records the changes in each version of `honehone`. The version before `2.0.0` (`1.0.0`) is the old implementation from before the rebuild, then named `skeleton`, and its history is not included in this document.

## V2_0_0

**This version was rebuilt from the design, and it has no backward compatibility at all with `1.0.0`.** None of the `1.0.0` API remains, and no means of migration is provided.

`1.0.0` wrapped one Routine and took on events, state, logging, pausing, reporting results, and even code generation and trial execution all at once, and the implementation could not keep up. Since then, passing data and the principles of execution were split out into gpframe, and the sending point for reports into fport. This version returns to the origin of the name, "a block with default behavior, where you override only the parts you want to change", and rebuilds it as a pair of a skeleton class that declares the shape with decorators and an implementation class that overrides the content.

version: 2.0.0

Added:

- Added skeleton classes that inherit `Skeleton` directly and declare the shape, and implementation classes that inherit them and override the content. Errors in the shape are reported with `SkeletonDefinitionError` when the class is defined. The standard `abc.abstractmethod` is used to require overriding.
- Added the groups `Sequence` / `Parallel`, the completion `until` (`all`, `first_success`, `first_done`), and `Parallel(lockstep=True)`.
- Added the modifiers `@repeat`, `@retry`, `@timeout`, `@optional`, `@service`, `@pinned` and `@isolated`. Groups can also be given `repeat`, `retry`, `timeout` and `optional` with `modifiers`.
- Added the flow of `boot`, body and `cleanup`, `cleanup` paired with a `boot`, and freezing the instance during the body.
- Added `@service`, which keeps running after it is ready, and stopping services in the reverse order in which they became ready.
- Added assigning threads as decided by the structure, and `ThreadBound`, which binds a resource to the thread that created it.
- Added `honehone.run()`, `honehone.start()`, `honehone.control()`, and the `Run` handle, which can pause at boundaries. `run()` turns Ctrl+C on the main thread into a stop request.
- Added the `Context` received by workers (`stopping`, `wait_stop()`, `on_stop()`, `checkpoint()`, `ready()`, `report()`).
- Added the result `Result`, which contains no gpframe types, the record `NodeRecord`, `SkeletonFailed` (an `ExceptionGroup`) gathering failures, and the warning `SkeletonWarning` for nodes that did not stop.
- Added reports through the sending point of fport (`run.started`, `node.changed`, `node.called`, `worker.report`, `run.finished`).
- Re-exported gpframe's `Channel` and `Shared` as `honehone.Channel` and `honehone.Shared`.
- Added `honehone.gpframe.routine` for joining a gpframe tree.
- Added the rules of behavior as the Specification (7 documents: Structure, Combinators, Lifecycle, Execution, Control, Result, Report). The tests are split into a file per document, and the name of each test includes the identifier of the rule it checks.
- Added two examples to `examples/`: the cooking timer `cooking.py`, which shows reusing a shape and pausing, and the instrument control `instrument.py`, which shows services and the order of cleanup.
- Added `examples/console.py`, an example of a CLI as a control panel that operates work running in the background with commands accepted by an input worker on another thread.
- Added `tools/check.py`, which gathers every check, and the GitHub Actions CI (`ci.yml`) and release (`release.yml`) workflows. A release passes the same checks as CI and is then published with PyPI Trusted Publishing.
- Added English published documents at the root of the repository (README, STATUS, CHANGELOG) and in `docs/specification/`. `scripts/published_docs.py` checks that the translations do not disagree with the canonical documents.

Changed:

- Changed the distribution name and the import name from `skeleton` to `honehone`, because `skeleton` is used by another project on PyPI. The GitHub repository keeps the name `skeleton`.
- Changed the supported Python to `>=3.11`.
- Added `gpframe` and `fport` as runtime dependencies.

Removed:

- Removed `make_skeleton_handle()`, `make_trial_skeleton_handle()` and the whole API of the handles.
- Removed the event handlers (`on_start` / `on_redo` / `on_end` / `on_cancel` / `on_close`). Observation is done with reports, and changing behavior by overriding methods.
- Removed the three-channel messages (`environment` / `event_message` / `routine_message`) and `Context.field`. Settings go through `__init__`, and sharing through a `Channel` / `Shared` prepared in `boot`.
- Removed the signals (`Redo` / `Graceful` / `Resigned`). Repetition is `@repeat`, and how a run ends is expressed by node states and the `Result`.
- Removed the code generation mode (`CodeTemplate`, `LinearLoop`) and trial execution.
