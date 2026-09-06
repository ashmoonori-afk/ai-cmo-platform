from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import typer

from aicmo.errors import AicmoError

from . import gate_cmds, inspect_cmds, quota_cmds, run_cmds, tool_cmds
from ._shared import (
    adapter_for_executor as adapter_for_executor,
)
from ._shared import (
    err_console,
)
from ._shared import (
    parse_input_pairs as parse_input_pairs,
)
from .run_cmds import (
    ingest_inbox as ingest_inbox,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def generated_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    return f"run_{timestamp}_{uuid4().hex}"


run_cmds.register(app, generated_run_id)
inspect_cmds.register(app)
gate_cmds.register(app)
run_cmds.register_retry(app)
tool_cmds.register(app)
quota_cmds.register(app)


def main() -> None:
    try:
        app()
    except AicmoError as exc:
        err_console.print(f"error: {exc}", markup=False)
        raise SystemExit(1) from None
    except Exception as exc:  # noqa: BLE001 — top-level CLI guard: surface a clean message
        err_console.print(f"unexpected error: {exc}", markup=False)
        raise SystemExit(1) from None
