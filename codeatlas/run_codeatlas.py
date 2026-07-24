#!/usr/bin/env python3
"""CodeAtlas command-line entry point.

Examples
--------
    # Offline heuristic mode (no API key needed) on the bundled sample:
    python run_codeatlas.py --path sample_project --output output/knowledge.json

    # LLM-authored analysis with OpenAI:
    export OPENAI_API_KEY=sk-...
    python run_codeatlas.py --path /path/to/repo --provider openai --model gpt-4o-mini

    # Analyse the reference Spring project after cloning it locally:
    git clone https://github.com/codejsha/spring-rest-sakila
    python run_codeatlas.py --path spring-rest-sakila --provider openai
"""

from __future__ import annotations

import argparse
import sys
import time

from codeatlas.aggregator import KnowledgeAggregator
from codeatlas.config import AtlasConfig


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="codeatlas",
        description="Extract structured knowledge from a codebase into JSON.",
    )
    parser.add_argument("--path", "-p", required=True, help="Root of the codebase to analyse.")
    parser.add_argument("--output", "-o", default="output/knowledge.json",
                        help="Where to write the JSON report.")
    parser.add_argument("--provider", default=None,
                        choices=["offline", "openai", "anthropic"],
                        help="LLM provider. Defaults to ATLAS_PROVIDER or 'offline'.")
    parser.add_argument("--model", default=None, help="Model name (provider-specific).")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="Token budget per chunk (default 2800).")
    parser.add_argument("--max-files", type=int, default=0,
                        help="Limit number of files analysed (0 = all).")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output.")
    return parser.parse_args(argv)


def _build_config(args: argparse.Namespace) -> AtlasConfig:
    config = AtlasConfig(root_path=args.path, output_path=args.output)
    if args.provider:
        config.provider = args.provider
    if args.model:
        config.model_name = args.model
    if args.max_tokens:
        config.max_tokens_per_chunk = args.max_tokens
    config.max_files = args.max_files
    return config


def _load_dotenv_if_available() -> None:
    """Load a local .env for convenience; silently skip if not installed."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass


def main(argv=None) -> int:
    _load_dotenv_if_available()
    args = _parse_args(argv)
    config = _build_config(args)

    def progress(i: int, total: int, rel_path: str) -> None:
        if not args.quiet:
            print(f"  [{i:>3}/{total}] {rel_path}", file=sys.stderr)

    aggregator = KnowledgeAggregator(config, progress=progress)
    if not args.quiet:
        print(f"CodeAtlas — mode: {aggregator.effective_mode}", file=sys.stderr)
        print(f"Scanning: {config.root_path}\n", file=sys.stderr)

    started = time.time()
    report = aggregator.run()
    out_path = aggregator.write(report)
    elapsed = time.time() - started

    stats = report["statistics"]
    if not args.quiet:
        print(
            f"\nDone in {elapsed:.2f}s — {stats['file_count']} files, "
            f"{stats['total_methods']} methods, avg CC "
            f"{stats['average_cyclomatic_complexity']}.",
            file=sys.stderr,
        )
    print(out_path)  # stdout gets the artifact path for easy scripting.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
