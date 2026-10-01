import pytest

from tests.test_rules import CATALOG, NOW, youth
from zipfit.rules import evaluate, sh_income_limit

SH = next(n for n in CATALOG["notices"] if n["rule_model"] == "sh_newlywed_20260930")


def family(**changes):
    return youth(**(dict(marriage="married", marriage_date="2010-05-01", household_size=2,
                        monthly_income_household=8_000_000, assets_household=350_000_000,
                        dual_income="no", benefit_certificate="no", sh_newborn="no",
                        sh_single_parent="no", sh_asset_children="none") | changes))


def status(**changes):
    return evaluate(SH, family(**changes), NOW)["status"]


def test_older_marriage_and_non_seoul_resident_still_eligible():
    assert status(residence="부산") == "match"


@pytest.mark.parametrize("income,dual,expected", [
    (8_212_778,"no","match"), (8_212_779,"no","mismatch"),
    (12_319_167,"yes","match"), (12_319_168,"yes","mismatch"),
    (8_212_778,"unknown","match"), (8_212_779,"unknown","unknown"),
    (12_319_168,"unknown","mismatch"), (None,"yes","unknown"), (0,"no","match"),
])
def test_sh_income_boundaries(income, dual, expected):
    assert status(monthly_income_household=income, dual_income=dual) == expected


def test_large_household_addition_and_one_person_ambiguity():
    assert sh_income_limit(6,130) == 12_878_142
    assert sh_income_limit(7,200) == 20_971_082
    assert status(household_size=6, monthly_income_household=12_878_142) == "match"
    assert status(household_size=6, monthly_income_household=12_878_143) == "mismatch"
    assert status(household_size=1) == "unknown"


@pytest.mark.parametrize("band,limit", [("none",362_000_000),("one",396_000_000),("multiple",431_000_000)])
def test_child_asset_exact_boundary(band, limit):
    assert status(sh_asset_children=band, assets_household=limit) == "match"
    assert status(sh_asset_children=band, assets_household=limit+1) == "mismatch"


def test_unknown_child_relaxation_does_not_reject():
    assert status(sh_asset_children="unknown", assets_household=362_000_000) == "match"
    assert status(sh_asset_children="unknown", assets_household=362_000_001) == "unknown"
    assert status(sh_asset_children="unknown", assets_household=431_000_001) == "mismatch"


def test_benefits_must_be_known_before_rejecting_above_threshold():
    assert status(monthly_income_household=99_000_000, benefit_certificate="unknown") == "unknown"
    assert status(monthly_income_household=99_000_000, assets_household=999_000_000, benefit_certificate="yes") == "conditional"
    assert status(marriage="planned", marriage_date=None, marriage_before_movein="yes",
                  monthly_income_household=99_000_000, benefit_certificate="yes") == "mismatch"
    assert status(marriage="planned", marriage_date=None, marriage_before_movein="yes",
                  monthly_income_household=99_000_000, benefit_certificate="yes", sh_newborn="unknown") == "unknown"


def test_newborn_and_single_parent_are_independent_family_routes():
    assert status(marriage="single", marriage_date=None, sh_newborn="yes", sh_asset_children="one") == "match"
    assert status(marriage="single", marriage_date=None, sh_single_parent="young_child") == "match"
    assert status(marriage="single", marriage_date=None) == "mismatch"
    assert status(marriage="single", marriage_date=None, sh_newborn="unknown") == "unknown"
    assert status(marriage="single", marriage_date=None, sh_single_parent="certified", benefit_certificate="yes", monthly_income_household=None, assets_household=None) == "conditional"


def test_prospective_couple_minor_and_no_separate_car_cap():
    assert status(marriage="planned", marriage_date=None, marriage_before_movein="yes") == "conditional"
    assert status(birth_date="2010-05-01", marriage_date=None) == "unknown"
    assert status(car_mode="simple", car_value=99_000_000) == "match"


def test_missing_information_has_actionable_field():
    result = evaluate(SH, family(monthly_income_household=9_000_000, dual_income="unknown"), NOW)
    assert result["unknown_reason"] == "needs_input"
    assert {f["field"] for f in result["missing_fields"]} == {"dual_income"}
    result = evaluate(SH, family(household_size=1), NOW)
    assert result["unknown_reason"] == "exception"
    assert not result["missing_fields"]
