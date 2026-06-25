# OpenClaw Handoff

## Mission

Inspect, maintain, and package the upgraded AI CMO Platform without weakening
the operating rules that make it shareable: role SOPs, reviewer gates, privacy
controls, Birkin integration contracts, and owner/director positioning.

## Repository State To Preserve

| Area | Paths |
|------|-------|
| Product overview | `README.md`, `docs/product/` |
| System rules | `CLAUDE.md`, `prompts/shared/gate-check.md`, `prompts/shared/knowledge-update.md` |
| User pipeline | `docs/system/user-pipeline.md`, `playbooks/00-chains/ai-cmo-operating-system.md` |
| Dogfooding | `docs/system/dogfooding-procedure.md`, `docs/dogfooding/` |
| Role SOPs | `docs/role-sop/README.md`, `playbooks/08-role-sops/` |
| Embedded skills | `skills/birkin/` |
| Birkin contracts | `integrations/birkin/`, `templates/handoffs/birkin/` |
| Core playbooks | `playbooks/01-strategy/` through `playbooks/07-operations/` |
| Client state | `clients/`, `knowledge-base/` |
| Handoff package | `handoff/` |

## Change Discipline

1. Keep `CLAUDE.md` as the routing authority.
2. Keep Reviewer as the final gate for client-facing, owner-facing, sent,
   published, or final artifacts.
3. Keep Reporter as the canonical writer for durable KB records.
4. Do not bypass approval gates for Birkin handoffs, publishing, sending,
   downloads, image generation, or live integrations.
5. Keep role SOP files in the same required-section format documented in
   `docs/system/role-sop-standard.md`.
6. Keep raw-data gates in playbooks that touch GA, CRM, customer feedback,
   sales files, meeting notes, or private analytics.
7. Keep visual workflows on the explicit `visual_asset_status` contract.
8. Keep `skills/birkin/` self-contained so downstream users do not need Birkin
   installed.

## Verification Commands

Run from the repository root:

```powershell
git diff --check
rg -n "Role SOP|Owner/Director|User Pipeline|Dogfooding|Neurosis|Odyssey|Morpheus|codex-image-gen" README.md CLAUDE.md docs playbooks integrations templates handoff
rg -n "TO[D]O|TB[D]|FIX[M]E" README.md CLAUDE.md docs playbooks integrations templates handoff agents prompts
rg -n "Sensitive Data Gate|Raw Data Gate|Private Data Gate|민감정보 입력 Gate" playbooks/02-intelligence playbooks/03-content playbooks/04-sales playbooks/06-analytics playbooks/07-operations
```

Expected result:

- `git diff --check` has no whitespace errors. On Windows it may print LF to
  CRLF warnings.
- Required routing terms appear in the intended docs.
- No unfinished marker appears in product-facing docs or playbooks.
- Raw/private data gates remain present on private-data workflows.

## Packaging Rules

- Include `README.md`, `CLAUDE.md`, `docs/`, `playbooks/`, `agents/`,
  `prompts/`, `integrations/`, `skills/`, `templates/`, `clients/`,
  `knowledge-base/`, and `handoff/`.
- Exclude `.git/`, `.omo/`, `outputs/`, local caches, temporary files, and any
  private client files not intentionally approved for transfer.
- Do not package secrets or environment files.

## Review Checklist

- Owner/director comparison still frames the owner value clearly.
- User pipeline still starts with intake and clarity, then routes to role SOPs.
- Birkin placements remain: Neurosis for clarity, Odyssey for complex
  execution, codex-image-gen for approved visuals, Morpheus for maintenance.
- Role SOPs stay consistent across all 10 roles.
- Safety language is repeated at the route level where sensitive inputs appear.
- Handoff docs match the current repository paths.
- Dogfooding runs list every discovered defect, its fix, and the final
  verification result.
- The embedded skill docs do not require external Birkin paths or commands for
  normal operation.
