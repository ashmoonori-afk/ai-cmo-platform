from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import cast
from zipfile import ZipFile

import pytest
from PIL import Image, ImageOps, PngImagePlugin
from typer.testing import CliRunner

from aicmo.cli import app
from aicmo.errors import WorkflowExecutionError
from aicmo.export import export_local_pack
from aicmo.photos import (
    MAX_PHOTO_BYTES,
    asset_path,
    import_photos,
    normalize_photo,
    parse_photos,
    photo_preview,
)
from aicmo.source_input import prepare_workflow_inputs
from tests.test_local_pack import (
    PackAdapter,
    _brief,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)


def _upload(root: Path, *, count: int = 2) -> dict[str, str]:
    folder = root / "private-uploads"
    folder.mkdir(exist_ok=True)
    Image.new("RGB", (64, 40), "#b86528").save(folder / "owner-original.jpg")
    manifest = folder / "upload.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "aicmo.photo-upload.v1",
                "photos": [
                    {
                        "path": "owner-original.jpg",
                        "news_index": index,
                        "caption": "가게 안의 합성 사진",
                        "rights_basis": "own_photo",
                        "privacy_reviewed": True,
                    }
                    for index in range(count)
                ],
            }
        ),
        encoding="utf-8",
    )
    return {**_brief(), "photos_json": import_photos(root, "shop", manifest)}


def test_photo_input_preserves_hash_identity_and_minimizes_caption() -> None:
    digest = "a" * 53 + "01012345678"
    asset = {
        "news_index": 0,
        "caption": "가게 사진 01012345678",
        "rights_basis": "own_photo",
        "privacy_reviewed": True,
        "sha256": digest,
        "format": "PNG",
        "width": 1,
        "height": 1,
        "byte_length": 1,
    }
    value = {"schema_version": "aicmo.photos.v1", "photos": [asset]}
    inputs = {"client": "shop", "photos_json": json.dumps(value)}
    safe = prepare_workflow_inputs({"client": "required", "photos_json": "optional"}, inputs).values
    photo = parse_photos(safe).photos[0]
    assert photo.sha256 == digest
    assert photo.caption == "가게 사진 [customer-phone]"
    assert prepare_workflow_inputs({}, safe).values == safe
    asset["sha256"] = "customer name: synthetic-owner"
    with pytest.raises(WorkflowExecutionError, match="invalid photo selection"):
        prepare_workflow_inputs({}, {"photos_json": json.dumps(value)})


@pytest.mark.parametrize("orientation", range(1, 9))
def test_orientation_metadata_and_transparency(orientation: int) -> None:
    source = Image.new("RGB", (9, 6), "white")
    source.putpixel((0, 0), (255, 0, 0))
    metadata = Image.Exif()
    metadata[274] = orientation
    metadata[270] = "PRIVATE_ORIGINAL_METADATA"
    metadata[34853] = {1: "N", 2: (37.0, 30.0, 0.0)}
    original = io.BytesIO()
    source.save(original, format="JPEG", exif=metadata)
    raw = original.getvalue()
    data, width, height = normalize_photo(raw)
    with Image.open(io.BytesIO(raw)) as reopened:
        expected = ImageOps.exif_transpose(reopened)
        with Image.open(io.BytesIO(data)) as output:
            assert (width, height) == expected.size
            assert output.tobytes() == expected.tobytes()
            assert output.info == {}
            assert not output.getexif()
    assert b"PRIVATE_ORIGINAL_METADATA" not in data
    palette = Image.new("P", (4, 3), 0)
    png_text = PngImagePlugin.PngInfo()
    png_text.add_text("Comment", "PRIVATE_ORIGINAL_METADATA")
    original = io.BytesIO()
    palette.save(original, format="PNG", transparency=0, pnginfo=png_text)
    data, _, _ = normalize_photo(original.getvalue())
    with Image.open(io.BytesIO(data)) as output:
        assert output.mode == "RGBA"
        assert output.getpixel((0, 0)) == (0, 0, 0, 0)
        assert output.info == {}


@pytest.mark.parametrize("kind", ["fake", "truncated", "animated", "large", "bomb", "bytes"])
def test_decoder_limits(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = io.BytesIO()
    picture = Image.new("RGB", (64, 40), "red")
    if kind == "animated":
        picture.save(
            buffer, format="PNG", save_all=True, append_images=[Image.new("RGB", (64, 40), "blue")]
        )
    else:
        picture.save(buffer, format="PNG")
    raw = buffer.getvalue()
    if kind == "fake":
        raw = b"not actually a photo"
    elif kind == "truncated":
        raw = raw[:40]
    elif kind == "large":
        monkeypatch.setattr("aicmo.photos.MAX_PHOTO_PIXELS", 100)
    elif kind == "bomb":
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    elif kind == "bytes":
        raw = b"x" * (MAX_PHOTO_BYTES + 1)
    with pytest.raises(WorkflowExecutionError, match=r"JPEG/PNG|20 MiB"):
        normalize_photo(raw)


@pytest.mark.parametrize("damage", ["escape", "absolute", "duplicate", "privacy", "unknown"])
def test_upload_contract(tmp_path: Path, damage: str) -> None:
    _upload(tmp_path)
    path = tmp_path / "private-uploads/upload.json"
    payload = json.loads(path.read_text("utf-8"))
    photo = payload["photos"][0]
    if damage == "escape":
        photo["path"] = "../PRIVATE_NAME.jpg"
    elif damage == "absolute":
        photo["path"] = str((tmp_path / "PRIVATE_NAME.jpg").resolve())
    elif damage == "duplicate":
        photo["news_index"] = 1
    elif damage == "privacy":
        photo["privacy_reviewed"] = False
    else:
        photo["original_name"] = "PRIVATE_NAME.jpg"
    path.write_text(json.dumps(payload), "utf-8")
    with pytest.raises(WorkflowExecutionError) as error:
        import_photos(tmp_path, "shop", path)
    assert "PRIVATE_NAME" not in str(error.value)


def test_photo_approval_export_and_model_boundary(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    inputs = _upload(tmp_path)
    assert runner.run("local-store-pack", "case", inputs).status == "waiting_approval"
    with pytest.raises(WorkflowExecutionError, match="photos-reviewed"):
        runner.approve("case", "owner_gate", "owner", "ok")
    cli = CliRunner().invoke(app, ["photo-preview", "case", "--repo", str(tmp_path)])
    assert cli.exit_code == 0, cli.output
    preview = (tmp_path / "artifacts/case/photo-preview.html").read_text("utf-8")
    assert preview.count("<img ") == 2
    assert "owner-original" not in preview
    runner.approve("case", "owner_gate", "synthetic-owner", "ok", photos_reviewed=True)
    assert runner.resume("case").status == "success"
    output = export_local_pack(runner, "case")
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["visual_asset_status"] == "provided"
        assert len([name for name in archive.namelist() if name.startswith("photos/")]) == 2
        for name, digest in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        for photo in parse_photos(inputs).photos:
            assert (
                archive.read(f"photos/news-{photo.news_index + 1}.png")
                == asset_path(tmp_path, "shop", photo.sha256).read_bytes()
            )
    assert output == export_local_pack(runner, "case")
    requests = cast("PackAdapter", runner.adapter).requests
    for request in requests:
        assert "owner-original" not in str(request)
        assert "private-uploads" not in str(request)
        assert "data:image" not in str(request)
        assert "iVBORw0" not in str(request)
    with runner.store.connect() as connection:
        dump = "\n".join(connection.iterdump())
    assert "owner-original" not in dump
    assert "private-uploads" not in dump
    assert "source_sha256" not in inputs["photos_json"]
    original_sha = hashlib.sha256(
        (tmp_path / "private-uploads/owner-original.jpg").read_bytes()
    ).hexdigest()
    assert original_sha not in dump
    assert all(original_sha not in str(request) for request in requests)


@pytest.mark.parametrize(
    "boundary",
    [
        "approve",
        "resume",
        "export",
        "manifest-edits",
        "binding",
        "manifest-resume",
        "manifest-export",
        "missing-png",
        "missing-manifest",
    ],
)
def test_changes_cannot_reuse_photo_approval(tmp_path: Path, boundary: str) -> None:
    runner = _runner(tmp_path)
    inputs = _upload(tmp_path, count=1)
    assert runner.run("local-store-pack", "case", inputs).status == "waiting_approval"
    if boundary in {
        "resume",
        "export",
        "binding",
        "manifest-resume",
        "manifest-export",
        "missing-png",
        "missing-manifest",
    }:
        runner.approve("case", "owner_gate", "owner", "ok", photos_reviewed=True)
    if boundary in {"export", "binding", "manifest-export", "missing-png", "missing-manifest"}:
        assert runner.resume("case").status == "success"
    photo = parse_photos(inputs).photos[0]
    previous_hash = runner.store.get_output_hashes("case", "photos")
    if boundary in {"manifest-edits", "manifest-resume", "manifest-export"}:
        (tmp_path / "artifacts/case/photos.json").write_text("{}", "utf-8")
    elif boundary == "missing-manifest":
        (tmp_path / "artifacts/case/photos.json").unlink()
    elif boundary == "missing-png":
        asset_path(tmp_path, "shop", photo.sha256).unlink()
    elif boundary == "binding":
        with runner.store.connect() as connection:
            connection.execute("update approvals set photo_manifest_sha256=null")
    else:
        asset_path(tmp_path, "shop", photo.sha256).write_bytes(b"changed")
    with pytest.raises(WorkflowExecutionError, match="photo"):  # noqa: PT012 — same boundary matrix
        if boundary in {"approve", "manifest-edits"}:
            runner.approve(
                "case", "owner_gate", "owner", "ok", accept_edits=True, photos_reviewed=True
            )
        elif boundary in {"resume", "manifest-resume"}:
            runner.resume("case")
        else:
            export_local_pack(runner, "case")
    assert runner.store.get_output_hashes("case", "photos") == previous_hash


def test_capacity_and_preview_escape(tmp_path: Path) -> None:
    inputs = _upload(tmp_path)
    payload = json.loads(inputs["brief_json"])
    payload["owner_minutes"] = 5
    inputs["brief_json"] = json.dumps(payload)
    with pytest.raises(WorkflowExecutionError, match="capacity"):
        _runner(tmp_path).run("local-store-pack", "case", inputs)
    inputs["brief_json"] = _brief()["brief_json"]
    photos = json.loads(inputs["photos_json"])
    photos["photos"][0]["caption"] = '<script>alert("caption")</script>'
    inputs["photos_json"] = json.dumps(photos)
    html = photo_preview(tmp_path, inputs)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_missing_client_is_a_safe_input_error(tmp_path: Path) -> None:
    inputs = _upload(tmp_path)
    del inputs["client"]
    with pytest.raises(WorkflowExecutionError, match="client"):
        _runner(tmp_path).run("local-store-pack", "case", inputs)
