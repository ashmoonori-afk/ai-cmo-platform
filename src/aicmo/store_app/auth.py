from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from aicmo.store_app.models import LoginWindow

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from django.http import HttpRequest

_MAX_LOGIN_WINDOWS = 10_000


class LimitedBackend(ModelBackend):
    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: object,
    ) -> AbstractBaseUser | None:
        now = timezone.now()
        keys = [
            ("account:" + (username or "").strip().casefold()[:150], 5),
            ("address:" + (str(request.META.get("REMOTE_ADDR", "")) if request else "local"), 30),
        ]
        windows: list[LoginWindow] = []
        with transaction.atomic():
            LoginWindow.objects.filter(opened_at__lt=now - timedelta(minutes=15)).delete()
            if LoginWindow.objects.count() >= _MAX_LOGIN_WINDOWS:
                raise PermissionDenied
            for value, limit in keys:
                key = salted_hmac("store-login", value, algorithm="sha256").hexdigest()
                window, _ = LoginWindow.objects.get_or_create(key=key, defaults={"opened_at": now})
                if window.failures >= limit:
                    raise PermissionDenied
                window.failures += 1
                window.save(update_fields=["failures"])
                windows.append(window)
        user = super().authenticate(request, username, password, **kwargs)
        if user is not None:
            with transaction.atomic():
                LoginWindow.objects.filter(pk=windows[0].pk).delete()
                LoginWindow.objects.filter(
                    pk=windows[1].pk, opened_at=windows[1].opened_at, failures__gt=0
                ).update(failures=F("failures") - 1)
        return user
