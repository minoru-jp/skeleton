"""A cooking timer: reusing a shape, pausing, and a display made from reports.

`PastaRecipe` holds only the shape of a recipe: "cook the pasta pot and the sauce pot
side by side, then toss and plate". Carbonara and Arrabbiata reuse that shape and fill
in only the content. The recipe becomes the class itself, and both recipes can be
stopped and paused in the same way.

    python examples/cooking.py

To finish the example quickly, a minute is counted as `MINUTE` seconds (0.02 s).
"""

from __future__ import annotations

import threading
import time
from abc import abstractmethod
from collections.abc import Callable

import honehone
from honehone import Context, Sequence, Skeleton

MINUTE = 0.02
"""How many seconds count as one minute."""


class PastaRecipe(Skeleton):
    """The shape of a recipe: the pasta and sauce pots side by side, then toss and plate.

    ```text
    main (Sequence)
    ├── pots (Parallel)
    │   ├── pasta (Sequence): boil_water → boil_pasta
    │   └── sauce (Sequence): make_sauce
    ├── toss
    └── plate
    ```
    """

    pasta_minutes: int = 8
    """Minutes to boil the pasta. Implementation classes can change it."""

    main = Sequence()
    pots = main.parallel()
    pasta = pots.sequence()

    @pasta
    def boil_water(self, ctx: Context) -> None:
        self.cook(ctx, "boil the water", 6)

    @pasta
    def boil_pasta(self, ctx: Context) -> None:
        self.cook(ctx, "boil the pasta", self.pasta_minutes)

    sauce = pots.sequence()

    @sauce
    @abstractmethod
    def make_sauce(self, ctx: Context) -> None:
        """Each recipe writes how to make its sauce in its implementation class."""

    @main
    def toss(self, ctx: Context) -> None:
        self.cook(ctx, "toss with the sauce", 1)

    @main
    def plate(self, ctx: Context) -> None:
        self.cook(ctx, "plate", 1)

    def cook(self, ctx: Context, what: str, minutes: int) -> None:
        """A task taking `minutes` minutes. Makes a boundary every minute and reports the time left.

        Since `ctx.checkpoint()` is called at each boundary, a pause request stops the
        task at the end of the current minute, even in the middle of it. Time does not
        advance while paused.
        """
        for left in range(minutes, 0, -1):
            ctx.checkpoint()
            ctx.report(what, left, minutes)
            if ctx.wait_stop(MINUTE):
                return
        ctx.report(what, 0, minutes)


class Carbonara(PastaRecipe):
    """Carbonara. The sauce is quick and waits for the pasta to be done."""

    def make_sauce(self, ctx: Context) -> None:
        self.cook(ctx, "fry the guanciale", 5)
        self.cook(ctx, "mix the eggs and cheese", 2)


class Arrabbiata(PastaRecipe):
    """Arrabbiata. The pasta is boiled a little firm while the sauce simmers."""

    pasta_minutes = 7

    def make_sauce(self, ctx: Context) -> None:
        self.cook(ctx, "fry the garlic and chili", 2)
        self.cook(ctx, "simmer the tomatoes", 12)


class Kitchen:
    """The listener of reports. Shows the start and end of tasks, pausing and resuming.

    A report arrives right there, on the thread of the worker that sent it (a promise
    of fport). The two pots run on separate threads, so the listener takes a lock so
    that the output does not get mixed.
    """

    def __init__(self, out: Callable[[str], object] = print) -> None:
        self._out: Callable[[str], object] = out
        self._away: bool = False
        self._lock: threading.Lock = threading.Lock()

    def __call__(self, tag: str, *args: object, **kwargs: object) -> None:
        with self._lock:
            self._show(tag, args, kwargs)

    def _show(
        self, tag: str, args: tuple[object, ...], kwargs: dict[str, object]
    ) -> None:
        if tag == "worker.report":
            _, what, left, minutes = args
            if left == minutes:
                _ = self._out(f"  {what} ({minutes} min)")
            elif left == 0:
                _ = self._out(f"  {what}: done")
        elif tag == "node.changed" and kwargs["name"] == "main":
            state = kwargs["state"]
            if state == "paused":
                self._away = True
                _ = self._out("  -- leaving the kitchen --")
            elif state == "running" and self._away:
                self._away = False
                _ = self._out("  -- back in the kitchen --")


def main() -> None:
    kitchen = Kitchen()

    print("Carbonara")
    result = honehone.run(Carbonara(), listener=kitchen)
    print(f"  => {result.outcome}")

    print("Arrabbiata (leaving the kitchen midway)")
    run = honehone.start(Arrabbiata(), listener=kitchen)
    time.sleep(4 * MINUTE)
    run.pause()  # every pot stops once its current minute ends
    _ = run.wait_until("main", "paused", timeout=5)
    time.sleep(10 * MINUTE)  # no pot advances while we are away
    run.resume()
    result = run.wait()
    assert result is not None
    print(f"  => {result.outcome}")


if __name__ == "__main__":
    main()
