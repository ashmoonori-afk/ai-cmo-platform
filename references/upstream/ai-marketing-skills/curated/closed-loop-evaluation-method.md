# Closed-Loop Evaluation Method

> Upstream source path: `closed-loop-analytics-upgrade/SKILL.md`
> Upstream commit: `6a6626727dc10644d8c4e54c39da207fea5d1089`
> License: MIT, Copyright (c) 2026 Single Grain
> Status: modified/sanitized for reference-only use

## Purpose

A change is not validated merely because it was completed. Closed-loop
evaluation compares a defined candidate with a relevant baseline, records the
outcome, and updates guidance only when the evidence supports doing so.

This reference assumes that measurements are already available as approved,
static inputs. It does not define data acquisition or external-system actions.

## Evaluation cycle

1. **Frame the change.** State one testable difference, its intended outcome,
   owner, audience, and measurement window.
2. **Define the baseline.** Select a comparable prior window or control and
   record why the comparison is suitable.
3. **Choose metrics in advance.** Name one primary metric, relevant guardrails,
   and diagnostic measures before reviewing the result.
4. **Compare like with like.** Normalize for exposure, time, audience, and cost
   where possible. Retain the raw values alongside normalized measures.
5. **Identify confounders.** Note seasonality, simultaneous changes, sample
   size, missing observations, and attribution uncertainty.
6. **Classify the result.** Use `promote`, `continue testing`, `revert`, or
   `unproven`; do not force a winner from weak evidence.
7. **Record the learning.** Capture the narrow rule supported by the evidence,
   its limits, and the next review condition.

## Measurement families

Choose only measures that fit the decision:

- **Reach:** qualified exposure or discoverability.
- **Engagement:** meaningful interaction normalized by exposure.
- **Progression:** movement to the next intended stage.
- **Outcome:** completed value event attributable to the change.
- **Quality:** review score, correction rate, or defect rate.
- **Efficiency:** elapsed time, resource use, or cost per accepted outcome.
- **Durability:** whether the effect persists across later observations.

A proxy should be labeled as a proxy. Diagnostic measures explain a result but
should not silently replace the declared primary metric.

## Decision rules

Promotion is supportable when the candidate improves the primary metric or
reveals a repeatable, decision-relevant signal while guardrail measures remain
acceptable. The claimed learning should be no broader than the evidence.

Keep the result unproven or continue testing when volume is insufficient,
comparison windows differ materially, attribution is ambiguous, source data is
incomplete, or a separate event plausibly explains the observed change.

Reversion is appropriate when a material guardrail worsens or the candidate
reliably underperforms the baseline. A favorable subjective review alone is not
evidence of outcome improvement.

## Readback record

Each evaluation record should contain:

- change and owner
- hypothesis and intended audience
- baseline and candidate windows
- supplied evidence sources
- primary, guardrail, and diagnostic metrics
- baseline value, candidate value, and delta for each measure
- comparison assumptions
- caveats and confounders
- decision and rationale
- narrowly stated learning
- next test or review condition

## Quality checks

- Was the primary metric chosen before result review?
- Are baseline and candidate genuinely comparable?
- Are absolute values and normalized values both visible where useful?
- Could another change explain the result?
- Are downside measures included?
- Is uncertainty explicit?
- Does the decision follow the predeclared rule?
- Is the retained learning bounded to the tested context?
