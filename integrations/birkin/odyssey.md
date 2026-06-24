# Odyssey Handoff

Embedded skill: `../../skills/birkin/odyssey/SKILL.md`

## Use When

Use the Odyssey pattern for complex work that needs more than one role, more than
one artifact, or explicit acceptance checks.

## Required Inputs

- approved brief
- target chain or playbooks
- role owners
- acceptance criteria
- evidence paths

## Expected Output

```yaml
plan:
  - step:
    owner:
    acceptance:
    evidence_path:
phase_status:
blockers:
next_step:
```

## Operating Rule

Plan, critique, execute, and verify one phase at a time. Do not skip reviewer or
evidence gates to move faster.

## Evidence

Each phase must leave a local artifact, reviewer result, or explicit unavailable
status.

## Failure Handling

If a phase fails twice, escalate with options instead of continuing to rewrite
the same artifact.
