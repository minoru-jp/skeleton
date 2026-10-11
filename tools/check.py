"""Runs every check of honehone together. CI uses this too.

Run at the root of the repository.

    python tools/check.py               # every check
    python tools/check.py lint tests    # only the chosen checks
    python tools/check.py dist --tag v2.0.0 --dist-dir dist
                                        # build and check the distributions, keep them
                                        # in dist/ (for releases)

Checks:

    docs         the canonical documents match a fresh render of the canonical sources,
                 and the English published documents do not disagree with them
    format       ruff format --check
    lint         ruff check
    types        basedpyright (src, scripts, tools)
    types-tests  basedpyright -p tests (tests, examples and document sources as user code)
    tests        pytest
    dist         build an sdist and a wheel; twine check, inspect their contents, and
                 confirm the wheel works in a clean venv

A failed check does not stop the rest; failures are reported together at the end. The
exit code is 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import venv
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Options:
    tag: str | None = None
    dist_dir: str | None = None


@dataclass(frozen=True)
class Outcome:
    ok: bool
    output: str


def command(*argv: str) -> Callable[[Options], Outcome]:
    def run(_: Options) -> Outcome:
        done = subprocess.run(
            argv, cwd=ROOT, capture_output=True, text=True, check=False
        )
        return Outcome(done.returncode == 0, done.stdout + done.stderr)

    return run


def check_docs(_: Options) -> Outcome:
    # Imported after ROOT is put on sys.path.
    from scripts import published_docs, render_devdocs

    lines: list[str] = []
    stale = render_devdocs.stale_documents()
    lines += [
        f"stale canonical document: {name} (run: python scripts/render_devdocs.py)"
        for name in stale
    ]
    lines += published_docs.problems()
    return Outcome(not lines, "\n".join(lines))


# ---------------------------------------------------------------- dist


REQUIRED_IN_WHEEL = (
    "honehone/__init__.py",
    "honehone/py.typed",
    "honehone/_define.py",
    "honehone/_engine.py",
    "honehone/_errors.py",
    "honehone/_result.py",
    "honehone/gpframe.py",
)
REQUIRED_IN_SDIST = (
    "PKG-INFO",
    "pyproject.toml",
    "README.md",
    "LICENSE",
    *(f"src/{name}" for name in REQUIRED_IN_WHEEL),
)

SMOKE = """
import honehone
from honehone import Context, Parallel, Skeleton, repeat


class Shape(Skeleton):
    main = Parallel()

    @main
    @repeat(times=3)
    def tick(self, ctx: Context) -> int:
        return 1

    @main
    def once(self, ctx: Context) -> str:
        return "done"


result = honehone.run(Shape())
assert result.outcome == "completed"
assert result.nodes["tick"].calls == 3
assert result.nodes["once"].value == "done"
print(honehone.__name__, "ok")
"""


def project() -> dict[str, object]:
    with (ROOT / "pyproject.toml").open("rb") as file:
        data = tomllib.load(file)
    return cast("dict[str, object]", data["project"])


def check_dist(options: Options) -> Outcome:
    version = str(project()["version"])
    name = str(project()["name"])
    lines: list[str] = []
    tag = options.tag
    if tag is not None and tag != f"v{version}":
        lines.append(f"tag {tag!r} does not match the project version v{version}")
    changelog = (
        ROOT / "devdocs" / "canonical_sources" / "changelog" / "canonical.py"
    ).read_text(encoding="utf-8")
    if f'version @= "{version}"' not in changelog:
        lines.append(f"the CHANGELOG has no entry for {version}")
    context = cast(
        "dict[str, dict[str, str]]",
        json.loads(
            (ROOT / "devdocs" / "config" / "context.json").read_text(encoding="utf-8")
        ),
    )
    if context["project"]["version"] != version:
        lines.append("devdocs/config/context.json has a different version")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "dist"
        built = subprocess.run(
            [
                PYTHON,
                "-m",
                "build",
                "--sdist",
                "--wheel",
                "--outdir",
                str(out),
                str(ROOT),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if built.returncode != 0:
            return Outcome(False, "\n".join([*lines, built.stdout, built.stderr]))
        wheels = sorted(out.glob("*.whl"))
        sdists = sorted(out.glob("*.tar.gz"))
        if [w.name for w in wheels] != [f"{name}-{version}-py3-none-any.whl"]:
            lines.append(f"unexpected wheels: {[w.name for w in wheels]}")
        if [s.name for s in sdists] != [f"{name}-{version}.tar.gz"]:
            lines.append(f"unexpected sdists: {[s.name for s in sdists]}")
        twine = subprocess.run(
            [PYTHON, "-m", "twine", "check", "--strict", *map(str, out.iterdir())],
            capture_output=True,
            text=True,
            check=False,
        )
        if twine.returncode != 0:
            lines.append("twine check failed:\n" + twine.stdout + twine.stderr)
        if wheels:
            lines += inspect_wheel(wheels[0], name, version)
            lines += smoke_test(wheels[0], Path(tmp))
        if sdists:
            lines += inspect_sdist(sdists[0], name, version)
        keep = options.dist_dir
        if keep is not None and not lines:
            target = ROOT / keep
            target.mkdir(parents=True, exist_ok=True)
            for path in out.iterdir():
                _ = shutil.copy2(path, target / path.name)
            kept = [f"kept {p.name} in {keep}/" for p in sorted(out.iterdir())]
            return Outcome(True, "\n".join(kept))
    return Outcome(not lines, "\n".join(lines))


def inspect_wheel(wheel: Path, name: str, version: str) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata = archive.read(f"{name}-{version}.dist-info/METADATA").decode()
    problems = [f"wheel lacks {n}" for n in REQUIRED_IN_WHEEL if n not in names]
    problems += [
        f"wheel contains {n}"
        for n in sorted(names)
        if not n.startswith((f"{name}/", f"{name}-{version}.dist-info/"))
    ]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "Description-Content-Type: text/markdown" not in metadata:
        problems.append("the wheel metadata does not declare a Markdown description")
    if readme.strip() not in metadata:
        problems.append(
            "the wheel metadata does not carry README.md as its description"
        )
    requires = str(project()["requires-python"])
    if f"Requires-Python: {requires}" not in metadata:
        problems.append(f"the wheel metadata does not require Python {requires}")
    for dependency in cast("list[str]", project()["dependencies"]):
        if f"Requires-Dist: {dependency}" not in metadata:
            problems.append(f"the wheel metadata does not require {dependency}")
    return problems


def inspect_sdist(sdist: Path, name: str, version: str) -> list[str]:
    prefix = f"{name}-{version}/"
    with tarfile.open(sdist) as archive:
        names = {n.removeprefix(prefix) for n in archive.getnames()}
    return [f"sdist lacks {n}" for n in REQUIRED_IN_SDIST if n not in names]


def smoke_test(wheel: Path, tmp: Path) -> list[str]:
    """Install the wheel with its dependencies into a clean venv and run it."""
    env = tmp / "venv"
    venv.EnvBuilder(with_pip=True).create(env)
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    # The dependencies (gpframe, fport) come from PyPI, the same way users install them.
    install = subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", str(wheel)],
        capture_output=True,
        text=True,
        check=False,
    )
    if install.returncode != 0:
        return ["installing the wheel failed:\n" + install.stdout + install.stderr]
    # Run in another directory so that the repository's src is not imported.
    run = subprocess.run(
        [str(python), "-I", "-c", SMOKE],
        cwd=tmp,
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0 or run.stdout.strip() != "honehone ok":
        return ["the installed wheel does not work:\n" + run.stdout + run.stderr]
    return []


# ---------------------------------------------------------------- main


CHECKS: dict[str, Callable[[Options], Outcome]] = {
    "docs": check_docs,
    "format": command(PYTHON, "-m", "ruff", "format", "--check", "."),
    "lint": command(PYTHON, "-m", "ruff", "check", "."),
    # Type checking uses the environment of the Python running the checks (the same in CI and locally).
    "types": command(PYTHON, "-m", "basedpyright", "--pythonpath", PYTHON),
    "types-tests": command(
        PYTHON, "-m", "basedpyright", "--pythonpath", PYTHON, "-p", "tests"
    ),
    "tests": command(PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"),
    "dist": check_dist,
}


class _Args(argparse.Namespace):
    checks: list[str] | None = None
    tag: str | None = None
    dist_dir: str | None = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run every check of honehone together."
    )
    _ = parser.add_argument(
        "checks", nargs="*", help=f"checks to run (all if omitted): {' '.join(CHECKS)}"
    )
    _ = parser.add_argument(
        "--tag", help="dist: the release tag; must equal v<version>"
    )
    _ = parser.add_argument(
        "--dist-dir", help="dist: keep the checked distributions in this directory"
    )
    args = parser.parse_args(argv, namespace=_Args())
    names = args.checks or list(CHECKS)
    options = Options(tag=args.tag, dist_dir=args.dist_dir)
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        parser.error(f"unknown checks: {' '.join(unknown)}")
    failed: list[str] = []
    for name in names:
        started = time.monotonic()
        outcome = CHECKS[name](options)
        elapsed = time.monotonic() - started
        print(f"{name}: {'ok' if outcome.ok else 'FAIL'} ({elapsed:.1f}s)", flush=True)
        if not outcome.ok:
            failed.append(name)
            print(outcome.output.rstrip(), flush=True)
        elif outcome.output and name == "dist":
            print(outcome.output.rstrip(), flush=True)
    if failed:
        print(f"failed: {' '.join(failed)}", flush=True)
        return 1
    print("all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
