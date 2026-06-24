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
| `docs/system/dogfooding-procedure.md` | Dogfooding procedure for running this platform against its own workflow. |
| `docs/dogfooding/2026-06-24-ai-cmo-platform-run.md` | Completed dogfooding run for this sellable upgrade. |
| `docs/product/owner-director-comparison.md` | Original owner workflow vs upgraded director workflow comparison. |
| `integrations/birkin/README.md` | Birkin skill placement and approval-gated handoff contracts. |

## Non-Transfer Local State

`.omo/` contains local planning and review evidence from this workspace. It is
ignored by Git and should not be treated as part of the sellable product
package. The durable product-facing references live in `docs/`, `playbooks/`,
`integrations/`, `templates/`, `agents/`, and `prompts/`.
