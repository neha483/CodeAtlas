"""Report assembly.

The aggregator drives the whole pipeline: scan -> extract each file ->
synthesise a project overview -> compute roll-up statistics -> emit one JSON
document. It is the single entry point the CLI calls.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Callable, List, Optional

from . import __version__
from .config import AtlasConfig
from .extractor import FileExtractor
from .llm_client import LangChainLLM, build_llm, heuristic_project_overview
from .prompts import SYSTEM_INSTRUCTION, build_project_prompt
from .scanner import RepositoryScanner


ProgressHook = Optional[Callable[[int, int, str], None]]


class KnowledgeAggregator:
    """Runs the full extraction and produces the final knowledge document."""

    def __init__(self, config: AtlasConfig, progress: ProgressHook = None):
        self.config = config
        self.progress = progress
        self.llm: Optional[LangChainLLM] = build_llm(config)

    @property
    def effective_mode(self) -> str:
        return "llm:" + self.config.provider if self.llm else "offline-heuristic"

    def run(self) -> dict:
        scanner = RepositoryScanner(self.config)
        files = scanner.discover()
        extractor = FileExtractor(self.config, self.llm)

        file_records: List[dict] = []
        for i, source in enumerate(files, start=1):
            if self.progress:
                self.progress(i, len(files), source.rel_path)
            file_records.append(extractor.extract(source))

        overview = self._synthesise_overview(file_records)
        statistics = self._roll_up(file_records)

        return {
            "metadata": {
                "generator": "CodeAtlas",
                "version": __version__,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "root_analysed": os.path.abspath(self.config.root_path),
                "extraction_mode": self.effective_mode,
                "model": self.config.model_name if self.llm else None,
            },
            "project_overview": overview,
            "statistics": statistics,
            "files": file_records,
        }

    def _synthesise_overview(self, file_records: List[dict]) -> dict:
        if self.llm is None:
            return heuristic_project_overview(file_records)

        # Send only compact summaries to the model to stay well within limits.
        compact = [
            {
                "path": r["path"],
                "role": r["primary_role"],
                "summary": r["knowledge"].get("summary", ""),
            }
            for r in file_records
        ]
        prompt = build_project_prompt(json.dumps(compact, ensure_ascii=False))
        try:
            return self.llm.invoke_json(SYSTEM_INSTRUCTION, prompt)
        except Exception:
            # If synthesis fails, don't lose the whole run — fall back locally.
            return heuristic_project_overview(file_records)

    @staticmethod
    def _roll_up(file_records: List[dict]) -> dict:
        by_language: dict[str, int] = {}
        by_role: dict[str, int] = {}
        total_methods = 0
        total_lines = 0
        complexity_sum = 0
        hotspots = []

        for record in file_records:
            by_language[record["language"]] = by_language.get(record["language"], 0) + 1
            by_role[record["primary_role"]] = by_role.get(record["primary_role"], 0) + 1
            total_methods += record["structure"]["method_count"]
            total_lines += record["lines"]
            cc = record["complexity"]["cyclomatic_complexity"]
            complexity_sum += cc
            if record["complexity"]["rating"] in ("high", "very-high"):
                hotspots.append({"path": record["path"], "cyclomatic_complexity": cc})

        n = len(file_records) or 1
        hotspots.sort(key=lambda h: -h["cyclomatic_complexity"])
        return {
            "file_count": len(file_records),
            "total_lines": total_lines,
            "total_methods": total_methods,
            "files_by_language": dict(sorted(by_language.items(), key=lambda kv: -kv[1])),
            "files_by_role": dict(sorted(by_role.items(), key=lambda kv: -kv[1])),
            "average_cyclomatic_complexity": round(complexity_sum / n, 2),
            "complexity_hotspots": hotspots[:10],
        }

    def write(self, report: dict) -> str:
        out_path = os.path.abspath(self.config.output_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
        return out_path
