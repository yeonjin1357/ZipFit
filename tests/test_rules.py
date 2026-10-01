from datetime import date, datetime
import json

import pytest
from pydantic import ValidationError

from zipfit.catalog import ROOT, schedule
from zipfit.models import Profile
from zipfit.rules import INCOME_120, age_on, evaluate

NOW = datetime.fromisoformat("2026-10-01T18:00:00+09:00")
CATALOG = json.loads((ROOT/"data/catalog.json").read_text(encoding="utf-8"))
SONGPA = next(n for n in CATALOG["notices"] if n["rule_model"] == "songpa_20260922")
LH = next(n for n in CATALOG["notices"] if n["rule_model"] == "lh_20261001")


def youth(**changes):
    values = dict(birth_date="1995-04-15",marriage="single",korean="yes",residence="부산",self_homeless="yes",household_homeless="yes",occupants_homeless="yes",car_mode="none",youth_income_scope="self",monthly_income_self=3_000_000,assets_self=80_000_000,reference_confirmed=True)
    return Profile(**(values|changes))


def tracks(p, notice=SONGPA, now=NOW):
    return {t["id"]:t for t in evaluate(notice,p,now)["tracks"]}


@pytest.mark.parametrize("dob,expected",[("1986-09-22","mismatch"),("1986-09-23","match"),("2007-09-22","match"),("2007-09-23","mismatch")])
def test_age_uses_notice_reference_date(dob,expected):
    assert tracks(youth(birth_date=dob))["youth_general"]["status"] == expected


def test_income_one_won_boundary_and_general_alternative():
    edge=INCOME_120[1]
    assert tracks(youth(monthly_income_self=edge))["youth_special"]["status"]=="match"
    result=evaluate(SONGPA,youth(monthly_income_self=edge+1),NOW)
    assert result["status"]=="match"
    assert next(t for t in result["tracks"] if t["id"]=="youth_special")["status"]=="mismatch"


def test_original_9300_salary_example_does_not_exclude_notice():
    p=youth(marriage="married",marriage_date="2024-05-01",monthly_income_household=7_750_000,household_size=2,assets_household=150_000_000)
    t=tracks(p)
    assert t["couple_special"]["status"]=="mismatch"
    assert t["couple_general"]["status"]=="match"
    assert evaluate(SONGPA,p,NOW)["status"]=="match"


def test_missing_is_not_zero():
    assert tracks(youth(monthly_income_self=None))["youth_special"]["status"]=="unknown"
    assert tracks(youth(monthly_income_self=0))["youth_special"]["status"]=="match"


def test_unemployed_youth_uses_parents_three_person_income():
    p=youth(youth_income_scope="parents",monthly_income_self=0,monthly_income_parents=INCOME_120[3]+1)
    assert tracks(p)["youth_special"]["status"]=="mismatch"


def test_six_person_footnote_not_guessed():
    p=youth(youth_income_scope="household",household_size=6,monthly_income_household=1)
    assert tracks(p)["youth_special"]["status"]=="unknown"


def test_pre_marriage_remains_conditional_and_not_final_pass():
    p=youth(marriage="planned",marriage_before_movein="yes",couple_homeless="yes",household_size=2,monthly_income_household=6_000_000,assets_household=100_000_000)
    assert tracks(p)["couple_general"]["status"]=="conditional"
    assert tracks(p)["couple_special"]["status"]=="conditional"


def test_2555_day_marriage_boundary():
    from datetime import timedelta
    ref=date(2026,9,22)
    assert tracks(youth(marriage="married",marriage_date=ref-timedelta(days=2555)))["couple_general"]["status"]=="match"
    assert tracks(youth(marriage="married",marriage_date=ref-timedelta(days=2556)))["couple_general"]["status"]=="mismatch"


def test_car_threshold_and_exceptions():
    assert tracks(youth(car_mode="simple",car_value=45_420_000))["youth_general"]["status"]=="match"
    assert tracks(youth(car_mode="simple",car_value=45_420_001))["youth_general"]["status"]=="mismatch"
    assert tracks(youth(car_mode="complex",car_value=99_000_000))["youth_general"]["status"]=="unknown"


def test_residence_is_not_songpa_eligibility_but_is_lh_requirement():
    p=youth(residence="부산")
    assert tracks(p)["youth_general"]["status"]=="match"
    assert tracks(p,LH)["general"]["status"]=="mismatch"


def test_lh_minor_exception_must_not_be_rejected():
    assert tracks(youth(birth_date="2010-04-15",residence="서울"),LH)["general"]["status"]=="unknown"


def test_reference_not_confirmed_does_not_reject_using_current_profile():
    assert evaluate(SONGPA,youth(reference_confirmed=False,car_mode="simple",car_value=99_000_000),NOW)["status"]=="unknown"


def test_stale_and_changed_rules_block_both_positive_and_negative_results():
    for n, now in [(SONGPA,datetime.fromisoformat("2026-10-03T17:00:00+09:00")),(SONGPA|{"review_invalidated":True},NOW)]:
        assert evaluate(n,youth(),now)["status"]=="unknown"
        assert evaluate(n,youth(birth_date="1980-01-01"),now)["status"]=="unknown"


def test_budget_requires_one_real_pair_and_does_not_change_eligibility():
    p=youth(deposit_budget=30_000_000,monthly_rent_budget=350_000)
    r=evaluate(SONGPA,p,NOW)
    assert r["status"]=="match"
    assert not any(o["within_budget"] for o in r["rent_options"])
    assert len(r["rent_options"])==12


def test_missing_rules_never_means_eligible():
    assert evaluate({"rule_model":None},youth(),NOW)["status"]=="unknown"


def test_end_time_and_timezone_are_respected():
    assert schedule(SONGPA,datetime.fromisoformat("2026-10-05T13:59:59+00:00"))["state"]=="open"
    assert schedule(SONGPA,datetime.fromisoformat("2026-10-05T14:00:01+00:00"))["state"]=="closed"
    assert schedule(LH,NOW)["state"]=="upcoming"
    assert schedule({"listed_closing_date":None},NOW)["state"]=="unknown"
    assert schedule({"source_status":"접수마감","listed_closing_date":"2026-10-01"},NOW)["state"]=="closed"


def test_profile_validation():
    for bad in ({"assets_self":-1},{"household_size":0},{"monthly_income_self":1.5},{"birth_date":"2099-01-01"},{"self_homeless":"no","household_homeless":"yes"}):
        with pytest.raises(ValidationError): Profile(**bad)
