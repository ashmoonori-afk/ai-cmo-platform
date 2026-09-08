# Provider completion and logical-call observations

## 한 장 요약

The direct Anthropic adapter previously accepted nonempty text without checking whether generation
completed. It also discarded provider usage. The shared executor now observes logical calls through
the existing event store, and the direct adapter rejects incomplete responses before artifact writing.
G02 and the remaining G09 quota, billing, and live-provider acceptance work remain OPEN.

## Implementation boundary

- Accept only `end_turn` with nonempty text blocks. Truncation, context exhaustion, refusal,
  tool requests, pauses, stop sequences, and unknown stop reasons return an error without deliverable text.
- Preserve reported input/output/cache token counts even when a response cannot be delivered.
  Missing, negative, boolean, and noninteger counts are unavailable, not zero.
- Record separate started/finished events for generation, semantic review, and reviewer format repair.
  Call IDs and step attempts distinguish these invocations. A crash may leave a started call unfinished.
  Elapsed time includes local observation overhead and is not pure network latency.
- Reuse the existing event store; no new dependency, billing ledger, or automatic continuation.
  Observation metadata contains identifiers and counts, not prompts or generated content.
  Apply supported PII minimization and a bounded identifier syntax before storing custom metadata.
  Unsupported free-text metadata becomes unavailable. Existing secret redaction remains active.
- Minimize supported customer PII in the initial reviewer response before sending format-repair input.
- `aicmo usage RUN` displays observations, retaining requested model identification when no response
  model is known. CLI executors without usage metadata report unavailable; demo cost is not applicable.

## Verification scope

Synthetic provider responses cover completion reasons, empty/non-text blocks, zero versus missing
usage, failed generation without artifact writing, custom metadata privacy, invalid counts, and CLI
inspection. Reviewer tests distinguish initial and repair calls and verify minimized repair input.
Final full pytest: **438 passed in 175.63s**. Ruff PASS, basedpyright **0 errors / 0 warnings**,
and `git diff --check` PASS. These results apply to the final code including custom metadata guards.
Independent reviewer: **PASS**, including a separate full **438 passed in 177.81s** run.
The review reproduced and closed unsafe custom metadata storage and static-check failures.

No real provider call or customer charge was made to establish these results. Logical calls do not
count SDK-internal retries, and a lost response does not prove that the provider did not charge.
No price, reservation, quota enforcement, refund, invoice reconciliation, or model availability is
established by these observations. Pattern-based minimization is not complete anonymization.

## Official response contract

Sources checked 2026-09-06:

- [Anthropic stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons):
  natural completion and other stopping conditions require different handling.
- [SDK Message type](https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/message.py):
  response content, model, stop reason, and usage fields.
- [SDK Usage type](https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/usage.py):
  input/output counts and optional cache counters. The implementation records components separately.

## 다음 단계

1. Review final regressions and preserve the distinction between unavailable and observed zero.
2. Implement remaining roadmap quota and manual-outcome work without treating these events as billing.
3. Validate live-provider and paid-operation behavior only with the required operational evidence.
