from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from django.contrib.auth.models import User


class Store(models.Model):
    owner: models.ForeignKey[User, User] = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    name: models.CharField[str, str] = models.CharField(max_length=120)
    client: models.SlugField[str, str] = models.SlugField(max_length=128, unique=True)

    class Meta:
        permissions = (("operate_stores", "Access and operate all stores"),)

    def __str__(self) -> str:
        return str(self.name)


class Job(models.Model):
    STATES: ClassVar = [
        (name, label)
        for name, label in (
            ("queued", "접수됨"),
            ("running", "작성 중"),
            ("waiting_approval", "사장님 확인"),
            ("success", "저장 가능"),
            ("needs_work", "검토 필요"),
            ("failed", "작업 실패"),
            ("cancelled", "취소됨"),
        )
    ]
    id: models.UUIDField[uuid.UUID, uuid.UUID] = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    store: models.ForeignKey[Store, Store] = models.ForeignKey(Store, on_delete=models.PROTECT)
    submission_key: models.UUIDField[uuid.UUID, uuid.UUID] = models.UUIDField()
    inputs = models.JSONField()
    state: models.CharField[str, str] = models.CharField(
        max_length=24, choices=STATES, default="queued"
    )
    approval = models.JSONField(default=dict)
    cancel_requested: models.BooleanField[bool, bool] = models.BooleanField(default=False)
    notice: models.CharField[str, str] = models.CharField(max_length=240, blank=True)
    created_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["store", "submission_key"], name="store_submission"),
            models.UniqueConstraint(
                fields=["store"],
                condition=models.Q(state__in=["queued", "running", "waiting_approval"]),
                name="store_one_active_job",
            ),
        ]

    def __str__(self) -> str:
        return self.run_id

    @property
    def run_id(self) -> str:
        return f"web-{self.id.hex}"


class LoginWindow(models.Model):
    key: models.CharField[str, str] = models.CharField(primary_key=True, max_length=64)
    failures: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(default=0)
    opened_at: models.DateTimeField[datetime, datetime] = models.DateTimeField()

    def __str__(self) -> str:
        return "Login attempt window"


class OnboardingDraft(models.Model):
    MAX_ATTEMPTS = 3
    id: models.UUIDField[uuid.UUID, uuid.UUID] = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    owner: models.OneToOneField[User, User] = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    data = models.JSONField(default=dict)
    revision: models.PositiveBigIntegerField[int, int] = models.PositiveBigIntegerField(default=0)
    completed_step: models.PositiveSmallIntegerField[int, int] = models.PositiveSmallIntegerField(
        default=0
    )
    state: models.CharField[str, str] = models.CharField(
        max_length=16,
        default="draft",
        choices=[
            ("draft", "작성 중"),
            ("queued", "접수됨"),
            ("running", "가게 준비 중"),
            ("failed", "확인 필요"),
            ("complete", "가게 준비 완료"),
        ],
    )
    output_hashes = models.JSONField(default=dict)
    attempts: models.PositiveSmallIntegerField[int, int] = models.PositiveSmallIntegerField(
        default=0
    )
    failure_code: models.CharField[str, str] = models.CharField(
        max_length=32, blank=True, default=""
    )
    stage_id: models.UUIDField[uuid.UUID | None, uuid.UUID | None] = models.UUIDField(
        null=True, blank=True, editable=False
    )
    store: models.OneToOneField[Store | None, Store | None] = models.OneToOneField(
        Store, on_delete=models.PROTECT, null=True, blank=True
    )
    confirmed_at: models.DateTimeField[datetime | None, datetime | None] = models.DateTimeField(
        null=True, blank=True
    )
    updated_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(completed_step__lte=3), name="onboarding_steps"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(state="complete", store__isnull=False)
                    | (~models.Q(state="complete") & models.Q(store__isnull=True))
                ),
                name="onboarding_completed_store",
            ),
        ]

    def __str__(self) -> str:
        return "가게 정보 입력"

    @property
    def client(self) -> str:
        return f"web-client-{self.id.hex}"
