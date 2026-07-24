"""Per-file extraction orchestration.

For each source file the extractor:
  1. parses its structure (for anchors + metrics),
  2. scores its complexity,
  3. chunks it to fit the token budget,
  4. asks the LLM (or the heuristic summariser) to describe each chunk,
  5. merges chunk-level answers into one file record.

The merge step is what makes multi-chunk files coherent: method lists are
unioned and de-duplicated, summaries are concatenated sensibly.
"""

from __future__ import annotations

from typing import List, Optional

from .chunker import chunk_text
from .complexity import analyse_complexity
from .config import AtlasConfig
from .language import parse_structure
from .llm_client import (
    LangChainLLM,
    heuristic_file_knowledge,
    parse_json_response,
)
from .prompts import SYSTEM_INSTRUCTION, build_file_prompt
from .scanner import SourceFile


def _merge_chunk_knowledge(parts: List[dict]) -> dict:
    """Fold several chunk-level JSON answers into one file-level answer."""
    if len(parts) == 1:
        return parts[0]

    merged = {
        "summary": " ".join(p.get("summary", "").strip() for p in parts if p.get("summary")),
        "responsibilities": [],
        "methods": [],
        "dependencies": [],
        "noteworthy": [],
    }
    seen_methods = set()
    for part in parts:
        for key in ("responsibilities", "dependencies", "noteworthy"):
            for item in part.get(key, []) or []:
                if item not in merged[key]:
                    merged[key].append(item)
        for method in part.get("methods", []) or []:
            marker = (method.get("name"), method.get("signature"))
            if marker not in seen_methods:
                seen_methods.add(marker)
                merged["methods"].append(method)
    return merged


class FileExtractor:
    """Turns one SourceFile into a structured knowledge record."""

    def __init__(self, config: AtlasConfig, llm: Optional[LangChainLLM]):
        self.config = config
        self.llm = llm

    def extract(self, source: SourceFile) -> dict:
        structure = parse_structure(source)
        complexity = analyse_complexity(source.text)

        if self.llm is None:
            # Offline / heuristic path — no chunking or tokens needed.
            knowledge = heuristic_file_knowledge(structure, complexity)
        else:
            knowledge = self._extract_with_llm(source)

        primary_role = knowledge.get("methods", [{}])[0].get("role") if knowledge.get("methods") else None
        return {
            "path": source.rel_path,
            "language": source.language,
            "package": structure.package,
            "lines": source.line_count,
            "primary_role": primary_role or _role_from_path(source.rel_path),
            "structure": {
                "types": [s.name for s in structure.symbols if s.kind in ("class", "interface", "enum", "record")],
                "method_count": sum(1 for s in structure.symbols if s.kind in ("method", "function")),
                "imports": structure.imports[:25],
            },
            "complexity": complexity.as_dict(),
            "knowledge": knowledge,
        }

    def _extract_with_llm(self, source: SourceFile) -> dict:
        chunks = chunk_text(
            source.rel_path,
            source.text,
            budget=self.config.max_tokens_per_chunk,
            overlap=self.config.chunk_overlap_tokens,
        )
        answers: List[dict] = []
        for chunk in chunks:
            prompt = build_file_prompt(
                source.language, source.rel_path, chunk.text, chunk.index, chunk.total
            )
            try:
                answers.append(self.llm.invoke_json(SYSTEM_INSTRUCTION, prompt))
            except Exception as exc:  # keep one bad file from killing the run
                answers.append(
                    {
                        "summary": f"(extraction failed for chunk {chunk.index + 1}: {exc})",
                        "responsibilities": [],
                        "methods": [],
                        "dependencies": [],
                        "noteworthy": [],
                    }
                )
        return _merge_chunk_knowledge(answers)


def _role_from_path(rel_path: str) -> str:
    low = rel_path.lower()
    for needle, role in (
        ("controller", "controller-endpoint"),
        ("resource", "controller-endpoint"),
        ("service", "service-logic"),
        ("repository", "data-access"),
        ("model", "data-model"),
        ("entity", "data-model"),
        ("config", "configuration"),
    ):
        if needle in low:
            return role
    return "helper"
