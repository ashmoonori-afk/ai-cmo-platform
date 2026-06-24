# User Pipeline

This is the sellable request-to-delivery pipeline for AI CMO Platform.
It is implemented by `playbooks/00-chains/ai-cmo-operating-system.md`.

## Pipeline

| Phase | Owner | Output | Gate |
|-------|-------|--------|------|
| 1. Intake | CMO | Client, goal, audience, constraints, owner, deadline, assets. | Missing required fields trigger Neurosis. |
| 2. Clarify | Neurosis pattern | One approved executable brief. | Ask one question at a time until the brief is actionable. |
| 3. Triage | CMO | Route to strategy, intelligence, content, sales, SEO, analytics, or operations. | Route must map to a playbook or role SOP. |
| 4. Plan | Odyssey pattern | Short step plan with acceptance criteria. | Complex chains verify each step before moving on. |
| 5. Execute | Specialist role | Draft artifact from the target playbook. | Role SOP evidence requirements must be satisfied. |
| 6. Visual handoff | codex-image-gen pattern | Prompt brief plus `visual_asset_status`; generated assets require `png_path`. | Never claim a generated image exists without a file path. |
| 7. Review | Reviewer | PASS, WARN, FAIL, or ESCALATE. | Facts, structure, brand, channel, and risk are checked. |
| 8. Deliver | Reporter/CMO | Final output path, summary, next actions. | Owner and follow-up trigger are visible. |
| 9. Improve | Morpheus pattern | Maintenance note and proposed SOP/KB refinements. | Consequential changes remain approval-gated. |

## Intake Minimum

```yaml
client:
goal:
audience:
artifact:
decision_owner:
deadline:
assets_available:
risk_level:
```

## Done Definition

A user request is complete only when:

- the final artifact exists under `outputs/{client}/`
- reviewer result is recorded
- evidence sources are visible
- follow-up owner and trigger are listed
- durable learning is recorded or queued
