# Loop Engine

A configurable async/sync loop engine that dynamically builds and runs event-driven “circuits” from user-defined actions and lifecycle handlers.

## 🔍 What It Does

- Defines a set of loop lifecycle phases (`on_start`, `on_pause`, `on_resume`, `on_end`, `on_stop`, `on_closed`, `on_result`, 何とか何とかぐらいｗｗｗ).
- Allows registering handlers for each phase or for interrupts (`pause`/`resume`) before starting the loop.
- Enables appending named “actions” that will execute in a linear sequence within the loop circuit.
- Dynamically generates and executes a Python function (“circuit”) that runs all registered actions in order, handling pauses, resumes, exceptions, and cleanup.
- Provides a handle to start, stop, pause, resume the loop, and inspect the loop’s state/result.

## Installation

Simply include `loop_engine.py` in your project. It has no external dependencies beyond Python 3.7+.

```bash
cp loop_engine.py your_project/
```

多分PIPかなｗｗｗｗｗｗｗｗｗｗｗｗｗ
> pip Uploadするぜ！！！！

```
python -m pip install skeleton
```

## How to Use
Import and configure the loop engine:

```python
from loop_engine import make_loop_engine_handle

# Create a loop handle with an optional name and logger
loop = make_loop_engine_handle(role="my_loop")
```

### 1. Register phase handlers
```python
def on_start(ctx):
    print("Loop started.")

def on_end(ctx):
    print("Loop ended normally.")

loop.set_on_start(on_start)
loop.set_on_end(on_end)
```

### 2. Register interrupt handlers (for pause/resume)
```python
def before_pause(ctx):
    print("Pausing...")

def after_resume(ctx):
    print("Resuming...")

loop.set_on_pause(before_pause, notify_ctx=True)
loop.set_on_resume(after_resume, notify_ctx=True)
```

### 3. Append actions
Actions run in a predefined order inside the circuit:
```python
def action_one(ctx):
    print("Action 1")
    return 1

async def action_two(ctx):
    print("Action 2 (async)")
    await asyncio.sleep(0.5)
    return 2

loop.append_action("act1", action_one, notify_ctx=True)
loop.append_action("act2", action_two, notify_ctx=True)
```

### 4. Optionally customize loop/circuit context

```python
loop.set_loop_context_builder_factory(lambda iface: (lambda evt, c: c, {}))
loop.set_circuit_context_builder_factory(lambda iface, lc: (lambda evt: lc, {}))
```

### 5. Start and control the loop

```python
# Start loop running an empty circuit—the engine will execute actions
loop.start(circuit=lambda ctx_upd, ctx, result_bridge, pauser: None)

# Pause or resume from another coroutine
loop.pause()
await asyncio.sleep(2)
loop.resume()

# Stopping the loop
loop.stop()
```

### 6. Inspect status & results
```python
if loop.task_is_running:
    print("Loop is running")

if loop.is_closed:
    print("Loop finished with result:", loop.result)
    if loop.exception:
        print("Loop raised:", loop.exception)
```

### Final Example ラセンガァァァン！
```python
import asyncio
from loop_engine import make_loop_engine_handle

async def main():
    loop = make_loop_engine_handle()

    loop.set_on_start(lambda ctx: print("Starting"))
    loop.set_on_end(lambda ctx: print("Finished successfully"))
    loop.set_on_handler_exception(lambda ctx: print("Handler error"))
    loop.set_on_circuit_exception(lambda ctx: print("Circuit error"))

    loop.set_on_pause(lambda ctx: print("Pausing loop"), notify_ctx=True)
    loop.set_on_resume(lambda ctx: print("Resuming loop"), notify_ctx=True)

    loop.append_action("a1", lambda ctx: print("First"))
    loop.append_action("a2", lambda ctx: print("Second"))

    loop.start(lambda *args: None)

    # simulate pause/resume
    await asyncio.sleep(0.1)
    loop.pause()
    await asyncio.sleep(1)
    loop.resume()

    # wait and stop
    await asyncio.sleep(0.5)
    loop.stop()
    await asyncio.sleep(0.1)

    print("Final state:", loop.current_mode, "Result:", loop.result)

asyncio.run(main())
```

🧰 API Overview
- `make_loop_engine_handle(role:str, logger:Logger=None)` → returns a Handle object.
- Handle methods:
    - `set_on_start(on_start_fn)`
    - `set_on_pause(on_pause_fn, notify_ctx:bool)`
    - `set_on_resume(on_resume_fn, notify_ctx:bool)`
    - `set_on_end(on_end_fn)`
    - `set_on_stop(on_stop_fn)`
    - `set_on_closed(on_closed_fn)`
    - `set_on_result(on_result_fn)`
    - `set_on_handler_exception(on_handler_exception_fn)`
    - `set_on_circuit_exception(on_circuit_exception_fn)`
    - `append_action(name:str, fn:callable, notify_ctx:bool=True)`
    - `set_loop_context_builder_factory(fn)`
    - `set_circuit_context_builder_factory(fn)`
    - `start(circuit_fn)` → schedules the loop (async circuit) and transitions state.
    - `stop()` → cancels the running loop.
    - `pause()`, `resume()` → signal pausing/resuming mid-run.
- Handle properties:
    - `task_is_running`, `is_active`, `is_closed`, `current_mode`, `pause_pending`, `resume_pending`
    - `result`, `exception`, `nested_exception`, `last_event`, `last_result`