"""Exercise quick inputs, housing rows and local saved notices in Chrome."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parents[1] / 'tmp/screenshots'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8765')
    base=parser.parse_args().base_url.rstrip('/')
    errors=[];OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1050})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.locator('.notice-card').first.wait_for()
        initial=page.request.get(base+'/api/notices').json()
        seoul=next(n for n in initial['notices'] if n.get('housing_document',{}).get('path','').endswith('seoul-units.xlsx'))
        assert len(seoul['housing_units'])==56
        page.locator('#quick-open').click()
        quick=page.locator('#quick-form')
        quick.locator('[name=birth_date]').fill('1995-04-15')
        quick.locator('[name=marriage]').select_option('married')
        quick.locator('[name=residence]').select_option('서울')
        quick.locator('[name=self_homeless]').select_option('yes')
        quick.locator('[name=reference_confirmed]').check()
        with page.expect_response('**/api/match') as response:
            quick.locator('[type=submit]').click()
        assert response.value.status==200
        expect(page.locator('#quick-dialog')).not_to_be_visible()
        page.evaluate('id=>openDetail(id)',seoul['id'])
        page.locator('#detail-dialog [data-needed]').first.click()
        needed=page.locator('#needed-form')
        assert needed.locator('input,select').count()==1
        needed.locator('[name=household_homeless]').select_option('yes')
        with page.expect_response('**/api/match') as response:
            needed.locator('[type=submit]').click()
        matched=next(n for n in response.value.json()['notices'] if n['id']==seoul['id'])
        assert matched['evaluation']['status']=='match'
        expect(page.locator('#detail-dialog')).to_be_visible()
        page.locator('#unit-area-min').fill('55')
        page.locator('#unit-area-max').fill('60')
        assert page.locator('.housing-table tbody tr').count()==sum(55<=u['area']<=60 for u in seoul['housing_units'])
        page.locator('#unit-area-min').fill('61')
        expect(page.locator('#unit-results')).to_contain_text('최소 면적이 최대 면적보다')
        page.locator('#unit-area-min').fill('');page.locator('#unit-area-max').fill('')
        page.locator('#unit-query').fill(seoul['housing_units'][0]['address'].split()[1])
        expected=[u for u in seoul['housing_units'] if seoul['housing_units'][0]['address'].split()[1] in u['address']]
        assert page.locator('.housing-table tbody tr').count()==len(expected)
        page.locator('#detail-dialog [data-save]').click()
        expect(page.locator('#saved-count')).to_have_text('1')
        with page.expect_download() as downloaded:
            page.locator('[data-calendar]').click()
        raw=Path(downloaded.value.path()).read_bytes()
        assert b'BEGIN:VCALENDAR' in raw and b'UID:' in raw and b'1995-04-15' not in raw
        assert page.request.get(base+'/api/housing-document/'+seoul['id']).body().startswith(b'PK')
        page.keyboard.press('Escape')
        page.locator('#profile-open-button').click()
        page.locator('#step-next').click();page.locator('#step-next').click()
        page.locator('#profile-form [name=deposit_budget]').fill('30000')
        with page.expect_response('**/api/match'):
            page.locator('#match-button').click()
        page.evaluate('id=>openDetail(id)',seoul['id'])
        page.locator('#unit-budget-only').check()
        assert page.locator('.housing-table tbody tr').count()==sum(u['deposit']<=300000000 for u in seoul['housing_units'])
        page.locator('#unit-query').scroll_into_view_if_needed()
        page.screenshot(path=str(OUT/'housing-desktop.png'))
        page.keyboard.press('Escape')
        page.locator('#budget-filter').select_option('within')
        assert page.locator('.notice-card').count()>0
        page.locator('#budget-filter').select_option('all')
        for index in range(3):page.locator('#cards [data-compare]').nth(index).click()
        page.locator('#cards [data-compare]').nth(3).click()
        expect(page.locator('#compare-count')).to_have_text('3')
        page.locator('#compare-open').click()
        assert page.locator('.compare-table thead th').count()==4
        page.screenshot(path=str(OUT/'compare-desktop.png'))
        page.keyboard.press('Escape')
        page.reload();page.locator('.notice-card').first.wait_for()
        expect(page.locator('#saved-count')).to_have_text('1')
        assert page.locator('#profile-form [name=birth_date]').input_value()==''
        assert page.locator('#profile-form [name=deposit_budget]').input_value()==''
        assert json.loads(page.evaluate("localStorage.getItem('zipfit:saved:v1')"))==[seoul['id']]
        page.locator('#saved-only').check()
        expect(page.locator('#result-count')).to_have_text('1')
        page.locator('#saved-only').uncheck()
        for state in ('open','upcoming','unknown'):
            page.locator('#schedule-filter').select_option(state)
            assert all(n==state for n in page.locator('.notice-card .schedule-label').evaluate_all("els=>els.map(el=>el.classList[1])"))
        page.locator('#schedule-filter').select_option('all')
        page.locator('#coverage-open').click()
        expect(page.locator('#coverage-content')).to_contain_text('수집 누락 점검')
        page.keyboard.press('Escape')
        for width in (390,360,768):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.locator('#quick-open').click()
            assert page.evaluate("document.querySelector('#quick-dialog').scrollWidth<=document.querySelector('#quick-dialog').clientWidth")
            page.keyboard.press('Escape')
            page.evaluate('id=>openDetail(id)',seoul['id'])
            page.locator('#unit-query').scroll_into_view_if_needed()
            assert page.evaluate("document.querySelector('#detail-dialog').scrollWidth<=document.querySelector('#detail-dialog').clientWidth")
            if width==390:page.screenshot(path=str(OUT/'housing-mobile.png'))
            page.keyboard.press('Escape')
            for index in range(2):page.locator('#cards [data-compare]').nth(index).click()
            page.locator('#compare-open').click()
            assert page.evaluate("document.querySelector('#compare-dialog').scrollWidth<=document.querySelector('#compare-dialog').clientWidth")
            if width==390:page.screenshot(path=str(OUT/'compare-mobile.png'))
            page.keyboard.press('Escape');page.locator('#compare-clear').click()
        for script in ("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Blocked','SecurityError')}})", "localStorage.setItem('zipfit:saved:v1','invalid JSON')", "localStorage.setItem('zipfit:saved:v1',JSON.stringify(['missing-id',{},null]))"):
            isolated=browser.new_context();isolated.add_init_script(script)
            tab=isolated.new_page();tab.on('pageerror',lambda e:errors.append(str(e)))
            tab.goto(base);tab.locator('.notice-card').first.wait_for()
            tab.locator('[data-save]').first.click()
            assert '개인정보' in tab.locator('#saved-help').inner_text() or '이번 방문' in tab.locator('#saved-help').inner_text()
            isolated.close()
        assert not errors,errors
        browser.close()
    print(json.dumps({'checks':'quick and missing-field forms, real housing rows and budgets, calendar and XLSX downloads, compare limit, saved IDs/privacy, schedule filters, coverage, storage failures, mobile dialogs','console_errors':errors},ensure_ascii=False))


if __name__=='__main__':main()
