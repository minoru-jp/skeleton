"""A CLI as a control panel: a managing side and an input worker operate background work.

`ControlPanel` has the shape "an input worker accepts commands while the work goes on
in the background". What the work is, an implementation class decides (here, a backup).

    python examples/console.py

    > status     the state and progress of the work
    > pause      stop the work at a boundary
    > resume     resume it
    > quit       finish (Ctrl+D also finishes)

How the roles are split:

- **The managing side** is the main thread that called `honehone.run()` (the home
  thread). Ctrl+C arrives here and becomes a stop request.
- **The input worker** is placed on another thread with `@isolated`. Even if a stop is
  requested while `input()` is waiting, a half-typed line is not discarded; the worker
  stops where Enter returns (a boundary). While input is being typed it is the
  person's turn, so waiting is the natural behavior.

The commands only use the Run handle taken out with `honehone.control(self)`.
"""

from __future__ import annotations

import threading
from abc import abstractmethod
from collections.abc import Callable

import honehone
from honehone import Context, Parallel, Shared, Skeleton, isolated, repeat

INTERVAL = 0.1
"""The interval between rounds of the work, in seconds."""


class ControlPanel(Skeleton):
    """The shape where an input worker accepts commands while the work goes on.

    ```text
    main (Parallel, until="first_done")  when either ends, the other is stopped
    ├── job      @repeat     advances the work one round at a time; True when done
    └── console  @isolated   reads input and runs commands; ends on quit
    ```
    """

    def __init__(
        self,
        read: Callable[[str], str] = input,
        out: Callable[[str], object] = print,
    ) -> None:
        self.read = read
        self.out = out
        self.output_lock = threading.Lock()

    main = Parallel(until="first_done")

    @main
    @repeat(every=INTERVAL, until=lambda finished: finished)
    @abstractmethod
    def job(self, ctx: Context) -> bool:
        """Advance the work by one round. Return `True` when all the work is done."""

    @abstractmethod
    def progress(self) -> str:
        """The progress of the work, shown by `status`."""

    @main
    @isolated
    @repeat(until=lambda command: command == "quit")
    def console(self, ctx: Context) -> str:
        """Read one command, run it, and return its name."""
        hint = ctx.on_stop(lambda: self.say("\n(Finishing. Please press Enter.)"))
        try:
            line = self.read("> ")
        except EOFError:  # Ctrl+D
            return "quit"
        finally:
            hint.cancel()
        if ctx.stopping:
            return "quit"  # a line typed while stopping is not run
        command, *_ = line.split() or [""]
        handler = self.commands().get(command)
        if handler is None:
            if command:
                self.say(f"Unknown command: {command} (help lists them)")
            return command
        handler()
        return command

    def commands(self) -> dict[str, Callable[[], None]]:
        return {
            "status": self.status,
            "pause": self.pause,
            "resume": self.resume,
            "help": self.help,
            "quit": lambda: None,
        }

    def status(self) -> None:
        self.say(f"job: {honehone.control(self).state('job')}  {self.progress()}")

    def pause(self) -> None:
        honehone.control(self).pause("job")  # stops once the current round ends
        self.say("Pause requested")

    def resume(self) -> None:
        honehone.control(self).resume("job")
        self.say("Resumed")

    def help(self) -> None:
        self.say("status / pause / resume / quit")

    def say(self, text: str) -> None:
        # The input worker and stop callbacks run on other threads, so output takes a lock
        with self.output_lock:
            _ = self.out(text)


class Backup(ControlPanel):
    """Work that copies files to a backup one at a time (simulated)."""

    def __init__(
        self,
        files: list[str],
        read: Callable[[str], str] = input,
        out: Callable[[str], object] = print,
    ) -> None:
        super().__init__(read, out)
        self.files = files
        self.copied = Shared(int, 0)  # progress shared by the work and status

    def job(self, ctx: Context) -> bool:
        self.copy(self.files[self.copied.get()])
        return self.copied.apply(lambda n: n + 1) >= len(self.files)

    def copy(self, name: str) -> None:
        """Copy one file. This is an example, so it does nothing."""

    def progress(self) -> str:
        return f"{self.copied.get()}/{len(self.files)} files"


def main() -> None:
    backup = Backup([f"photo{n:03}.jpg" for n in range(60)])
    result = honehone.run(backup)  # Ctrl+C stops it
    print(f"=> {result.outcome}  {backup.progress()}")


if __name__ == "__main__":
    main()
