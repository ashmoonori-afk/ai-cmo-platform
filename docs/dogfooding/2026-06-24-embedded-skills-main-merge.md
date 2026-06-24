# Dogfooding Run: Embedded Skills and Main Merge

## Intake

| Field | Value |
|-------|-------|
| Request | Make the platform usable for people who download only this repository, fully merge the Birkin-pattern skills, and merge the work into `main`. |
| Client | AI CMO Platform internal product |
| Goal | Remove dependency on a local Birkin checkout for Neurosis, Odyssey, Morpheus, and codex-image-gen workflow behavior. |
| Decision owner | User |
| Risk level | Medium: branch merge and public repository packaging. |

## Neurosis Clarity Gate

| Gap | Resolution |
|-----|------------|
| Does "fully merge" mean live Birkin runtime or standalone repository docs? | Resolved as standalone embedded skill protocols because most users will not have Birkin installed. |
| Should external Birkin commands be required? | No. External Birkin tooling is optional only when explicitly installed and approved. |
| How should `main` be handled? | Preserve `origin/main`, merge the current product branch into it, resolve conflicts, and push `main` without force. |

## Odyssey Plan

| Step | Acceptance | Status |
|------|------------|--------|
| Read source skills | The four source skills are reviewed before adaptation. | PASS |
| Vendor skills | `skills/birkin/*/SKILL.md` exists for all four skills. | PASS |
| Update routing | README, CLAUDE, handoff, integrations, and system docs point to embedded skill paths. | PASS |
| Verify package | Search and JSON checks prove self-contained references. | PASS |
| Merge to main | `main` includes embedded skills and prior `origin/main` history without force push. | PASS |

## Defect Log

| ID | Severity | Surface | Symptom | Fix | Verification | Status |
|----|----------|---------|---------|-----|--------------|--------|
| ESM-001 | high | `integrations/birkin/` and handoff docs | Skill behavior was documented as handoff contracts but not included for users without Birkin. | Added standalone `skills/birkin/` protocols and rewired docs to those paths. | `rg -n "skills/birkin"` across routing docs. | closed |
| ESM-002 | medium | Branch topology | `origin/main` and `master` had unrelated histories. | Merged with unrelated histories while preserving `origin/main` client/design assets and adding embedded skills. | `git log --graph --all` and final push to `main`. | closed |

## Reviewer Gate

Final verification must pass:

- `git diff --check`
- manifest JSON parse
- required embedded skill search
- unfinished marker scan
- sensitive-data gate scan
- `main` tracks `origin/main` after push

## Verification Notes

Package verification passed before the `main` merge:

- `git diff --check` passed with only Windows LF-to-CRLF warnings.
- `handoff/package-manifest.json` parsed and reports
  `external_birkin_required=false`.
- `skills/birkin/*/SKILL.md` exists for all four embedded protocols.
- No unfinished marker was found in README, CLAUDE, docs, playbooks,
  integrations, templates, handoff, skills, agents, or prompts.
- Sensitive-data gates remain present across private-data workflows.
