# Embedded Birkin-Pattern Skills

These documents place selected Birkin-pattern skills inside AI CMO Platform
workflows. The actual standalone skill instructions are vendored in
`skills/birkin/`, so users do not need a separate Birkin installation.

| Skill | AI CMO placement | Contract | Embedded skill |
|-------|------------------|----------|----------------|
| Neurosis | Before execution when a user request is vague or high stakes. | `neurosis.md` | `../../skills/birkin/neurosis/SKILL.md` |
| Odyssey | Before multi-step work that needs stepwise verification. | `odyssey.md` | `../../skills/birkin/odyssey/SKILL.md` |
| Morpheus | After delivery, for maintenance notes and proposed improvements. | `morpheus.md` | `../../skills/birkin/morpheus/SKILL.md` |
| codex-image-gen | During content or campaign workflows that need a real image. | `codex-image-gen.md` | `../../skills/birkin/codex-image-gen/SKILL.md` |

## Runtime Rule

Do not call external Birkin commands by default. Use the embedded skill docs as
the source of operating instructions. External Birkin tooling is optional only
when an operator explicitly installs it and approves its use.

## Approval Rule

All consequential actions remain approval-gated:

- creating or editing client files
- running external tools
- generating or downloading images
- changing SOPs or memory
- publishing or sending client-facing assets
