import json
from typing import Any

from django import forms

from aicmo.errors import AicmoError
from aicmo.local_pack import parse_brief
from aicmo.onboarding import OnboardingAnswers, validate_answers


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


class StoreBasicsForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)
    company_name = forms.CharField(label="가게 이름", max_length=120)
    neighborhood = forms.CharField(
        label="동네·상권",
        max_length=200,
        help_text="예: 성수동, 중앙시장. 개인 주소는 적지 마세요.",
    )
    business_type = forms.CharField(
        label="어떤 가게인가요?", max_length=120, help_text="예: 카페, 미용실, 반찬 가게"
    )
    website = forms.URLField(
        label="가게 홈페이지 주소",
        max_length=1000,
        required=False,
        help_text="없으면 비워 두세요. 주소를 자동으로 열거나 수집하지 않습니다.",
    )


class StoreOfferForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)
    offer = forms.CharField(
        label="대표 상품이나 서비스", max_length=600, widget=forms.Textarea(attrs={"rows": 3})
    )
    price = forms.CharField(
        label="대표 상품 가격",
        max_length=120,
        required=False,
        help_text="예: 아메리카노 4,000원. 아직 모르면 비워 두세요.",
    )
    business_hours = forms.CharField(
        label="영업시간·휴무일",
        max_length=300,
        required=False,
        help_text="확인한 시간만 적어 주세요. 모르면 비워 두세요.",
    )
    differentiator = forms.CharField(
        label="손님에게 알려 줄 가게 특징",
        max_length=600,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="직접 확인할 수 있는 특징만 적어 주세요. 아직 정하지 못했다면 비워 두세요.",
    )

    def clean_price(self) -> str:
        value = str(self.cleaned_data["price"])
        try:
            validate_answers(onboarding_answers({"price": value}, "validation", ""))
        except AicmoError:
            reason = "가격은 음수나 숨은 문자 없이 입력해 주세요."
            raise forms.ValidationError(reason) from None
        return value


class StorePurposeForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)
    objective = forms.ChoiceField(
        label="이번에 가장 하고 싶은 일",
        choices=[
            ("가게 소식 안내", "가게 소식 알리기"),
            ("리뷰 답글 준비", "리뷰 답글 준비하기"),
            ("방문·문의 안내", "방문·문의 안내하기"),
        ],
    )
    channel = forms.ChoiceField(
        label="먼저 사용할 채널",
        choices=[("네이버", "네이버")],
        help_text="현재 실행팩은 네이버를 지원합니다. 사장님이 확인한 뒤 직접 게시합니다.",
    )
    weekly_capacity = forms.IntegerField(
        label="주당 홍보에 쓸 수 있는 시간(분)", min_value=5, max_value=240, initial=20
    )
    market_type = forms.ChoiceField(
        label="주로 누구에게 판매하나요?",
        initial="unknown",
        choices=[
            ("unknown", "아직 정하지 않았어요"),
            ("b2c", "일반 손님"),
            ("b2b", "회사·사업자"),
            ("both", "둘 다"),
        ],
    )
    audience = forms.CharField(label="주로 어떤 손님이 찾아오나요?", max_length=400, required=False)
    proof = forms.CharField(
        label="참고할 실제 후기나 확인된 근거",
        max_length=1200,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="없으면 비워 두세요. 고객 이름·연락처를 넣거나 후기를 지어내지 마세요.",
    )
    cta = forms.CharField(
        label="소식을 본 손님이 무엇을 하면 좋을까요?",
        max_length=300,
        required=False,
        help_text="예: 영업시간 확인 후 방문. 정하지 못했다면 비워 두세요.",
    )


class OnboardingConfirmForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    checked = forms.BooleanField(
        label="입력한 사실과 사용 권리를 확인했습니다. 빈 항목은 미확인으로 남깁니다."
    )


ONBOARDING_FORMS = {1: StoreBasicsForm, 2: StoreOfferForm, 3: StorePurposeForm}


def onboarding_answers(
    values: dict[str, str], client: str, confirmed_date: str
) -> OnboardingAnswers:
    unknown = "[미확인 — 추정 작성 금지]"
    return OnboardingAnswers(
        client=client,
        company_name=values.get("company_name") or unknown,
        neighborhood=values.get("neighborhood") or "모름",
        business_type=values.get("business_type") or "모름",
        offer=values.get("offer") or unknown,
        price=values.get("price") or "모름",
        business_hours=values.get("business_hours") or "모름",
        audience=values.get("audience") or unknown,
        problem=unknown,
        differentiator=values.get("differentiator") or unknown,
        channel=values.get("channel") or "네이버",
        proof=values.get("proof") or "후기없음",
        cta=values.get("cta") or unknown,
        website=values.get("website") or "미입력",
        objective=values.get("objective") or "모름",
        weekly_capacity=(
            f"{values['weekly_capacity']}분" if values.get("weekly_capacity") else "모름"
        ),
        market_type=values.get("market_type") or "unknown",
        fact_status="unknown",
        onboarding_date=confirmed_date,
    )
