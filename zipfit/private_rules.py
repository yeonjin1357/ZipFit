"""Individually reviewed Seomyeon and GH Care Hub notices."""
from datetime import date

from .rules import age_on, aggregate, check, common, limit_check, yes_check


def gh_care_tracks(p):
    c = common(p,date(2026,8,21)) + [yes_check('household_homeless','신청일 현재 공고상 세대 전원 무주택',p.household_homeless,1)]
    c[0].update(label='공고별 판단 기준일',reason='기본 판단일은 2026.08.21이에요. 무주택은 신청일 현재, 소득은 서류 접수일 등 항목별 기준을 함께 확인해 주세요.')
    if p.marriage == 'married':
        c.append(check('family','혼인가구 신청 유형','pass','PDF 5쪽 ⑦ 혼인가구를 포함해요. 가점과 최종 심사는 별도예요.',5))
    elif p.marriage == 'planned':
        c.append(check('family','입주일 전일까지 혼인신고','conditional' if p.marriage_before_movein=='yes' else 'fail' if p.marriage_before_movein=='no' else 'unknown','구성될 세대의 무주택 및 입주 전 혼인 증명이 필요해요.',5,'marriage_before_movein'))
    else:
        state = 'pass' if p.gh_family_type in ('newborn','certified_parent','young_parent') else 'fail' if p.gh_family_type=='none' and p.marriage=='single' else 'unknown'
        c.append(check('family','신생아·한부모가족 유형',state,'신생아는 2024.08.22 이후 출생·입양·태아, 어린 자녀 한부모는 2019.08.22 이후 출생·태아 기준이에요.',5,'gh_family_type'))
    limits={1:4_576_036,2:6_452_897,3:8_168_429,4:8_802_202,5:9_326_985,6:9_906_263}
    income=limit_check('income','공고 표의 세대 소득 기준',p.monthly_income_household,limits.get(p.household_size),5,'monthly_income_household')
    if p.gh_income_reference_confirmed!='yes':
        income.update(state='unknown',reason='이 공고는 서류 접수일의 공적 소득자료 기준이에요. 해당 기준으로 확인한 금액인지 알려주세요.',field='gh_income_reference_confirmed')
    elif p.household_size not in limits:
        income.update(state='unknown',reason='공고의 1~6인 가구 표 밖은 별도 확인이 필요해요.',field='household_size')
    c += [income,limit_check('assets','세대 총자산 3억 4,500만원 이하',p.assets_household,345_000_000,5,'assets_household'),limit_check('car','세대 자동차 중 최고 가액 4,542만원 이하',p.gh_car_value,45_420_000,7,'gh_car_value')]
    return [{'id':'gh_care_family','name':'GH Care Hub 신혼부부형 기본조건','checks':c,'status':aggregate(c)}]


def seomyeon_tracks(p):
    reference = date(2026, 9, 29)
    age = age_on(p.birth_date, reference) if p.birth_date else None
    base = common(p, reference) + [
        check("age", "공고일 만 19~39세", "unknown" if age is None else "pass" if 19 <= age <= 39 else "fail", "생년월일을 입력해 주세요." if age is None else f"2026.09.29 기준 만 {age}세", 6, "birth_date"),
        yes_check("korean", "신청자 대한민국 국적", p.korean, 6),
    ]
    youth = base + [
        check("marriage", "혼인 중이 아닌 청년", "unknown" if p.marriage == "unknown" else "fail" if p.marriage == "married" else "pass", "공고일에 혼인 중이 아닌 청년 기준이에요.", 6, "marriage"),
        yes_check("self_homeless", "신청자 본인 무주택", p.self_homeless, 6),
        check("income_assets", "일반공급 소득·자산 제한 없음", "pass", "일반공급에는 소득·자산 한도를 적용하지 않아요. 주택 소유 판정 예외는 원문 확인이 필요해요.", 7),
    ]
    family = list(base)
    if p.marriage == "planned":
        family += [check("marriage", "입주 전 혼인사실 증명", "conditional" if p.marriage_before_movein == "yes" else "fail" if p.marriage_before_movein == "no" else "unknown", "입주 전 혼인사실 증명 및 혼인으로 구성될 세대 전원의 무주택 확인이 필요해요.", 5, "marriage_before_movein"), yes_check("household_homeless", "입주 시 구성할 세대 전원 무주택", p.household_homeless, 5)]
    elif p.marriage == "married":
        # This notice uses cumulative marriage duration, which a single date
        # cannot establish after remarriage. Ask explicitly instead of guessing.
        family += [yes_check("marriage_total_within_7_years", "혼인 합산 기간 7년 이내", p.marriage_total_within_7_years, 5), yes_check("household_homeless", "세대구성원 모두 무주택", p.household_homeless, 6)]
    else:
        family += [check("marriage", "신혼·예비신혼부부", "unknown" if p.marriage == "unknown" else "fail", "혼인 중이거나 입주 전 혼인을 계획한 가구 기준이에요.", 5, "marriage")]
    limits = {2: 7_039_524, 3: 9_802_115, 4: 10_562_642, 5: 11_192_382, 6: 11_887_516, 7: 12_582_649, 8: 13_277_783}
    income = limit_check("income", "세대 월평균 소득 120% 이하", p.monthly_income_household, limits.get(p.household_size), 6, "monthly_income_household")
    if p.household_size not in limits:
        income.update(reason="2~8인 가구 표를 지원해요. 가구원 수를 확인하고 9인 이상은 원문의 가산 기준을 확인해 주세요.", field="household_size")
    tracks = [("seomyeon_youth", "청년 일반공급", youth), ("seomyeon_couple", "신혼부부 일반공급", family + [check("income_assets", "일반공급 소득·자산 제한 없음", "pass", "일반공급에는 특별공급의 소득 한도를 적용하지 않아요.", 7)]), ("seomyeon_special", "신혼부부 특별공급", family + [income])]
    return [{"id": key, "name": name, "checks": checks, "status": aggregate(checks)} for key, name, checks in tracks]
