# Dogfooding Run: Full SOP / Platform End-to-End

**Date**: 2026-06-26
**Route**: System/product — full operating surface
**Owner**: AI CMO Platform maintainer
**Risk level**: Medium
**Request**: Dogfood the entire SOP — exercise every `aicmo` CLI surface and both
workflows end-to-end as a real user, verify SOP/doc coherence, log all defects, and fix
what is cheap and reproducible. Baseline before the run: 91 tests, ruff (ALL) and
basedpyright (`src tests`) clean.

## Intake

After PRs #4–#7 the platform grew a value layer (onboard, evaluate, mockup, serve,
kb-flush), an LLM/executor seam, and reliability hardening (atomic writes, hash-verified
resume, idempotent KB, fail-closed gate, concurrency lease). The dogfood goal was to prove
those work together on real commands, not only in unit tests, and to catch any drift
between the documented SOP and the running engine.

## Neurosis Clarity Gate

- Resolved: live generation runs via the Claude Code CLI (`--executor claude`), not an API
  key; headless `claude -p` is unavailable in this sandbox, so the deterministic
  LocalAdapter (and a deterministic echo-executor) were used to prove the pipe.
- Unresolved (non-blocking): real-model generation quality is only observable in the
  owner's authenticated terminal.

## Triage

Routed to the system/product path: it exercises runtime behavior, CLI, web surface, and
the documentation that ships with the GitHub link.

## Odyssey Plan (acceptance criteria)

Six CLI dimensions were dogfooded in parallel (one isolated temp repo/DB per agent), plus a
doc-coherence pass, each with explicit acceptance criteria:

| Dimension | Acceptance |
|-----------|-----------|
| engine: blog-article | run → 5 real artifacts; status 5/5 success; resume idempotent; delete-artifact → regenerate; list-runs |
| engine: approval gate | waiting_approval (exit 75) → approve → success; reject → retry blocked with concise error, no traceback |
| onboard + evaluate | onboard → placeholder-free jargon-annotated config+brand+KB; evaluate strong ≥80/PASS, weak <40/CRITICAL + fixes |
| mockup + web | mockup → valid escaped HTML; serve GET form + POST mockup (UTF-8 Korean roundtrip) |
| kb + reliability | kb-flush append+idempotent+crash-idempotent; tamper-resume restores; gate fails closed on empty text |
| concurrency + presets | live foreign lease blocks resume; crash lease recovers; `--executor` presets + clean unknown error |
| SOP/doc coherence | routing terms present; private-data gates; handoff JSON valid; new commands documented |

## Execution

**All six CLI dimensions: PASS** (independently verified by six parallel dogfooding agents
running real `uv run aicmo` commands against isolated temp repos/DBs; every agent cleaned up
its temp + artifacts). Highlights proven on the real CLI:

- blog-article: 5 artifacts with real content; idempotent resume (byte-identical, attempts
  unchanged); deleting `draft.md` → regenerated (attempt 1→2) while untouched steps stayed at 1.
- approval gate: `waiting_approval` (exit 75) → approve → success; rejected-gate retry fails
  with `rejected gate decision is terminal; start a new run`, exit 1, no traceback.
- onboard: 5 files for a coffee brand, **zero leftover `{{…}}` placeholders**, ICP/CTA defs present.
- evaluate: strong copy 86/100 PASS, weak 29/100 CRITICAL with a prioritized fix list.
- mockup/web: valid Tailwind HTML, XSS payload escaped; web form GET + POST roundtrip Korean UTF-8.
- reliability: KB crash-idempotent (one block after re-queue), tamper-resume restored
  `draft.md` byte-for-byte via sha256 mismatch, empty-text gate FAILed closed.
- concurrency/presets: live foreign lease blocked resume (draft attempt unchanged), crash
  lease recovered (1→2); `--executor` presets resolve, unknown errors cleanly.

Three cheap, reproducible defects were fixed during the run (see Defect Log).

## Defect Log

| ID | Severity | Surface | Symptom | Root Cause | Fix | Verification | Status |
|----|----------|---------|---------|------------|-----|--------------|--------|
| DF-DOG-01 | low | `cli.py` main guard | CLI error messages went to **stdout**, not stderr (POSIX), polluting captured output. | Error branches used the stdout `console`. | Added `err_console = Console(stderr=True)`; error/unexpected branches print to it. | `aicmo … --executor bogus 1>/dev/null` → message only on stderr; updated `test_main_reports_unexpected_error_without_traceback`. | closed |
| DF-DOG-02 | low | `aicmo evaluate` console | The prioritized improvement list only appeared with `--out`; plain console showed scores only. | `evaluate_cmd` printed dimensions but not `result.improvements`. | Print `개선 우선순위` block to console after the dimension loop. | `aicmo evaluate --from weak.md` now lists fixes in the console. | closed |
| DF-DOG-05 | low | `kb-flush` count message | On crash-replay, `kb-flush` reported "1 appended" though 0 new content was written. | `flush_kb_updates` always incremented the counter even when the marker made the append a no-op. | `_append_insight` now returns `bool`; the counter increments only on a real append. | `test_kb_flush_idempotent_under_replay` asserts the replay flush returns `0`. | closed |
| DF-DOC-01 | medium | `README.md`, `docs/system/workflow-engine.md` | The value-layer commands (`onboard`/`evaluate`/`mockup`/`serve`/`kb-flush`) and `--executor`/`--review` were undocumented. | Docs were not updated alongside PRs #4–#7. | Added the commands to the README example block and the workflow-engine §CLI row. | `rg` shows the commands now present in both. | closed |
| DF-DOG-03 | low | `aicmo onboard` date | Onboarding date defaults to UTC date, can be a day behind a local calendar east of UTC. | `datetime.now(UTC)`; overridable via `--date`. | Accepted — `--date` override exists; surfacing the stamped date is a future polish. | n/a | accepted |
| DF-DOG-04 | low | dogfooding harness | `pkill` is unavailable in the Git Bash sandbox; the `serve` teardown step needed PowerShell. | Environment, not product. `aicmo serve` shuts down cleanly via Ctrl-C / process kill. | Accepted — harness/runner caveat only. | n/a | accepted |
| DF-DOG-06 | low | lease TTL constants | Operative lease TTL is 30s (`step_executor.lease_ttl_seconds`) while `step_state._DEFAULT_LEASE_TTL` is 300s; manual lease-injection tests must finish within 30s. | Two TTL defaults for two callers (runtime executor vs. ad-hoc direct `mark_step_running`). | Accepted — intentional (30s operative is renewed by the heartbeat; 300s is a conservative fallback for direct calls). Documented here. | n/a | accepted |
| DF-DOC-02 | low | `CLAUDE.md` folder comment | Says "40 playbooks"; actual is 55. | Comment not updated as playbooks grew. | Accepted — `CLAUDE.md` is protected (baseline-inventory) and this is a cosmetic appendix comment, not the functional routing map. | n/a | accepted |
| DF-DOC-03 | medium | sensitive playbooks | `02-intelligence` / `06-analytics` lack the **inline** private-data gate headers the procedure scan expects. | Safety is centralized (CLAUDE.md "Mandatory safety gate" + `prompts/shared/gate-check.md` "Safety And Trust Gate"). | Accepted — central gates cover the behavior; a per-playbook gate-reference pass is queued as follow-up. | central gate present in `gate-check.md` | accepted |

No `blocker` or `high` defect was found. No reproducible `medium` remains open (DF-DOC-01
fixed; DF-DOC-03 accepted with a central-gate rationale and a queued follow-up).

## Verification

Commands from the repository root after the fixes:

```powershell
uv run pytest -q                       # 91 passed
uv run ruff check src tests examples   # All checks passed
uv run basedpyright src tests          # 0 errors, 0 warnings, 0 notes
git diff --check                       # no whitespace errors
```

Real CLI surfaces (captured during the run): blog run/status/resume/list-runs,
approval approve/reject/retry, onboard, evaluate (strong/weak), mockup, serve GET+POST,
kb-flush (incl. crash-replay), tamper-resume, empty-gate fail-closed, lease block+recover,
`--executor` presets — all observed as documented.

## Reviewer Gate

**PASS**

- Every CLI command and both workflows run end-to-end on the real CLI.
- Reliability guarantees (atomic write, hash-verified resume, idempotent KB, fail-closed
  gate, concurrency lease) hold under direct manipulation.
- All discovered defects are low (3 fixed, 4 accepted) or documentation (1 fixed, 2
  accepted); no internal blocker remains open.
- Docs now match the shipped command surface.

## Reporter Notes

Durable learning candidates:

- The platform is reliable enough to trust with real client work via the CLI; remaining
  items are polish (stderr/console UX), documentation depth, and product packaging.
- Live generation is a CLI-executor concern (`--executor claude`), decoupled from the
  engine — proven via the deterministic echo-executor; real-model output is the owner's
  authenticated-terminal concern.

## Follow-Up Queue

| Priority | Owner | Action | Status |
|----------|-------|--------|--------|
| P2 | SOP/docs | Add per-playbook private-data gate references to `02-intelligence` and `06-analytics`, matching the procedure's gate scan (DF-DOC-03). | queued |
| P3 | Product | Surface the stamped onboarding date in the `onboard` success message; consider local date (DF-DOG-03). | queued |
| P3 | Product | Unify/clarify the lease TTL constants and expose `lease_ttl_seconds` via CLI/env for slow-start environments (DF-DOG-06). | queued |
| P3 | Product | Hosting/deploy of `aicmo serve`; named executor profiles with timeouts/redaction. | queued |
