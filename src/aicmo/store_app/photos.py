from __future__ import annotations

import hashlib
import sqlite3
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from pydantic import TypeAdapter

from aicmo.errors import AicmoError, RunNotFoundError
from aicmo.photos import PhotoAsset, PhotoSelection, asset_path, verify_photo_assets
from aicmo.store_app import services
from aicmo.store_app.models import Store


def store_photo(
    store: Store, normalized: tuple[bytes, int, int], caption: str, rights_basis: str
) -> str:
    data, width, height = normalized
    selection = PhotoSelection.model_validate(
        {
            "photos": [
                {
                    "news_index": 0,
                    "caption": caption,
                    "rights_basis": rights_basis,
                    "privacy_reviewed": True,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "width": width,
                    "height": height,
                    "byte_length": len(data),
                }
            ]
        }
    )
    photo: PhotoAsset = selection.photos[0]
    root = Path(settings.REPO_ROOT)
    target = asset_path(root, str(store.client), photo.sha256)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Recheck after directory creation; client namespaces must never follow a junction.
    target = asset_path(root, str(store.client), photo.sha256)
    if not target.exists():
        with TemporaryDirectory(prefix=".photo-", dir=target.parent) as temporary:
            staging = Path(temporary) / "image.png"
            staging.write_bytes(data)
            staging.replace(target)
    manifest = selection.model_dump_json()
    verify_photo_assets(root, {"client": str(store.client), "photos_json": manifest})
    return manifest


@login_required
@require_GET
@never_cache
def preview(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_job(request.user, job_id)
    try:
        inputs = TypeAdapter(dict[str, str]).validate_python(job.inputs, strict=True)
        if inputs.get("client") != job.store.client:
            raise Http404
        runner = services.reader()
        try:
            runner.store.db_path.stat()
        except FileNotFoundError:
            frozen = None
        else:
            try:
                frozen = runner.store.get_inputs(job.run_id)
            except RunNotFoundError:
                frozen = None
        if frozen is not None and frozen != inputs:
            raise Http404
        if frozen is None and (job.state not in ("queued", "running") or job.approval):
            raise Http404
        files = verify_photo_assets(Path(settings.REPO_ROOT), inputs)
        if set(files) != {"photos/news-1.png"}:
            raise Http404
    except (AicmoError, OSError, ValueError, sqlite3.Error):
        raise Http404 from None
    response = HttpResponse(files["photos/news-1.png"], content_type="image/png")
    response["X-Content-Type-Options"] = "nosniff"
    return response
