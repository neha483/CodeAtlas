"""Lightweight structural parsing.

Full compiler front-ends are overkill here — we only need the *shape* of a
file so the LLM has anchors to describe and so we can compute metrics without
the model. Python is parsed with the standard `ast` module; Java, JS/TS, Go,
Kotlin and C# are handled by a compact declaration scanner tuned per family.

The output is intentionally uniform (`Symbol` records) regardless of source
language, so downstream code never branches on language again.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import List

from .scanner import SourceFile


@dataclass
class Symbol:
    """A named construct discovered in a file (class, method, function...)."""

    name: str
    kind: str                 # class | interface | method | function | enum
    signature: str            # best-effort single-line signature
    start_line: int
    modifiers: List[str] = field(default_factory=list)


@dataclass
class FileStructure:
    """Everything the structural pass learned about one file."""

    rel_path: str
    language: str
    package: str | None
    imports: List[str]
    symbols: List[Symbol]


# ---------------------------------------------------------------------------
# Python — real AST, so it is exact.
# ---------------------------------------------------------------------------
def _parse_python(source: SourceFile) -> FileStructure:
    symbols: List[Symbol] = []
    imports: List[str] = []
    try:
        tree = ast.parse(source.text)
    except SyntaxError:
        return FileStructure(source.rel_path, "python", None, [], [])

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            for alias in node.names:
                imports.append((module + "." + alias.name).strip("."))
        elif isinstance(node, ast.ClassDef):
            symbols.append(Symbol(node.name, "class", f"class {node.name}", node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = ", ".join(a.arg for a in node.args.args)
            symbols.append(
                Symbol(node.name, "function", f"def {node.name}({args})", node.lineno)
            )
    return FileStructure(source.rel_path, "python", None, sorted(set(imports)), symbols)


# ---------------------------------------------------------------------------
# C-family / JVM — declaration scanner driven by regexes.
# ---------------------------------------------------------------------------
_PKG_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", re.MULTILINE)

_TYPE_RE = re.compile(
    r"^\s*(?P<mods>(?:public|private|protected|abstract|final|static|sealed|\s)*)"
    r"\b(?P<kind>class|interface|enum|record)\s+(?P<name>[A-Za-z_]\w*)",
    re.MULTILINE,
)

# Methods: modifiers, optional generics, return type, name, parenthesised args,
# followed by a body brace or a semicolon (interface/abstract declarations).
_METHOD_RE = re.compile(
    r"^\s*(?P<mods>(?:public|private|protected|static|final|abstract|synchronized|default|\s)*)"
    r"(?:<[^>]+>\s*)?"
    r"(?P<ret>[A-Za-z_][\w<>\[\],.\s]*?)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*"
    r"\((?P<args>(?:[^(){};]|\([^()]*\))*)\)\s*"
    r"(?:throws\s+[\w.,\s]+)?\s*[{;]",
    re.MULTILINE,
)

# Reserved words that _look_ like method returns but are control flow.
_NON_METHOD_NAMES = {"if", "for", "while", "switch", "catch", "return", "new"}

# If any of these appear as a token in the "return type", the match is really a
# statement (e.g. `throw new X(...)`, `return foo()`), not a declaration.
_STATEMENT_KEYWORDS = {
    "return", "throw", "new", "else", "assert", "yield", "await",
    "break", "continue", "super", "this",
}


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _parse_cfamily(source: SourceFile) -> FileStructure:
    text = source.text
    package_match = _PKG_RE.search(text)
    package = package_match.group(1) if package_match else None
    imports = _IMPORT_RE.findall(text)

    symbols: List[Symbol] = []
    for match in _TYPE_RE.finditer(text):
        mods = [m for m in match.group("mods").split() if m]
        name = match.group("name")
        symbols.append(
            Symbol(name, match.group("kind"), match.group(0).strip(), _line_of(text, match.start()), mods)
        )

    for match in _METHOD_RE.finditer(text):
        name = match.group("name")
        if name in _NON_METHOD_NAMES:
            continue
        ret = match.group("ret").strip()
        if ret in ("else", "do", "try"):
            continue
        # Reject control-flow statements masquerading as declarations.
        ret_tokens = set(ret.split())
        if ret_tokens & _STATEMENT_KEYWORDS:
            continue
        args = " ".join(match.group("args").split())
        signature = f"{ret} {name}({args})"
        mods = [m for m in match.group("mods").split() if m]
        symbols.append(Symbol(name, "method", signature, _line_of(text, match.start()), mods))

    symbols.sort(key=lambda s: s.start_line)
    return FileStructure(source.rel_path, source.language, package, sorted(set(imports)), symbols)


_CFAMILY_LANGS = {"java", "javascript", "typescript", "go", "kotlin", "csharp", "rust", "php"}


def parse_structure(source: SourceFile) -> FileStructure:
    """Dispatch a source file to the right structural parser."""
    if source.language == "python":
        return _parse_python(source)
    if source.language in _CFAMILY_LANGS:
        return _parse_cfamily(source)
    # Config / markup languages: no symbols, but keep a uniform record.
    return FileStructure(source.rel_path, source.language, None, [], [])
