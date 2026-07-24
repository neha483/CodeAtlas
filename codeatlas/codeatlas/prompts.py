"""Prompt templates handed to the language model.

Keeping prompts in one module makes them easy to audit and tune. Each prompt
demands strict JSON so the response is machine-readable without brittle
post-processing. We describe the exact schema and forbid prose outside the
JSON object — this is the single most reliable way to get parseable output.
"""

from __future__ import annotations

# System role: sets expectations once per request.
SYSTEM_INSTRUCTION = (
    "You are CodeAtlas, a precise static-analysis assistant. You read source "
    "code and return factual, structured knowledge about it. You never invent "
    "APIs that are not present. You respond with a single valid JSON object "
    "and no surrounding commentary, markdown fences, or explanation."
)

# Per-file / per-chunk extraction prompt. `{schema}` is injected below so the
# schema definition lives in exactly one place.
FILE_SCHEMA = """{
  "summary": "one-to-three sentence plain-English description of what this file does",
  "responsibilities": ["short bullet phrases of the file's responsibilities"],
  "methods": [
    {
      "name": "method or function name",
      "signature": "single-line signature",
      "description": "what it does, its inputs and outputs",
      "role": "e.g. controller-endpoint | service-logic | data-access | helper"
    }
  ],
  "dependencies": ["notable frameworks, libraries or internal modules used"],
  "noteworthy": ["design patterns, risks, TODOs, or unusual aspects"]
}"""

FILE_PROMPT = (
    "Analyse the following {language} source file named '{rel_path}'.\n"
    "{chunk_note}\n"
    "Return ONLY a JSON object matching exactly this schema:\n"
    "{schema}\n\n"
    "If a field has no applicable content, use an empty list or empty string. "
    "Do not add keys that are not in the schema.\n\n"
    "----- BEGIN CODE -----\n"
    "{code}\n"
    "----- END CODE -----"
)

# Project-level synthesis prompt: given the per-file summaries, produce the
# high-level overview. Kept compact because it only sees summaries, not code.
PROJECT_SCHEMA = """{
  "project_purpose": "what the whole project is for, in 2-4 sentences",
  "architecture": "how the pieces fit together (layers, modules, data flow)",
  "primary_technologies": ["frameworks/languages/tools that define the stack"],
  "key_components": [
    {"name": "component or layer", "purpose": "its role in the system"}
  ],
  "observations": ["cross-cutting strengths, risks, or improvement ideas"]
}"""

PROJECT_PROMPT = (
    "You are given per-file summaries extracted from a codebase. Synthesise a "
    "high-level project overview. Return ONLY a JSON object matching this "
    "schema:\n{schema}\n\n"
    "----- FILE SUMMARIES (JSON) -----\n"
    "{summaries}\n"
    "----- END -----"
)


def build_file_prompt(language: str, rel_path: str, code: str, chunk_index: int, chunk_total: int) -> str:
    chunk_note = ""
    if chunk_total > 1:
        chunk_note = (
            f"This is part {chunk_index + 1} of {chunk_total} of a file that was "
            "split to fit the context window; describe only what is visible here."
        )
    return FILE_PROMPT.format(
        language=language,
        rel_path=rel_path,
        chunk_note=chunk_note,
        schema=FILE_SCHEMA,
        code=code,
    )


def build_project_prompt(summaries_json: str) -> str:
    return PROJECT_PROMPT.format(schema=PROJECT_SCHEMA, summaries=summaries_json)
