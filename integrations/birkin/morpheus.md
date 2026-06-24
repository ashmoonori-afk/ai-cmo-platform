# Morpheus Handoff

## Use When

Use the Morpheus pattern after meaningful work has been delivered and reviewed.
It is for maintenance notes, not unattended automation.

## Required Inputs

- final output path
- reviewer result
- user feedback or performance feedback
- recurring issue or durable learning

## Expected Output

```yaml
learned:
saved:
proposed:
requires_approval:
```

## Operating Rule

Record what was learned, what was saved, and what should be proposed next. Do not
apply consequential changes without explicit approval.

## Evidence

Link the source output, reviewer notes, and target KB or SOP path.

## Failure Handling

If the learning is not durable or evidence-backed, leave it out of memory and put
it in a follow-up queue instead.
