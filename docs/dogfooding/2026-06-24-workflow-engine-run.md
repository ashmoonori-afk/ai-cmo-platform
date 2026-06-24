# Dogfooding Run: Workflow Engine MVP

**Date**: 2026-06-24  
**Route**: System/product workflow engine upgrade  
**Owner**: AI CMO Platform maintainer  
**Risk level**: Medium  
**Request**: Validate the recommendation to compile Markdown SOPs into an
executable YAML DAG plus SQLite runner, then implement the engine in this repo.

## Intake

The request required an executable layer without replacing the existing
Markdown-first AI CMO operating system. The accepted product shape was:

```text
Markdown playbook
  -> workflow YAML/JSON spec
  -> runner
  -> agent/tool step
  -> artifact store
  -> reviewer gate
  -> reporter/KB queue
```

## Triage

This was routed to the system/product path because it changes runtime behavior,
handoff usability, README guidance, and dogfooding expectations.

## Execution

Implemented:

- `src/aicmo/` Python package with CLI, spec loader, Pydantic models, SQLite
  store, runner, typed errors, and local deterministic adapters.
- `workflows/blog-article.workflow.yaml` for the main SEO blog workflow.
- `workflows/approval-demo.workflow.yaml` for manual approval gate smoke tests.
- `docs/system/workflow-engine.md` with the validated architecture, state
  tables, CLI contract, adapter boundary, and KB safety rule.
- README and handoff manifest updates for AI agents receiving the GitHub link.
- Tests covering idempotent run, failed-step resume, and manual approval gate.

## Defect Log

| ID | Severity | Surface | Symptom | Root Cause | Fix | Verification | Status |
|----|----------|---------|---------|------------|-----|--------------|--------|
| DF-WFE-001 | medium | pytest import | `aicmo` module was not importable under `uv run pytest`. | `pyproject.toml` lacked a build system for the `src/` layout. | Added Hatch build backend and package target. | `uv run pytest -q` | closed |
| DF-WFE-002 | medium | approval gate | Approved gate resumed as `waiting_approval`. | Runner did not distinguish waiting without approval from approved waiting step. | Resume now treats approved waiting gates as executable. | `uv run aicmo approve ... && uv run aicmo resume ...` | closed |
| DF-WFE-003 | medium | SQLite resources | pytest reported unclosed sqlite connections. | `sqlite3.Connection` context manager commits but does not close. | Wrapped store connections in a closing context manager. | `uv run pytest -q` | closed |
| DF-WFE-004 | low | lint/security | ruff flagged dynamic SQL string assembly in run updates. | Optional completed timestamp used an f-string query branch. | Replaced with fixed SQL branches. | `uv run ruff check src tests` | closed |
| DF-WFE-005 | low | generated files | Python cache files appeared as untracked files. | Test and CLI runs generated `__pycache__`. | Removed caches and ignored `__pycache__/` plus `*.pyc`. | `git status --short --untracked-files=all` | closed |
| DF-WFE-006 | medium | run idempotency | Reusing the same `run_id` with different inputs could silently reuse the existing run. | `ensure_run` inserted with `on conflict do nothing` but did not compare existing inputs. | Added a run conflict guard and regression test. | `uv run pytest -q` | closed |
| DF-WFE-007 | high | path safety | Unsafe workflow ids and run ids could escape intended workflow/artifact paths. | Ids and output templates were only resolved after interpolation, not constrained as local ids. | Added safe id validation and repo-contained path resolution tests. | `uv run pytest -q` | closed |
| DF-WFE-008 | high | workflow graph | Duplicate steps, duplicate dependencies, missing dependencies, cycles, or duplicate outputs were not rejected before execution. | Workflow model parsed structure but did not validate graph invariants. | Added Pydantic graph validation and regression tests. | `uv run pytest -q` | closed |
| DF-WFE-009 | medium | state transitions | Retrying or approving invalid steps could report success. | Store methods did not enforce waiting-gate-only approvals or failed-step-only retries. | Added strict transition guards and regression tests. | `uv run pytest -q` | closed |
| DF-WFE-010 | medium | code structure | `store.py` grew too large for a reliable state-machine review. | Schema, run state, step state, approvals, events, and KB queue lived in one file. | Split the store into DB, schema, run, step, and ledger modules while preserving the `WorkflowStore` API. | `uv run pytest -q` and `uv run basedpyright src tests` | closed |
| DF-WFE-011 | high | gate transition | A rejected manual gate could be overwritten by a later approval before resume. | Approval rows used an upsert and gate decisions were not append-only. | Made gate decisions immutable, fail the run immediately on rejection, and added a rejection terminal regression test. | `uv run pytest -q` | closed |
| DF-WFE-012 | high | CLI run ids | Automatic run ids used second-level timestamps and could collide across fast CLI launches. | `generated_run_id()` lacked an entropy suffix. | Added microsecond timestamp plus UUID token and a same-timestamp uniqueness test. | `uv run pytest -q` | closed |
| DF-WFE-013 | high | rejected retry | `retry` could queue a rejected manual gate even though the immutable rejected approval row made the next resume fail again. | Retry checked failed step status but not terminal approval decisions. | Blocked retry for rejected gates and documented that reversing a rejection requires a new run. | `uv run pytest -q` | closed |
| DF-WFE-014 | medium | CLI errors | Expected CLI failures printed Python tracebacks. | The console-script entrypoint raised `typer.Exit` outside Click's normal suppression path. | Changed handled workflow errors to exit with `SystemExit(1)` after printing a concise error. | rejected-gate retry smoke test | closed |

## Verification

Commands run from the repository root:

```powershell
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run basedpyright src tests
git diff --check
```

Observed results:

- `pytest`: `10 passed`
- `ruff check`: `All checks passed`
- `ruff format --check`: `19 files already formatted`
- `basedpyright`: `0 errors, 0 warnings, 0 notes`
- `git diff --check`: no whitespace errors

Real CLI smoke tests:

```powershell
uv run aicmo run blog-article --client sample-client-a --topic "기업 꽃 구독" --run-id run_cli_20260624_008 --db .aicmo/cli-final-7.sqlite3
uv run aicmo status run_cli_20260624_008 --db .aicmo/cli-final-7.sqlite3
uv run aicmo resume run_cli_20260624_008 --db .aicmo/cli-final-7.sqlite3
```

Result:

- run status: `success`
- step attempts: `load_context=1`, `keyword_research=1`, `draft=1`,
  `review=1`, `report=1`
- artifacts created under `artifacts/run_cli_20260624_008/`

Approval smoke test:

```powershell
uv run aicmo run approval-demo --client sample-client-a --run-id run_cli_approval_009 --db .aicmo/approval-final-8.sqlite3
uv run aicmo approve run_cli_approval_009 owner_gate --reviewer owner --notes Approved --db .aicmo/approval-final-8.sqlite3
uv run aicmo resume run_cli_approval_009 --db .aicmo/approval-final-8.sqlite3
```

Result:

- initial status: `waiting_approval`
- final status: `success`
- approval row: `owner_gate`, `approved`, `owner`
- artifacts created under `artifacts/run_cli_approval_009/`

Rejected gate smoke test:

```powershell
uv run aicmo run approval-demo --client sample-client-a --run-id run_cli_reject_003 --db .aicmo/reject-final-3.sqlite3
uv run aicmo reject run_cli_reject_003 owner_gate --reviewer owner --notes Rejected --db .aicmo/reject-final-3.sqlite3
uv run aicmo retry run_cli_reject_003 owner_gate --db .aicmo/reject-final-3.sqlite3
```

Result:

- retry exits non-zero with a concise error;
- no traceback is printed;
- message: `rejected gate decision is terminal; start a new run`.

## Reviewer Gate

**PASS**

- The engine preserves Markdown playbooks as the operating source.
- Successful steps are idempotent by `(run_id, step_id)`.
- Failed runs resume from the failed step without repeating successful upstream
  steps.
- Manual gates stop the run and require explicit approval or rejection.
- Durable KB records remain Reporter-owned; the runner only queues candidates.
- Runtime state is ignored by Git.

## Reporter Notes

Durable learning candidate:

- A sellable AI CMO workflow engine should start as a CLI-driven YAML DAG plus
  SQLite artifact ledger, not as a visual workflow builder.
- The adapter boundary should be kept behind deterministic local step
  contracts until Hermes, OpenAI, Claude, Codex, browser, image, GA, GSC, and
  CRM adapters are added deliberately.

## Follow-Up Queue

| Priority | Owner | Action | Status |
|----------|-------|--------|--------|
| P1 | Product/engineering | Add workflow spec validation tests for cycles, missing dependency references, and unsafe paths. | closed |
| P2 | Product/engineering | Add a dashboard over SQLite runs and artifacts after CLI adoption is stable. | queued |
| P2 | Agent integrations | Implement live Hermes/OpenAI/Codex adapters behind the current local adapter interface. | queued |
