---
name: neurosis
description: "Clarify vague marketing requests through one-question-at-a-time interviewing before AI CMO execution."
version: 1.0.0-ai-cmo
license: MIT
source: "Adapted from the Birkin Neurosis skill for standalone AI CMO Platform use."
---

# Neurosis

## Purpose

Use Neurosis when a request is too vague, high value, or risky to execute
directly. The goal is to convert an unclear request into an approved executable
brief before any specialist role starts work.

## When To Use

- The client, goal, audience, output, success metric, owner, or constraint is
  missing.
- The request may affect price, legal, compliance, private data, brand risk, or
  a buyer-facing decision.
- The user asks for deep clarification, interview, requirements, or "do not
  assume."

## When Not To Use

- The request already has a clear client, goal, artifact, audience, acceptance
  criteria, and owner.
- The task is a quick one-off edit with no downstream risk.
- The user explicitly says to skip questions. In that case, mark unknown fields
  as `[missing]` and narrow the scope.

## Procedure

1. Restate the request in Korean in one sentence.
2. Identify missing fields from the intake checklist.
3. Ask exactly one focused question at a time.
4. Prefer questions that remove execution risk rather than questions that add
   optional detail.
5. Stop when the request can be written as an executable brief.
6. Record the approved brief in the output or dogfooding report.

## Executable Brief Format

```yaml
client:
goal:
audience:
artifact:
required_inputs:
constraints:
success_criteria:
decision_owner:
deadline:
missing_fields:
route:
```

## Completion Rule

Neurosis is complete only when the route can move to a role SOP or chain
playbook without inventing client facts.
