"""honehone: a library for writing classes whose processing has a fixed shape.

The shape (which workers run, in what order, and side by side how) is declared with
decorators by a skeleton class that inherits `Skeleton` directly, and the content is
filled in by implementation classes that inherit it and override its methods.

```python
import honehone
from honehone import Context, Sequence, Skeleton


class Greeting(Skeleton):
    main = Sequence()

    @main
    def hello(self, ctx: Context) -> str:
        return "hello"


print(honehone.run(Greeting()).outcome)  # completed
```
"""

from gpframe import Channel, Shared

from honehone._define import (
    Group,
    Modifier,
    Parallel,
    Sequence,
    Skeleton,
    boot,
    cleanup,
    isolated,
    optional,
    pinned,
    repeat,
    retry,
    service,
    timeout,
)
from honehone._engine import Context, Run, StopHandle, ThreadBound, control, run, start
from honehone._errors import (
    FrozenSkeletonError,
    SkeletonDefinitionError,
    SkeletonError,
    SkeletonFailed,
    SkeletonStateError,
    SkeletonWarning,
    ThreadAffinityError,
    WorkerTimeout,
)
from honehone._result import NodeRecord, NodeState, Outcome, Result

__version__ = "2.0.0"

__all__ = (
    "Channel",
    "Context",
    "FrozenSkeletonError",
    "Group",
    "Modifier",
    "NodeRecord",
    "NodeState",
    "Outcome",
    "Parallel",
    "Result",
    "Run",
    "Sequence",
    "Shared",
    "Skeleton",
    "SkeletonDefinitionError",
    "SkeletonError",
    "SkeletonFailed",
    "SkeletonStateError",
    "SkeletonWarning",
    "StopHandle",
    "ThreadAffinityError",
    "ThreadBound",
    "WorkerTimeout",
    "__version__",
    "boot",
    "cleanup",
    "control",
    "isolated",
    "optional",
    "pinned",
    "repeat",
    "retry",
    "run",
    "service",
    "start",
    "timeout",
)
