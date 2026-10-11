"""Checks that the examples in examples/ work as written."""

from __future__ import annotations

import contextlib
import os
import queue
import signal
import sqlite3
import threading
import time
from pathlib import Path

import pytest

import honehone
from examples import console, cooking, instrument
from tests.conftest import WAIT, Recorder, finish


def _reports(recorder: Recorder) -> list[tuple[object, ...]]:
    with recorder.lock:
        return [args for tag, args, _ in recorder.events if tag == "worker.report"]


def _index(reports: list[tuple[object, ...]], what: str, left: int | None) -> int:
    """The position of the report of task `what` with `left` remaining (None for its start)."""
    for i, args in enumerate(reports):
        if args[1] != what:
            continue
        if (left is None and args[2] == args[3]) or args[2] == left:
            return i
    raise AssertionError(f"no report for {what} {left}")


# ---------------------------------------------------------------------------
# The cooking timer
# ---------------------------------------------------------------------------


def test_cooking_recipe_needs_a_sauce() -> None:
    with pytest.raises(TypeError):
        _ = cooking.PastaRecipe()  # pyright: ignore[reportAbstractUsage] - checks that the shape alone cannot be instantiated


@pytest.mark.parametrize("recipe", [cooking.Carbonara, cooking.Arrabbiata])
def test_cooking_recipes_share_the_shape(
    recipe: type[cooking.PastaRecipe], recorder: Recorder
) -> None:
    result = honehone.run(recipe(), listener=recorder)
    assert result.outcome == "completed"
    reports = _reports(recorder)
    # Inside the pasta pot, steps go in order
    assert _index(reports, "boil the water", 0) < _index(
        reports, "boil the pasta", None
    )
    # Tossing waits for both pots, and plating comes last
    assert _index(reports, "boil the pasta", 0) < _index(
        reports, "toss with the sauce", None
    )
    assert _index(reports, "toss with the sauce", 0) < _index(reports, "plate", None)
    assert reports[-1][1:3] == ("plate", 0)


def test_cooking_two_pots_cook_at_the_same_time(recorder: Recorder) -> None:
    _ = honehone.run(cooking.Arrabbiata(), listener=recorder)
    reports = _reports(recorder)
    # The pasta pot advances while the sauce simmers
    assert _index(reports, "simmer the tomatoes", None) < _index(
        reports, "boil the pasta", 0
    )
    assert _index(reports, "boil the pasta", 0) < _index(
        reports, "simmer the tomatoes", 0
    )


def test_cooking_nothing_advances_while_paused(recorder: Recorder) -> None:
    run = honehone.start(cooking.Arrabbiata(), listener=recorder)
    deadline = time.monotonic() + WAIT
    while not any(a[1] == "simmer the tomatoes" for a in _reports(recorder)):
        assert time.monotonic() < deadline
        time.sleep(0.005)
    run.pause()
    assert run.wait_until("main", "paused", WAIT)
    paused_at = len(_reports(recorder))
    time.sleep(10 * cooking.MINUTE)
    assert len(_reports(recorder)) == paused_at
    run.resume()
    assert finish(run).outcome == "completed"
    assert len(_reports(recorder)) > paused_at


def test_cooking_main(capsys: pytest.CaptureFixture[str]) -> None:
    cooking.main()
    out = capsys.readouterr().out
    assert out.count("=> completed") == 2
    assert out.index("-- leaving the kitchen --") < out.index(
        "-- back in the kitchen --"
    )


# ---------------------------------------------------------------------------
# Instrument control
# ---------------------------------------------------------------------------


def _rows(path: Path) -> list[tuple[int, float]]:
    with contextlib.closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT n, celsius FROM samples ORDER BY n").fetchall()


def _order(recorder: Recorder) -> list[object]:
    return [args[1] for args in _reports(recorder)]


def test_instrument_records_every_sample(tmp_path: Path, recorder: Recorder) -> None:
    db = tmp_path / "bench.db"
    result = honehone.run(instrument.BenchThermometer(str(db)), listener=recorder)
    assert result.outcome == "completed"
    assert result.nodes["record"].value == instrument.SAMPLES
    assert [n for n, _ in _rows(db)] == list(range(1, instrument.SAMPLES + 1))
    # The recording is closed and the monitor stopped before disconnecting
    assert _order(recorder) == [
        "connected",
        "recorded",
        "monitor stopped",
        "disconnected",
    ]
    assert result.nodes["monitor"].state == "succeeded"


def test_instrument_stops_safely_when_overheated(
    tmp_path: Path, recorder: Recorder
) -> None:
    db = tmp_path / "hot.db"
    result = honehone.run(instrument.HotPlate(str(db)), listener=recorder)
    assert result.outcome == "failed"
    assert "overheated" in str(result.nodes["monitor"].errors[0])
    assert result.nodes["measure"].state == "stopped"
    recorded = result.nodes["record"].value
    assert isinstance(recorded, int) and 0 < recorded < instrument.SAMPLES
    assert len(_rows(db)) == recorded  # what was received before stopping is kept
    assert _order(recorder)[-1] == "disconnected"
    with pytest.raises(honehone.SkeletonFailed):
        result.raise_if_failed()


def test_instrument_ctrl_c_keeps_the_order(tmp_path: Path, recorder: Recorder) -> None:
    assert threading.current_thread() is threading.main_thread()
    db = tmp_path / "bench.db"
    timer = threading.Timer(0.3, os.kill, (os.getpid(), signal.SIGINT))
    timer.start()
    result = honehone.run(instrument.BenchThermometer(str(db)), listener=recorder)
    timer.join()
    assert result.outcome == "stopped"
    recorded = result.nodes["record"].value
    assert isinstance(recorded, int) and 0 < recorded < instrument.SAMPLES
    assert len(_rows(db)) == recorded
    assert _order(recorder) == [
        "connected",
        "recorded",
        "monitor stopped",
        "disconnected",
    ]
    assert result.nodes["monitor"].state == "stopped"


def test_instrument_main(capsys: pytest.CaptureFixture[str]) -> None:
    instrument.main()
    out = capsys.readouterr().out
    assert f"=> completed, recorded {instrument.SAMPLES} samples" in out
    assert "=> failed: overheated" in out


# ---------------------------------------------------------------------------
# A CLI as a control panel
# ---------------------------------------------------------------------------


class Keyboard:
    """Stands in for input. Returns the typed lines in order as the return values of `input()`."""

    EOF = object()

    def __init__(self) -> None:
        self.lines: queue.Queue[object] = queue.Queue()
        self.waiting = threading.Event()

    def __call__(self, prompt: str) -> str:
        self.waiting.set()
        line = self.lines.get(timeout=WAIT)
        self.waiting.clear()
        if line is Keyboard.EOF:
            raise EOFError
        assert isinstance(line, str)
        return line

    def type(self, line: object) -> None:
        assert self.waiting.wait(WAIT), "the console is not waiting for input"
        self.waiting.clear()
        self.lines.put(line)


class Screen:
    """Stands in for output. Records the lines and can wait for a new one."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.cond = threading.Condition()

    def __call__(self, text: str) -> None:
        with self.cond:
            self.lines.append(text)
            self.cond.notify_all()

    def wait_for(self, fragment: str) -> str:
        with self.cond:
            assert self.cond.wait_for(
                lambda: any(fragment in line for line in self.lines), WAIT
            ), f"{fragment!r} was not shown: {self.lines}"
            return next(line for line in self.lines if fragment in line)


def _backup(files: int) -> tuple[console.Backup, Keyboard, Screen]:
    keyboard, screen = Keyboard(), Screen()
    backup = console.Backup([f"f{n}" for n in range(files)], read=keyboard, out=screen)
    return backup, keyboard, screen


def test_console_commands_operate_the_job() -> None:
    backup, keyboard, screen = _backup(1000)
    run = honehone.start(backup)
    keyboard.type("status")
    assert screen.wait_for("job: ").startswith("job: running")
    keyboard.type("pause")
    _ = screen.wait_for("Pause requested")
    assert run.wait_until("job", "paused", WAIT)
    paused_at = backup.copied.get()
    time.sleep(3 * console.INTERVAL)
    assert backup.copied.get() == paused_at  # no progress while paused
    keyboard.type("resume")
    _ = screen.wait_for("Resumed")
    keyboard.type("quit")
    result = finish(run)
    assert result.outcome == "completed"
    assert result.nodes["console"].state == "succeeded"
    assert (
        result.nodes["job"].state == "stopped"
    )  # quit ended first and stopped the work


def test_console_unknown_commands_are_reported() -> None:
    backup, keyboard, screen = _backup(1000)
    run = honehone.start(backup)
    keyboard.type("frobnicate")
    _ = screen.wait_for("Unknown command: frobnicate")
    keyboard.type(Keyboard.EOF)  # Ctrl+D also finishes
    assert finish(run).outcome == "completed"


def test_console_waits_for_enter_when_the_job_finishes_first() -> None:
    backup, keyboard, screen = _backup(3)
    run = honehone.start(backup)
    assert run.wait_until("job", "succeeded", WAIT)
    _ = screen.wait_for(
        "Please press Enter"
    )  # input is in progress, so it waits until the line is finished
    assert run.state("console") in ("running", "stopped")
    keyboard.type("")
    result = finish(run)
    assert result.outcome == "completed"
    assert result.nodes["job"].state == "succeeded"
    assert backup.progress() == "3/3 files"


def test_console_does_not_run_a_line_typed_while_stopping() -> None:
    backup, keyboard, screen = _backup(1000)
    run = honehone.start(backup)
    assert keyboard.waiting.wait(WAIT)
    run.stop()
    _ = screen.wait_for("Please press Enter")
    keyboard.type("pause")
    result = finish(run)
    assert result.outcome == "stopped"
    assert not any("Pause requested" in line for line in screen.lines)


@pytest.mark.skipif(os.name != "posix", reason="needs a pseudo terminal (POSIX)")
def test_console_ctrl_c_in_a_real_terminal() -> None:
    import pty
    import select
    import subprocess
    import sys

    script = Path(__file__).resolve().parent.parent / "examples" / "console.py"
    leader, follower = pty.openpty()
    # Run the example itself as a child process on a terminal (no fork in this process)
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdin=follower,
        stdout=follower,
        stderr=follower,
    )
    os.close(follower)

    def read_until(fragment: str) -> str:
        out = ""
        deadline = time.monotonic() + WAIT
        while fragment not in out and time.monotonic() < deadline:
            if select.select([leader], [], [], 0.1)[0]:
                try:
                    out += os.read(leader, 4096).decode(errors="replace")
                except OSError:
                    break
        assert fragment in out, out
        return out

    try:
        _ = read_until("> ")
        os.write(leader, b"status\n")
        shown = read_until("job: running")
        if not shown.rstrip(" ").endswith(">"):
            _ = read_until("> ")  # press it once the next prompt is waiting
        proc.send_signal(signal.SIGINT)  # Ctrl+C while waiting for input
        _ = read_until("Please press Enter")
        os.write(leader, b"\n")
        _ = read_until("=> stopped")
        assert proc.wait(WAIT) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            _ = proc.wait()
        os.close(leader)
