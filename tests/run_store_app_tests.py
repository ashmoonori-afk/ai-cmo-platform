"""Use Django's own test database lifecycle from the existing pytest suite."""

import os
import sys

import django
from django.conf import settings
from django.core.management import call_command
from django.test.runner import DiscoverRunner

if "--worker" in sys.argv:
    settings.DATABASES["default"]["NAME"] = os.environ["AICMO_TEST_DB"]
    django.setup()
    call_command("work", once=True)
    raise SystemExit(0)

django.setup()
settings.DATABASES["default"]["TEST"]["NAME"] = os.environ["AICMO_TEST_DB"]
raise SystemExit(
    DiscoverRunner(verbosity=2, interactive=False).run_tests(
        sys.argv[1:] or ["tests.store_app_cases"]
    )
)
