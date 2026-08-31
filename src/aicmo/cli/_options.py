from typing import Annotated

import typer

# Shared executor/reviewer option definitions, reused across run/ingest/resume. run's
# --executor-cmd help diverges (mentions the local-adapter fallback), so it keeps its own.
ExecutorCmdRunOpt = Annotated[
    str | None,
    typer.Option(
        "--executor-cmd",
        help="Live executor; the prompt is piped on stdin (e.g. 'claude -p'). "
        "Omit to use the deterministic local adapter.",
    ),
]
ExecutorCmdOpt = Annotated[
    str | None,
    typer.Option("--executor-cmd", help="Live executor command (prompt piped on stdin)."),
]
ExecutorOpt = Annotated[
    str | None, typer.Option("--executor", help="Preset: local|claude|codex|anthropic"),
]
AnthropicOpt = Annotated[bool, typer.Option("--anthropic", help="Anthropic API executor")]
ReviewOpt = Annotated[
    str | None, typer.Option("--review", help="Reviewer preset: claude|codex|anthropic"),
]
ReviewCmdOpt = Annotated[
    str | None, typer.Option("--review-cmd", help="Semantic gate reviewer command"),
]
ReviewAnthropicOpt = Annotated[
    bool, typer.Option("--review-anthropic", help="Anthropic as gate reviewer"),
]
