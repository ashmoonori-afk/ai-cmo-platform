# Baseline Inventory

This repository is a Markdown-first AI CMO operating system. The sellable layer
must preserve the existing operating surface while adding clearer buyer-facing
contracts.

## Current Counts

| Surface | Count | Preservation rule |
|---------|-------|-------------------|
| Agents in `agents/` | 10 | Keep existing agent names and prompt contracts. |
| Core playbooks in `playbooks/01-*` through `playbooks/07-*` | 33 | Do not delete, rename, or renumber the existing core playbooks. |
| Chain playbooks in `playbooks/00-chains/` | 4 | Existing chains remain usable; `ai-cmo-operating-system.md` is the new user pipeline. |
| Routing rows in `CLAUDE.md` | 43 | Do not reduce the existing natural-language routing map. |
| Shared prompts in `prompts/shared/` | 3 | Keep the reviewer and KB record policies non-destructive. |

## Protected Dirty Work

Do not overwrite or revert these paths without explicit user approval:

- `CLAUDE.md`
- `agents/reviewer.md`
- `AI-CMO-Platform-사용설명서.md`
- `AI-CMO-Platform-카톡공유용.md`
- existing `.omo/` state

## Sellable Additions

| Addition | Path | Purpose |
|----------|------|---------|
| Role SOP standard | `docs/system/role-sop-standard.md` | Defines the minimum standard for every role SOP. |
| User pipeline | `docs/system/user-pipeline.md` | Explains the upgraded request-to-delivery pipeline. |
| Product positioning | `docs/product/sellable-positioning.md` | Explains what the platform sells. |
| Owner/director comparison | `docs/product/owner-director-comparison.md` | Shows the business operator before/after model. |
| Role SOP playbooks | `playbooks/08-role-sops/` | Gives each role an executable SOP surface. |
| Birkin integration contracts | `integrations/birkin/` | Places Neurosis, Odyssey, Morpheus, and codex-image-gen at approval-gated handoff points. |

## Verification Commands

Run from the repository root.

```powershell
$core = (Get-ChildItem playbooks -Recurse -Filter '*.md' | Where-Object { $_.FullName -match '\\playbooks\\0[1-7]-' }).Count
$chains = (Get-ChildItem playbooks\00-chains -Filter '*.md').Count
$roles = (Get-ChildItem playbooks\08-role-sops -Filter '*.md').Count
$maps = (Select-String -Path CLAUDE.md -Pattern '^\| [0-9]+ \|' -Encoding UTF8).Count
"core=$core chains=$chains role_sops=$roles mappings=$maps"
```

Expected after this upgrade:

- `core=33`
- `chains=4`
- `role_sops=10`
- `mappings=43`
