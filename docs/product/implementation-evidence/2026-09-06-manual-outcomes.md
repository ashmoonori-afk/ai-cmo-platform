# Manual outcomes and reviewed weekly summaries

## 한 장 요약

The existing weekly-report playbook summarized generated documents but had no persisted daily outcome
input or runnable reporting workflow. This change adds validated manual counts, a preview/import
boundary, and a native weekly calculation followed by the existing terminal reviewer gate.
Document generation, actual posting, and observed business outcomes remain distinct.

## Implemented behavior

- `aicmo outcomes` previews UTF-8/BOM CSV headers, date window, channel, existing/proposed rows,
  source SHA, and a versioned confirmation SHA. It accepts one channel and 1–7 daily rows per week.
  Supported channel labels are manual classifications, not integrations. All dates use Asia/Seoul.
- Counts are bounded nonnegative integers or null. Malformed encoding, rows, duplicate headers/dates,
  formulas, control characters, other weeks/channels, future observations, and extra columns fail
  without echoing the invalid cell contents.
- Confirmation binds schema, client, week, channel, input bytes and current stored rows. Import checks
  it again under `BEGIN IMMEDIATE`. Differing rows require explicit replacement; omitted dates survive.
  Replacement includes null cells and is described as whole-row correction in the preview instructions.
- A primary key prevents duplicate daily records. Confirmation receipts make successful request replay
  a no-op when proposed values still match, while later corrections reject stale replay. Conflicts roll
  back the whole import, including any earlier rows written in the same request.
- `metrics.report` produces a frozen weekly report with current/previous daily data, per-metric
  coverage, source CSV SHA, revision numbers, and snapshot SHA. Percent change requires two complete
  weeks and a positive previous total. Unknown data and an observed zero are not interchangeable.
- A successful report remains the same on resume after a source correction; a new run produces a new
  snapshot and review. Existing artifact/dependency hashes protect the frozen report version.
- Native calculation does not become demo content merely because no generation adapter was configured.
  Agent workflows still retain the demo guard. Final reviewer configuration and PASS remain required
  for `deliverable=true`; file existence alone is not delivery approval.
- Weekly-report documentation/registry/AGENTS are synchronized. The native report does not append KB
  knowledge automatically. Reviewed adoption and feedback are separate roadmap work.

## Validation and actual artifact

Regression tests exercise preview/import/replay, whole-request rollback, concurrent duplicate imports,
stale file/database previews, invalid schema values, row limits/encoding, client/channel isolation,
partial/zero/complete week arithmetic, CLI JSON/text preview, and native report/reviewer/resume behavior.
Full pytest: **464 passed in 193.31s**. Ruff PASS, basedpyright **0 errors / 0 warnings**, and
`git diff --check` PASS. A subsequent documentation-only edit clarified KB candidate handling;
the final native reporting/workflow/registry checks passed **50 tests in 6.79s**, and the real
synthetic workflow was rerun against that prompt version with artifact hashes verified.
Independent reviewer: **PASS**, separate **98 tests in 34.63s** and full **464 tests in 179.21s**.
The reviewer reconstructed the report snapshot SHA and metric totals from SQLite and verified
all three output hashes. Records, confirmation receipts, and the report agree.

A real PowerShell CLI preview and confirmed import stored seven synthetic daily rows. Repeating the
same confirmed command reported zero changed rows. The native workflow generated an actual Markdown
report and delivery JSON with a synthetic reviewer, and all three produced files passed the existing
artifact/dependency hash verification. The report contains posts=2 across 7/7 days and inquiries=6
across 6/7 days, retaining missing data. These are fixture values, not customer results or live-model proof.

## Sources and limits

The implementation uses Python's existing [csv](https://docs.python.org/3/library/csv.html) and
[sqlite3](https://docs.python.org/3/library/sqlite3.html) support (checked 2026-09-06), plus already
installed Pydantic. No dependency was added. The column, count, file-size, and timezone limits are
documented product constraints, not platform-wide or legal requirements.

The local CLI does not authenticate the record provider as the store owner. Its report labels data as
user-provided records, not independently verified results. This feature does not establish causal
attribution, revenue, live integrations, tenant authentication, or real-user usability. G02 remains OPEN.

## 다음 단계

1. Use `docs/OUTCOMES.md` and the synthetic CSV to verify a prepared local store's reporting flow.
2. Connect reviewed adoption/edits and remaining usage limits through the existing roadmap.
3. Keep actual user, business, and paid-operation evidence separate from these implementation checks.
