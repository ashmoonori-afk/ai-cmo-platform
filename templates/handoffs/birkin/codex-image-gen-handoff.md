# codex-image-gen Handoff

```yaml
visual_goal:
channel:
aspect_ratio:
audience:
brand_constraints:
must_include:
must_avoid:
prompt:
output_path:
png_path:
unavailable_reason:
approval_owner:
visual_asset_status:
reviewer_notes:
```

Exactly one visual route must be true:

- `visual_asset_status=generated` with a real `png_path`
- `visual_asset_status=unavailable` with `unavailable_reason`
- `visual_asset_status=needs_approval` with `approval_owner`
