import json
from typing import Any

from django import forms

from aicmo.errors import AicmoError
from aicmo.local_pack import parse_brief


class PackForm(forms.Form):
    submission_key = forms.UUIDField(widget=forms.HiddenInput)
    fact = forms.CharField(
        label="이번 주 알릴 소식",
        max_length=1200,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="실제 확인한 상품·휴무·행사 내용을 적어 주세요. 가격과 기간도 확인해 주세요.",
    )
    reviews = forms.CharField(
        label="답글을 쓸 리뷰",
        required=False,
        max_length=6000,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text="한 줄에 리뷰 하나, 최대 5개입니다. 고객 이름·연락처는 빼 주세요.",
    )
    owner_minutes = forms.IntegerField(
        label="이번 주에 쓸 수 있는 시간(분)", min_value=5, max_value=240, initial=20
    )

    def clean(self) -> dict[str, Any] | None:  # pyright: ignore[reportExplicitAny]
        data = super().clean()
        if not data or self.errors:
            return data
        brief = json.dumps(
            {
                "facts": [data["fact"]],
                "reviews": [line.strip() for line in data["reviews"].splitlines() if line.strip()],
                "owner_minutes": data["owner_minutes"],
            },
            ensure_ascii=False,
        )
        try:
            parse_brief({"brief_json": brief})
        except AicmoError:
            self.add_error(None, "리뷰는 최대 5개, 한 리뷰는 1,200자 이내로 입력해 주세요.")
        else:
            data["brief"] = brief
        return data


class ApprovalForm(forms.Form):
    pack_sha = forms.RegexField(r"^[a-f0-9]{64}$", widget=forms.HiddenInput)
    photo_sha = forms.RegexField(r"^[a-f0-9]{64}$", widget=forms.HiddenInput)
    checked = forms.BooleanField(label="가격·기간·문안과 사용 권리를 확인했습니다.")
