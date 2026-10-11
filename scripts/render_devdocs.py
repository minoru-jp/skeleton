"""Generates the canonical documents from the canonical sources in devdocs.

Run at the root of the repository.

    python scripts/render_devdocs.py            # generate into devdocs/canonical_documents
    python scripts/render_devdocs.py --check    # only check that the output is up to date

`RENDERS` is the single place listing the documents to generate; the tests use it too.
"""

from __future__ import annotations

import argparse
import contextlib
import filecmp
import io
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from shikumi_devdoc.cli import main as devdoc_main

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "devdocs" / "config"
DOCUMENTS = ROOT / "devdocs" / "canonical_documents"


@dataclass(frozen=True)
class Render:
    kind: Literal["document", "index"]
    module: str
    subdir: str = ""
    uses_context: bool = False
    index_title: str = ""


RENDERS: tuple[Render, ...] = (
    Render("document", "devdocs.canonical_sources.readme.canonical", uses_context=True),
    Render("document", "devdocs.canonical_sources.status.canonical", uses_context=True),
    Render("document", "devdocs.canonical_sources.changelog.canonical"),
    Render(
        "document", "devdocs.canonical_sources.specification", subdir="specification"
    ),
    Render(
        "index",
        "devdocs.canonical_sources.specification",
        subdir="specification",
        index_title="honehone Specification",
    ),
)


def render(output: Path) -> None:
    """Generate every canonical source into `output`. `RuntimeError` on failure."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    context = (CONFIG / "context.json").read_text(encoding="utf-8")
    for item in RENDERS:
        target = output / item.subdir if item.subdir else output
        argv = ["render", item.kind, item.module, "-o", str(target)]
        if item.uses_context:
            argv += ["--context", context]
        if item.index_title:
            argv += ["--index-title", item.index_title]
        argv += ["--notice", str(CONFIG / "notice.toml"), "--translation-source"]
        log = io.StringIO()
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            status = devdoc_main(argv)
        if status != 0:
            raise RuntimeError(f"failed to render {item.module}:\n{log.getvalue()}")


def _markdown_files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*.md")}


def stale_documents() -> list[str]:
    """Return the canonical documents that would change if regenerated, or are missing or extra."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        render(fresh)
        names = sorted(_markdown_files(fresh) | _markdown_files(DOCUMENTS))
        return [
            name
            for name in names
            if not (fresh / name).exists()
            or not (DOCUMENTS / name).exists()
            or not filecmp.cmp(fresh / name, DOCUMENTS / name, shallow=False)
        ]


class _Args(argparse.Namespace):
    check: bool = False


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the canonical documents from the canonical sources in devdocs."
    )
    _ = parser.add_argument(
        "--check", action="store_true", help="only check that the output is up to date"
    )
    args = parser.parse_args(namespace=_Args())
    if args.check:
        stale = stale_documents()
        for name in stale:
            print(f"stale: {name}")
        return 1 if stale else 0
    render(DOCUMENTS)
    for name in sorted(_markdown_files(DOCUMENTS)):
        print(Path("devdocs/canonical_documents") / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
