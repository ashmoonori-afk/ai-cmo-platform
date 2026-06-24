# Dogfooding Procedure

## Purpose

Use the AI CMO Platform on its own product work before shipping. A dogfooding
run proves that the intake, clarity, routing, execution, review, delivery, and
maintenance loop works on a real request, not only in documentation.

## When To Run

Run this procedure before committing or publishing changes that affect:

- `CLAUDE.md`
- `README.md`
- `docs/`
- `playbooks/`
- `agents/`
- `prompts/shared/`
- `integrations/`
- `handoff/`
- `templates/`

## Pipeline Mapping

| AI CMO Phase | Dogfooding Action | Evidence |
|--------------|-------------------|----------|
| Intake | Restate the user's request as an executable internal brief. | Run report includes request, goal, owner, constraints, and risk level. |
| Neurosis clarity gate | Identify missing decisions. Ask the user only when the gap blocks execution or creates risk. | Run report lists resolved and unresolved gaps. |
| Triage | Select system, product, operations, content, sales, analytics, or handoff route. | Run report names the route and source files. |
| Odyssey plan | Break the work into verifiable steps. | Run report includes acceptance criteria for each step. |
| Specialist execution | Edit or create the target docs, SOPs, templates, or handoff files. | Git diff and file paths. |
| Reviewer gate | Check structure, claims, privacy, link paths, handoff usability, and unfinished markers. | Verification command results. |
| Reporter delivery | Record what changed, what was verified, and what remains blocked. | Dogfooding run report and final user summary. |
| Morpheus maintenance | Capture durable improvements without unattended side effects. | Proposed follow-up queue with owner and status. |

## Defect Loop

Every discovered issue must be logged before it is closed.

| Field | Required |
|-------|----------|
| `id` | Stable identifier such as `DF-001`. |
| `severity` | `blocker`, `high`, `medium`, or `low`. |
| `surface` | File, command, link, handoff, or workflow where the issue appeared. |
| `symptom` | What failed or looked unsafe. |
| `root_cause` | Why it happened, or `[unproven]` when not knowable. |
| `fix` | Exact change made. |
| `verification` | Command or review that proves closure. |
| `status` | `closed`, `accepted`, or `blocked-external`. |

Do not mark a run complete while any `blocker`, `high`, or reproducible
`medium` defect remains open.

## Verification Commands

Run from the repository root.

```powershell
git diff --check
git diff --staged --check
rg -n "TO[D]O|TB[D]|FIX[M]E" README.md CLAUDE.md docs playbooks integrations templates handoff agents prompts
rg -n "Role SOP|Owner/Director|User Pipeline|Dogfooding|Neurosis|Odyssey|Morpheus|codex-image-gen|Hermes Agent|OpenClaw" README.md CLAUDE.md docs playbooks integrations templates handoff
rg -n "Sensitive Data Gate|Raw Data Gate|Private Data Gate|민감정보 입력 Gate" playbooks/02-intelligence playbooks/03-content playbooks/04-sales playbooks/06-analytics playbooks/07-operations
Get-Content -LiteralPath "handoff/package-manifest.json" -Raw | ConvertFrom-Json
```

Expected result:

- no whitespace errors;
- unfinished marker scan returns no matches;
- required routing terms appear in intended surfaces;
- private-data gates remain present on sensitive workflows;
- handoff manifest parses as JSON.

## Exit Criteria

A dogfooding run is complete only when:

1. The run report exists in `docs/dogfooding/`.
2. Every discovered defect has a status.
3. No internal blocker remains open.
4. All verification commands pass or the remaining issue is explicitly marked
   `blocked-external`.
5. The final commit includes the run report, unless the run is intentionally
   local-only.
