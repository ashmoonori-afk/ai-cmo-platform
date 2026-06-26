---
name: ultraresearch-swarm
description: "Force a project-operating agent to run an evidence-bound $omo:ultraresearch-style research swarm before high-risk AI CMO phases."
version: 1.0.0-ai-cmo
license: MIT
source: "AI CMO Platform embedded operating skill."
---

# ultraresearch-swarm

## Purpose

Use this skill when an AI CMO workflow phase needs current, source-backed
research before strategy, copy, design, or execution decisions. This skill makes
the research step mandatory for the operating agent instead of optional
background browsing.

## Trigger

Run this skill before any phase that depends on market facts, competitor claims,
trend analysis, pricing, SEO data, platform rules, or UI/image generation
references. If the operator explicitly requests `$omo:ultraresearch`, treat this
skill as the local project contract for that request.

## Required Swarm Shape

The operating agent must create a compact research plan, then split work across
at least these tracks when tools are available:

1. Codebase librarian: inspect repo prompts, playbooks, workflows, previous KB,
   and tests that constrain the phase.
2. Web explorer: gather current external evidence from primary or high-quality
   sources.
3. Competitor and market checker: verify comparable offers, positioning, claims,
   and channel assumptions.
4. Artifact reviewer: convert findings into phase-specific acceptance criteria.

If true subagents are unavailable, the operating agent must simulate the tracks
sequentially and label evidence by track.

## Evidence Contract

Every research phase must produce a Markdown artifact under:

```text
artifacts/{run_id}/research/{phase_id}.md
```

The artifact must include:

- `phase_id`
- `research_question`
- `sources_checked`
- `facts_to_use`
- `risks_or_unknowns`
- `artifact_acceptance_criteria`
- `handoff_to_next_phase`

Do not continue to dependent generation until this artifact exists. Do not use
unsourced claims as decisive facts.

## User-Facing Phase Announcement

Before starting the phase, tell the user which research artifact will be
created and what downstream artifact it unlocks. Example:

```text
phase research_strategy deliverables:
  artifacts/{run_id}/research/research_strategy.md
  unlocks: artifacts/{run_id}/strategy.md
```

## Completion Rule

The phase is complete only when the research artifact exists, sources are
listed, and the next phase can point to the research artifact as evidence.
