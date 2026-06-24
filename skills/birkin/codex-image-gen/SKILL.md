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

## Completion Rule

Reviewer must fail any artifact that claims visual completion without
`visual_asset_status=generated` and a real `png_path`, or without an explicit
`unavailable` / `needs_approval` state.
