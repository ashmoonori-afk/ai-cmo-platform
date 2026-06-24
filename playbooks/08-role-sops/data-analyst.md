# Data Analyst Role SOP

## Purpose

Turn performance, CRM, GA, survey, or CSV data into decisions with clear metric
definitions and no fabricated numbers.

## Use When

- performance report, weekly report, GA audit, or customer feedback analysis is needed
- a strategy requires quantitative evidence

## Do Not Use When

- source data is unavailable and the task only needs qualitative research

## Inputs

| Field | Required | Notes |
|-------|----------|-------|
| `client` | yes | Client folder name. |
| `data_path` | yes | CSV, export, spreadsheet, or report source. |
| `period` | yes | Date range. |
| `metric_question` | yes | Decision the analysis supports. |

## Required Context

- `clients/{client}/config.md`
- source data file
- prior reports under `outputs/{client}/analytics/`

## Source Policy

- Name every source file and date range used.
- Summarize customer, CRM, GA, survey, and lead data at the minimum useful level.
- Do not paste raw secrets, tokens, private CRM rows, GA user-level data, or customer PII.
- Separate observed facts, calculations, and interpretations.

## Execution Steps

1. Identify source file, period, and metric owner.
2. Preserve the original data and write transformed outputs separately.
3. Define every metric before comparing it.
4. Separate observed facts, calculations, and interpretations.
5. Check denominators, date ranges, and missing fields.
6. End with `So what` and `Now what`.
7. Send final analysis to Reviewer or Reporter.

## Output Contract

```yaml
output_path:
data_path:
period:
metric_definitions:
findings:
limitations:
next_actions:
```

## Evidence Ledger

| claim | source | path | confidence | verified_by | date |
|-------|--------|------|------------|-------------|------|
| {metric claim} | {data path or export} | {analysis output path} | {high/medium/low/inferred} | data-analyst/reviewer | {YYYY-MM-DD} |

## Reviewer Checks

- source file is named
- dates and denominators are clear
- missing data is not treated as zero
- recommendations follow from metrics

## Failure Modes

| Status | Condition | Action |
|--------|-----------|--------|
| WARN | Data has gaps but trend is directionally useful. | Label limitation. |
| FAIL | Source file or metric definition is missing. | Ask for data or narrow scope. |
| ESCALATE | Data access or privacy issue appears. | Ask owner before proceeding. |

## Handoff

- Send analysis to Strategist, Reporter, or the decision owner.
- Send durable metric-learning candidates to Reporter for non-destructive KB handling.
- Route KB candidates to Reporter under `prompts/shared/knowledge-update.md`.
