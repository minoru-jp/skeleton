"""Checks that the English published documents do not disagree with the Japanese canonical documents.

Published documents are made by translating the canonical documents (the translation
itself is done by a person or an LLM). This checks mechanically that translations are
not stale and that translating did not break the essentials.

- Correspondence: every canonical document has a published document, and there are no
  extra published documents.
- Freshness: the stamp at the top of a published document matches the SHA-256 of the
  current canonical document. When a canonical document changes, the check fails until
  it is re-translated and stamped again.
- Code: Python code examples have the same syntax tree, apart from comments and docstrings.
- Rules: the rule headings of the Specification (such as `## STRUCT_001`) are the same,
  in the same order and number.
- Links: relative links, and GitHub links pointing to this repository, have existing targets.

    python scripts/published_docs.py check             # check
    python scripts/published_docs.py stamp README.md   # stamp a re-translated document
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "devdocs" / "canonical_documents"
REPOSITORY = "https://github.com/minoru-jp/honehone/blob/main/"
TREE = "https://github.com/minoru-jp/honehone/tree/main/"

# Where each canonical document lives (relative to CANONICAL) and its published document (relative to ROOT).
PLACES: tuple[tuple[str, str], ...] = (
    ("", ""),
    ("specification/", "docs/specification/"),
)

STAMP = re.compile(
    r"\A<!-- Published from devdocs/canonical_documents/(?P<source>\S+) "
    + r"sha256:(?P<digest>[0-9a-f]{64})\. .*? -->\n"
)
RULE = re.compile(r"^## ([A-Z]+_\d{3})\s*$", re.MULTILINE)
CODE = re.compile(r"^```python\n(.*?)^```", re.MULTILINE | re.DOTALL)
LINK = re.compile(r"\]\(([^)\s]+)\)")
CODE_FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")


@dataclass(frozen=True)
class Pair:
    canonical: Path
    published: Path

    @property
    def source_name(self) -> str:
        return self.canonical.relative_to(CANONICAL).as_posix()


def find_all(pattern: re.Pattern[str], text: str) -> list[str]:
    """Return every match of a regular expression with one group, as strings."""
    matches = cast("list[object]", pattern.findall(text))
    return [found for found in matches if isinstance(found, str)]


def pairs() -> list[Pair]:
    found: list[Pair] = []
    for source_dir, published_dir in PLACES:
        for canonical in sorted((CANONICAL / source_dir).glob("*.md")):
            found.append(Pair(canonical, ROOT / published_dir / canonical.name))
    return found


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp_line(pair: Pair) -> str:
    return (
        f"<!-- Published from devdocs/canonical_documents/{pair.source_name} "
        + f"sha256:{digest(pair.canonical)}. Translated from the Japanese canonical "
        + "document; edit the canonical source instead of this file. -->\n"
    )


def code_shape(code: str) -> str:
    """The syntax tree without comments and docstrings, the only two things a translation may change."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body[0] = ast.Pass()
    return ast.dump(tree, annotate_fields=False)


def check_pair(pair: Pair) -> list[str]:
    name = pair.published.relative_to(ROOT).as_posix()
    if not pair.published.exists():
        return [f"{name}: missing (published from {pair.source_name})"]
    text = pair.published.read_text(encoding="utf-8")
    source = pair.canonical.read_text(encoding="utf-8")
    problems: list[str] = []
    match = STAMP.match(text)
    if match is None or match["source"] != pair.source_name:
        problems.append(f"{name}: no valid stamp for {pair.source_name}")
    elif match["digest"] != digest(pair.canonical):
        problems.append(
            f"{name}: stale; {pair.source_name} changed. Re-translate it, then run "
            + f"`python scripts/published_docs.py stamp {name}`"
        )
    if find_all(RULE, text) != find_all(RULE, source):
        problems.append(f"{name}: rule headings differ from {pair.source_name}")
    published_code = find_all(CODE, text)
    source_code = find_all(CODE, source)
    if len(published_code) != len(source_code):
        problems.append(
            f"{name}: {len(published_code)} code examples, expected {len(source_code)}"
        )
    else:
        for index, (ours, theirs) in enumerate(
            zip(published_code, source_code, strict=True)
        ):
            try:
                same = code_shape(ours) == code_shape(theirs)
            except SyntaxError as error:
                problems.append(
                    f"{name}: code example {index + 1} does not parse: {error}"
                )
                continue
            if not same:
                problems.append(
                    f"{name}: code example {index + 1} differs from the canonical one "
                    + "beyond comments and docstrings"
                )
    problems += check_links(pair.published, text)
    return problems


def check_links(path: Path, text: str) -> list[str]:
    name = path.relative_to(ROOT).as_posix()
    problems: list[str] = []
    # `[...](...)` inside code is not a link.
    prose = INLINE_CODE.sub("", CODE_FENCE.sub("", text))
    for target in find_all(LINK, prose):
        target = target.split("#", 1)[0]
        if not target:
            continue
        if target.startswith((REPOSITORY, TREE)):
            local = ROOT / target.removeprefix(REPOSITORY).removeprefix(TREE)
        elif "://" in target or target.startswith("mailto:"):
            continue
        else:
            local = path.parent / target
        if not local.exists():
            problems.append(f"{name}: broken link {target}")
    return problems


def extra_documents() -> list[str]:
    """Published documents with no corresponding canonical document."""
    expected = {p.published for p in pairs()}
    extra: list[str] = []
    for _, published_dir in PLACES[1:]:
        for path in sorted((ROOT / published_dir).glob("*.md")):
            if path not in expected:
                extra.append(
                    f"{path.relative_to(ROOT).as_posix()}: no canonical document"
                )
    return extra


def problems() -> list[str]:
    found: list[str] = []
    for pair in pairs():
        found += check_pair(pair)
    return found + extra_documents()


def stamp(names: list[str]) -> int:
    by_name = {p.published.relative_to(ROOT).as_posix(): p for p in pairs()}
    for name in names:
        pair = by_name.get(Path(name).as_posix())
        if pair is None:
            print(f"unknown published document: {name}", file=sys.stderr)
            return 2
        text = pair.published.read_text(encoding="utf-8")
        text = STAMP.sub("", text, count=1)
        _ = pair.published.write_text(stamp_line(pair) + text, encoding="utf-8")
        print(f"stamped {name}")
    return 0


class _Args(argparse.Namespace):
    command: str = ""
    names: list[str] | None = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the English published documents."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    _ = commands.add_parser("check", help="check the published documents")
    stamp_parser = commands.add_parser(
        "stamp", help="stamp re-translated published documents"
    )
    _ = stamp_parser.add_argument("names", nargs="+")
    args = parser.parse_args(argv, namespace=_Args())
    if args.command == "stamp":
        return stamp(list(args.names or []))
    found = problems()
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
