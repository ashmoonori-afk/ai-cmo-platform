---
name: odyssey
description: "Run complex AI CMO work as a planned, stepwise, verified execution cycle."
version: 1.0.0-ai-cmo
license: MIT
source: "Adapted from the Birkin Odyssey skill for standalone AI CMO Platform use."
---

# Odyssey

## Purpose

Use Odyssey for complex work that needs more than one role, more than one
artifact, or step-by-step verification. It prevents multi-step marketing work
from turning into an untracked draft pile.

## When To Use

- Full strategy, launch planning, onboarding, sales bundles, campaign packages,
  dogfooding, packaging, or repo release work.
- The user asks for ultrawork, end-to-end completion, or "finish until there are
  no bugs."
- The output needs intermediate acceptance criteria.

## When Not To Use

- A simple question, one small document edit, or a single playbook run.
- Pure requirements clarification with no execution. Use Neurosis only.
- Background maintenance after delivery. Use Morpheus.

## Procedure

1. Confirm whether Neurosis is needed first.
2. Create a short plan with independently verifiable steps.
3. Assign each step to a role or system surface.
4. Execute one step at a time.
5. Verify each step against its acceptance criterion before moving on.
6. Record blockers explicitly instead of silently skipping them.
7. Finish only when every step has a status.

## Plan Format

```yaml
goal:
steps:
  - id:
    owner:
    action:
    acceptance:
    evidence_path:
    status:
blockers:
overall_review_status:
```

## Completion Rule

Odyssey is complete only when all essential steps are `pass`, `complete`, or
explicitly `blocked-external` with evidence.
