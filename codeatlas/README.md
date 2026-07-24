# CodeAtlas

**CodeAtlas is a codebase knowledge-extraction toolkit.** Point it at a source
tree and it produces a single, well-structured JSON document describing what the
project does, its key methods and signatures, its architecture, and objective
complexity metrics — using a Large Language Model for the prose and local static
analysis for the numbers.

It was built and validated against the layered structure of the reference
project [`codejsha/spring-rest-sakila`](https://github.com/codejsha/spring-rest-sakila)
(a Spring Boot REST API over the Sakila database), and ships with a small
Spring-style sample project so you can run it immediately without cloning
anything.

---

## 1. What it produces

A single JSON file (`output/knowledge.json`) with four sections:

| Section | Contents |
|---|---|
| `metadata` | Generator version, timestamp, root analysed, extraction mode, model used. |
| `project_overview` | High-level purpose, architecture, primary technologies, key components, cross-cutting observations. |
| `statistics` | Roll-ups: file/method counts, files by language and by role, average cyclomatic complexity, complexity hotspots. |
| `files[]` | Per-file records: path, language, package, detected types, imports, complexity metrics, and the LLM-authored `knowledge` block (summary, responsibilities, methods with signatures + descriptions, dependencies, noteworthy aspects). |

Every response is strict, machine-readable JSON — no markdown, no prose outside
the structure.

---

## 2. Approach & methodology

CodeAtlas is a small, composable pipeline. Each stage is a separate module with
one job, which keeps the design easy to read, test, and extend:

```
 scanner  ->  language  ->  chunker  ->  llm_client  ->  extractor  ->  aggregator
 (find      (structural   (token-safe   (LLM or        (per-file      (project
  files)     parsing)      slicing)      heuristic)     assembly)      report)
```

1. **Scan** (`scanner.py`) — walk the tree once, prune noise directories
   (`node_modules`, `target`, `.git`, …), skip binary/oversized files, and
   decode the rest. Memory stays flat on large repositories.

2. **Understand structure** (`language.py`) — Python is parsed with the standard
   `ast` module (exact); Java / Kotlin / JS / TS / Go / C# are parsed with a
   compact declaration scanner that extracts packages, imports, classes,
   interfaces, enums and method signatures. This gives the model reliable
   anchors and lets us compute metrics without spending tokens.

3. **Respect token limits** (`chunker.py`) — token counts come from `tiktoken`
   when installed (exact for OpenAI models) and from a calibrated char/word
   heuristic otherwise. Files larger than the per-request budget are split along
   natural boundaries (blank lines, then single lines) with a small overlap so a
   symbol spanning a split is still described coherently. **No request ever
   exceeds the configured budget.**

4. **Comprehend** (`llm_client.py` + `prompts.py`) — each chunk is sent to the
   LLM via **LangChain** (`langchain-openai` / `langchain-anthropic`) with a
   strict JSON schema in the prompt. Responses are parsed defensively (markdown
   fences and stray text are tolerated). When no provider/key is configured, a
   deterministic **offline heuristic summariser** produces the same schema from
   the structural parse — so the whole tool runs end-to-end with zero external
   calls.

5. **Assemble** (`extractor.py` + `aggregator.py`) — merge multi-chunk answers
   (union + de-dup of methods, concatenated summaries), synthesise a
   project-level overview from the compact per-file summaries (cheap on tokens),
   compute roll-up statistics, and write one JSON document.

### Choice of LLM

The default target is **`gpt-4o-mini`** via LangChain: it is strong at code
comprehension, cheap enough for whole-repository sweeps, and supports large
context windows. The provider is pluggable — Anthropic Claude models work by
setting `--provider anthropic` — and the offline heuristic mode means the tool
never *hard*-depends on any single vendor.

### Best practices applied

- **Token safety** — every payload is measured and bounded before it is sent;
  project synthesis sees only summaries, never raw code.
- **Machine-readable output** — schema-constrained prompts + defensive JSON
  parsing produce consistent, parseable results.
- **Resilience** — a failed chunk or a failed synthesis call degrades locally
  instead of aborting the run.
- **Separation of concerns** — deterministic metrics are computed locally; only
  natural-language comprehension is delegated to the model.
- **No secrets in source** — credentials come from environment variables / `.env`.

---

## 3. Project layout

```
codeatlas/
├── codeatlas/                 # the package
│   ├── __init__.py
│   ├── config.py              # run configuration + language/ignore tables
│   ├── scanner.py             # source discovery
│   ├── language.py            # structural parsing (Python AST + C-family scanner)
│   ├── chunker.py             # token-aware chunking (tiktoken or heuristic)
│   ├── complexity.py          # cyclomatic-complexity metrics
│   ├── prompts.py             # schema-constrained prompt templates
│   ├── llm_client.py          # LangChain wrapper + offline heuristic summariser
│   ├── extractor.py           # per-file orchestration + chunk merging
│   └── aggregator.py          # pipeline driver + report writer
├── run_codeatlas.py           # command-line entry point
├── tests/test_pipeline.py     # offline verification tests
├── sample_project/            # bundled Spring-style Java app to analyse
├── output/knowledge.json      # example generated report
├── requirements.txt
├── .env.example
└── README.md
```

---

## 4. How to run it

### Requirements
- Python 3.9+ (developed on 3.11).

### Quick start — offline mode (no API key, works immediately)

```bash
cd codeatlas

# (optional) create a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Offline mode needs NO third-party packages. Analyse the bundled sample:
python3 run_codeatlas.py --path sample_project --output output/knowledge.json
```

You'll see per-file progress and a summary line, and `output/knowledge.json`
will be written. This is the fastest way to confirm everything works.

### Full mode — LLM-authored analysis

```bash
# Install the LLM + tokenizer dependencies
pip install -r requirements.txt

# Provide a key (either export it, or copy .env.example -> .env and fill it in)
export OPENAI_API_KEY=sk-...

# Run against any codebase
python3 run_codeatlas.py --path /path/to/your/repo \
    --provider openai --model gpt-4o-mini \
    --output output/knowledge.json
```

### Analyse the reference Spring project

```bash
git clone https://github.com/codejsha/spring-rest-sakila
python3 run_codeatlas.py --path spring-rest-sakila --provider openai
```

### Command-line options

| Flag | Default | Meaning |
|---|---|---|
| `--path`, `-p` | *(required)* | Root of the codebase to analyse. |
| `--output`, `-o` | `output/knowledge.json` | Where to write the JSON report. |
| `--provider` | `offline` (or `$ATLAS_PROVIDER`) | `offline` \| `openai` \| `anthropic`. |
| `--model` | `gpt-4o-mini` (or `$ATLAS_MODEL`) | Model name for the provider. |
| `--max-tokens` | `2800` | Token budget per chunk. |
| `--max-files` | `0` (all) | Cap the number of files analysed. |
| `--quiet` | off | Suppress progress output. |

### Run the tests

```bash
python3 tests/test_pipeline.py          # built-in runner, no pytest needed
# or, if you have pytest:
python3 -m pytest -q
```

---

## 5. Assumptions & limitations

- **Structural parsing is heuristic for non-Python languages.** The C-family
  scanner is regex-based; it reliably captures ordinary declarations but is not
  a full compiler front-end, so exotic generics or macro-heavy code may be
  approximated. Python uses the real `ast` and is exact.
- **Offline mode is deterministic, not generative.** It produces valid,
  well-structured knowledge from the parsed structure and metrics, but the prose
  is templated. Configure an LLM provider for rich, human-quality descriptions.
- **Token counts are exact only with `tiktoken` installed** and only for
  cl100k-based models; otherwise a conservative heuristic is used.
- **Cyclomatic complexity is an approximation** (decision-point counting), which
  is standard for lightweight tooling but can differ slightly from a full
  control-flow analysis.
- **LLM cost/latency scale with repository size.** Use `--max-files` or
  `--max-tokens` to bound a run while iterating.

---

## 6. License / attribution

CodeAtlas is an original implementation written for this task. The reference
repository `codejsha/spring-rest-sakila` is used only as a representative input
shape; none of its code is redistributed here. The bundled `sample_project/` is
original demo code.
