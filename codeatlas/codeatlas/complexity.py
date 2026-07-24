"""Heuristic code-complexity metrics.

We deliberately avoid a heavy static-analysis dependency. Instead we compute a
McCabe-style cyclomatic-complexity approximation by counting decision points,
plus a couple of cheap structural signals. This runs locally, costs no tokens,
and gives the report objective numbers to sit alongside the LLM's prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Keywords / operators that each introduce an independent execution path.
_DECISION_PATTERNS = [
    r"\bif\b", r"\belse\s+if\b", r"\bfor\b", r"\bwhile\b", r"\bcase\b",
    r"\bcatch\b", r"\b&&\b", r"\|\|", r"\?", r"\bexcept\b", r"\belif\b",
]
_DECISION_RE = re.compile("|".join(_DECISION_PATTERNS))
_COMMENT_LINE_RE = re.compile(r"^\s*(//|#|\*|/\*|\*/)")


@dataclass
class ComplexityReport:
    """Objective, model-free metrics for one file."""

    cyclomatic_complexity: int
    lines_of_code: int          # non-blank, non-comment
    comment_lines: int
    decision_points: int
    rating: str                 # low | moderate | high | very-high

    def as_dict(self) -> dict:
        return {
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "lines_of_code": self.lines_of_code,
            "comment_lines": self.comment_lines,
            "decision_points": self.decision_points,
            "rating": self.rating,
        }


def _rate(cc: int) -> str:
    if cc <= 5:
        return "low"
    if cc <= 10:
        return "moderate"
    if cc <= 20:
        return "high"
    return "very-high"


def analyse_complexity(text: str) -> ComplexityReport:
    """Compute a complexity report for a single file's text."""
    decisions = len(_DECISION_RE.findall(text))
    loc = 0
    comments = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _COMMENT_LINE_RE.match(stripped):
            comments += 1
        else:
            loc += 1
    cc = decisions + 1  # McCabe: one base path plus each decision point.
    return ComplexityReport(cc, loc, comments, decisions, _rate(cc))
