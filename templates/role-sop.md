# {Role} SOP

## Purpose

{One sentence explaining why this role exists.}

## Use When

- {Trigger 1}
- {Trigger 2}

## Do Not Use When

- {Route elsewhere}

## Inputs

| Field | Required | Notes |
|-------|----------|-------|
| `client` | yes | Client folder name. |
| `artifact` | yes | Requested output or upstream file. |
| `decision_owner` | yes for client-facing work | Person who approves the output. |

## Required Context

- `clients/{client}/config.md`
- `knowledge-base/{client}/insights.md`
- role-specific upstream artifacts

## Source Policy

- Cite URLs or local paths for factual claims.
- Mark unsupported inferences as `[inferred]`.
- Mark stale sources as `[old: YYYY-MM]`.
- Ask one clarifying question when a required input is missing.

## Execution Steps

1. Load required context.
2. Restate the decision or artifact.
3. Gather evidence.
4. Produce the artifact in the target template.
5. Complete the evidence ledger.
6. Send to reviewer.
7. Hand off durable learning to reporter.

## Output Contract

```yaml
output_path:
review_status:
source_files:
source_urls:
next_action:
owner:
```

## Evidence Ledger

| claim | source | path | confidence | verified_by | date |
|-------|--------|------|------------|-------------|------|
| {claim} | {URL or local source} | {output or data path} | {high/medium/low/inferred} | {role/reviewer} | {YYYY-MM-DD} |

## Reviewer Checks

- required sections are present
- sources and local paths exist where claimed
- safety gate in `prompts/shared/gate-check.md` passes
- client facts match `clients/{client}/config.md`
- final output includes next action, owner, and follow-up trigger when relevant

## Failure Modes

| Status | Condition | Action |
|--------|-----------|--------|
| WARN | Non-blocking gap. | Deliver with warning. |
| FAIL | Required section or evidence missing. | Return correction instructions. |
| ESCALATE | Approval or business decision needed. | Ask the decision owner. |

## Handoff

- Send final artifacts to Reviewer before client-facing delivery.
- Send durable learning candidates to Reporter for non-destructive KB handling.
- Route KB candidates to Reporter under `prompts/shared/knowledge-update.md`.
