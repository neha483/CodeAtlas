"""
CodeAtlas — an automated codebase knowledge-extraction toolkit.

CodeAtlas walks a source tree, understands its structure per language,
splits it into token-safe units of work, and asks a Large Language Model
to summarise purpose, key methods and noteworthy characteristics. The
result is emitted as a single, well-structured JSON knowledge file.

The package is intentionally small and composable:

    scanner      -> discover source files, honouring ignore rules
    language     -> language detection + lightweight structural parsing
    chunker      -> token-aware slicing so nothing overruns the model window
    complexity   -> heuristic cyclomatic-complexity scoring
    prompts      -> the instruction templates handed to the model
    llm_client   -> a thin LangChain wrapper with an offline fallback
    extractor    -> orchestrates a single file end-to-end
    aggregator   -> folds per-file results into the final report
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
