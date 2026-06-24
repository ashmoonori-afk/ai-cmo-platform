# Neurosis Handoff

Embedded skill: `../../skills/birkin/neurosis/SKILL.md`

## Use When

Use the Neurosis pattern before execution when the request is vague, high value,
or risky.

## Required Inputs

- raw user request
- client folder or new-client status
- intended artifact
- known constraints
- decision owner

## Expected Output

```yaml
approved_brief:
goal:
audience:
artifact:
constraints:
success_criteria:
decision_owner:
open_questions:
```

## Operating Rule

Ask one clarifying question at a time. Stop asking when the request can be routed
to a role SOP or chain playbook.

## Evidence

Record the final approved brief in the delivery artifact or onboarding report.

## Failure Handling

If the user cannot answer a required question, mark the gap as `[missing]` and
either narrow the scope or escalate to the decision owner.
