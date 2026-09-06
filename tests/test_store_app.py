from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_django_store_app(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "aicmo.store_app.settings",
        "AICMO_WEB_SECRET_KEY": "synthetic-tests-only-do-not-deploy-012345678901234567890123456789",
        "AICMO_WEB_LOCAL": "1",
        "AICMO_REPO": str(Path(__file__).resolve().parents[1]),
        "AICMO_TEST_DB": str(tmp_path / "web-test.sqlite3"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "tests.run_store_app_tests"],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
