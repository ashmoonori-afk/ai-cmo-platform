# AI CMO Platform Handoff Package

This folder packages the sellable AI CMO Platform upgrade for downstream agents.
It is intentionally small, explicit, and safe to hand to another coding or
operations agent without exposing local run logs.

## Files

| File | Use |
|------|-----|
| `hermes-agent.md` | Operational handoff for a Hermes-style agent that will route user requests through the platform. |
| `openclaw.md` | Repository handoff for an OpenClaw-style agent that will inspect, verify, extend, or package the project. |
| `package-manifest.json` | Machine-readable inventory of entrypoints, safety gates, and acceptance checks. |

## Primary Entrypoints

| Entrypoint | Purpose |
|------------|---------|
| `README.md` | Human-facing product overview and quick start. |
| `CLAUDE.md` | System brain for natural-language routing, agent dispatch, and safety rules. |
| `playbooks/00-chains/ai-cmo-operating-system.md` | Main upgraded user pipeline. |
| `docs/role-sop/README.md` | Role SOP registry and operating standard. |
| `docs/system/user-pipeline.md` | Detailed intake-to-delivery pipeline. |
| `docs/system/workflow-engine.md` | Executable workflow engine contract, CLI, state tables, and adapter boundary. |
| `docs/system/dogfooding-procedure.md` | Dogfooding procedure for running this platform against its own workflow. |
| `docs/dogfooding/2026-06-24-ai-cmo-platform-run.md` | Completed dogfooding run for this sellable upgrade. |
| `docs/dogfooding/2026-06-24-workflow-engine-run.md` | Completed dogfooding run for the executable workflow engine. |
| `docs/product/owner-director-comparison.md` | Original owner workflow vs upgraded director workflow comparison. |
| `integrations/birkin/README.md` | Birkin skill placement and approval-gated handoff contracts. |
| `skills/README.md` | Embedded standalone skills, no external Birkin install required. |
| `workflows/blog-article.workflow.yaml` | Sample executable workflow spec. |
| `workflows/approval-demo.workflow.yaml` | Manual approval gate smoke-test workflow. |
| `src/aicmo/` | Python runner, SQLite store, local adapters, and CLI. |

## Non-Transfer Local State

`.omo/` contains local planning and review evidence from this workspace. It is
ignored by Git and should not be treated as part of the sellable product
package. The durable product-facing references live in `docs/`, `playbooks/`,
`integrations/`, `skills/`, `templates/`, `agents/`, and `prompts/`.

`.aicmo/` and `artifacts/` are local workflow-engine run state. They are useful
for debugging a specific run, but they are not required when transferring the
repository as a clean product package.
