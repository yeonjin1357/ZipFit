"""Deterministic basic-condition checks. Final eligibility is never asserted.

Only reviewed, notice-specific tracks are evaluated. Unknown inputs and special
cases stay unknown. Income, asset and rent values are integer KRW.
"""
from datetime import date, datetime, timedelta, timezone

from .models import Profile

KST = timezone(timedelta(hours=9))
INCOME_120 = {1: 4_576_036, 2: 7_039_524, 3: 9_802_115, 4: 10_562_642, 5: 11_192_382}
LABELS = {"match": "기본조건 일치", "conditional": "조건부 검토", "unknown": "추가 확인 필요", "mismatch": "기본조건 불일치"}
FIELD_LABELS = {
    "birth_date": "생년월일", "marriage": "혼인 상태", "marriage_date": "혼인신고일",
    "marriage_before_movein": "입주 전 혼인신고 가능 여부", "korean": "국적", "residence": "등본상 거주지",
    "self_homeless": "본인 무주택 여부", "household_homeless": "세대 전원 무주택 여부",
    "couple_homeless": "예비부부 무주택 여부", "occupants_homeless": "입주예정자 무주택 여부",
    "car_mode": "차량 소유·운행 여부", "car_value": "차량 가액", "youth_income_scope": "청년 소득 합산 범위",
    "monthly_income_self": "본인 월평균 소득", "monthly_income_household": "세대 월평균 소득",
    "monthly_income_parents": "본인·부모 월평균 소득", "household_size": "소득 산정 가구원 수",
    "assets_self": "본인 총자산", "assets_household": "세대 총자산", "reference_confirmed": "공고일 기준 정보 확인",
    "sh_newborn": "신생아·태아 가구 여부", "sh_single_parent": "한부모가족 유형",
    "dual_income": "맞벌이 소득 유형", "benefit_certificate": "검증 면제 증명서", "sh_asset_children": "자산 완화 대상 자녀",
}


def age_on(birth: date, reference: date) -> int:
    return reference.year - birth.year - ((reference.month, reference.day) < (birth.month, birth.day))


def check(key, label, state, reason, page=None, field=None):
    return {"key": key, "label": label, "state": state, "reason": reason, "page": page, "field": field}


def yes_check(key, label, answer, page, field=None):
    state = {"yes": "pass", "no": "fail", "unknown": "unknown"}[answer]
    return check(key, label, state, {"yes": "입력한 조건이 기준과 일치해요.", "no": "입력한 조건이 기준과 달라요.", "unknown": "이 조건을 확인하려면 추가 입력이 필요해요."}[answer], page, field or key)


def aggregate(checks):
    states = {r["state"] for r in checks}
    if "fail" in states:
        return "mismatch"
    if "unknown" in states:
        return "unknown"
    if "conditional" in states:
        return "conditional"
    return "match"


def alternative_status(tracks):
    states = {t["status"] for t in tracks}
    # A rejected special track must not hide an available general track.
    return next((s for s in ("match", "conditional", "unknown", "mismatch") if s in states), "unknown")


def limit_check(key, label, value, limit, page, field):
    if value is None or limit is None:
        return check(key, label, "unknown", "소득 합산 범위·가구원 수·금액을 확인해 주세요." if key == "income" else "해당 범위의 금액을 입력해 주세요.", page, field)
    return check(key, label, "pass" if value <= limit else "fail", f"입력 {value:,}원 / 기준 {limit:,}원 이하", page, field)


def common(profile, reference):
    return [check("reference", "공고일 기준 정보", "pass" if profile.reference_confirmed else "unknown", f"{reference.isoformat()} 기준으로 혼인·가족·거주·무주택·소득·자산 정보를 확인해 주세요. 나이는 생년월일로 계산해요.", 1, "reference_confirmed")]


def car_check(p):
    if p.car_mode == "none":
        return check("car", "입주예정자 자동차·이륜차", "pass", "입주예정자 모두 소유·운행하는 차량이 없다는 입력입니다.", 10, "car_mode")
    if p.car_mode == "simple":
        return limit_check("car", "자동차 가액", p.car_value, 45_420_000, 10, "car_value")
    return check("car", "자동차 가액", "unknown", "공동지분·여러 대·장애인·국가유공자·보조금 등은 별도 확인이 필요해요." if p.car_mode == "complex" else "입주예정자의 차량 소유·운행 정보를 입력해 주세요.", 10, "car_mode")


def songpa_tracks(p):
    reference = date(2026, 9, 22)
    base = common(p, reference)
    a = age_on(p.birth_date, reference) if p.birth_date else None
    base += [check("age", "공고일 만 19~39세", "unknown" if a is None else "pass" if 19 <= a <= 39 else "fail", "생년월일을 입력해 주세요." if a is None else f"2026.09.22 기준 만 {a}세", 12, "birth_date"),
             yes_check("korean", "신청자 대한민국 국적", p.korean, 12),
             yes_check("occupants_homeless", "입주예정자 모두 무주택", p.occupants_homeless, 10), car_check(p)]
    tracks = []
    for group in ("youth", "couple"):
        for supply in ("special", "general"):
            c = list(base)
            page = 12 if supply == "special" else 15 if group == "youth" else 16
            if group == "youth":
                c += [check("marriage", "미혼 청년", "unknown" if p.marriage == "unknown" else "fail" if p.marriage == "married" else "pass", "혼인 중인 경우 신혼부부 유형을 확인해 주세요." if p.marriage == "married" else "공고일에 혼인신고를 하지 않은 청년 기준입니다.", page, "marriage"), yes_check("self_homeless", "신청자 본인 무주택", p.self_homeless, page)]
            else:
                if p.marriage == "planned":
                    c.append(check("marriage", "입주 전 혼인 사실 증명", "conditional" if p.marriage_before_movein == "yes" else "fail" if p.marriage_before_movein == "no" else "unknown", "실제 입주 전 혼인신고 및 증명서 제출이 필요해요. 입주 예정 기간은 10.27~12.04예요.", page, "marriage_before_movein"))
                    c.append(yes_check("couple_homeless", "예비부부 각각 무주택", p.couple_homeless, page))
                elif p.marriage == "married":
                    days = (reference - p.marriage_date).days if p.marriage_date else None
                    c.append(check("marriage", "공고일 혼인 후 2,555일 이내", "unknown" if days is None else "pass" if 0 <= days <= 2555 else "unknown" if days < 0 else "fail", "공고일 기준 혼인신고일을 확인해 주세요." if days is None or days < 0 else f"혼인 후 {days:,}일 / 공고는 2,555일까지 인정해요.", page, "marriage_date"))
                    c.append(yes_check("household_homeless", "공고상 세대구성원 모두 무주택", p.household_homeless, page))
                else:
                    c.append(check("marriage", "신혼·예비신혼부부", "unknown" if p.marriage == "unknown" else "fail", "혼인 상태 또는 예비신혼 계획을 확인해 주세요.", page, "marriage"))
            if supply == "special":
                if group == "youth":
                    scope = p.youth_income_scope
                    field = {"self": "monthly_income_self", "household": "monthly_income_household", "parents": "monthly_income_parents"}.get(scope)
                    size = 1 if scope == "self" else 3 if scope == "parents" else p.household_size
                    value = getattr(p, field) if field else None
                    assets, asset_limit, asset_field = p.assets_self, 251_000_000, "assets_self"
                else:
                    field, size, value = "monthly_income_household", p.household_size, p.monthly_income_household
                    assets, asset_limit, asset_field = p.assets_household, 345_000_000, "assets_household"
                    if size is not None and size < 2:
                        size = None
                income = limit_check("income", "해당 가구 월평균 소득 120% 이하", value, INCOME_120.get(size), 12 if group == "youth" else 13, field or "youth_income_scope")
                if size and size >= 6:
                    income["reason"] = "6인 이상 표의 가산 방식은 추가 검토 중이에요. 자동으로 제외하지 않아요."
                if size is None and (group == "couple" or scope == "household"):
                    income["field"] = "household_size"
                c += [income, limit_check("assets", "본인 자산" if group == "youth" else "세대 총자산", assets, asset_limit, 12, asset_field)]
            else:
                c.append(check("income_assets", "소득·자산·지역 제한 없음", "pass", "이 공고의 일반공급에는 소득·총자산·지역 요건이 없어요. 자동차 기준은 적용돼요.", page))
            name = ("청년" if group == "youth" else "신혼부부") + (" 특별공급" if supply == "special" else " 일반공급")
            tracks.append({"id": f"{group}_{supply}", "name": name, "checks": c, "status": aggregate(c)})
    return tracks


def lh_tracks(p):
    reference = date(2026, 10, 1)
    c = common(p, reference)
    a = age_on(p.birth_date, reference) if p.birth_date else None
    c.append(check("age", "성년 신청자 또는 미성년 예외", "pass" if a is not None and a >= 19 else "unknown", "공고일 만 19세 이상이에요." if a is not None and a >= 19 else "미성년 세대주 예외가 있어 원문 4쪽 확인이 필요해요.", 4, "birth_date"))
    c.append(yes_check("household_homeless", "무주택세대구성원", p.household_homeless, 4))
    c.append(check("residence", "등본상 수도권 거주", "unknown" if not p.residence else "pass" if p.residence in ("서울", "경기", "인천") else "fail", "신청자의 등본상 주소가 서울·경기·인천이어야 해요. 희망 지역과는 별개예요.", 3, "residence"))
    return [{"id": "general", "name": "든든전세 기본조건", "checks": c, "status": aggregate(c)}]


SH_INCOME = {
    130: {2: 8_212_778, 3: 10_618_958, 4: 11_442_863, 5: 12_125_081},
    200: {2: 12_319_167, 3: 16_336_858, 4: 17_604_404, 5: 18_653_970},
}


def sh_income_limit(size, percent):
    if size is None or size < 2:
        return None
    return SH_INCOME[percent][size] if size <= 5 else SH_INCOME[percent][5] + (size - 5) * {130: 753_061, 200: 1_158_556}[percent]


def sh_family_check(p):
    if p.sh_newborn == "yes" or p.sh_single_parent in ("certified", "young_child"):
        return check("family", "공고상 신청 가구 유형", "pass", "입력한 신생아·한부모 가구 요건을 기준으로 비교해요. 자녀의 공고일 기준 나이와 증빙을 확인해 주세요.", 6)
    if p.marriage == "married":
        if p.marriage_date and p.marriage_date > date(2026, 9, 30):
            return check("family", "공고상 신청 가구 유형", "unknown", "혼인신고일이 공고일보다 늦어요. 공고일 당시 예비신혼 요건을 원문에서 확인해 주세요.", 6)
        return check("family", "공고상 신청 가구 유형", "pass", "공고일에 혼인 중인 가구는 혼인 7년 초과 여부와 관계없이 신청 유형에 포함돼요. 신청 순위는 별도 확인이 필요해요.", 6)
    if p.marriage == "planned" and p.marriage_before_movein == "yes":
        return check("family", "입주일 전일까지 혼인신고", "conditional", "입주일 전일까지 혼인신고하고 입주 시 혼인관계증명서를 제출해야 해요.", 6, "marriage_before_movein")
    unknown_field = "marriage" if p.marriage == "unknown" else "marriage_before_movein" if p.marriage == "planned" and p.marriage_before_movein == "unknown" else "sh_newborn" if p.sh_newborn == "unknown" else "sh_single_parent" if p.sh_single_parent == "unknown" else None
    return check("family", "공고상 신청 가구 유형", "unknown" if unknown_field else "fail", "혼인·예비신혼 외에 신생아·한부모 가구 유형도 확인해 주세요." if unknown_field else "입력한 정보로는 이 공고의 신청 가구 유형에 해당하지 않아요.", 6, unknown_field)


def sh_tracks(p):
    reference = date(2026, 9, 30)
    c = common(p, reference)
    age = age_on(p.birth_date, reference) if p.birth_date else None
    c += [check("age", "성년 신청자 또는 미성년 예외", "pass" if age is not None and age >= 19 else "unknown", "공고일 만 19세 이상이에요." if age is not None and age >= 19 else "생년월일을 확인해 주세요. 만 19세 미만은 자녀가 있는 세대주 등 예외 심사가 필요해요.", 8, "birth_date"),
          yes_check("korean", "신청자 대한민국 국적", p.korean, 8),
          yes_check("household_homeless", "공고상 세대 전원 무주택", p.household_homeless, 7), sh_family_check(p)]
    # The certificate exemption is explicitly unavailable to prospective couples.
    exemption = "yes" if p.sh_single_parent == "certified" else p.benefit_certificate
    if p.marriage == "planned":
        # Other family routes may coexist with prospective marriage. Do not
        # reject their exemption without reviewing the route actually used.
        exemption = "no" if p.sh_newborn == "no" and p.sh_single_parent == "no" else "unknown" if exemption != "no" else "no"
    if exemption == "yes" and p.marriage != "unknown":
        c.append(check("income_assets", "소득·자산 검증 면제 증명", "conditional", "수급자·지원대상 한부모·차상위 증명서를 제출할 수 있다는 입력이에요. 실제 제출해야 검증 면제가 적용돼요. 예비신혼부부에는 적용되지 않아요.", 11, "benefit_certificate"))
    else:
        lower = sh_income_limit(p.household_size, 130)
        upper = sh_income_limit(p.household_size, 200)
        # Income below the lower cap needs no dual-income declaration.
        percent = 200 if p.dual_income == "yes" and p.marriage in ("married", "planned") else 130
        income = limit_check("income", f"세대 월평균 소득 {percent}% 이하", p.monthly_income_household, sh_income_limit(p.household_size, percent), 10, "monthly_income_household")
        if lower is None:
            income.update(reason="태아를 포함한 공고상 가구원 수를 확인해 주세요. 1인 가구는 이 공고의 표에 없어 별도 확인이 필요해요.", field="household_size")
        elif p.monthly_income_household is not None and lower < p.monthly_income_household <= upper and p.dual_income == "unknown" and p.marriage in ("married", "planned", "unknown"):
            income.update(state="unknown", reason=f"130% 기준 {lower:,}원을 넘어요. 본인과 (예비)배우자 모두 근로·사업소득이 있으면 200% 기준 {upper:,}원을 적용해요.", field="dual_income")
        limit = {"none": 362_000_000, "one": 396_000_000, "multiple": 431_000_000}.get(p.sh_asset_children)
        if limit is None and p.assets_household is not None and p.assets_household <= 362_000_000:
            limit = 362_000_000
        if limit is None and p.assets_household is not None and p.assets_household > 431_000_000:
            limit = 431_000_000
        assets = limit_check("assets", "세대 총자산 (자동차 포함)", p.assets_household, limit, 10, "assets_household")
        if limit is None and p.assets_household is not None:
            assets.update(reason="기본 한도는 3억 6,200만원이에요. 출생일·자녀 수에 따라 3억 9,600만원 또는 4억 3,100만원 한도를 적용해요.", field="sh_asset_children")
        for row in (income, assets):
            # Unknown benefit status is not evidence of ineligibility.
            if row["state"] == "fail" and exemption in ("unknown", "yes"):
                row.update(state="unknown", reason=row["reason"] + " · 소득·자산 검증 면제 증명서 대상인지 확인이 필요해요.", field="benefit_certificate" if p.marriage != "unknown" else "marriage")
                if p.marriage == "planned":
                    row["reason"] = "예비신혼부부에는 소득·자산 검증 면제가 적용되지 않아요. 신생아·한부모 유형도 충족하는 경우 해당 유형의 면제 적용 여부를 별도로 확인해 주세요."
                    row["field"] = "sh_newborn" if p.sh_newborn == "unknown" else "sh_single_parent" if p.sh_single_parent == "unknown" else None
        c += [income, assets]
    return [{"id": "sh_family", "name": "신혼·신생아 매입임대Ⅱ 기본조건", "checks": c, "status": aggregate(c)}]


def budget_options(notice, p, tracks):
    statuses = {t["id"]: t["status"] for t in tracks}
    options = []
    for option in notice.get("rent_options", []):
        row = dict(option)
        row["track_status"] = statuses.get(row["track"], "unknown")
        row["within_budget"] = (p.deposit_budget is None or row["deposit"] <= p.deposit_budget) and (p.monthly_rent_budget is None or row["monthly_rent"] <= p.monthly_rent_budget)
        options.append(row)
    return options


def evaluate(notice, p, now=None):
    now = now or datetime.now(KST)
    model = notice.get("rule_model")
    builders = {"songpa_20260922": songpa_tracks, "lh_20261001": lh_tracks, "sh_newlywed_20260930": sh_tracks}
    tracks = builders[model](p) if model in builders else []
    if not p.reference_confirmed:
        for track in tracks:
            track["status"] = "unknown"
    # A catalog refresh cannot prove that attachments or correction links remain
    # unchanged. Never renew a rule review timestamp from list data alone.
    reviewed = notice.get("rule_reviewed_at")
    try:
        reviewed_time = datetime.fromisoformat(reviewed) if reviewed else None
        fresh = reviewed_time is not None and reviewed_time.tzinfo is not None and timedelta() <= now - reviewed_time <= timedelta(hours=24)
    except (ValueError, TypeError):
        fresh = False
    stale = bool(tracks) and (not fresh or any(notice.get(key) for key in ("review_invalidated", "superseded_by", "correction_url", "withdrawn")))
    if stale:
        for track in tracks:
            track["checks"].append(check("version", "공고 최신 버전 재확인", "unknown", "규칙 검토 후 24시간이 지났거나 원문 목록 정보가 바뀌었어요. 정정·취소와 첨부파일을 다시 확인해야 해요."))
            # Even historical failure must not be asserted against a changed rule.
            track["status"] = "unknown"
    status = alternative_status(tracks)
    missing = {}
    for track in tracks:
        for row in track["checks"]:
            field = row.get("field")
            value = getattr(p, field, None) if field else None
            if row["state"] == "unknown" and field and (value is None or value in ("", "unknown") or (field == "reference_confirmed" and value is False)):
                row["input_needed"] = True
                if track["status"] == "unknown":
                    missing[field] = {"field": field, "label": FIELD_LABELS.get(field, row["label"])}
    reason = ("unreviewed" if not tracks else "stale" if stale else "needs_input" if missing else "exception") if status == "unknown" else None
    label = {"unreviewed":"조건 검토 중", "stale":"공고 재확인 필요", "needs_input":"내 정보 입력 필요", "exception":"별도 확인 필요"}.get(reason, LABELS[status])
    return {"status": status, "label": label, "unknown_reason": reason, "missing_fields": [] if stale else list(missing.values()), "tracks": tracks, "rent_options": budget_options(notice, p, tracks), "version_stale": stale,
            "scope": "입력값과 검토한 기본조건의 비교입니다. 중복신청·세대 예외·증빙·최종 자격심사는 원문 확인이 필요해요." if tracks else "이 공고의 자격 규칙은 아직 검토 중이에요. 원문에서 신청 조건을 확인해 주세요."}
