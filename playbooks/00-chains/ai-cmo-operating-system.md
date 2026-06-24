# AI CMO Operating System Chain

## Purpose

Turn a vague marketing request into a reviewed, evidence-backed marketing output
without losing context, ownership, or follow-up. This chain is the upgraded user
pipeline for sellable client work.

## When to use

Use this chain when a request is broad, high value, multi-step, or unclear:

- new client onboarding
- full marketing strategy
- launch plan
- sales enablement package
- content campaign package
- owner/director business review
- platform dogfooding run
- any request that needs multiple agents or approval gates

For narrow one-off work, keep using the existing 33 core playbooks.

## Chain overview

```
User request
  -> Intake
  -> Neurosis clarity gate when vague
  -> Triage and workflow selection
  -> Odyssey-style step plan for complex chains
  -> Specialist role execution
  -> Optional codex-image-gen visual asset brief
  -> Reviewer gate
  -> Reporter delivery, KB records, follow-up queue
  -> Morpheus-style maintenance notes
```

## Phase 1: Intake

Collect only the fields needed to route the work.

| Field | Required | Use |
|-------|----------|-----|
| `client` | yes | Load `clients/{client}/config.md`. |
| `goal` | yes | Decide output and success criteria. |
| `business_context` | yes | Prevent generic strategy. |
| `deadline` | no | Prioritize scope and depth. |
| `decision_owner` | yes for client-facing work | Identify who approves the output. |
| `assets_available` | no | Find CSV, website, product, deck, GA, CRM, brand, and image inputs. |
| `risk_level` | yes | Decide whether reviewer-only is enough or user approval is needed. |

## Phase 2: Neurosis clarity gate

Use `skills/birkin/neurosis/SKILL.md` as the local protocol. Do not require a
separate Birkin install.

If any of these are missing, pause execution and ask one focused question:

- target customer
- intended output
- channel or workflow
- decision owner
- success metric
- hard constraint such as budget, region, compliance, brand rule, or deadline

The gate ends when the request can be written as:

```
For {client}, produce {artifact} for {audience} to achieve {goal}, using {required inputs}, by {deadline or default cadence}, reviewed by {owner/reviewer}.
```

## Phase 3: Triage and workflow selection

| Intake signal | Route | Primary playbook/chain |
|---------------|-------|------------------------|
| "What should we do?" | Strategy | `playbooks/00-chains/full-strategy-chain.md` |
| "Who are we selling to?" | Intelligence | `playbooks/02-intelligence/icp-analysis.md` |
| "Make campaign/content" | Content | `playbooks/00-chains/content-full-cycle.md` |
| "Prepare sales" | Sales | `playbooks/00-chains/sales-prep-bundle.md` |
| "Check SEO/search" | SEO | `playbooks/05-seo/seo-audit.md` |
| "Analyze performance/data" | Analytics | `playbooks/06-analytics/performance-report.md` |
| "Set up or clean process" | Operations | `playbooks/07-operations/client-onboarding.md` |

## Phase 4: Odyssey execution plan

Use `skills/birkin/odyssey/SKILL.md` as the local protocol for multi-step work.

For multi-step work, create a short checklist before running agents.

| Step | Owner | Acceptance |
|------|-------|------------|
| Confirm brief | CMO | Goal, audience, artifact, owner, and constraints are explicit. |
| Gather evidence | Researcher/Competitor/Data Analyst | Sources or data files are listed. |
| Draft output | Specialist role | Artifact follows the target playbook template. |
| Review | Reviewer | PASS or WARN with concrete notes. |
| Deliver | Reporter/CMO | Output path, summary, and next actions are recorded. |
| Improve | Reporter/Morpheus pattern | Durable learning is recorded or queued. |

## Phase 5: Specialist execution

Use the existing agent contracts. Do not bypass them.

| Work type | Specialist roles |
|-----------|------------------|
| Strategy | researcher + competitor -> strategist -> reviewer |
| Content | seo-specialist -> copywriter -> repurposer -> reviewer |
| Sales | researcher -> sales-writer -> reviewer |
| Analytics | data-analyst -> reviewer or reporter |
| Operations | researcher + competitor -> strategist -> reporter -> reviewer |

## Phase 6: Optional visual asset route

Use `codex-image-gen` only when the user asks for a real image, ad visual,
thumbnail, card-news visual, or product/offer scene.

Use `skills/birkin/codex-image-gen/SKILL.md` as the local protocol.

Minimum visual brief:

```
visual_goal:
target_channel:
audience:
brand_constraints:
must_include:
must_avoid:
prompt:
output_path:
visual_asset_status:
png_path:
unavailable_reason:
approval_owner:
reviewer_notes:
```

Exactly one visual route must be true:

- `visual_asset_status=generated` with a real `png_path`
- `visual_asset_status=unavailable` with `unavailable_reason`
- `visual_asset_status=needs_approval` with `approval_owner`

No visual artifact is complete outside those three states.

## Phase 7: Reviewer gate

Reviewer applies `prompts/shared/gate-check.md`.

| Result | Action |
|--------|--------|
| PASS | Deliver and hand durable-learning candidates to Reporter for KB reflection. |
| WARN | Deliver with visible warning and follow-up owner. |
| FAIL | Return to the source role with correction instructions. |
| ESCALATE | Ask the user or decision owner for a choice. |

## Phase 8: Reporter and KB handoff

Reporter records:

- output path
- source artifacts
- reviewer result
- durable insights
- follow-up tasks
- owner and due date

KB records preserve existing entries. Follow-up tasks belong in the delivery report, not inside
`insights.md`.

## Phase 9: Morpheus-style maintenance

Use `skills/birkin/morpheus/SKILL.md` as the local protocol.

At the end of a meaningful run, record one maintenance note:

| Learned | Saved | Proposed |
|---------|-------|----------|
| What became clearer about the client, role, or workflow. | Which KB/SOP item was saved or queued by Reporter. | Which future improvement should be queued for approval. |

This is a documentation pattern for this platform. It does not run unattended
automation unless the user explicitly installs or invokes a Morpheus-like system.

## Owner/Director comparison table

| Decision area | Owner/director before AI CMO | Upgraded AI CMO pipeline |
|---------------|------------------------------|--------------------------|
| Request quality | Gives broad instructions and repeats context. | Intake plus Neurosis turns requests into executable briefs. |
| Priority | Reacts to urgent requests first. | Triage selects the right workflow and depth. |
| Execution | One person coordinates freelancers, staff, and agencies. | Odyssey-style checklist coordinates agents and gates. |
| Creative | Ideas and assets are separated. | Copy and codex-image-gen visual briefs travel together. |
| Quality | Owner catches issues after drafts are done. | Reviewer checks structure, claims, brand, and channel rules before delivery. |
| Memory | Learnings stay in chat, meetings, or personal memory. | Reporter records KB entries and creates follow-up tasks; Morpheus-style notes propose improvements. |

## Output

```
outputs/{client}/operations/{YYYYMMDD}_ai-cmo-operating-system-run.md
```

Include links to all source artifacts and final outputs.

## Command patterns

- "AI CMO 운영체계로 정리해줘"
- "이 요청을 먼저 분류하고 실행해줘"
- "원장/대표에게 보여줄 비교표까지 만들어줘"
- "전체 파이프라인으로 실행해줘"
- "Neurosis로 명확히 한 뒤 Odyssey 방식으로 진행해줘"
