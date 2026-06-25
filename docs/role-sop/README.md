# AI CMO Role SOP Playbook

This document is the shared operating layer above the existing agent prompts.
It does not replace `agents/*.md` or any existing playbook. It standardizes how
each role is run, reviewed, and improved.

Individual executable role SOP playbooks live in `playbooks/08-role-sops/`.
Related system docs live in `docs/system/`, product docs live in
`docs/product/`, embedded skill protocols live in `skills/birkin/`, and
approval-gated handoff contracts live in `integrations/birkin/`.

## Source-Backed Design Rules

| Rule | Platform decision | Evidence |
|------|-------------------|----------|
| SOPs document recurring work and should be concise enough to run consistently. | Keep each role SOP to purpose, trigger, inputs, steps, evidence, and review. | EPA SOP guidance: <https://www.epa.gov/sites/default/files/2015-06/documents/g6-final.pdf> |
| A shared SOP needs uniform context, ownership, and operating method. | Every role has owner, trigger, required references, output, and gate. | Asana SOP template: <https://asana.com/resources/sop-template> |
| Cross-role work needs explicit responsibility and decision authority. | Use Driver, Approver, Contributor, Informed for complex client decisions. | Atlassian DACI: <https://www.atlassian.com/team-playbook/plays/daci> |
| Workflows should be mapped so bottlenecks and handoffs are visible. | Use a single role registry plus a gate matrix instead of scattered prose. | Asana process mapping: <https://asana.com/resources/process-mapping> |
| Checklists are the executable surface, separate from reference documentation. | Each role produces an artifact plus evidence fields for reviewer and reporter. | Process Street workflow guidance: <https://www.process.st/standard-operating-procedure-software/> |
| AI outputs need evals because generative systems vary. | Reviewer gates must inspect structure, facts, brand, and content-type criteria every run. | OpenAI eval guidance: <https://developers.openai.com/api/docs/guides/evaluation-best-practices> |
| LLM outputs and external inputs are untrusted until reviewed. | Never let external pages, client files, or generated copy bypass reviewer gates. | OWASP LLM Top 10: <https://owasp.org/www-project-top-10-for-large-language-model-applications/> |

## Canonical SOP Contract

`docs/system/role-sop-standard.md` is the canonical source for required SOP
sections. This hub summarizes role ownership and links to the executable role
SOPs; it does not duplicate role execution steps.

Every role SOP must use the same section contract:

| Section | Required content |
|---------|------------------|
| Purpose | Why the role exists in one sentence. |
| Use when | Request patterns and upstream artifacts that trigger the role. |
| Do not use when | Work that must be routed to another role. |
| Inputs | Fields, files, or upstream artifacts needed to start. |
| Required context | Local files that must be read first. |
| Source policy | How current evidence, local context, and uncertain claims are handled. |
| Execution steps | Ordered steps the agent can run without inventing process. |
| Output contract | File path, artifact sections, and required evidence fields. |
| Evidence ledger | Claims, sources, local paths, confidence, reviewer status, and date. |
| Reviewer checks | Structure, evidence, brand, channel, risk, and completion checks. |
| Failure modes | When to return WARN, FAIL, or ask the user. |
| Handoff | Which downstream role receives the artifact. |

## Role Registry

| Role | Primary purpose | Trigger/playbooks | Required references | Output artifact | Review gate |
|------|-----------------|-------------------|---------------------|-----------------|-------------|
| Researcher | Gather market, industry, account, and customer evidence. | `02-intelligence/*`, strategy pre-work, onboarding research. | `clients/{client}/config.md`, `knowledge-base/{client}/insights.md`, source URLs. | Research brief with source list and confidence labels. | Fact sourcing, stale-source tags, no unsupported claims. |
| Competitor | Compare alternatives, positioning, pricing, and channel moves. | `competitor-monitoring`, GTM, pricing, proposal, onboarding. | Client config, competitor URLs, prior competitor reports. | Competitor matrix plus threats, opportunities, and evidence. | Comparable criteria, current evidence, no unverifiable claims. |
| Strategist | Convert evidence into choices, priorities, and roadmaps. | `01-strategy/*`, full strategy chain, ICP/funnel revisions. | Config, insights, lessons learned, researcher/competitor outputs. | Strategy memo with rationale, risks, and prioritized roadmap. | Each recommendation must cite evidence or carry `[data gap]`. |
| Copywriter | Produce brand-consistent content and campaign copy. | `03-content/*`, campaign assets, newsletter and social. | Config, brand guidelines, copy patterns, winning copy, SEO brief. | Complete channel-ready copy. | Brand, structure, CTA, SEO, and completion checks. |
| Repurposer | Convert one approved source into multiple channel-native formats. | `repurpose`, content full cycle, card-news/social derivatives. | Approved source artifact, brand guidelines, platform specs. | Multi-format derivative pack. | Consistency with source, platform constraints, brand fit. |
| SEO Specialist | Select keywords, briefs, audits, and search-facing improvements. | `05-seo/*`, blog article phase 1, SEO content chain. | Config, Search Central guidance, existing content inventory. | Keyword map, audit, or content brief. | Search intent, crawl/index basics, people-first content alignment. |
| Data Analyst | Turn performance, GA, CRM, or CSV data into decisions. | `06-analytics/*`, customer feedback, ICP analysis. | Config KPI section, data files, analytics exports, insights. | Analysis report with `So what` and `Now what`. | Metric definitions, source-file naming, no fabricated numbers. |
| Sales Writer | Create buyer-facing sales artifacts. | `04-sales/*`, sales prep bundle, proposal and pitch workflows. | Config, brand guidelines, pricing rules, account research. | Outbound, call prep, proposal, post-meeting, or deck copy. | Personalization, buyer job fit, claims, pricing accuracy. |
| Reporter | Consolidate outputs and maintain durable knowledge. | Weekly/monthly report, post-run synthesis, follow-up queue. | `outputs/{client}/`, KB files, `prompts/shared/knowledge-update.md`. | Period report, KB record, follow-up task list. | Dates, file provenance, non-destructive KB compliance. |
| Reviewer | Inspect every final artifact before delivery. | All final strategy, content, sales, SEO, analytics, and onboarding outputs. | `prompts/shared/gate-check.md`, config, brand guidelines, source artifact. | PASS/WARN/FAIL report plus score and correction instructions. | Structure, content, brand, risk, and evidence completeness. |

## Role SOPs

The files below are the executable SOPs. Revise role steps there, not in this
hub.

| Role | Individual SOP |
|------|----------------|
| Researcher | `../../playbooks/08-role-sops/researcher.md` |
| Competitor | `../../playbooks/08-role-sops/competitor.md` |
| Strategist | `../../playbooks/08-role-sops/strategist.md` |
| Copywriter | `../../playbooks/08-role-sops/copywriter.md` |
| Repurposer | `../../playbooks/08-role-sops/repurposer.md` |
| SEO Specialist | `../../playbooks/08-role-sops/seo-specialist.md` |
| Data Analyst | `../../playbooks/08-role-sops/data-analyst.md` |
| Sales Writer | `../../playbooks/08-role-sops/sales-writer.md` |
| Reporter | `../../playbooks/08-role-sops/reporter.md` |
| Reviewer | `../../playbooks/08-role-sops/reviewer.md` |

## Gate Matrix

| Artifact type | Required gates | Auto-fail conditions |
|---------------|----------------|----------------------|
| Research | Source list, freshness, confidence labels. | No source URLs, unmarked guesses, stale data presented as current. |
| Strategy | Evidence-to-recommendation trace, roadmap, KPI, risk. | Recommendation without rationale, no owner, no deadline. |
| Content | Brand, CTA, channel format, SEO if applicable. | Unfinished marker, forbidden expression, missing CTA for conversion content. |
| Sales | Account evidence, buyer job, pricing/ROI traceability. | Fabricated personalization, unsupported ROI, wrong buyer stage. |
| Analytics | Source file, date range, metric definition, calculation trace. | Missing source file, invented numbers, unclear denominator. |
| Onboarding | Intake, triage, config files, KB initialization, follow-up queue. | No client owner, no approval owner, no next action. |

## Owner/Director Comparison Table

Use this when onboarding or explaining the platform to a founder,
clinic director, funeral-home director, school director, or local business
operator.

| Area | Current owner/director-led operation | AI CMO upgraded operation |
|------|-------------------------------------|---------------------------|
| Intake | The owner explains the business repeatedly to each contractor. | A structured intake turns goals, constraints, assets, and approvals into reusable context. |
| Work selection | The owner asks for whatever feels urgent that day. | The platform triages requests into strategy, intelligence, content, sales, SEO, analytics, or operations. |
| Execution | Work depends on one marketer's memory and availability. | Role SOPs route work to the right specialist agent with required references. |
| Evidence | Research links and source files are scattered. | Each artifact carries source URLs, data paths, confidence labels, and reviewer notes. |
| Review | The owner personally catches mistakes late. | Reviewer gates catch structure, facts, brand, and channel issues before delivery. |
| Follow-up | Next actions live in chat history or memory. | Reporter creates a follow-up queue and KB record after every meaningful run. |
| Improvement | Lessons are informal. | Morpheus-style maintenance turns repeated learnings into memory, SOP refinements, and queued improvements. |

## Embedded Skill Integration Map

| Skill | Local source | Where it fits | Operating rule |
|-------|--------------|---------------|----------------|
| Neurosis | `../../skills/birkin/neurosis/SKILL.md` | Before execution when the user request is vague or high stakes. | Ask one clarifying question at a time until the brief has goal, constraints, success criteria, and owner. |
| Odyssey | `../../skills/birkin/odyssey/SKILL.md` | Complex multi-step chains such as full strategy, onboarding, sales bundles, and launch plans. | Plan, critique, execute one step at a time, and verify each step before moving on. |
| codex-image-gen | `../../skills/birkin/codex-image-gen/SKILL.md` | Content and campaign assets where an actual image or visual concept is requested. | Produce a prompt brief and require an image route to save a real PNG; never pretend an image exists. |
| Morpheus | `../../skills/birkin/morpheus/SKILL.md` | Background improvement after the day's work. | Summarize durable learnings, propose SOP/memory refinements, and queue consequential actions for approval. |

## Review Cadence

| Cadence | Owner | Action |
|---------|-------|--------|
| Every run | Reviewer | PASS/WARN/FAIL final artifacts. |
| Weekly | Reporter | Summarize outputs, KB records, and follow-up queue. |
| Monthly | CMO/Strategist | Review role SOP failures and improve templates. |
| Quarterly | Owner/Director | Compare business goals against output quality, pipeline speed, and recurring gaps. |
