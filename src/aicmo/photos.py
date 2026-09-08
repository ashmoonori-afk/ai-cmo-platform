from __future__ import annotations

import hashlib
import io
import json
import re
import warnings
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

from PIL import Image, ImageOps
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from aicmo.errors import WorkflowExecutionError
from aicmo.paths import parse_safe_id, resolve_inside_repo
from aicmo.redaction import safe_kb_text

MAX_PHOTO_BYTES = 20 * 1024 * 1024
MAX_PHOTO_PIXELS = 24_000_000
MAX_PHOTO_EDGE = 2048
_MAX_MANIFEST_BYTES = 8 * 1024
_STEP = "photos"
PHOTO_STEP = _STEP
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Caption = Annotated[str, Field(max_length=200), AfterValidator(safe_kb_text)]


class PhotoDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    news_index: int = Field(ge=0, le=1)
    caption: Caption
    rights_basis: Literal["own_photo", "permission_received"]
    privacy_reviewed: bool


class PhotoUpload(PhotoDeclaration):
    path: str = Field(min_length=1, max_length=500)


class PhotoAsset(PhotoDeclaration):
    sha256: Hash
    format: Literal["PNG"] = "PNG"
    width: int = Field(gt=0, le=MAX_PHOTO_EDGE)
    height: int = Field(gt=0, le=MAX_PHOTO_EDGE)
    byte_length: int = Field(gt=0, le=MAX_PHOTO_BYTES)


class PhotoSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["aicmo.photos.v1"] = "aicmo.photos.v1"
    photos: list[PhotoAsset] = Field(default_factory=list, max_length=2)


class PhotoUploads(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["aicmo.photo-upload.v1"]
    photos: list[PhotoUpload] = Field(min_length=1, max_length=2)


def _json(raw: str) -> object:
    if len(raw.encode("utf-8")) > _MAX_MANIFEST_BYTES:
        raise WorkflowExecutionError(_STEP, "photo manifest exceeds 8 KiB")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                reason = "duplicate key"
                raise ValueError(reason)
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def _validate_declarations(photos: list[PhotoAsset] | list[PhotoUpload]) -> None:
    if len({photo.news_index for photo in photos}) != len(photos) or any(
        not photo.privacy_reviewed for photo in photos
    ):
        raise WorkflowExecutionError(_STEP, "each news needs a unique, privacy-reviewed photo")


def parse_photos(inputs: dict[str, str]) -> PhotoSelection:
    try:
        selection = PhotoSelection.model_validate(_json(inputs.get("photos_json", "{}")))
    except (ValueError, RecursionError):
        raise WorkflowExecutionError(_STEP, "invalid photo selection") from None
    _validate_declarations(selection.photos)
    return selection


def _read(path: Path, maximum: int) -> bytes:
    try:
        if not path.is_file():
            raise OSError  # noqa: TRY301 — reject directories/devices with the same safe error
        with path.open("rb") as stream:
            raw = stream.read(maximum + 1)
    except OSError:
        raise WorkflowExecutionError(_STEP, "photo file unavailable") from None
    if not raw or len(raw) > maximum:
        raise WorkflowExecutionError(_STEP, "photo file is empty or exceeds its byte limit")
    return raw


def normalize_photo(raw: bytes) -> tuple[bytes, int, int]:
    """Decode supported pixels, apply orientation, resize, and discard all source metadata."""
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        raise WorkflowExecutionError(_STEP, "photo exceeds 20 MiB or is empty")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(io.BytesIO(raw), formats=("JPEG", "PNG")) as probe:
                if (
                    probe.width * probe.height > MAX_PHOTO_PIXELS
                    or getattr(probe, "n_frames", 1) != 1
                ):
                    raise ValueError  # noqa: TRY301 — safe decoding error below
                probe.verify()
            with Image.open(io.BytesIO(raw), formats=("JPEG", "PNG")) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((MAX_PHOTO_EDGE, MAX_PHOTO_EDGE), Image.Resampling.LANCZOS)
                # A fresh pixel image does not inherit EXIF, ICC, comments or PNG text chunks.
                alpha = "A" in oriented.getbands() or "transparency" in oriented.info
                converted = oriented.convert("RGBA" if alpha else "RGB")
                clean = Image.frombytes(converted.mode, converted.size, converted.tobytes())
                output = io.BytesIO()
                clean.save(output, format="PNG")
                data, width, height = output.getvalue(), clean.width, clean.height
        if len(data) > MAX_PHOTO_BYTES:
            raise ValueError  # noqa: TRY301
    except (OSError, ValueError, SyntaxError, Warning, Image.DecompressionBombError):
        raise WorkflowExecutionError(
            _STEP, "use a complete, single-frame JPEG/PNG up to 20 MiB and 24 million pixels"
        ) from None
    return data, width, height


def asset_path(repo: Path, client: str, digest: str) -> Path:
    if re.fullmatch(r"[a-f0-9]{64}", digest) is None:
        raise WorkflowExecutionError(_STEP, "invalid photo digest")
    slug = parse_safe_id("client", client)
    namespace = hashlib.sha256(slug.encode()).hexdigest()
    # Hash values only: original filenames and customer paths never enter stored manifests.
    relative = f".aicmo/photos/{namespace}/{digest}.png"
    resolved = resolve_inside_repo(repo, relative, {})
    if resolved != repo.resolve() / relative:
        raise WorkflowExecutionError(_STEP, "photo storage must not redirect to another location")
    return resolved


def import_photos(repo: Path, client: str, upload_file: Path) -> str:
    parse_safe_id("client", client)
    try:
        uploads = PhotoUploads.model_validate(
            _json(_read(upload_file, _MAX_MANIFEST_BYTES).decode("utf-8-sig"))
        )
    except (ValueError, RecursionError):
        raise WorkflowExecutionError(_STEP, "invalid UTF-8 photo upload manifest") from None
    _validate_declarations(uploads.photos)
    assets: list[PhotoAsset] = []
    for upload in uploads.photos:
        try:
            source = resolve_inside_repo(upload_file.resolve().parent, upload.path, {})
        except (WorkflowExecutionError, ValueError, OSError, RuntimeError):
            raise WorkflowExecutionError(
                _STEP, "photo path must stay inside the upload folder"
            ) from None
        raw = _read(source, MAX_PHOTO_BYTES)
        data, width, height = normalize_photo(raw)
        digest = hashlib.sha256(data).hexdigest()
        target = asset_path(repo, client, digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if _read(target, MAX_PHOTO_BYTES) != data:
                raise WorkflowExecutionError(_STEP, "stored photo changed; preserve and inspect it")
        else:
            with TemporaryDirectory(prefix=".photo-", dir=target.parent) as temporary:
                staging = Path(temporary) / "image.png"
                staging.write_bytes(data)
                staging.replace(target)
        assets.append(
            PhotoAsset(
                **upload.model_dump(exclude={"path"}),
                sha256=digest,
                width=width,
                height=height,
                byte_length=len(data),
            )
        )
    return PhotoSelection(photos=assets).model_dump_json()


def verify_photo_assets(repo: Path, inputs: dict[str, str]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for photo in parse_photos(inputs).photos:
        data = _read(asset_path(repo, inputs.get("client", ""), photo.sha256), MAX_PHOTO_BYTES)
        if len(data) != photo.byte_length or hashlib.sha256(data).hexdigest() != photo.sha256:
            raise WorkflowExecutionError(_STEP, "photo version changed; start a new run")
        normalized, width, height = normalize_photo(data)
        if normalized != data or (width, height) != (photo.width, photo.height):
            raise WorkflowExecutionError(_STEP, "stored photo is not a clean PNG")
        files[f"photos/news-{photo.news_index + 1}.png"] = data
    return files


def photo_manifest(repo: Path, inputs: dict[str, str]) -> str:
    verify_photo_assets(repo, inputs)
    selection = parse_photos(inputs)
    return json.dumps(
        {
            "schema_version": "aicmo.photo-manifest.v1",
            "summary": "제공한 사진과 소식 연결입니다. 사장님이 실제 사진과 권리를 확인합니다.",
            "client": inputs["client"],
            "selection": selection.model_dump(),
            "visual_asset_status": "provided" if selection.photos else "unavailable",
            "pixel_review": "owner_review_required; text reviewer does not inspect pixels",
            "normalization": "EXIF orientation; max edge 2048; fresh PNG without source metadata",
            "next_steps": [
                "photo-preview로 정규화된 사진을 확인합니다.",
                "사용권과 잔여 개인정보 확인 뒤 --photos-reviewed로 승인합니다.",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def verify_photo_manifest(repo: Path, inputs: dict[str, str], raw: bytes) -> dict[str, bytes]:
    try:
        if _json(raw.decode("utf-8")) != json.loads(photo_manifest(repo, inputs)):
            raise ValueError  # noqa: TRY301
    except (ValueError, RecursionError):
        raise WorkflowExecutionError(_STEP, "photo manifest changed; start a new run") from None
    return verify_photo_assets(repo, inputs)


def photo_preview(repo: Path, inputs: dict[str, str]) -> str:
    verify_photo_assets(repo, inputs)
    cards: list[str] = []
    for photo in parse_photos(inputs).photos:
        url = escape(asset_path(repo, inputs["client"], photo.sha256).as_uri(), quote=True)
        rights = "직접 촬영" if photo.rights_basis == "own_photo" else "사용 허락을 받음"
        cards.append(
            f"<section><h2>소식 {photo.news_index + 1}</h2>"
            f'<img src="{url}" alt="{escape(photo.caption, quote=True)}">'
            f"<p>{escape(photo.caption)}</p><p>사용권 선언: {rights}</p>"
            f"<p>PNG SHA-256: <code>{photo.sha256}</code></p></section>"
        )
    return (
        '<!doctype html><html lang="ko"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>사진 승인 전 확인</title><style>body{font:18px sans-serif;max-width:900px;"
        "margin:auto;padding:24px;color:#182230}img{max-width:100%;height:auto}"
        "code{overflow-wrap:anywhere}section{margin:32px 0}</style><h1>사진 승인 전 확인</h1>"
        "<p>정규화된 실제 사진입니다. 인물·연락처 등 잔여 개인정보와 사용권을 확인하세요. "
        "이 화면은 권리나 개인정보 검증을 인증하지 않습니다.</p>"
        + "".join(cards)
        + ("<p>제공한 사진이 없습니다.</p>" if not cards else "")
        + "<h2>다음 단계</h2><p>문제 있으면 새 사진으로 새 실행을 만드세요. "
        "확인했다면 owner_gate를 --photos-reviewed와 함께 승인하세요.</p></html>"
    )
