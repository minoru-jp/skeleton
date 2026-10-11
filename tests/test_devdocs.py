"""Tests about the canonical sources of the documents.

- The canonical documents match a fresh render of the canonical sources
- The code examples of the README actually work and give the results they describe
- The version injected into the documents matches pyproject.toml
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import signal
import sqlite3
import subprocess
import threading
import tomllib
import webbrowser
from pathlib import Path

import pytest

import honehone
from devdocs.canonical_sources.readme import canonical as readme
from scripts import render_devdocs

ROOT = Path(__file__).resolve().parent.parent


def _exec(example: str, namespace: dict[str, object] | None = None) -> str:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(  # noqa: S102 - runs the README examples themselves to check them
            compile(example, "<README example>", "exec"),
            {"__name__": "__readme__"} if namespace is None else namespace,
        )
    return output.getvalue()


def test_canonical_documents_are_up_to_date() -> None:
    stale = render_devdocs.stale_documents()
    assert stale == [], "regenerate with: python scripts/render_devdocs.py"


class _FakeProcess:
    """Stands in for the external process the README example starts. terminate() makes wait() return."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self._done = threading.Event()

    def terminate(self) -> None:
        self._done.set()

    def wait(self) -> int:
        _ = self._done.wait(10)
        return 0


def test_readme_devenv_example_runs_and_stops_on_ctrl_c(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(subprocess, "Popen", _FakeProcess)
    monkeypatch.setattr(webbrowser, "open", opened.append)
    timer = threading.Timer(0.3, os.kill, (os.getpid(), signal.SIGINT))
    timer.start()
    output = _exec(readme.DEVENV_EXAMPLE)
    timer.join()
    assert opened == ["http://localhost:8000"]
    assert "run.finished" in output
    stopped = {
        name
        for name in ("api", "database")
        for line in output.splitlines()
        if f"'name': '{name}'" in line and "'state': 'stopped'" in line
    }
    assert stopped == {"api", "database"}


def test_readme_archiver_example_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    namespace: dict[str, object] = {"__name__": "__readme__"}
    _ = _exec(readme.ARCHIVER_EXAMPLE, namespace)
    archiver = namespace["Archiver"]
    assert isinstance(archiver, type) and issubclass(archiver, honehone.Skeleton)

    class Lines(archiver):
        def collect(self, ctx: honehone.Context) -> None:
            for line in ("a", "b", "c"):
                self.lines.put(line)  # pyright: ignore[reportAttributeAccessIssue] - an attribute prepared in boot
            self.lines.close()  # pyright: ignore[reportAttributeAccessIssue] - an attribute prepared in boot

    result = honehone.run(Lines())
    assert result.outcome == "completed", result
    with contextlib.closing(sqlite3.connect(tmp_path / "archive.db")) as db:
        rows = db.execute("SELECT line FROM lines").fetchall()
    assert rows == [("a",), ("b",), ("c",)]


def test_readme_control_example_runs() -> None:
    assert _exec(readme.CONTROL_EXAMPLE).strip() == "stopped True"


def test_context_version_matches_project() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    context = json.loads(
        (ROOT / "devdocs" / "config" / "context.json").read_text(encoding="utf-8")
    )
    assert context["project"]["version"] == project["project"]["version"]
    assert (
        context["project"]["requires-python"] == project["project"]["requires-python"]
    )
    assert honehone.__version__ == project["project"]["version"]
