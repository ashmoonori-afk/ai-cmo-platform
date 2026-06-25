# Demo Scenarios

Use these scenarios to demonstrate what the platform does.

## Scenario 1: New Client Onboarding

Prompt:

```text
Add a new client and create the first 90-day AI CMO operating plan.
```

Expected flow:

1. Intake fields are collected.
2. Neurosis clarifies missing buyer, offer, or approval details.
3. `client-onboarding.md` creates the client base files.
4. Strategist creates the initial roadmap.
5. Reviewer checks the output.
6. Reporter records follow-up tasks.

Proof paths:

- `playbooks/07-operations/client-onboarding.md`
- `playbooks/00-chains/ai-cmo-operating-system.md`
- `docs/product/owner-director-comparison.md`

## Scenario 2: Content Campaign With Visual Brief

Prompt:

```text
Create a four-week content campaign and prepare visual prompts for the hero posts.
```

Expected flow:

1. SEO specialist defines intent and keyword cluster.
2. Copywriter drafts blog/social/newsletter assets.
3. codex-image-gen handoff produces a visual brief and waits for actual PNG proof.
4. Reviewer checks claims, brand, CTA, and visual status.

Proof paths:

- `playbooks/00-chains/content-full-cycle.md`
- `playbooks/03-content/blog-article.md`
- `playbooks/03-content/social-post.md`
- `integrations/birkin/codex-image-gen.md`

## Scenario 3: Owner Monthly Review

Prompt:

```text
Show the owner what changed this month and what to do next.
```

Expected flow:

1. Reporter scans outputs and KB records.
2. Data analyst separates observed metrics from interpretation.
3. Reviewer checks missing data and claims.
4. Morpheus-style maintenance note proposes SOP or KB improvements.

Proof paths:

- `playbooks/06-analytics/performance-report.md`
- `playbooks/06-analytics/weekly-report.md`
- `playbooks/08-role-sops/reporter.md`
- `integrations/birkin/morpheus.md`
