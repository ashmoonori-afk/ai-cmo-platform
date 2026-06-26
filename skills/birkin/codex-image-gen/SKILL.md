---
name: codex-image-gen
description: "Route approved real-image generation requests and require file-path proof instead of fake visual completion."
version: 1.0.0-ai-cmo
license: MIT
source: "Adapted from the Birkin codex-image-gen skill for standalone AI CMO Platform use."
---

# codex-image-gen

## Purpose

Use codex-image-gen when the AI CMO workflow needs a real raster image, ad
visual, thumbnail, campaign scene, or product visual. The platform must never
claim that an image exists unless a generated file path exists.

## When To Use

- The user asks for a real image or visual asset.
- A content playbook sets `image_required=yes`.
- A campaign or social output needs a prompt brief and image route.

## When Not To Use

- Plain copy, strategy, SEO, analytics, or sales text.
- ASCII diagrams or simple layout descriptions.
- Any case where no approved image route exists. Mark the visual route
  unavailable or approval-needed instead.

## Approved Routes

Use the first available approved route:

1. A local or inherited image generation tool available in the current agent
   environment.
2. An approved CLI or app workflow selected by the operator.
3. A manual handoff to a designer or downstream image agent.

Do not require a Birkin installation. Do not require a Birkin MCP server.

## Required Output Contract

Exactly one state must be true:

```yaml
visual_asset_status: generated
png_path:
```

```yaml
visual_asset_status: unavailable
unavailable_reason:
```

```yaml
visual_asset_status: needs_approval
approval_owner:
```

## Prompt Brief Format

```yaml
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

## UI And Design Prompt Assist

When the requested visual is a design mockup, dashboard, app screen, UI concept,
or marketing layout, help the operator build the prompt before image generation.
Use these reference patterns:

- GPT-Image2-Skill prompt gallery and skill:
  https://github.com/wuyoscar/GPT-Image2-Skill
- Evolink GPT image prompt examples:
  https://evolink.ai/gpt-image-2-prompts

For UI prompts, keep this order so the generator receives a precise brief:

```yaml
background_or_scene:
screen_or_subject:
layout_structure:
core_components:
content_density:
brand_constraints:
typography:
color_and_lighting:
interaction_cues:
must_include:
must_avoid:
output_path:
```

Prefer concrete UI details over vague style words. State the actual product,
screen state, data modules, navigation, cards/tables/charts, and any mobile or
desktop viewport constraints. If the user has not chosen a format, ask for the
desired artifact format before generation and produce that exact format.

## Completion Rule

Reviewer must fail any artifact that claims visual completion without
`visual_asset_status=generated` and a real `png_path`, or without an explicit
`unavailable` / `needs_approval` state.
