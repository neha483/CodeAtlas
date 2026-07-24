"""Central configuration for a CodeAtlas run.

Everything tunable lives here so the rest of the code stays declarative.
Values can be overridden from the command line (see run_codeatlas.py) or
through environment variables, which keeps secrets out of the source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


# File extensions CodeAtlas knows how to reason about, mapped to a language
# label. Anything not in this table is treated as an opaque/no-parse asset.
LANGUAGE_BY_EXTENSION = {
    ".java": "java",
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".rb": "ruby",
    ".kt": "kotlin",
    ".cs": "csharp",
    ".php": "php",
    ".rs": "rust",
    ".sql": "sql",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".xml": "xml",
    ".gradle": "gradle",
}

# Directories that never carry meaningful source and only bloat the scan.
DEFAULT_IGNORED_DIRS = {
    ".git", ".idea", ".vscode", "node_modules", "target", "build",
    "dist", "out", "__pycache__", ".mvn", ".gradle", "venv", ".venv",
    "bin", "obj", ".pytest_cache",
}


@dataclass
class AtlasConfig:
    """Immutable-ish run configuration passed down the pipeline."""

    # Where to read the code from and where to write the report.
    root_path: str
    output_path: str = "output/knowledge.json"

    # Model + provider selection. `provider` is one of: openai, anthropic,
    # offline. When credentials are missing we degrade gracefully to
    # `offline`, which uses the deterministic heuristic summariser.
    provider: str = field(default_factory=lambda: os.getenv("ATLAS_PROVIDER", "offline"))
    model_name: str = field(default_factory=lambda: os.getenv("ATLAS_MODEL", "gpt-4o-mini"))
    temperature: float = 0.1

    # Token budgeting. `max_tokens_per_chunk` is the ceiling for a single
    # request payload; `chunk_overlap_tokens` preserves context across splits.
    max_tokens_per_chunk: int = 2800
    chunk_overlap_tokens: int = 120

    # Scanning behaviour.
    languages: List[str] = field(default_factory=lambda: list(LANGUAGE_BY_EXTENSION.values()))
    ignored_dirs: set = field(default_factory=lambda: set(DEFAULT_IGNORED_DIRS))
    max_file_bytes: int = 400_000          # skip pathologically large files
    max_files: int = 0                     # 0 == unlimited

    def api_key(self) -> str | None:
        """Return the relevant API key for the chosen provider, if any."""
        if self.provider == "openai":
            return os.getenv("OPENAI_API_KEY")
        if self.provider == "anthropic":
            return os.getenv("ANTHROPIC_API_KEY")
        return None
