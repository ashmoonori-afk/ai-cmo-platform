from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import date, timedelta
from typing import TYPE_CHECKING, cast

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import DatabaseError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from aicmo import outcomes
from aicmo.errors import AicmoError
from aicmo.source_input import source_checked_date
from aicmo.store_app import outcome_services, report_services, services
from aicmo.store_app.models import Store

if TYPE_CHECKING:
    from django.core.files.uploadedfile import UploadedFile
    from django.http import HttpRequest, HttpResponse, QueryDict
    from django.utils.datastructures import MultiValueDict

CHANNELS = [
    ("naver", "네이버"),
    ("google-business", "Google 비즈니스"),
    ("instagram", "Instagram"),
    ("offline", "오프라인"),
]
METRIC_LABELS: dict[str, str] = dict(
    zip(outcomes.METRICS, ("게시", "문의", "예약", "쿠폰 사용"), strict=True)
)
INPUT_ERROR = "입력 항목과 숫자를 다시 확인해 주세요."
MAX_COUNT = 1_000_000


class ScopeForm(forms.Form):
    week_start = forms.DateField(
        label="보고 싶은 주의 월요일",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    channel = forms.ChoiceField(
        label="기록한 채널",
        choices=CHANNELS,
        error_messages={"invalid_choice": INPUT_ERROR},
    )

    def clean_week_start(self) -> date:
        value = cast("date", self.cleaned_data["week_start"])
        try:
            return outcomes.week_start_date(value.isoformat())
        except AicmoError:
            reason = "한국 시간 오늘까지의 월요일을 선택해 주세요."
            raise forms.ValidationError(reason) from None


class CountField(forms.RegexField):
    def __init__(self, label: str) -> None:
        super().__init__(
            r"^[0-9]{1,7}$",
            label=label,
            required=False,
            max_length=7,
            strip=False,
            widget=forms.NumberInput(
                attrs={"min": 0, "max": 1_000_000, "step": 1, "inputmode": "numeric"}
            ),
            error_messages={"invalid": "빈칸 또는 0~1,000,000의 정수를 입력해 주세요."},
        )

    def clean(self, value: object) -> int | None:
        cleaned = super().clean(value)
        if not cleaned:
            return None
        count = int(cleaned)
        if count > MAX_COUNT:
            reason = "1,000,000 이하의 정수를 입력해 주세요."
            raise forms.ValidationError(reason)
        return count


class DailyForm(ScopeForm):
    input_kind = forms.ChoiceField(
        choices=[("web_manual", "직접 입력")],
        widget=forms.HiddenInput,
        error_messages={"invalid_choice": INPUT_ERROR},
    )
    date = forms.DateField(
        label="관측한 날짜 (한국 시간)",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    posts = CountField("게시 건수")
    inquiries = CountField("문의 건수")
    reservations = CountField("예약 건수")
    coupon_redemptions = CountField("쿠폰 사용 건수")

    def clean(self) -> dict[str, object]:
        data = super().clean() or {}
        observed, start = data.get("date"), data.get("week_start")
        if (
            isinstance(observed, date)
            and isinstance(start, date)
            and not (start <= observed <= min(start + timedelta(days=6), source_checked_date()))
        ):
            self.add_error("date", "선택한 주에 실제로 관측한 날짜를 입력해 주세요.")
        return data


class CsvForm(ScopeForm):
    input_kind = forms.ChoiceField(
        choices=[("web_csv", "CSV 가져오기")],
        widget=forms.HiddenInput,
        error_messages={"invalid_choice": INPUT_ERROR},
    )
    csv_file = forms.FileField(
        label="일별 숫자 CSV 파일 1개",
        widget=forms.FileInput(attrs={"accept": ".csv,text/csv"}),
        help_text="UTF-8 또는 UTF-8 BOM, 32 KiB 이하. 한 주·한 채널·최대 7행입니다.",
    )


class ConfirmForm(forms.Form):
    token = forms.CharField(max_length=outcome_services.MAX_TOKEN_LENGTH, widget=forms.HiddenInput)
    raw_csv = forms.CharField(max_length=outcome_services.MAX_ENCODED_CSV, widget=forms.HiddenInput)
    action = forms.ChoiceField(
        choices=[("save", "저장"), ("edit", "다시 입력")],
        required=False,
        error_messages={"invalid_choice": INPUT_ERROR},
    )
    checked = forms.BooleanField(required=False, label="날짜·채널·숫자와 빈칸을 확인했습니다.")
    replace = forms.BooleanField(
        required=False,
        label="변경된 날짜의 기존값을 이 내용으로 정정합니다. 빈칸도 미입력으로 바뀝니다.",
    )


def submitted(
    form: forms.Form,
    data: QueryDict,
    files: MultiValueDict[str, UploadedFile],
) -> forms.Form:
    form.is_valid()
    allowed_files = {
        name for name, field in form.fields.items() if isinstance(field, forms.FileField)
    }
    if (
        set(data) - set(form.fields) - {"csrfmiddlewaretoken"}
        or any(len(data.getlist(name)) != 1 for name in data)
        or set(files) - allowed_files
        or any(len(files.getlist(name)) != 1 for name in files)
        or any(
            data.get(name, "") not in {"", "on"}
            for name in ("checked", "replace")
            if name in form.fields
        )
    ):
        form.add_error(None, INPUT_ERROR)
    form.data = {
        name: value for name, value in form.cleaned_data.items() if name not in allowed_files
    }
    return form


def _initial() -> dict[str, object]:
    today = source_checked_date()
    return {"week_start": today - timedelta(days=today.weekday()), "channel": "naver"}


def _context(store: Store, scope: ScopeForm, selected_day: date | None = None) -> dict[str, object]:
    initial = _initial()
    snapshot = None
    notice = ""
    if scope.is_valid():
        initial.update(scope.cleaned_data)
        try:
            snapshot = outcome_services.read(
                store,
                cast("date", initial["week_start"]).isoformat(),
                outcomes.parse_channel(str(initial["channel"])),
            )
        except (AicmoError, OSError, ValueError, sqlite3.Error):
            notice = (
                "저장한 기록을 확인할 수 없습니다. 잠시 후 다시 열거나 운영자에게 문의해 주세요."
            )
    start = cast("date", initial["week_start"])
    today = source_checked_date()
    selected_day = selected_day or min(today, start + timedelta(days=6))
    daily = DailyForm(
        initial={
            **initial,
            "date": selected_day,
            "input_kind": "web_manual",
        },
        auto_id="daily_%s",
    )
    daily.fields["date"].widget.attrs.update(
        min=start.isoformat(), max=min(today, start + timedelta(days=6)).isoformat()
    )
    csv_form = CsvForm(initial={**initial, "input_kind": "web_csv"}, auto_id="csv_%s")
    records: list[dict[str, object]] = []
    totals: list[dict[str, object]] = []
    if snapshot is not None:
        by_day = {row.date: row for row in snapshot.current}
        selected = by_day.get(selected_day.isoformat())
        if selected is not None:
            daily.initial.update({name: getattr(selected, name) for name in outcomes.METRICS})
        for offset in range(7):
            day = start + timedelta(days=offset)
            row = by_day.get(day.isoformat())
            records.append(
                {
                    "day": day,
                    "future": day > today,
                    "row": row,
                    "edit_url": f"{reverse('outcomes', args=[store.pk])}"
                    f"?week_start={start.isoformat()}&channel={snapshot.channel}&day={day.isoformat()}",
                    "values": [getattr(row, name) if row else None for name in outcomes.METRICS],
                }
            )
        totals = [
            {"label": METRIC_LABELS[name], "metric": metric}
            for name, metric in snapshot.totals.items()
        ]
    return {
        "store": store,
        "scope": scope,
        "daily_form": daily,
        "csv_form": csv_form,
        "snapshot": snapshot,
        "records": records,
        "totals": totals,
        "notice": notice,
        "week_start": start,
        "week_end": start + timedelta(days=6),
    }


def _confirmation(prepared: outcome_services.PreparedOutcome) -> dict[str, object]:
    old = {row.date: row for row in prepared.preview.existing}
    rows: list[dict[str, object]] = []
    for row in prepared.preview.rows:
        prior = old.get(row.date)
        rows.append(
            {
                "date": row.date,
                "prior": prior,
                "existing": [
                    getattr(prior, metric) if prior else None for metric in outcomes.METRICS
                ],
                "values": [getattr(row, metric) for metric in outcomes.METRICS],
            }
        )
    return {"confirmation": asdict(prepared), "preview": prepared.preview, "rows": rows}


@login_required
@require_GET
@never_cache
def index(request: HttpRequest, store_id: int) -> HttpResponse:
    store = services.owned_store(request.user, store_id)
    data = request.GET.copy()
    selected_days = data.pop("day", [])
    if not data:
        data.update({name: str(value) for name, value in _initial().items()})
    scope = cast("ScopeForm", submitted(ScopeForm(data, auto_id="scope_%s"), data, request.FILES))
    selected_day = None
    if selected_days:
        try:
            selected_day = forms.DateField(input_formats=["%Y-%m-%d"]).clean(selected_days[-1])
            start = scope.cleaned_data.get("week_start")
            if (
                len(selected_days) != 1
                or not isinstance(start, date)
                or not (
                    start <= selected_day <= min(start + timedelta(days=6), source_checked_date())
                )
            ):
                raise forms.ValidationError(INPUT_ERROR)  # noqa: TRY301 — one safe date error
        except forms.ValidationError:
            selected_day = None
            scope.add_error(None, "선택한 주에 실제로 관측한 날짜를 골라 주세요.")
    context = _context(store, scope, selected_day)
    snapshot = context["snapshot"]
    if scope.is_valid() and isinstance(snapshot, outcomes.OutcomeSnapshot):
        context["report_form"] = report_services.form_for(request.user, store, snapshot)
    return render(
        request,
        "store_app/outcomes.html",
        context,
        status=200 if scope.is_valid() else 400,
    )


@login_required
@require_POST
@never_cache
def preview(request: HttpRequest, store_id: int) -> HttpResponse:
    store = services.owned_store(request.user, store_id)
    kind = request.POST.get("input_kind")
    form = (
        CsvForm(request.POST, request.FILES, auto_id="csv_%s")
        if kind == "web_csv"
        else DailyForm(request.POST, auto_id="daily_%s")
    )
    submitted(form, request.POST, request.FILES)
    if form.is_valid():
        try:
            data = form.cleaned_data
            channel = outcomes.parse_channel(data["channel"])
            if kind == "web_csv":
                raw = data["csv_file"].read(outcomes.MAX_CSV_BYTES + 1)
            else:
                raw = outcomes.daily_outcome_csv(
                    outcomes.DailyOutcome(
                        date=data["date"].isoformat(),
                        channel=channel,
                        **{metric: data[metric] for metric in outcomes.METRICS},
                    )
                )
            prepared = outcome_services.prepare(
                request.user,
                store,
                data["week_start"].isoformat(),
                channel,
                raw,
                cast("outcome_services.WebInputKind", kind),
            )
        except (AicmoError, OSError, ValueError, sqlite3.Error):
            form.add_error(
                None,
                "날짜·채널·숫자와 CSV의 열·인코딩·32 KiB 상한을 확인해 주세요. "
                "파일은 다시 선택해 주세요.",
            )
        else:
            return render(
                request,
                "store_app/outcome_confirm.html",
                {"store": store, "input_kind": kind, **_confirmation(prepared)},
            )
    scope = ScopeForm(
        {key: form.cleaned_data.get(key) for key in ("week_start", "channel")}, auto_id="scope_%s"
    )
    context = _context(store, scope)
    context["csv_form" if kind == "web_csv" else "daily_form"] = form
    return render(request, "store_app/outcomes.html", context, status=400)


@login_required
@require_POST
@never_cache
def confirm(request: HttpRequest, store_id: int) -> HttpResponse:
    store = services.owned_store(request.user, store_id)
    form = submitted(ConfirmForm(request.POST), request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            "store_app/error.html",
            {"notice": "저장할 숫자와 정정 여부를 확인한 뒤 다시 미리 봐 주세요."},
            status=400,
        )
    try:
        data = form.cleaned_data
        envelope, raw = outcome_services.decode(request.user, store, data["token"], data["raw_csv"])
        if data["action"] == "edit":
            prepared = outcome_services.prepare(
                request.user,
                store,
                envelope.week_start,
                envelope.channel,
                raw,
                envelope.input_kind,
            )
            scope = ScopeForm(
                {"week_start": envelope.week_start, "channel": envelope.channel},
                auto_id="scope_%s",
            )
            context = _context(store, scope)
            if envelope.input_kind == "web_manual":
                row = prepared.preview.rows[0]
                context["daily_form"] = DailyForm(
                    initial={
                        **row.model_dump(),
                        "week_start": envelope.week_start,
                        "input_kind": "web_manual",
                    },
                    auto_id="daily_%s",
                )
                context["notice"] = (
                    "입력한 숫자를 다시 채웠습니다. 바꿀 항목을 수정하고 미리 봐 주세요."
                )
            else:
                context["notice"] = (
                    "같은 주와 채널을 선택했습니다. 수정할 CSV 파일을 다시 선택해 주세요."
                )
            return render(request, "store_app/outcomes.html", context)
        if not data["checked"] or (envelope.replace_required and not data["replace"]):
            return render(
                request,
                "store_app/error.html",
                {
                    "notice": "날짜·채널·숫자와 빈칸을 확인해 주세요. "
                    "기존값이 바뀐다면 정정 확인 항목에도 체크한 뒤 저장해 주세요."
                },
                status=400,
            )
        changed = outcome_services.save(
            request.user,
            store,
            data["token"],
            data["raw_csv"],
            replace=data["replace"],
        )
    except (DatabaseError, sqlite3.Error):
        return render(
            request,
            "store_app/error.html",
            {
                "notice": "저장 여부를 확인할 수 없습니다. "
                "잠시 후 같은 확인 화면에서 다시 저장하거나 최신 기록을 확인해 주세요."
            },
            status=409,
        )
    except (AicmoError, OSError, ValueError, signing.BadSignature):
        return render(
            request,
            "store_app/error.html",
            {"notice": "확인 시간이 지났거나 자료가 바뀌었습니다. 최신 기록과 다시 대조해 주세요."},
            status=409,
        )
    messages.success(
        request,
        "확인한 숫자를 저장했습니다."
        if changed
        else "변경할 숫자가 없어 기록을 그대로 유지했습니다.",
    )
    return redirect(
        f"{reverse('outcomes', args=[store.pk])}?week_start={envelope.week_start}"
        f"&channel={envelope.channel}"
    )
