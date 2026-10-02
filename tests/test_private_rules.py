from zipfit.private_rules import seomyeon_tracks
from tests.test_rules import youth
from zipfit.rules import lh_tracks
from datetime import datetime
from zipfit.catalog import schedule
import pytest


def tracks(**changes):
    return {t["id"]: t for t in seomyeon_tracks(youth(**changes))}


def test_seomyeon_youth_age_uses_own_reference_date_and_own_house():
    assert tracks(birth_date="1986-09-29")["seomyeon_youth"]["status"] == "mismatch"
    assert tracks(birth_date="1986-09-30", household_homeless="no")["seomyeon_youth"]["status"] == "match"
    assert tracks(birth_date="2007-09-30")["seomyeon_youth"]["status"] == "mismatch"


def test_general_does_not_inherit_special_income_or_other_notices_car_cap():
    t = tracks(marriage="married", marriage_total_within_7_years="yes", household_size=2, monthly_income_household=7_039_525, car_mode="simple", car_value=99_000_000)
    assert t["seomyeon_special"]["status"] == "mismatch"
    assert t["seomyeon_couple"]["status"] == "match"
    assert tracks(marriage="married", marriage_total_within_7_years="yes", household_size=2, monthly_income_household=7_039_524)["seomyeon_special"]["status"] == "match"


def test_cumulative_marriage_duration_is_not_guessed_from_single_date():
    assert tracks(marriage="married", marriage_date="2025-01-01")["seomyeon_couple"]["status"] == "unknown"
    assert tracks(marriage="married", marriage_total_within_7_years="no")["seomyeon_couple"]["status"] == "mismatch"
    assert tracks(marriage="planned", marriage_before_movein="yes")["seomyeon_couple"]["status"] == "conditional"


def test_generic_lh_rule_uses_reviewed_notice_config():
    config = {"reference_date": "2026-10-01", "regions": ["서울", "경기", "인천"], "eligibility_page": 4, "region_page": 3}
    assert lh_tracks(youth(residence="경기"), config)[0]["status"] == "match"
    assert lh_tracks(youth(residence="부산"), config)[0]["status"] == "mismatch"
    assert lh_tracks(youth(residence="경기", birth_date="2010-01-01"), config)[0]["status"] == "unknown"


@pytest.mark.parametrize("stamp,state", [("2026-10-06T08:59:59+09:00", "upcoming"), ("2026-10-06T00:00:00+00:00", "open"), ("2026-10-06T17:30:00+09:00", "upcoming"), ("2026-10-07T08:59:59+09:00", "upcoming"), ("2026-10-07T17:29:59+09:00", "open"), ("2026-10-07T17:30:00+09:00", "closed")])
def test_daily_application_hours_do_not_advertise_overnight_acceptance(stamp, state):
    n = {"application_start":"2026-10-06T09:00:00+09:00", "application_end":"2026-10-07T17:30:00+09:00", "daily_hours":["09:00", "17:30"]}
    assert schedule(n, datetime.fromisoformat(stamp))["state"] == state
