# Personal Strategic Signal Intelligence Method

> Upstream source paths: `personal-strategic-signal-intelligence/SKILL.md` and
> `personal-strategic-signal-intelligence/README.md`
> Upstream commit: `6a6626727dc10644d8c4e54c39da207fea5d1089`
> License: MIT, Copyright (c) 2026 Single Grain
> Status: modified/sanitized for reference-only use

## Purpose and boundary

This method turns a consenting person's supplied reading history, highlights,
notes, decision records, and applied work into source-grounded decision support.
It distinguishes attention from conviction and treats inferred beliefs as
private hypotheses rather than declared facts.

It is unsuitable for personality diagnosis, hidden-motive claims, assessment of
other people from private activity, or broad archive summaries without a
decision question.

## Evidence strength

Evidence becomes stronger as engagement becomes more deliberate and outcomes
become observable:

| Level | Evidence event | Default interpretation |
|---:|---|---|
| 1 | Save, reaction, follow, or bookmark | Weak attention |
| 2 | Similar saves recur across time or sources | Sustained attention |
| 3 | Item marked as completed reading | Deliberate exposure |
| 4 | Highlight or annotation | Salient idea |
| 5 | Original note or synthesis | Active interpretation |
| 6 | Stated belief or decision reference | Expressed conviction |
| 7 | Experiment, prototype, purchase, or operating change | Applied conviction |
| 8 | Repeated application with a measured result | Validated operating belief |

These levels are defaults, not proof by themselves. Accumulating weak events
does not automatically create a strong claim.

## Evidence and claim records

A source record should preserve a stable identifier, source type, capture and
engagement dates, engagement type, minimal relevant excerpt, optional
user-authored text, privacy classification, and a content fingerprint.

A derived claim should preserve:

- a stable claim identifier and concise statement
- claim type: observation, private inferred belief, hypothesis, or recommendation
- identifiers for primary supporting and contradicting evidence
- identifiers for any derived material used for navigation
- confidence level, creation date, and intended audience

Material claims require primary source identifiers. A question or hypothesis
without direct evidence must be labeled accordingly.

## Lineage rules

1. Primary evidence is a source item, explicit statement, observed application,
   or measured outcome.
2. A summary, cluster, score, or previous inference is derived evidence.
3. Derived evidence may organize analysis but cannot increase confidence by
   being counted again as an independent observation.
4. A later user annotation is new primary evidence; the generated text around
   it remains derived.
5. Derivation links must be acyclic and trace back to primary evidence.

## Review method

### 1. Set context

Record the review window, available evidence types, decision question, privacy
boundary, intended audience, and desired artifact. When no decision question is
available, label broad signal detection as exploratory.

### 2. Minimize and normalize

Use only the fields and excerpts needed for the question. Deduplicate by stable
source identifier, canonical identity, and content fingerprint. Multiple
engagement events for one item remain events on that item, not independent
sources.

### 3. Score separate dimensions

Assess attention strength, conviction strength, source quality, strategic
relevance, novelty, and contradiction separately. Do not collapse attention and
conviction into one opaque score.

### 4. Build claims against alternatives

For each useful pattern, state the observation, cite primary evidence, list
plausible alternative explanations, identify counter-evidence, label any belief
inference as private and provisional, and name the decision or test it informs.
Confidence follows evidence quality rather than narrative coherence.

### 5. Apply review lenses

Score each selected lens from 0 to 100 and show the configured pass threshold;
the source method proposes 90 as a default for recommendations. Useful lenses
include evidence lineage, decision value, strongest counterargument,
actionability, audience safety, domain credibility, and measurability. Items
below threshold can remain explicit exploratory hypotheses.

### 6. Produce a bounded artifact

A promoted insight should become a decision question, falsifiable experiment,
small build specification, contradiction to resolve, offer hypothesis to test,
content gap for private consideration, or monitored theme with a review trigger.

### 7. Capture feedback

Record explicit acceptance, rejection, correction, application, and measured
outcome. A person's correction is new evidence; a restatement of earlier model
output is not.

## Capability lenses

- **Attention drift:** Compare windows to identify emerging, accelerating,
  fading, persistent, and application-bound themes.
- **Pre-decision framing:** Express converging research and tests as candidate
  decision questions, not predictions about what a person will choose.
- **Contradiction review:** Present the strongest case for competing
  interpretations, missing evidence, and a resolving test or decision rule.
- **Signal-to-build:** Progress from attention to reading, annotation,
  synthesis, specification, bounded build, and measurement.
- **Original-framework recombination:** Distinguish the person's contribution
  from antecedents and require evidence before asserting novelty.
- **Offer hypothesis review:** Compare recurring pain, demonstrated capability,
  available proof, cost, and reversibility without treating attention as demand.
- **Content negative space:** Identify privately studied or applied themes that
  are absent from authorized public material while retaining private boundaries.

## Decision Court scope

Explicit decisions within the configured scope may enter review directly.
Inferred high-stakes candidates should first be presented as nominations with
source-grounded rationale. Routine notes, questions, and tasks are not decisions.

The source method's initial scope includes strategic bets, product or offer
changes, senior hiring, capital allocation, consequential partnerships, and
consequential client bets. Routine matters enter only when a configured
materiality gate is met. Suggested starting gates are at least USD 5,000 of
downside or committed spend, at least 40 person-hours, material reputation risk,
or meaningful irreversibility. These values must remain configurable and
unknown estimates must remain unknown.

For a qualifying contradiction:

1. Describe the tension neutrally.
2. Construct the strongest interpretation for each side.
3. Cite primary evidence for both.
4. Classify the disagreement as factual, temporal, contextual, or values-based.
5. Identify missing observations.
6. State a resolving test, decision rule, or explicit unresolved status.

## Review cadence

A compact review is useful when enough new evidence exists. Event-based review
is appropriate after a high-strength cluster, explicit decision note, applied or
measured item, meaningful contradiction, changed strategic context, or direct
request. If little changed, record that rather than manufacturing novelty.

## Recommendation lifecycle

1. Observed: primary signals are identified and deduplicated.
2. Inferred: a provisional claim includes counter-evidence.
3. Reviewed: evidence, audience, and quality checks are complete.
4. Proposed: a bounded decision, test, or artifact is described.
5. Accepted or rejected: the person supplies explicit disposition.
6. Testing: the action has an owner, measure, and stop condition.
7. Validated, revised, or retired: outcomes update the claim.
8. Archived or deleted: the applicable retention boundary is applied.

## Review checklist

- The window, decision context, and audience are defined.
- Attention and conviction remain separate.
- Strong claims rely on strong engagement or observed outcomes.
- Material claims trace to primary evidence without recursive counting.
- Private inferred beliefs are provisional, confidence-rated, and isolated.
- Counter-evidence and alternative explanations are visible.
- The panel threshold and result are recorded.
- Recommendations are bounded, measurable, and decision-relevant.
- Each promoted item has an owner, status, stop condition, and review point.
