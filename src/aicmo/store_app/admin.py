from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin

from aicmo.store_app.models import Store

if TYPE_CHECKING:
    from django.http import HttpRequest

    StoreAdminBase = admin.ModelAdmin[Store]
else:
    StoreAdminBase = admin.ModelAdmin


@admin.register(Store)
class StoreAdmin(StoreAdminBase):
    list_display = ("name", "owner", "client")

    def get_readonly_fields(
        self,
        request: HttpRequest,  # noqa: ARG002 — Django hook
        obj: Store | None = None,
    ) -> tuple[str, ...]:
        return ("client",) if obj else ()
