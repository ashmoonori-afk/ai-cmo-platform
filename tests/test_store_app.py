from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "label",
    [
        "tests.store_app_cases",
        "tests.store_onboarding_cases",
        "tests.store_guidance_cases",
        "tests.store_editor_cases",
        "tests.store_archive_cases",
        "tests.store_photo_cases",
        "tests.store_rewrite_cases",
        "tests.store_delivery_cases",
        "tests.store_publication_cases",
        "tests.store_authority_cases",
        "tests.store_onboarding_metadata_cases",
        "tests.store_boundary_cases",
        "tests.store_upload_boundary_cases",
        "tests.store_outcomes_cases",
        "tests.store_native_job_cases",
        "tests.store_report_cases",
        "tests.store_action_cases",
        "tests.store_feedback_cases",
    ],
)
def test_django_store_app(tmp_path: Path, label: str) -> None:
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "aicmo.store_app.settings",
        "AICMO_WEB_SECRET_KEY": "synthetic-tests-only-do-not-deploy-012345678901234567890123456789",
        "AICMO_WEB_LOCAL": "1",
        "AICMO_REPO": str(Path(__file__).resolve().parents[1]),
        "AICMO_TEST_DB": str(tmp_path / "web-test.sqlite3"),
    }
    result = subprocess.run(  # noqa: S603 — labels are the fixed parametrization above
        [sys.executable, "-m", "tests.run_store_app_tests", label],
        env=env,
        capture_output=True,
        text=True,
        # The real eight-case engine/DB matrix took 1513s under Windows memory pressure.
        # Bound the suite wait separately from the unchanged engine and DB timeouts.
        timeout=2400,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
