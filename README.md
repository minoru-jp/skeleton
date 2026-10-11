<!-- Published from devdocs/canonical_documents/README.md sha256:214a60f73cc7f96f8d7dc6f8894b443e0b058b158f56bfc7ee104314cbf7941a. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# honehone

`honehone` is a library for writing **classes with work of a fixed shape**.

The shape (which workers run, in what order, arranged how) is declared with decorators by a skeleton class, and the content is filled in by an implementation class by overriding methods. When you pass an instance and start it, it runs on its own following the declared shape, and how to stop, cleanup, pausing and reports come with it.

## Writing the shape, filling in the content

For example, consider a tool that brings up a development environment. It starts the DB and the API in parallel, opens the browser once both are ready, then keeps watching, and on Ctrl+C cleans everything up and stops.

```python
import subprocess
import webbrowser
from abc import abstractmethod

import honehone
from honehone import Context, Sequence, Skeleton, repeat, service


class DevEnv(Skeleton):
    """The shape of bringing up a development environment. Implementation classes fill in the content."""

    main = Sequence()
    services = main.parallel()  # goes inside main, at this position

    @services
    @service
    @abstractmethod
    def database(self, ctx: Context) -> None: ...

    @services
    @service
    @abstractmethod
    def api(self, ctx: Context) -> None: ...

    @main
    def open_browser(self, ctx: Context) -> None: ...  # does nothing by default

    @main
    @repeat(every=1.0)
    def watch(self, ctx: Context) -> None: ...


class MyDevEnv(DevEnv):
    """The content for this project. No decorators."""

    def __init__(self, port: int) -> None:
        self.port = port  # __init__ only receives settings

    def database(self, ctx: Context) -> None:
        proc = subprocess.Popen(["postgres", "-D", "data"])
        ctx.on_stop(proc.terminate)
        ctx.ready()  # ready; it keeps running from here on
        proc.wait()

    def api(self, ctx: Context) -> None:
        proc = subprocess.Popen(["uvicorn", "app:app", "--port", str(self.port)])
        ctx.on_stop(proc.terminate)
        ctx.ready()
        proc.wait()

    def open_browser(self, ctx: Context) -> None:
        webbrowser.open(f"http://localhost:{self.port}")


def show(tag: str, *args: object, **kwargs: object) -> None:
    print(
        tag, *args, kwargs
    )  # the listener of reports; usable for progress displays or logs


result = honehone.run(MyDevEnv(port=8000), listener=show)  # stops on Ctrl+C
result.raise_if_failed()
```

What to notice when reading it is the difference between the roles of the two classes.

- `DevEnv` (the skeleton class) holds **only the shape**. What runs in what order is declared with decorators, and you can see the procedure by reading the class. Workers with `@abstractmethod` must be overridden by an implementation class before it can be created
- `MyDevEnv` (the implementation class) holds **only the content**. It uses no decorators and simply overrides methods

The same `DevEnv` can be used with different content in another project.

## What comes with the shape

Because the shape is declared, you get the following without writing them.

- **How to stop.** When a stop is requested with Ctrl+C or `stop()`, the watching stops, and the services stop one at a time in the reverse order in which they became ready (the API before the DB)
- **Cleanup.** `cleanup` always runs, whether the run succeeded, failed or was stopped
- **Pausing.** Since the skeleton owns the loops and the transitions between steps, it can stop at boundaries even if the workers do nothing to cooperate
- **Reports.** The state changes of each worker are sent, so a progress display or a log can be made by preparing one listener
- **Running while unfinished.** The default of a non-abstract worker does nothing, so you can run the shape first and fill in the content little by little

## What to know first

- **Only skeleton classes can define workers.** Only a class that inherits `Skeleton` directly can declare groups and workers. Implementation classes that inherit it only override the content and do not change the shape
- **One instance is one run.** To run it again, create the instance again
- **The instance is frozen while the body runs.** Attributes can be written only during `boot` and `cleanup`. Workers exchange values through a `Channel` or `Shared` prepared in `boot`
- **Stopping and pausing are cooperative.** The skeleton stops at boundaries, but it does not interrupt a call in progress. Workers that did not stop are reported
- Python `>=3.11` is required.

## Writing the shape

From here on, the tools for writing the shape are explained one by one.

### Groups and order

Groups are declared as class attributes and used as decorators as they are. A group that goes inside another group is made with the parent's `sequence()` / `parallel()`. The order within a group is the order of definition in the class body. The shape of the first example is the following tree.

```text
main (Sequence)
├── services (Parallel)
│   ├── database   @service
│   └── api        @service
├── open_browser
└── watch          @repeat(every=1.0)
```

There is only one group without a parent (the root). Errors in the shape (two roots, an empty group, an implementation class trying to change the shape, and so on) become errors when the class is defined, without waiting for the run.

### Combinations

The kind of a group is decided by the combination of how its children are arranged and how it completes.

| | `until="all"` (default) | `until="first_success"` | `until="first_done"` |
| --- | --- | --- | --- |
| `Sequence` | All, in order | Try in order until the first success | (not available) |
| `Parallel` | All, at the same time | First success wins; the rest are stopped | First to end wins; the rest are stopped |

Children that were stopped are not counted as failures. With `Parallel(lockstep=True)`, repeating workers advance in step, one round at a time.

### Modifiers

Modifiers can be attached to workers with decorators.

- `@repeat(times=, every=, until=)`: the skeleton repeats the call. The worker only writes one round and does not need to check for a stop
- `@retry(times, backoff=)`: calls again on failure
- `@timeout(seconds)`: limits the time of one call
- `@optional`: does not stop the whole on failure. The failure remains in the record
- `@service`: moves on once ready and keeps running until the body ends (tells it is ready with `ctx.ready()`)
- `@pinned` / `@isolated`: constraints on the thread it runs on (see below)

Modifiers apply, regardless of the order they are stacked in, from the inside in the order `timeout`, `retry`, `repeat`, `optional`.

### Preparation, cleanup and threads

Resources are prepared in `boot` and cleaned up in `cleanup`. A `cleanup` paired with a `boot`, as in `@cleanup(of=connect)`, runs only when that `boot` succeeded. Since `@boot` returns the function as it is, implementation classes can override the content of `boot` and `cleanup` as plain methods too. The `cleanup`s run in the reverse order of definition, all of them even if one fails.

```python
import sqlite3
from abc import abstractmethod

import honehone
from honehone import Context, Parallel, Skeleton, boot, cleanup, pinned


class Archiver(Skeleton):
    body = Parallel()

    @boot
    def connect(self, ctx: Context) -> None:
        # attributes can be written only during boot; resources are prepared here
        db = sqlite3.connect("archive.db")
        db.execute("CREATE TABLE IF NOT EXISTS lines (line TEXT)")
        self.db = honehone.ThreadBound(db)
        self.lines = honehone.Channel(str)

    @cleanup(of=connect)
    def disconnect(self, ctx: Context) -> None:  # runs only when connect succeeded
        self.db.get().close()

    @body
    @abstractmethod
    def collect(
        self, ctx: Context
    ) -> None: ...  # sends to self.lines and closes it at the end

    @body
    @pinned
    def store(self, ctx: Context) -> None:
        db = self.db.get()  # usable, since this runs on the home thread
        for line in self.lines.receive(ctx):
            db.execute("INSERT INTO lines VALUES (?)", (line,))
        db.commit()
```

Which thread a worker runs on is decided by the structure. What runs in order runs on the same thread as its parent, and the children of a `Parallel` run on threads of their own. On top of that, constraints can be attached to leaves.

- `@pinned`: always runs on the **home thread** (the thread `boot` ran on). Attach it to workers that use resources that cannot cross threads, such as an sqlite connection. If the resource is wrapped in `honehone.ThreadBound`, touching it from another thread is reported with an error
- `@isolated`: always runs on a thread of its own. Attached to work that might hang, it lets the run give up on it if it does not stop and move on to cleanup

## Running and operating

`honehone.run()` runs on the calling thread and waits until the run ends. For a small tool, this is enough. To operate it while it runs, receive the `Run` handle with `honehone.start()`. Nodes are referred to by name.

```python
import honehone
from honehone import Context, Parallel, Skeleton, repeat


class Ticker(Skeleton):
    clocks = Parallel()

    @clocks
    @repeat(every=0.1)
    def fast(self, ctx: Context) -> None:
        ctx.report("tick")

    @clocks
    @repeat(every=0.5)
    def slow(self, ctx: Context) -> None: ...


run = honehone.start(Ticker())
run.wait_until("fast", "running")
run.pause("fast")  # returns right after requesting; it stops at the next boundary
run.wait_until("fast", "paused")
run.resume("fast")
run.stop()
result = run.wait()
print(result.outcome, result.nodes["fast"].calls > 0)  # stopped True
```

| Operation | Content |
| --- | --- |
| `pause(name)` / `resume(name)` | Pause and resume. Without a name, the whole body |
| `stop()` | Stops the whole. Also wakes and stops what is paused |
| `wait(timeout)` | Waits for the run to end and returns the result |
| `wait_until(name, state, timeout)` | Waits until a node reaches the given state |
| `state(name)` | The current state of a node |

`pause()` returns right after making the request. A node goes through `pausing` and becomes `paused` at the next boundary (before the next round of a repetition, at a transition between steps, before children start). Only a service that keeps running after it is ready has no boundaries, so to pause it, call `ctx.checkpoint()` inside the worker.

## Results and reports

`run()` and `Run.wait()` raise no exception and always return a result `Result`. `result.outcome` is one of `"completed"`, `"failed"` and `"stopped"`, and a failure takes precedence over a stop. With `result.nodes["name"]` you can see the state, exceptions, number of calls, last return value and duration of each node. To handle a failure as an exception, call `result.raise_if_failed()`, which raises `SkeletonFailed` (an `ExceptionGroup`).

When you pass a `listener` to `run()` or `start()`, the events of the run are reported. Reports go through the sending point of [fport](https://github.com/minoru-jp/fport), so a failing listener does not affect the run. Workers can also send their own progress with `ctx.report()`.

## Relation to gpframe and fport

`honehone` works on the same principles as [gpframe](https://github.com/minoru-jp/gpframe). A stop is a cooperative request that travels from top to bottom, failures are gathered upward, and work that did not stop is reported rather than stopped forcibly. For passing values between workers, gpframe's `Channel` and `Shared` are used as they are. However, gpframe types do not appear on the public surface of `honehone`, and people writing skeletons can use it without knowing gpframe.

The choice between them is about **when the structure is decided**. Something whose structure is decided at run time, such as a server whose workers come and go per connection or request, is written with gpframe. Something whose procedure or shape is decided when the class is written is written with `honehone`. The two can be combined; to put a skeleton inside a gpframe tree, use `s.spawn(honehone.gpframe.routine, obj)`. For example, a server can start "the procedure for one connection" as a skeleton for each connection.

## Examples

[`examples/`](https://github.com/minoru-jp/skeleton/tree/main/examples) holds examples that each show one property particular to `honehone`. All of them run with the standard library only, and can be run with `python examples/<name>.py`.

- [`cooking.py`](https://github.com/minoru-jp/skeleton/blob/main/examples/cooking.py): **Reusing a shape, and pausing.** It writes one recipe shape (advance a pasta pot and a sauce pot in parallel, then plate), and carbonara and arrabbiata fill in only its content. Since the work calls `ctx.checkpoint()` along the way, no pot advances while you are away from the kitchen after `pause()`, and they continue from where they were after `resume()`. The listener of reports is the cooking display as it is.
- [`instrument.py`](https://github.com/minoru-jp/skeleton/blob/main/examples/instrument.py): **Services and the order of cleanup.** It connects to a device, measures while a service watches the temperature, records to sqlite from a `@pinned` worker, and finally disconnects. Whether it ends normally, fails by overheating, or is stopped with Ctrl+C, the order is kept: close the recording, stop the watching, then disconnect. Implementation classes decide only which device to use.
- [`console.py`](https://github.com/minoru-jp/skeleton/blob/main/examples/console.py): **A CLI as a control panel.** It operates work running in the background (a simulated backup) with `status` / `pause` / `resume` / `quit`. The decision to stop on Ctrl+C belongs to the managing side (the main thread that called `honehone.run()`), and the input is read by an `@isolated` worker on another thread. Even when it is going to stop in the middle of input, the half-typed line is not erased, and it stops where Enter returns. The commands only call the handle from `honehone.control(self)`.

## Installation

```bash
pip install "git+https://github.com/minoru-jp/skeleton"
```

[gpframe](https://github.com/minoru-jp/gpframe) and [fport](https://github.com/minoru-jp/fport) are installed as dependencies.

## Development

The tools used for development are gathered in the `dev` extra. Every check is run with `tools/check.py`, and CI and releases use the same one.

```console
pip install -e ".[dev]"
python tools/check.py            # every check
python tools/check.py lint tests # only the chosen checks
```

Rules of behavior are written in the canonical sources (in Japanese) in `devdocs/canonical_sources/`, and `python scripts/render_devdocs.py` generates the canonical documents. The English published documents are translations of the canonical documents.

## Related documents

- [STATUS.md](https://github.com/minoru-jp/skeleton/blob/main/STATUS.md): development stage, scope, what is decided, and future direction
- [docs/specification/INDEX.md](https://github.com/minoru-jp/skeleton/blob/main/docs/specification/INDEX.md): rules of behavior (Specification)
- [CHANGELOG.md](https://github.com/minoru-jp/skeleton/blob/main/CHANGELOG.md): changes in each version
