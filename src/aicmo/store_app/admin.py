from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin

from aicmo.store_app.models import OnboardingDraft, Store

if TYPE_CHECKING:
    from django.http import HttpRequest

    StoreAdminBase = admin.ModelAdmin[Store]
    OnboardingAdminBase = admin.ModelAdmin[OnboardingDraft]
else:
    StoreAdminBase = admin.ModelAdmin
    OnboardingAdminBase = admin.ModelAdmin


@admin.register(Store)
class StoreAdmin(StoreAdminBase):
    list_display = ("name", "owner", "client")

    def get_readonly_fields(
        self,
        request: HttpRequest,  # noqa: ARG002 — Django hook
        obj: Store | None = None,
    ) -> tuple[str, ...]:
        return ("client",) if obj else ()


@admin.register(OnboardingDraft)
class OnboardingAdmin(OnboardingAdminBase):
    # Fixed diagnostics only; profile answers and filesystem paths stay off this list.
    list_display = ("id", "owner", "state", "failure_code", "attempts", "updated_at")
    fields = ("id", "owner", "state", "failure_code", "attempts", "revision", "store", "updated_at")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest) -> bool:  # noqa: ARG002 — Django hook
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,  # noqa: ARG002 — Django hook
        obj: OnboardingDraft | None = None,  # noqa: ARG002 — Django hook
    ) -> bool:
        return False
