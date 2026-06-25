# Workflow Engine

## Verdict

The reviewed recommendation is correct for this repository: the product should
not start by building an n8n-style visual automation system. The first
version is a thin compiler/executor around the existing Markdown operating
system:

```text
Markdown playbook
  -> workflow YAML/JSON spec
  -> runner
  -> local or external agent/tool adapter
  -> artifact ledger
  -> reviewer gate
  -> reporter/KB queue
```

The current implementation keeps the Markdown assets as the source of operating
truth and adds only the state machine needed to make runs repeatable.

## Runtime Surface

| Layer | Path | Responsibility |
|-------|------|----------------|
| Workflow specs | `workflows/*.workflow.yaml` | Declare step order, inputs, dependencies, outputs, and gates. |
| Runner | `src/aicmo/runner.py` | Execute the DAG, skip successful steps, resume failed runs, and stop at gates. |
| Store | `src/aicmo/store.py` | Keep SQLite state for workflows, runs, steps, artifacts, events, approvals, and KB update queues. |
| CLI | `src/aicmo/cli.py` | Provide `run`, `status`, `resume`, `approve`, `reject`, `retry`, `list-runs`, plus the value-layer commands `onboard`, `evaluate`, `mockup`, `serve`, and `kb-flush`. `run`/`resume` also take `--executor` (local/claude/codex/anthropic) and `--review` for the gate's semantic reviewer. |
| Playbooks and agents | `playbooks/`, `agents/`, `prompts/shared/` | Remain the human-readable SOP source. |
| Artifacts | `artifacts/{run_id}/` | Store deterministic step outputs and gate payloads. |
| Local state | `.aicmo/runs.sqlite3` | Store resumable execution state. |

## CLI

Run the sample blog workflow:

```powershell
uv run aicmo run blog-article --client sample-client-a --topic "기업 꽃 구독"
```

Use a deterministic run id when testing:

```powershell
uv run aicmo run blog-article --client sample-client-a --topic "기업 꽃 구독" --run-id run_demo_001
uv run aicmo status run_demo_001
uv run aicmo resume run_demo_001
```

Run the approval demo:

```powershell
uv run aicmo run approval-demo --client sample-client-a --run-id run_approval_001
uv run aicmo status run_approval_001
uv run aicmo approve run_approval_001 owner_gate --reviewer owner --notes "Approved"
uv run aicmo resume run_approval_001
```

Use `aicmo reject` to record a terminal rejected gate. Use `aicmo retry` only
for failed non-terminal steps after the source artifact is fixed. A rejected
manual gate keeps its decision immutable; start a new run when the owner wants
to reverse a rejection.

## SQLite Tables

| Table | Purpose |
|-------|---------|
| `workflows` | Registered spec id, name, and source path. |
| `runs` | One execution instance with inputs and current status. |
| `steps` | Per-step status, attempt count, output paths, and errors. |
| `artifacts` | File ledger for every persisted output. |
| `events` | Append-only run and step timeline. |
| `approvals` | Manual approval or rejection decisions. |
| `kb_updates` | Reporter-owned durable learning queue. |

`run_id + step_id` is the idempotency key. A successful step is skipped on
resume. A failed step is attempted again when the missing dependency or prompt
is fixed. Output paths are fixed by the workflow spec, so a resumed run writes
to the same artifact locations.

The runner rejects unsafe ids and graph specs before execution:

- `workflow_id` and `run_id` must be simple local identifiers;
- output and input paths must stay inside the repository;
- duplicate step ids, unknown dependencies, cycles, and duplicate output paths
  fail spec validation;
- a `run_id` cannot be reused with a different workflow or different inputs;
- retry, approval, and rejection commands fail when the target step does not
  exist.

## Gate Semantics

Reviewer gates use the same vocabulary as `prompts/shared/gate-check.md`:

| Status | Meaning |
|--------|---------|
| `PASS` | Continue and deliver. |
| `WARN` | Continue with visible warning and follow-up owner. |
| `FAIL` | Stop and retry the source step after correction. |
| `ESCALATE` | Stop and ask the user or decision owner. |
| `WAITING_APPROVAL` | Stop until `aicmo approve` or `aicmo reject`. |

The MVP gate writes deterministic local payloads. Live review by Hermes,
Claude, OpenAI, or Codex should be added behind an adapter, not by weakening
the state machine.

## Adapter Boundary

The first adapter is intentionally local and deterministic. It reads role files
and prompt files, then writes an artifact that records what would be handed to a
live executor. This proves the runner before adding costly or risky external
calls.

Future adapters should preserve the same contract:

- receive `run_id`, `step_id`, role, prompt path, inputs, and dependency outputs;
- write declared outputs only;
- never update durable KB directly;
- return a typed success, warning, failure, escalation, or approval-needed
  result;
- record enough source paths for Reviewer and Reporter.

## KB Rule

The runner does not write directly to `knowledge-base/`. It records queued KB
updates in SQLite and artifacts. Reporter remains the canonical durable KB
writer, preserving the append-only and de-duplication rules in
`prompts/shared/knowledge-update.md`.

## Product Phases

| Phase | Scope |
|-------|-------|
| 1 | CLI, Markdown artifacts, SQLite state, reviewer gates. |
| 2 | SQLite dashboard over runs, steps, gates, and artifacts. |
| 3 | Web UI for workflow launches and approval review. |
| 4 | External SaaS integrations such as GA, GSC, CRM, browser, and image systems. |

This order keeps the current repository useful from a GitHub link while making
the operating system executable enough to sell and support.
