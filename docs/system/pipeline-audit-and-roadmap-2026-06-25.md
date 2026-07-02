# AI CMO Platform — Pipeline Audit & Feature Roadmap

> **STATUS (2026-07-02): HISTORICAL SNAPSHOT.** Sections 0–6 describe the repository **as of the 2026-06-25 audit**, before the roadmap was built. The P0–P3 items were shipped on the same date (see §7 and the commit history: live executor presets, evaluated gates, KB flush, onboarding wizard, mockup/serve). For the **current** engine behavior, read `docs/system/workflow-engine.md`; do not cite §0–§6 as the present state.

**Date:** 2026-06-25
**Method:** 8 parallel auditors — 4 internal (code + SOP, evidence cited as `file:line`) and 4 external (web research, cited as source URLs). Claims were verified against the repository, not taken from `CLAUDE.md`.
**North-star this audit measures against (owner's stated vision):** *A complete novice — "my mom, who knows nothing about marketing" — can start a brand and automatically receive (1) marketing proposals, (2) design mockups (시안), (3) working prototypes, and have any existing assets (4) coldly and objectively evaluated with (5) derived improvement points, plus good strategies, methods, and examples.*

---

## 0. Executive Verdict (cold)

The platform is a **well-built orchestration skeleton with zero live marketing capability**. There is a genuine, ~700-LOC Python workflow engine (DAG runner, SQLite state, idempotent resume, manual approval gates, path-safety validation) and a large, mostly-coherent Markdown SOP library (11 agents, ~54 playbooks). But:

- **It does not generate anything.** Every "agent" step writes a deterministic placeholder that literally says *"Replace this adapter with Hermes, Claude, OpenAI, or Codex for live agent execution"* (`src/aicmo/step_executor.py:65-85`). No LLM, HTTP, or subprocess call exists anywhere in `src/`.
- **The quality gate is fake.** A reviewer gate with no manual approver hardcodes `status: PASS` (`step_executor.py:111-112`); the `pass_if` condition is stored but never evaluated (`models.py:64` is dead data). The "stage-gate validation" the docs advertise does not exist in code.
- **No novice can use it.** There is no web UI — it runs only inside Claude Code (a developer CLI). Onboarding templates are blank tables of unexplained jargon (ICP, ACV, KPI, channel %). The onboarding playbook has a **circular dependency**: agents assume `config.md`/`brand-guidelines.md` exist, but those are the very files onboarding is supposed to create.
- **No visual output, ever.** `outputs/` contains only `.gitkeep` files — zero `.md`, `.html`, `.png`, or `.svg` deliverables have been produced and committed. Design "output" is a text spec; image generation is a contract shell with no engine wired in.
- **Evaluation is a prose checklist, not a scorer.** No numeric rubric, no benchmark thresholds, no score bands.

**The gap between `CLAUDE.md`'s claims and the code's reality is large.** The foundation is sound and worth keeping; the entire value-producing layer is unbuilt. The roadmap below sequences that build, using patterns proven by current market tools.

---

## 1. What's Real vs. What the Docs Claim

| Capability the docs imply | Reality in code | Evidence |
|---|---|---|
| Subagents produce research/copy/strategy | Deterministic stub artifact; no model call | `step_executor.py:65-85`; grep: zero LLM/HTTP/subprocess in `src/` |
| Reviewer "stage-gate" validates every output | Auto-`PASS`; `pass_if` never parsed | `step_executor.py:111-112,148`; `models.py:64` |
| Knowledge accumulation loop | KB updates enqueued but nothing consumes the queue | `step_executor.py:114-135` |
| Self-executing playbooks | Uneven; some are 7-line wrappers or unfinished templates | `playbooks/08-design/design-audit.md` (7 lines); `landing-page.md` (11 unfilled `{placeholder}`s) |
| Design output = landing pages / detail pages | Markdown spec only; `designer.md` declares HTML but playbooks emit `.md` | `agents/designer.md` (`output_format: html`) vs `playbooks/08-design/landing-page.md` output path `.md`; `outputs/**` empty |
| Image generation available | Contract/skill shell, no generator wired; ends `unavailable`/`needs_approval` | `skills/birkin/codex-image-gen/SKILL.md`; `integrations/birkin/codex-image-gen.md` |

**What is genuinely solid (keep it):** topological DAG execution with stable ordering (`models.py:158-187`); idempotent resume that skips `SUCCESS` and reopens steps whose artifacts vanished (`runner.py:60-64`, `step_executor.py:179-192`); immutable rejected gates (`step_state.py:191-217`); path-traversal rejection (`paths.py:24-40`); WAL + `busy_timeout` concurrency and idempotent `kb.update` via `ON CONFLICT DO NOTHING` (`db.py:17-32`, `ledger_state.py:66-85`). Test honesty: **B-** — real integration tests against the runner/SQLite, but they assert artifacts *exist*, never their *content* (`tests/test_workflow_engine.py:26-29` checks `draft.md` exists, never opens it), so a stub file passes as a "successful SEO blog article."

**Correction to one sub-finding (verified):** `prompts/shared/knowledge-update.md` and `prompts/shared/boilerplate.md` **do exist** (confirmed by glob); references to them are *not* dead. The real consistency defect is two competing scoring systems with no precedence rule: `agents/reviewer.md` (5-category weighted matrix) vs `prompts/shared/gate-check.md` (Structure 30 / Accuracy 40 / Brand 30, 100-pt). Pick one canonical rubric.

---

## 2. Capability Audit vs. the Vision

| # | Vision capability | Status | Why |
|---|---|---|---|
| 1 | Marketing **proposals** (research → strategy → copy) | ⚠️ **SOP exists, execution stubbed** | Playbooks are good but the executor produces placeholders, not content |
| 2 | Design **mockups (시안)** | ❌ **Text-only** | No rendered HTML/PNG ever produced; designer→playbook format mismatch |
| 3 | Working **prototypes** | ❌ **Absent** | No clickable/deployable output capability anywhere |
| 4 | **Objective evaluation** of existing assets | ❌ **Checklist only** | No numeric rubric, no score bands, no benchmark |
| 5 | **Improvement** derivation | ⚠️ **Prose, unprioritized** | `design-audit.md` is narrative; no scored priority list |
| — | **Novice can self-serve** | ❌ **No** | CLI-only, jargon configs, circular onboarding dependency |

Every value-layer capability the owner described is either stubbed or absent. The platform today would hand "mom" a set of files that say *"replace this adapter with a real model."*

---

## 3. Market Gap — what beginner-facing tools already ship (cited)

Three converged lanes in 2025–2026, all of which now treat the following as **table-stakes**: real visual/site output, guided novice onboarding, auto-generated brand kit, one-click repurposing, and a low/free entry price.

| Feature the platform lacks | Exemplar | Source | Tag |
|---|---|---|---|
| 3-question conversational onboarding → full site | Durable | durable.com/ai-website-builder | table-stakes |
| Auto brand-identity kit (logos, templates, assets) | Looka | looka.com/brand-kit | differentiator |
| Text-prompt → on-brand design generation | Canva Magic Studio | canva.com/canva-ai | table-stakes |
| Real ad/visual generation | AdCreative.ai | adcreative.ai/ad-creatives | table-stakes |
| **Objective creative SCORING (predicted performance %)** | AdCreative.ai | adcreative.ai/creative-scoring | **differentiator — matches vision #4** |
| Working deployable prototype from natural language | Lovable / v0 / Bolt | lovable.dev, v0.dev | differentiator — matches vision #3 |
| One-click content repurposing in brand voice | HubSpot Breeze | hubspot.com/.../breeze-ai-agents | table-stakes |
| Stored brand-voice engine across channels | Jasper Brand Voice | jasper.ai/brand-voice | table-stakes |

*Vendor performance numbers (e.g., AdCreative "90% accuracy," Lovable "$20M ARR") are self-reported/single-source — not independently verified.*

**Where this platform can still win** (defensible edges, not yet realized):
1. **Auditable, gated reasoning** vs. black-box generation — a step-by-step marketing *plan* with citations and approval gates, closer to a junior CMO than a template filler.
2. **End-to-end orchestration in one opinionated pipeline** — the market pain is fragmentation ("dozens of copilots"); a single research→strategy→copy→design→review graph is structurally aligned to win *if execution gets wired*.
3. **Objective evaluation of a client's EXISTING assets** — most tools only score their own net-new output; cold-auditing what a brand already has is under-served and is exactly vision #4.

---

## 4. Feature Roadmap (prioritized)

Priority = impact on the vision × inverse effort. **P0 is the unlock without which nothing else produces value.**

| Pri | Feature | Why it matters | Method (proven) | Plugs into |
|---|---|---|---|---|
| **P0** | **Live agent adapter** (stub → real LLM) | Single change that turns the skeleton into a product | Anthropic SDK client; inject role+prompt+context, write model output | replace body of `_run_agent` `step_executor.py:65-85`; new `src/aicmo/agent_client.py` + API-key config |
| **P1** | **Objective Evaluation Engine** | The differentiator; mostly automatable; directly = vision #4/#5 | 100-pt rubric synthesized from LIFT, Dunford, StoryBrand, 5-sec test, NN/g | new `src/aicmo/evaluate.py`; reuse `gate-check.md` vocabulary; new playbook `08-design/asset-evaluation.md` |
| **P1** | **Novice Onboarding Wizard** | Removes the #1 blocker to "mom" use; breaks the circular dependency | Conversational one-question-at-a-time + sensible defaults + jargon translation | rewrite `playbooks/07-operations/client-onboarding.md` to *generate* config from plain answers; populate `clients/_template/*` with inline definitions |
| **P2** | **Mockup + Prototype generator** | = vision #2/#3; turns text specs into real 시안 | LLM emits self-contained HTML/Tailwind → Playwright screenshot → PNG; Netlify Drop for live URL | new `src/aicmo/render.py`; fix `landing-page.md` output to `.html`; new step type `render` |
| **P2** | **Real reviewer gate + KB consumer** | Makes the advertised quality loop true | parse `pass_if` / `gate-check.md`; reporter dequeues `kb_updates` → appends to `knowledge-base/` | `_run_gate` `step_executor.py:87-112`; new reporter consumer of queue at `step_executor.py:133` |
| **P3** | **Non-CLI access layer** | Structural prerequisite for true non-technical users | Phase-3 web form / hosted chat over the existing CLI/runner | per `docs/system/workflow-engine.md` Phase 3 |

**Test-honesty fix (cross-cutting):** every new generator step needs a content assertion, not just an existence check — otherwise the test suite keeps green-lighting stubs.

---

## 5. Concrete Specs & Examples (methods + examples)

### 5.1 Live adapter (P0) — sketch
```
# src/aicmo/agent_client.py  (new)
# Reads: role prompt (agents/{role}.md), playbook step inputs, dependency artifacts, loaded client context.
# Calls: Anthropic Messages API with model from the workflow spec (opus/sonnet/haiku per CLAUDE.md §4.5).
# Writes: the model's markdown output to the step's declared artifact path (unchanged path contract).
# Fails typed: success | warning | failure | escalate | approval_needed  (preserve runner contract).
```
Keep the deterministic adapter behind a `--dry-run`/offline flag so existing tests still exercise the state machine without API cost.

### 5.2 Objective Evaluation Engine (P1) — rubric (sourced + synthesized)
Score an existing landing page / brand asset 0–100:

| Dimension | Weight | Sourced from |
|---|---|---|
| Message clarity (headline, above-fold, 5-second passability) | 20 | LIFT (Clarity); 5-Second Test (Lyssna) |
| Value proposition & positioning (Dunford 5-component) | 20 | April Dunford, *Obviously Awesome* |
| CTA strength (verb, placement, specificity, above-fold) | 15 | Unbounce CRO audit |
| Social proof & trust signals (specificity, placement) | 15 | Unbounce; LIFT (Anxiety) |
| Narrative structure (StoryBrand element presence) | 10 | StoryBrand BrandScript |
| UX / usability (NN/g heuristics, readability) | 10 | NN/g 10 Heuristics |
| Brand consistency across pages | 10 | Frontify brand audit |

**Bands:** PASS 80–100 · WARN 60–79 · FAIL 40–59 · CRITICAL <40. *(Dimensions/weights/bands are an engineering synthesis informed by the sourced frameworks, not a single published rubric.)*

**Automatable now (no external data):** 5-second clarity gate, StoryBrand element presence, CTA verb/placement, Flesch-Kincaid readability, trust-signal presence, Dunford completeness, distraction count.
**Needs real data (mark `[미확인 — 데이터 필요]`):** actual conversion rate, A/B results, share-of-search, competitive attribute verification.

### 5.3 Novice Onboarding Wizard (P1) — the 7-question intake
Ask one at a time, in plain language; infer the rest; let the user edit:

| # | Plain-language question | Fills |
|---|---|---|
| 1 | "What do you sell, in one sentence?" | Category / Offer |
| 2 | "Who is this for — describe the person most likely to buy it." | ICP / Target |
| 3 | "What problem do they have before they find you?" | Problem / JTBD |
| 4 | "Why would they pick you over doing nothing or what they use now?" | UVP / Differentiator |
| 5 | "Where do those people spend time or search?" | Channel |
| 6 | "Any customer who got a result? Even one story." | Proof |
| 7 | "What's the one thing you want a first-time visitor to do?" | CTA / Funnel entry |

**Jargon → plain-language (put inline in `clients/_template/*`):** ICP = "the one type of person most likely to buy and love this"; Positioning = "what makes you different, in one sentence"; Funnel = "the steps a stranger takes to become a paying customer"; CTA = "the one thing you want someone to do next"; UVP = "why someone chooses you over doing nothing." This wizard also **breaks the circular dependency** by writing `config.md`/`brand-guidelines.md` *before* any downstream agent runs.

### 5.4 Mockup + Prototype stack (P2)
- **Pipeline:** structured brief → LLM emits one self-contained `<!DOCTYPE html>` with inline CSS/JS (Anthropic Cookbook "frontend aesthetics" prompt) → Python `playwright` headless Chromium `page.screenshot(full_page=True)` → PNG 시안 → optional Netlify Drop for a live clickable URL.
- **Why HTML+screenshot, not an image model:** image models hallucinate nav, misalign text, and can't be copy-accurate; a real browser render is pixel-faithful and free at low volume. Reserve image models for hero/mood visuals only.
- **Minimum prototype = one responsive, shareable landing page.** Local deps: Python 3.10+, `playwright`, Chromium (auto-installed). No Node/React build. *Caveat:* `cdn.tailwindcss.com` is dev-only — inline critical CSS for client deliverables.

---

## 6. Risks & Honesty Notes
- **Do not ship another stub.** The credibility risk is building eval/mockup features that *look* done but no-op, repeating the `_run_agent` pattern. Gate each with a content-level test.
- **Vendor metrics are marketing.** AdCreative/Lovable/Looka numbers are self-reported; cite as claims, not facts.
- **The eval rubric weights/bands are a design decision**, synthesized from sourced frameworks — calibrate against real examples before trusting the score.
- **"Mom" cannot reach a CLI.** Until P3 (a hosted entry point) exists, the realistic user is the *owner operating on her behalf*; state this honestly in positioning.

## 7. Suggested first two weeks (sequenced)
1. **Days 1–4 — P0 live adapter** behind an offline flag; add one content-assertion test per generator step. *Now the platform actually produces a blog/strategy draft.*
2. **Days 5–8 — P1 Evaluation Engine** (automatable dimensions only) + `asset-evaluation` playbook. *Now it can coldly score an existing landing page and output a prioritized fix list — the differentiator.*
3. **Days 9–12 — P1 Onboarding Wizard** rewrite + template definitions. *Now a novice answers 7 plain questions and gets a real config.*
4. **Days 13–14 — P2 mockup render PoC** (one HTML→PNG landing page for `sample-client-a`). *Now there is a real 시안 in `outputs/`.*

---

## Appendix — Sources
Internal: `src/aicmo/*.py`, `tests/*.py`, `agents/*.md`, `playbooks/**`, `prompts/shared/*.md`, `docs/system/*.md` (cited inline as `file:line`).
External (retrieved 2026-06-25): conversion.com/framework/the-lift-model; nngroup.com (heuristic evaluation; progressive disclosure); baymard.com (UX-Ray 2026 roadmap); unbounce.com/conversion-rate-optimization/cro-audit; aprildunford.com; storybrand.com workbook; lyssna.com/guides/five-second-testing; frontify.com/en/guide/brand-audit; durable.com; looka.com/brand-kit; canva.com/canva-ai; adcreative.ai/creative-scoring; lovable.dev; v0.dev; bolt.new; figma.com/blog/figma-make-general-availability; platform.claude.com/cookbook (frontend aesthetics); playwright.dev/docs/screenshots; github.com/abi/screenshot-to-code; businessmodelanalyst.com/lean-canvas; chameleon.io/blog/jobs-to-be-done; candu.ai (Notion/Airtable onboarding).

---

## Update log

### 2026-06-25 — P1 Novice Onboarding Wizard SHIPPED

The first roadmap item the owner chose was built and verified the same day (independent review, 36 tests green).

- `aicmo onboard --client <slug> --from answers.json` deterministically scaffolds a **placeholder-free, jargon-annotated** Korean `config.md` + `brand-guidelines.md` + 3 KB files from 7 plain-language answers. Inline definitions for ICP/UVP/CTA; safe slug validation; no-overwrite-without-`--force`.
- `playbooks/07-operations/client-onboarding.md` rewritten **wizard-first**: Mode A writes `config.md` **before** any agent runs — this breaks the pre-onboarding **circular dependency** flagged in §3.5.
- `clients/_template/config.md` de-jargoned (the blank jargon table in §3.2 is gone).
- New code: `src/aicmo/onboarding.py`, `src/aicmo/templates/onboarding/*.md`, `tests/test_onboarding.py`.

This closes the "Novice self-serve onboarding" gap at the config layer. It does **not** by itself remove the P3 dependency (a non-CLI entry point is still required before a true non-technical user can self-serve end to end), and it does **not** touch P0 (the live-execution stub) — recommended next.

### 2026-06-25 — P0 Live Execution Adapter SHIPPED

The §0 verdict's central defect ("it does not generate anything") is now structurally fixed (independent review, 45 tests green).

- New `src/aicmo/adapters.py`: `StepAdapter` Protocol + `LocalAdapter` (deterministic default — keeps every existing test green) + `CommandAdapter` (pipes the composed prompt to an operator-configured subprocess on stdin and captures stdout as the artifact). `step_executor._run_agent` now delegates generation to the injected adapter; a missing role/prompt file still fails the step exactly as before.
- CLI: `aicmo run --executor-cmd "<cmd>"` (also on `resume`) selects a live executor, e.g. `--executor-cmd "claude -p"`, `"codex exec"`, `"ollama run llama3"`, or any script. Default (no flag) = the deterministic local adapter.
- Surface-proven on the real CLI with `examples/executors/echo_executor.py`: the composed 11k-char prompt is genuinely piped to an external process and its real stdout is written as `draft.md` (not the stub). Executor failure (non-zero/missing/timeout) → clean run failure with no stranded RUNNING step.
- Honest limitation: a `claude -p` headless smoke timed out in this sandbox (auth/interactive), so wiring a specific LLM CLI is an operator configuration step; `claude`/`codex` are on PATH. An Anthropic-SDK adapter (API-key based) can be added behind the same `StepAdapter` Protocol.

The stub→real unlock is done at the executor layer. Remaining to make the live path turn-key for a non-technical owner: P2 (real reviewer gate that evaluates content + KB consumer) and P3 (non-CLI entry point).

### 2026-06-25 — P2 engine, P1 evaluation, P2 mockup, P3 access ALL SHIPPED

The remaining roadmap was built out sequentially, each built test-first and verified on the real CLI surface with independent review. Final suite: **71 tests green, ruff(ALL) + basedpyright clean.**

- **P2 — real reviewer gate** (`src/aicmo/gate.py`): `_run_gate` no longer hardcodes PASS. It evaluates the gated artifacts deterministically (empty / TODO·TBD·placeholder `{{}}` → FAIL; thin → WARN; else PASS), checks against `pass_if`, and a FAIL stops the run. Recognizes the offline-stub sentinel → WARN so deterministic default runs still pass. Surface-proven: a TODO artifact fails the run at `review`; clean passes.
- **P2 — KB consumer** (`src/aicmo/reporter.py`, `aicmo kb-flush`): dequeues queued `kb_updates` → appends to `knowledge-base/<client>/insights.md` (append-only) and marks them consumed (idempotent). Closes the durable-learning loop.
- **P1 — objective evaluation engine** (`src/aicmo/evaluate.py`, `aicmo evaluate`): scores an existing asset 0–100 across 7 sourced dimensions (clarity/value/CTA/proof/narrative/readability/structure), band PASS/WARN/FAIL/CRITICAL, prioritized fixes. Surface: strong copy 94/PASS, weak 21/CRITICAL with an ordered improvement list. **The differentiator — coldly evaluates already-made assets.**
- **P2 — mockup generator** (`src/aicmo/mockup.py`, `aicmo mockup`): turns the same 7 onboarding answers into a real, self-contained, responsive HTML landing page (a viewable 시안 + clickable minimum prototype), all fields HTML-escaped. PNG via Playwright degrades gracefully to an "unavailable" status when absent.
- **P3 — non-CLI access layer** (`src/aicmo/web.py`, `aicmo serve`): a dependency-free localhost web app — a plain-Korean form (the 7 questions) → POST → the brand's landing 시안 rendered in the browser. This is the entry point a non-technical owner ("mom") can actually use. Surface: real server, GET form + POST returns the brand mockup; hardened against malformed Content-Length (socket-level test).

**Status vs. the vision:** the engine now (1) executes real work (P0 adapter), (2) onboards a novice in plain language (P1 wizard), (3) coldly evaluates existing assets with improvements (P1 eval), (4) produces real design mockups/prototypes (P2 mockup), (5) gates quality for real + accumulates knowledge (P2), and (6) is reachable without a CLI (P3 web). Remaining future work is now about *depth*, not *existence*: wiring a specific LLM into the adapter for bespoke generation, an LLM-backed semantic reviewer behind the deterministic gate, hosting/deployment, and per-agent model selection in the workflow spec.
