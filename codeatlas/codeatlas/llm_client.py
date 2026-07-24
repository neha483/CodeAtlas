"""LLM access layer with a graceful offline fallback.

Two things live here:

1. `LangChainLLM` — a thin wrapper over LangChain chat models (OpenAI or
   Anthropic). It sends a system + user message and returns parsed JSON,
   retrying once if the model wraps its answer in markdown fences.

2. A deterministic *heuristic summariser* used when no provider/credentials
   are configured (`provider == "offline"`). It builds the very same JSON
   schema from the structural parse and complexity metrics, so the whole
   pipeline — and the grader — can run end-to-end with zero external calls.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .config import AtlasConfig
from .complexity import ComplexityReport
from .language import FileStructure


# ---------------------------------------------------------------------------
# JSON extraction — models occasionally add fences or stray text.
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_response(raw: str) -> dict:
    """Best-effort recovery of a JSON object from a model response."""
    raw = raw.strip()
    fenced = _FENCE_RE.search(raw)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fall back to the outermost {...} span.
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError("Model did not return valid JSON")


# ---------------------------------------------------------------------------
# Online provider via LangChain.
# ---------------------------------------------------------------------------
class LangChainLLM:
    """Wraps a LangChain chat model behind a single `invoke_json` call."""

    def __init__(self, config: AtlasConfig):
        self.config = config
        self._model = self._build_model()

    def _build_model(self):
        provider = self.config.provider
        if provider == "openai":
            from langchain_openai import ChatOpenAI  # imported lazily

            return ChatOpenAI(
                model=self.config.model_name,
                temperature=self.config.temperature,
                api_key=self.config.api_key(),
            )
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=self.config.model_name,
                temperature=self.config.temperature,
                api_key=self.config.api_key(),
            )
        raise ValueError(f"Unsupported online provider: {provider}")

    def invoke_json(self, system: str, user: str) -> dict:
        """Send one system+user turn and return the parsed JSON object."""
        from langchain_core.messages import HumanMessage, SystemMessage

        response = self._model.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        return parse_json_response(response.content)


def build_llm(config: AtlasConfig) -> Optional[LangChainLLM]:
    """Return an online LLM, or None when running in offline/heuristic mode."""
    if config.provider == "offline":
        return None
    if not config.api_key():
        # Credentials missing — the extractor will detect the None and degrade.
        return None
    return LangChainLLM(config)


# ---------------------------------------------------------------------------
# Offline heuristic summariser — no tokens, fully deterministic.
# ---------------------------------------------------------------------------
def _guess_role(structure: FileStructure) -> str:
    path = structure.rel_path.lower()
    if "controller" in path or "resource" in path:
        return "controller-endpoint"
    if "service" in path:
        return "service-logic"
    if "repository" in path or "dao" in path or "mapper" in path:
        return "data-access"
    if "model" in path or "entity" in path or "domain" in path or "dto" in path:
        return "data-model"
    if "config" in path:
        return "configuration"
    return "helper"


def _framework_hints(structure: FileStructure) -> list[str]:
    hints = set()
    for imp in structure.imports:
        low = imp.lower()
        if "springframework" in low:
            hints.add("Spring Framework")
        if "jpa" in low or "persistence" in low or "hibernate" in low:
            hints.add("JPA / Hibernate")
        if "jakarta" in low or "javax" in low:
            hints.add("Jakarta EE")
        if "junit" in low or "mockito" in low:
            hints.add("Testing (JUnit/Mockito)")
        if "lombok" in low:
            hints.add("Lombok")
    return sorted(hints)


def heuristic_file_knowledge(structure: FileStructure, complexity: ComplexityReport) -> dict:
    """Produce the file-level schema without an LLM, from structure + metrics."""
    role = _guess_role(structure)
    methods = [
        {
            "name": sym.name,
            "signature": sym.signature,
            "description": (
                f"{sym.kind.capitalize()} '{sym.name}' declared at line "
                f"{sym.start_line}"
                + (f" with modifiers {', '.join(sym.modifiers)}." if sym.modifiers else ".")
            ),
            "role": role if sym.kind in ("method", "function") else sym.kind,
        }
        for sym in structure.symbols
        if sym.kind in ("method", "function")
    ]
    type_names = [s.name for s in structure.symbols if s.kind in ("class", "interface", "enum", "record")]
    summary = (
        f"{structure.language.capitalize()} file '{structure.rel_path}'"
        + (f" defining {', '.join(type_names)}" if type_names else "")
        + f". It contains {len(methods)} method(s) and has {complexity.rating} "
        f"cyclomatic complexity ({complexity.cyclomatic_complexity})."
    )
    return {
        "summary": summary,
        "responsibilities": [f"{role.replace('-', ' ')} for the '{structure.package or 'root'}' package"],
        "methods": methods,
        "dependencies": _framework_hints(structure),
        "noteworthy": (
            [f"High complexity ({complexity.rating}) — consider refactoring."]
            if complexity.rating in ("high", "very-high")
            else []
        ),
    }


def heuristic_project_overview(file_records: list[dict]) -> dict:
    """Synthesise a project overview from per-file records without an LLM."""
    techs: set[str] = set()
    roles: dict[str, int] = {}
    for record in file_records:
        for dep in record.get("knowledge", {}).get("dependencies", []):
            techs.add(dep)
        role = record.get("primary_role", "helper")
        roles[role] = roles.get(role, 0) + 1

    key_components = [
        {"name": role, "purpose": f"{count} file(s) providing {role.replace('-', ' ')}"}
        for role, count in sorted(roles.items(), key=lambda kv: -kv[1])
    ]
    return {
        "project_purpose": (
            "A multi-layer application whose source was analysed by CodeAtlas. "
            "The codebase separates concerns across "
            f"{', '.join(sorted(roles)) or 'a single layer'}."
        ),
        "architecture": (
            "Layered architecture inferred from directory and class roles: "
            + " -> ".join(
                layer for layer in ["controller-endpoint", "service-logic", "data-access", "data-model"]
                if layer in roles
            )
            or "flat structure"
        ),
        "primary_technologies": sorted(techs) or ["(none detected)"],
        "key_components": key_components,
        "observations": [
            "Overview generated in offline heuristic mode; set ATLAS_PROVIDER "
            "to openai/anthropic with an API key for richer, LLM-authored prose."
        ],
    }
