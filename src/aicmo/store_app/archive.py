from __future__ import annotations

from typing import cast

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, Paginator
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from aicmo.store_app.models import Job, Store
from aicmo.store_app.services import allowed_stores


class ArchiveForm(forms.Form):
    store = forms.ModelChoiceField(
        label="가게", queryset=Store.objects.none(), required=False, empty_label="모든 가게"
    )
    state = forms.ChoiceField(
        label="상태",
        choices=[("", "모든 상태"), *Job.STATES],
        required=False,
        error_messages={"invalid_choice": "목록에서 상태를 다시 선택해 주세요."},
    )
    start = forms.DateField(
        label="시작일", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    end = forms.DateField(
        label="종료일", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    page = forms.IntegerField(required=False, min_value=1, max_value=2_147_483_647)

    def clean(self) -> dict[str, object]:
        data = super().clean() or {}
        # Retain parsed fields for correction, never rejected metadata or raw choice values.
        self.data = dict(data)
        start, end = data.get("start"), data.get("end")
        if start and end and start > end:
            self.add_error("end", "종료일은 시작일과 같거나 이후여야 합니다.")
        return data


@login_required
@require_GET
@never_cache
def index(request: HttpRequest) -> HttpResponse:
    stores = allowed_stores(request.user).order_by("name", "pk")
    form = ArchiveForm(request.GET)
    store_field = cast("forms.ModelChoiceField[Store]", form.fields["store"])
    store_field.queryset = stores
    valid = form.is_valid()
    for name in form.fields:
        if len(request.GET.getlist(name)) > 1:
            form.add_error(None, "같은 검색 항목을 여러 번 지정할 수 없습니다.")
            valid = False
            break
    page_obj = None
    query = QueryDict(mutable=True)
    if valid:
        data = form.cleaned_data
        jobs = Job.objects.filter(store__in=stores).select_related("store")
        if data["store"]:
            jobs = jobs.filter(store=data["store"])
            query["store"] = str(data["store"].pk)
        if data["state"]:
            jobs = jobs.filter(state=data["state"])
            query["state"] = data["state"]
        # Django's date lookup uses the configured local timezone, including both end dates.
        if data["start"]:
            jobs = jobs.filter(created_at__date__gte=data["start"])
            query["start"] = data["start"].isoformat()
        if data["end"]:
            jobs = jobs.filter(created_at__date__lte=data["end"])
            query["end"] = data["end"].isoformat()
        paginator = Paginator(jobs.order_by("-created_at", "-pk"), 20)
        try:
            page_obj = paginator.page(data["page"] or 1)
        except EmptyPage:
            form.add_error(None, "해당 페이지가 없습니다. 검색을 다시 적용해 주세요.")
            valid = False
    return render(
        request,
        "store_app/archive.html",
        {"form": form, "page_obj": page_obj, "filter_query": query.urlencode()},
        status=200 if valid else 400,
    )
