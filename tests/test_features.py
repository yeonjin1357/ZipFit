from datetime import datetime, timedelta
import json
import pytest

from zipfit.catalog import ROOT, schedule
from zipfit.calendar import export_calendar
from zipfit.collect import jobs_for,merge_records
from zipfit.schedules import parse_lh,refresh_one
from zipfit.verification import binding
from zipfit.private_rules import gh_care_tracks
from scripts.import_housing import read_units
from tests.test_rules import youth

NOW=datetime.fromisoformat('2026-10-03T22:00:00+09:00')


def test_lh_read_rendered_period_and_script_without_document_deadline():
    for name,expected in [('lh-seoul','2026-10-14'),('lh-schedule-sample','2026-10-12')]:
        windows=parse_lh((ROOT/f'research/phase6/{name}.html').read_bytes())
        assert len(windows)==1 and windows[0]['start']==expected
    with pytest.raises(ValueError):parse_lh(b'<html>Request denied</html>')


def test_lh_multiple_supply_periods_do_not_merge_gap_into_open_days():
    html='''<div id="sub_container"><script>var currPanId='';var currPanKdCd='';</script><table><thead><tr><th>공급구분</th><th>접수기간</th></tr></thead><tbody><tr><td>우선공급</td><td>2026.10.05~2026.10.06</td></tr><tr><td>일반공급</td><td>2026.10.09~2026.10.10</td></tr></tbody></table></div>'''
    windows=parse_lh(html.encode())
    assert len(windows)==2 and windows[0]['label']=='우선공급'
    n={'application_windows':windows}
    assert schedule(n,datetime.fromisoformat('2026-10-07T12:00:00+09:00'))['state']=='upcoming'
    assert schedule(n,datetime.fromisoformat('2026-10-09T12:00:00+09:00'))['state']=='open'
    aggregate = "<span id='sta_acpDt'>2026.10.05~2026.10.10</span>"
    assert parse_lh(html.replace('<table>',aggregate+'<table>').encode()) == windows


def test_schedule_errors_and_expired_checks_keep_old_values_but_block_export(monkeypatch):
    from zipfit import schedules
    n={'id':'x','url':'https://apply.lh.or.kr/x','application_windows':[{'label':'청약','start':'2026-10-05','end':'2026-10-06'}]}
    def fail(*args):raise ValueError('blocked')
    monkeypatch.setattr(schedules,'fetch',fail)
    result=refresh_one(n,NOW)
    assert result['application_windows']==n['application_windows']
    assert schedule(result,NOW)['state']=='unknown'
    with pytest.raises(ValueError):export_calendar(result,NOW)
    n['schedule_source']={'state':'extracted','checked_at':(NOW-timedelta(days=2)).isoformat()}
    assert schedule(n,NOW)['state']=='unknown'


def test_expanded_scan_and_missing_records_are_preserved():
    jobs=jobs_for('LH',6,NOW,365)
    assert len(jobs)==6 and jobs[0]['data']['startDt']=='2025-10-03'
    old={'id':'a','application_windows':[{'start':'2026-10-10','end':'2026-10-11'}],'list_fingerprint':{'title':'old'}}
    result=merge_records([old,{'id':'absent'}],[{'id':'a','title':'new'}])
    assert result[0]['schedule_invalidated']
    assert result[1]['id']=='absent'


def test_calendar_daily_hours_utc_dates_escaping_and_folding():
    n={'id':'private','title':'긴 공고명 '*40+'\r\nBEGIN:VEVENT','url':'https://www.applyhome.co.kr/test','application_start':'2026-10-06T09:00:00+09:00','application_end':'2026-10-07T17:30:00+09:00','daily_hours':['09:00','17:30']}
    ics=export_calendar(n,NOW)
    assert ics.count('\r\nBEGIN:VEVENT\r\n')==2
    assert 'DTSTART:20261006T000000Z' in ics
    assert 'DTEND:20261007T083000Z' in ics
    assert all(len(line.encode())<=75 for line in ics.split('\r\n'))
    assert '\\nBEGIN:VEVENT' in ics.replace('\r\n ','')
    assert [x for x in ics.splitlines() if x.startswith('UID:')]==[x for x in export_calendar(n,NOW+timedelta(hours=1)).splitlines() if x.startswith('UID:')]


def test_calendar_date_end_exclusive_and_changed_notice_denied():
    n={'id':'dates','title':'공고','url':'https://apply.lh.or.kr/x','application_start':'2026-10-06','application_end':'2026-10-07'}
    assert 'DTEND;VALUE=DATE:20261008' in export_calendar(n,NOW)
    for key,value in [('review_invalidated',True),('withdrawn',True),('correction_url','https://apply.lh.or.kr/new')]:
        with pytest.raises(ValueError):export_calendar(n|{key:value},NOW)


def test_real_housing_rows_and_won_units():
    seoul=read_units(ROOT/'research/phase6/seoul-units.xlsx','seoul')
    north=read_units(ROOT/'research/phase6/north-units.xlsx','north')
    assert len(seoul)==56 and len(north)==134
    assert (seoul[0]['area'],seoul[0]['deposit'],seoul[0]['source_row'])==(54.18,342280000,8)
    assert north[0]['deposit']==255167000 and north[0]['area']==74.0354
    assert all(u['monthly_rent']==0 and u['address'] for u in seoul+north)
    n={'housing_units':seoul};before=binding(n);n['housing_units'][0]['deposit']+=1
    assert binding(n)!=before


def test_gh_rules_do_not_reuse_sh_200_percent_or_vehicle_scope():
    def result(**kw):return gh_care_tracks(youth(marriage='married',household_size=2,assets_household=345000000,gh_car_value=45420000,**kw))[0]['status']
    assert result(monthly_income_household=6452897,gh_income_reference_confirmed='yes')=='match'
    assert result(monthly_income_household=6452898,gh_income_reference_confirmed='yes',dual_income='yes')=='mismatch'
    assert result(monthly_income_household=6452897)=='unknown'


def test_no_region_limit_does_not_require_residence():
    from zipfit.rules import lh_tracks
    config={'reference_date':'2026-09-30','regions':None,'eligibility_page':4,'region_page':3}
    assert lh_tracks(youth(residence=''),config)[0]['status']=='match'


def test_download_endpoints_and_path_guards(monkeypatch):
    from fastapi.testclient import TestClient
    from zipfit.main import app
    n={'id':'synthetic','title':'청약','url':'https://apply.lh.or.kr/x',
       'application_start':'2099-01-01','application_end':'2099-01-02',
       'housing_document':{'path':'research/phase6/seoul-units.xlsx'}}
    monkeypatch.setattr('zipfit.main.load_catalog',lambda:{'notices':[n]})
    with TestClient(app) as client:
        response=client.get('/api/calendar/synthetic')
        assert response.status_code==200 and response.headers['content-type'].startswith('text/calendar')
        assert 'DTEND;VALUE=DATE:20990103' in response.text
        assert 'attachment' in response.headers['content-disposition']
        assert client.get('/api/housing-document/synthetic').content.startswith(b'PK')
        n['housing_document']['path']='pyproject.toml'
        assert client.get('/api/housing-document/synthetic').status_code==404
        n['withdrawn']=True
        assert client.get('/api/calendar/synthetic').status_code==409
        assert client.get('/api/calendar/missing').status_code==404


def test_gh_car_and_assets_boundaries_and_missing_scope():
    def checks(**kw):
        profile={'marriage':'married','household_size':2,'monthly_income_household':6000000,
                 'gh_income_reference_confirmed':'yes','assets_household':345000000,'gh_car_value':45420000}
        return gh_care_tracks(youth(**(profile|kw)))[0]['status']
    assert checks()=='match'
    assert checks(assets_household=345000001)=='mismatch'
    assert checks(gh_car_value=45420001)=='mismatch'
    assert checks(gh_car_value=None,car_mode='none')=='unknown'
    assert checks(household_size=7)=='unknown'


def test_housing_document_tampering_is_audit_error():
    from zipfit.audit import audit
    c=json.loads((ROOT/'data/release-catalog.json').read_text(encoding='utf-8'))
    n=next(n for n in c['notices'] if n.get('housing_document'))
    n['housing_units'][0]['deposit']=-1
    assert audit(c,NOW)['errors']


def test_gh_detail_attachment_is_the_reviewed_pdf():
    from zipfit.verification import extract_detail
    c=json.loads((ROOT/'data/release-catalog.json').read_text(encoding='utf-8'))
    n=next(n for n in c['notices'] if n.get('rule_model')=='gh_care_20260821')
    detail=extract_detail((ROOT/'research/phase6/gh-care.html').read_bytes(),n)
    assert len(detail['attachments'])==1
    assert detail['attachments'][0]['url']==n['document']['url']
