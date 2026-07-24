"""Source discovery.

The scanner walks the target tree once, filters out noise directories and
binary/oversized files, and yields a small record per source file. It never
loads a file it will not analyse, which keeps memory flat on large repos.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator, List

from .config import AtlasConfig, LANGUAGE_BY_EXTENSION


@dataclass
class SourceFile:
    """A single discovered source file plus its decoded text."""

    path: str            # absolute path on disk
    rel_path: str        # path relative to the scan root (stable id)
    language: str        # resolved language label
    text: str            # decoded file contents
    line_count: int
    byte_size: int


def _looks_binary(sample: bytes) -> bool:
    """Cheap binary sniff: a NUL byte in the first block is a strong signal."""
    return b"\x00" in sample


class RepositoryScanner:
    """Discovers analysable source files under a root directory."""

    def __init__(self, config: AtlasConfig):
        self.config = config

    def _language_for(self, filename: str) -> str | None:
        _, ext = os.path.splitext(filename)
        lang = LANGUAGE_BY_EXTENSION.get(ext.lower())
        if lang and lang in self.config.languages:
            return lang
        return None

    def discover(self) -> List[SourceFile]:
        """Return every source file worth analysing, ordered deterministically."""
        found: List[SourceFile] = []
        root = os.path.abspath(self.config.root_path)

        for current_dir, subdirs, files in os.walk(root):
            # Prune ignored directories in place so os.walk skips them entirely.
            subdirs[:] = sorted(
                d for d in subdirs if d not in self.config.ignored_dirs
            )
            for filename in sorted(files):
                language = self._language_for(filename)
                if language is None:
                    continue

                abs_path = os.path.join(current_dir, filename)
                try:
                    size = os.path.getsize(abs_path)
                except OSError:
                    continue
                if size == 0 or size > self.config.max_file_bytes:
                    continue

                with open(abs_path, "rb") as handle:
                    raw = handle.read()
                if _looks_binary(raw[:1024]):
                    continue

                text = raw.decode("utf-8", errors="replace")
                found.append(
                    SourceFile(
                        path=abs_path,
                        rel_path=os.path.relpath(abs_path, root),
                        language=language,
                        text=text,
                        line_count=text.count("\n") + 1,
                        byte_size=size,
                    )
                )
                if self.config.max_files and len(found) >= self.config.max_files:
                    return found
        return found

    def iter_discover(self) -> Iterator[SourceFile]:
        """Streaming variant for callers that prefer to process lazily."""
        yield from self.discover()
