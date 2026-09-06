from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from aicmo.errors import AicmoError
from aicmo.onboarding import scaffold_client
from aicmo.paths import native_io_path, resolve_inside_repo
from aicmo.store_app.forms import onboarding_answers
from aicmo.store_app.models import OnboardingDraft, Store
from aicmo.store_app.onboarding import new_owner, validated_values
from aicmo.store_app.services import StoreActionError

_MAX_PROFILE_FILE = 64 * 1024
_PROFILE_FILES = (
    "config.md",
    "brand-guidelines.md",
    "pricing-rules.md",
    "copy-patterns.md",
    "primer-report.html",
)
_KB_FILES = ("insights.md", "winning-copy.md", "lessons-learned.md")


class FileStamp(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(ge=1, le=_MAX_PROFILE_FILE)


def _path(root: Path, relative: str) -> Path:
    resolved = resolve_inside_repo(root, relative, {})
    if resolved != root.resolve() / relative:
        reason = "onboarding path must not redirect"
        raise StoreActionError(reason)
    return resolved


def _stamp(path: Path) -> FileStamp:
    with native_io_path(path).open("rb") as stream:
        data = stream.read(_MAX_PROFILE_FILE + 1)
    return FileStamp(sha256=hashlib.sha256(data).hexdigest(), size=len(data))


def _expected(client: str) -> set[str]:
    return {f"clients/{client}/{name}" for name in _PROFILE_FILES} | {
        f"knowledge-base/{client}/{name}" for name in _KB_FILES
    }


def _verify_directory(directory: Path, stamps: dict[str, FileStamp]) -> None:
    contents = list(native_io_path(directory).iterdir())
    if {path.name for path in contents} != set(stamps) or any(
        path.is_symlink() or path.is_junction() or not path.is_file() for path in contents
    ):
        reason = "onboarding directory differs from its confirmed manifest"
        raise StoreActionError(reason)
    if any(_stamp(path) != stamps[path.name] for path in contents):
        reason = "onboarding file changed"
        raise StoreActionError(reason)


def _prepare(draft: OnboardingDraft, root: Path, values: dict[str, str]) -> None:
    if draft.confirmed_at is None:
        reason = "onboarding confirmation is missing"
        raise StoreActionError(reason)
    if draft.attempts >= OnboardingDraft.MAX_ATTEMPTS:
        reason = "onboarding preparation attempts exhausted"
        raise StoreActionError(reason)
    draft.attempts += 1
    draft.save(update_fields=["attempts", "updated_at"])
    attempt = uuid.uuid4()
    stage = _path(root, f".aicmo/onboarding/{draft.id.hex}/{attempt.hex}")
    native_io_path(stage).mkdir(parents=True, exist_ok=False)
    answers = onboarding_answers(
        values, draft.client, timezone.localtime(draft.confirmed_at).date().isoformat()
    )
    result = scaffold_client(stage, answers, pdf=False)
    stamps = {path.relative_to(stage).as_posix(): _stamp(path) for path in result.created}
    if set(stamps) != _expected(draft.client):
        reason = "onboarding output contract changed"
        raise StoreActionError(reason)
    changed = OnboardingDraft.objects.filter(
        pk=draft.pk, state="running", stage_id__isnull=True
    ).update(
        stage_id=attempt,
        output_hashes={path: stamp.model_dump() for path, stamp in stamps.items()},
    )
    if changed != 1:
        reason = "onboarding changed before publication"
        raise StoreActionError(reason)
    draft.refresh_from_db()


def _promote(draft: OnboardingDraft, root: Path) -> None:
    if draft.stage_id is None:
        reason = "onboarding stage receipt is missing"
        raise StoreActionError(reason)
    stamps = TypeAdapter(dict[str, FileStamp]).validate_python(draft.output_hashes, strict=True)
    if set(stamps) != _expected(draft.client):
        reason = "invalid onboarding file manifest"
        raise StoreActionError(reason)
    stage = _path(root, f".aicmo/onboarding/{draft.id.hex}/{draft.stage_id.hex}")
    for category in ("clients", "knowledge-base"):
        relative = f"{category}/{draft.client}"
        target = _path(root, relative)
        expected = {
            Path(path).name: stamp
            for path, stamp in stamps.items()
            if path.startswith(relative + "/")
        }
        if not native_io_path(target).exists():
            source = _path(stage, relative)
            _verify_directory(source, expected)
            native_io_path(target.parent).mkdir(parents=True, exist_ok=True)
            native_io_path(source).rename(native_io_path(target))
        _verify_directory(target, expected)


def _finish(draft: OnboardingDraft, values: dict[str, str]) -> None:
    with transaction.atomic():
        current = OnboardingDraft.objects.select_related("owner").get(pk=draft.pk)
        if current.state != "running" or not new_owner(current.owner):
            reason = "onboarding owner or state changed"
            raise StoreActionError(reason)
        current.store = Store.objects.create(
            owner=current.owner, name=values["company_name"], client=current.client
        )
        current.state = "complete"
        current.save(update_fields=["store", "state", "updated_at"])


def run_onboarding() -> bool:
    """Called under the existing repository worker lock; no provider configuration is needed."""
    draft = (
        OnboardingDraft.objects.filter(state__in=["queued", "running"])
        .order_by("updated_at")
        .first()
    )
    if draft is None:
        return False
    OnboardingDraft.objects.filter(pk=draft.pk).update(state="running")
    draft.refresh_from_db()
    failure_code = "invalid_input"
    try:
        if not new_owner(draft.owner):
            reason = "onboarding owner is not eligible"
            raise StoreActionError(reason)  # noqa: TRY301 — record rejection as failed below
        values = validated_values(draft)
        root = Path(settings.REPO_ROOT)
        if draft.stage_id is None:
            if draft.output_hashes != {}:
                reason = "onboarding manifest is missing its stage"
                raise StoreActionError(reason)  # noqa: TRY301 — record rejection as failed below
            failure_code = "prepare_failed"
            _prepare(draft, root, values)
        failure_code = "profile_conflict"
        _promote(draft, root)
        failure_code = "store_changed"
        _finish(draft, values)
    except (AicmoError, OSError, ValueError, IntegrityError, StoreActionError):
        OnboardingDraft.objects.filter(pk=draft.pk, state="running").update(
            state="failed",
            failure_code=failure_code,
        )
    return True
