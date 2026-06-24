---
name: morpheus
description: "Capture durable learning and proposed improvements after an AI CMO delivery without unattended side effects."
version: 1.0.0-ai-cmo
license: MIT
source: "Adapted from the Birkin Morpheus skill for standalone AI CMO Platform use."
---

# Morpheus

## Purpose

Use Morpheus after meaningful work has been delivered and reviewed. It captures
what should be remembered, what should be queued, and what should be improved
next without running unattended automation.

## When To Use

- A campaign, strategy, onboarding, dogfooding run, or release is complete.
- Reviewer feedback exposed a repeatable issue.
- A workflow lesson should become a KB candidate, SOP refinement, or follow-up
  action.

## When Not To Use

- During active drafting.
- To perform consequential actions directly.
- To write unsupported memory entries without evidence.

## Procedure

1. Review the final output path and reviewer result.
2. Extract durable learning only when it will help future work.
3. Send KB candidates to Reporter instead of editing durable KB directly from a
   source role.
4. Queue consequential changes for owner approval.
5. Record a compact maintenance note in the delivery artifact.

## Maintenance Note Format

```yaml
source_output:
review_result:
learned:
saved_to:
proposed_change:
approval_needed:
owner:
status:
```

## Completion Rule

Morpheus is complete only when every proposed improvement has an owner and a
status, or is explicitly discarded as non-durable.
