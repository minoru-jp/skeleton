"""Instrument control: a service, a cleanup paired with a boot, and a thread-bound resource.

`Measurement` has the shape of a measurement: "connect to the device, measure while
monitoring the temperature, record into sqlite, and disconnect at the end". Which
device to use, an implementation class decides.

    python examples/instrument.py    # Ctrl+C stops it midway

Even when stopped midway, the order is kept: the measuring stops, the recording is
closed, and the monitoring stops before the device is disconnected. The monitor never
reads a disconnected device.
"""

from __future__ import annotations

import itertools
import sqlite3
import tempfile
import threading
from abc import abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import honehone
from honehone import (
    Channel,
    Context,
    Sequence,
    Skeleton,
    ThreadBound,
    boot,
    cleanup,
    pinned,
    repeat,
    service,
)

SAMPLES = 20
"""The number of values taken in one measurement."""

INTERVAL = 0.05
"""The interval between values, in seconds."""


class Device(Protocol):
    """A device used for measuring."""

    def read(self) -> float: ...
    def close(self) -> None: ...


class SimulatedThermometer:
    """A simulated thermometer. The temperature rises a little on every read; reading after close fails."""

    def __init__(self, start: float, step: float = 0.05) -> None:
        self._value: float = start
        self._step: float = step
        self._closed: bool = False
        self._lock: threading.Lock = threading.Lock()

    def read(self) -> float:
        with self._lock:
            if self._closed:
                raise RuntimeError("the device is closed")
            self._value += self._step
            return round(self._value, 2)

    def close(self) -> None:
        with self._lock:
            self._closed = True


class Measurement(Skeleton):
    """The shape of a measurement that monitors the temperature and records into sqlite.

    ```text
    boot: connect                      (paired cleanup: disconnect)
    main (Sequence)
    ├── monitor            @service    watches the temperature; once ready, the next
    │                                  step starts and it keeps running
    └── work (Parallel)
        ├── acquire (Sequence)
        │   ├── measure    @repeat     takes a value and sends it to the Channel
        │   └── finish                 signals that sending is over
        └── record         @pinned     receives from the Channel and writes to sqlite
                                       on the home thread
    ```
    """

    limit: float = 80.0
    """Above this temperature, the measurement stops as overheated."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path  # __init__ only takes settings

    @abstractmethod
    def open_device(self) -> Device:
        """Open the device to use. Each device writes this in its implementation class."""

    @boot
    def connect(self, ctx: Context) -> None:
        # Attributes can be written only during boot. Every resource is prepared here
        self.device = self.open_device()
        db = sqlite3.connect(self.db_path)
        db.execute("CREATE TABLE IF NOT EXISTS samples (n INTEGER, celsius REAL)")
        self.db = ThreadBound(db)  # bound to the creating thread (the home thread)
        self.samples = Channel(tuple)
        self.counter = itertools.count(1)
        ctx.report("connected")

    @cleanup(of=connect)
    def disconnect(self, ctx: Context) -> None:
        # Runs only if connect succeeded, after the monitor has stopped
        self.device.close()
        self.db.get().close()
        ctx.report("disconnected")

    main = Sequence()

    @main
    @service
    def monitor(self, ctx: Context) -> None:
        ctx.ready()
        while not ctx.wait_stop(INTERVAL):
            celsius = self.device.read()
            if celsius > self.limit:
                raise RuntimeError(f"overheated: {celsius}")
        ctx.report("monitor stopped")

    work = main.parallel()
    acquire = work.sequence()

    @acquire
    @repeat(every=INTERVAL, until=lambda n: n >= SAMPLES)
    def measure(self, ctx: Context) -> int:
        n = next(self.counter)
        self.samples.put((n, self.device.read()))
        return n

    @acquire
    def finish(self, ctx: Context) -> None:
        self.samples.close()  # ends the receiving loop

    @work
    @pinned
    def record(self, ctx: Context) -> int:
        db = self.db.get()  # usable because this runs on the home thread
        count = 0
        for n, celsius in self.samples.receive(ctx):
            db.execute("INSERT INTO samples VALUES (?, ?)", (n, celsius))
            count += 1
        db.commit()  # even when stopped, what was received is kept
        ctx.report("recorded", count)
        return count


class BenchThermometer(Measurement):
    """A thermometer on the lab bench."""

    def open_device(self) -> Device:
        return SimulatedThermometer(start=21.5)


class HotPlate(Measurement):
    """A hot plate being heated. It goes over the limit during the measurement."""

    def open_device(self) -> Device:
        return SimulatedThermometer(start=79.6)


class Console:
    """The listener of reports. Shows worker reports and state changes of the main nodes."""

    def __init__(self, out: Callable[[str], object] = print) -> None:
        self._out: Callable[[str], object] = out
        self._lock: threading.Lock = threading.Lock()

    def __call__(self, tag: str, *args: object, **kwargs: object) -> None:
        with (
            self._lock
        ):  # reports arrive on worker threads, so output is serialized here
            if tag == "worker.report":
                _ = self._out("  " + " ".join(str(a) for a in args))
            elif tag == "node.changed" and kwargs["name"] in ("monitor", "measure"):
                _ = self._out(f"  {kwargs['name']}: {kwargs['state']}")


def main() -> None:
    console = Console()
    with tempfile.TemporaryDirectory() as tmp:
        print("Bench thermometer")
        result = honehone.run(
            BenchThermometer(str(Path(tmp, "bench.db"))), listener=console
        )
        print(f"  => {result.outcome}, recorded {result.nodes['record'].value} samples")

        print("Hot plate (overheats midway)")
        result = honehone.run(HotPlate(str(Path(tmp, "hotplate.db"))), listener=console)
        print(f"  => {result.outcome}: {result.nodes['monitor'].errors[0]}")
        print(
            f"     recorded {result.nodes['record'].value} samples before overheating"
        )


if __name__ == "__main__":
    main()
