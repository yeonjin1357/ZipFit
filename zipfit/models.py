from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000, strict=True)]
Answer = Literal["yes", "no", "unknown"]


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    birth_date: date | None = None
    marriage: Literal["single", "planned", "married", "unknown"] = "unknown"
    marriage_date: date | None = None
    marriage_before_movein: Answer = "unknown"
    korean: Answer = "unknown"
    residence: str = Field(default="", max_length=30)
    self_homeless: Answer = "unknown"
    household_homeless: Answer = "unknown"
    couple_homeless: Answer = "unknown"
    occupants_homeless: Answer = "unknown"
    car_mode: Literal["none", "simple", "complex", "unknown"] = "unknown"
    car_value: Money | None = None
    youth_income_scope: Literal["self", "household", "parents", "unknown"] = "unknown"
    monthly_income_self: Money | None = None
    monthly_income_household: Money | None = None
    monthly_income_parents: Money | None = None
    household_size: Annotated[int, Field(ge=1, le=20, strict=True)] | None = None
    assets_self: Money | None = None
    assets_household: Money | None = None
    deposit_budget: Money | None = None
    monthly_rent_budget: Money | None = None
    reference_confirmed: bool = False
    # Notice-specific declarations avoid guessing family or benefit status.
    sh_newborn: Answer = "unknown"
    sh_single_parent: Literal["certified", "young_child", "no", "unknown"] = "unknown"
    dual_income: Answer = "unknown"
    benefit_certificate: Answer = "unknown"
    sh_asset_children: Literal["none", "one", "multiple", "unknown"] = "unknown"

    @model_validator(mode="after")
    def dates_are_consistent(self):
        today = datetime.now(timezone(timedelta(hours=9))).date()
        if self.birth_date and not date(1900, 1, 1) <= self.birth_date <= today:
            raise ValueError("생년월일을 확인해 주세요.")
        if self.marriage_date and self.birth_date and self.marriage_date < self.birth_date:
            raise ValueError("혼인신고일이 생년월일보다 빠릅니다.")
        if self.marriage == "married" and self.marriage_date and self.marriage_date > today:
            raise ValueError("혼인 중이라면 실제 혼인신고일을 입력해 주세요.")
        if self.self_homeless == "no" and (self.household_homeless == "yes" or self.couple_homeless == "yes"):
            raise ValueError("본인과 세대·부부의 무주택 응답이 서로 다릅니다.")
        if self.sh_newborn == "yes" and self.sh_asset_children == "none":
            raise ValueError("신생아·태아 가구 응답과 자산 완화 대상 자녀 응답을 확인해 주세요.")
        if self.sh_single_parent == "certified" and self.benefit_certificate == "no":
            raise ValueError("지원대상 한부모 증명서와 소득·자산 검증 면제 증명서 응답이 서로 다릅니다.")
        return self


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Profile = Field(default_factory=Profile)
