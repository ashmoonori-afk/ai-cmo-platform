# codex-image-gen Handoff

## Use When

Use codex-image-gen only when the user asks for a real image, ad visual,
thumbnail, card-news visual, product scene, or campaign concept image.

## Required Inputs

- visual goal
- channel and aspect ratio
- audience
- brand constraints
- must-include elements
- must-avoid elements
- output path
- approval owner

## Expected Output

```yaml
prompt:
output_path:
png_path:
visual_asset_status: generated | unavailable | needs_approval
reviewer_notes:
```

## Operating Rule

Never fake image completion. A visual task is complete only when
`visual_asset_status=generated` includes a real `png_path`, or the route is
marked `visual_asset_status=unavailable` or `visual_asset_status=needs_approval`.

## Evidence

Record the generated file path, prompt, and reviewer notes in the final content
artifact.

## Failure Handling

If image generation is unavailable, return the prompt brief and mark
`visual_asset_status=unavailable`. Do not claim that the image was generated.
