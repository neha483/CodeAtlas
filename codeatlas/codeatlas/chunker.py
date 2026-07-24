"""Token-aware chunking.

The single hard constraint when talking to an LLM is the context window.
This module counts tokens with `tiktoken` when it is installed and falls
back to a calibrated word/char heuristic otherwise, then splits oversized
files along natural boundaries (blank lines, then single lines) so a request
never exceeds the configured budget. A small overlap preserves context so a
symbol split across two chunks is still described coherently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

try:  # tiktoken gives exact counts for OpenAI models; optional dependency.
    import tiktoken

    _ENCODER = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:
        return len(_ENCODER.encode(text))

except Exception:  # pragma: no cover - exercised only when tiktoken absent
    def _count_tokens(text: str) -> int:
        # ~1 token per 4 characters is the widely used rule of thumb; we blend
        # it with a word count to stay conservative and avoid under-counting.
        return max(len(text) // 4, int(len(text.split()) * 1.3)) + 1


count_tokens: Callable[[str], int] = _count_tokens


@dataclass
class Chunk:
    """A slice of a file small enough to send to the model in one request."""

    rel_path: str
    index: int
    total: int
    text: str
    token_estimate: int


def _split_oversized_block(block: str, budget: int) -> List[str]:
    """Split a block that is itself larger than the budget, line by line."""
    pieces: List[str] = []
    current: List[str] = []
    running = 0
    for line in block.splitlines(keepends=True):
        line_tokens = count_tokens(line)
        if running + line_tokens > budget and current:
            pieces.append("".join(current))
            current, running = [], 0
        current.append(line)
        running += line_tokens
    if current:
        pieces.append("".join(current))
    return pieces


def chunk_text(rel_path: str, text: str, budget: int, overlap: int = 0) -> List[Chunk]:
    """Break `text` into ordered chunks that each fit within `budget` tokens."""
    if count_tokens(text) <= budget:
        return [Chunk(rel_path, 0, 1, text, count_tokens(text))]

    # First pass: group whole paragraphs (blank-line separated) greedily.
    blocks = text.split("\n\n")
    raw_chunks: List[str] = []
    current: List[str] = []
    running = 0

    for block in blocks:
        block_with_sep = block + "\n\n"
        block_tokens = count_tokens(block_with_sep)

        if block_tokens > budget:
            # Flush what we have, then hard-split the giant block.
            if current:
                raw_chunks.append("".join(current))
                current, running = [], 0
            raw_chunks.extend(_split_oversized_block(block_with_sep, budget))
            continue

        if running + block_tokens > budget and current:
            raw_chunks.append("".join(current))
            current, running = [], 0

        current.append(block_with_sep)
        running += block_tokens

    if current:
        raw_chunks.append("".join(current))

    # Second pass: prepend a small overlap tail from the previous chunk.
    chunks: List[Chunk] = []
    total = len(raw_chunks)
    for i, body in enumerate(raw_chunks):
        if overlap and i > 0:
            tail = raw_chunks[i - 1][-overlap * 4 :]  # ~overlap tokens of chars
            body = tail + body
        chunks.append(Chunk(rel_path, i, total, body, count_tokens(body)))
    return chunks
