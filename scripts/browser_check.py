"""Exercise the MVP in installed Chrome, including the mobile layout."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tmp/screenshots"
OUT.mkdir(parents=True,exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel="chrome",headless=True)
        page=browser.new_page(viewport={"width":1440,"height":1050},device_scale_factor=1)
        page.on("pageerror",lambda err:errors.append(str(err)))
        page.goto(base_url + "/")
        page.locator(".notice-card").first.wait_for()
        page.evaluate("document.fonts.ready")
        assert page.evaluate("document.fonts.check('16px Pretendard')")
        assert page.locator(".notice-card").count()==18
        page.screenshot(path=str(OUT/"desktop.png"),full_page=False)
        initial = page.request.get(base_url + "/api/notices").json()
        for reason in ("needs_input", "unreviewed", "stale"):
            expected = [n for n in initial["notices"] if n["kind"] == "recruitment" and n["schedule"]["state"] not in ("closed", "superseded") and n["evaluation"]["unknown_reason"] == reason]
            page.locator("#eligibility-filter").select_option(reason)
            expect(page.locator("#result-count")).to_have_text(str(len(expected)))
        sh_initial = next(n for n in initial["notices"] if n.get("rule_model") == "sh_newlywed_20260930")
        if not sh_initial["evaluation"]["version_stale"]:
            page.locator("#eligibility-filter").select_option("needs_input")
            page.locator('button.card-title-button[data-detail="SH:GS0401:310653"]').click()
            page.screenshot(path=str(OUT/"missing-inputs.png"))
            page.locator('.missing-inputs [data-profile-field="household_size"]').click()
            expect(page.locator("#detail-dialog")).not_to_be_visible()
            expect(page.locator(".profile-step[data-step='2']")).to_be_visible()
            expect(page.locator("[name='household_size']")).to_be_focused()
            expect(page.locator("[name='household_size']")).to_be_visible()
            page.keyboard.press("Escape")
        page.locator("#eligibility-filter").select_option("all")
        page.locator("#show-closed").check()
        page.locator("#search").fill("2026년 2차 청년안심주택")
        page.locator('button.card-title-button[data-detail="SEOUL_YOUTH:BMSR00015:6624"]').click()
        expect(page.locator('#detail-dialog a[href*="seq=309925"]')).to_have_text("정정 공고로 이동 ↗")
        expect(page.locator("#detail-dialog .schedule-label")).to_have_text("정정본 있음")
        page.keyboard.press("Escape")
        page.locator("#show-closed").uncheck()
        page.locator("#search").fill("")
        page.get_by_role("button",name="예시 조건으로 둘러보기",exact=True).click()
        expect(page.locator("#profile-dialog")).to_be_visible()
        expect(page.locator("[data-marriage='married']")).to_have_attribute("aria-pressed","true")
        page.screenshot(path=str(OUT/"profile-desktop.png"))
        page.get_by_role("button",name="다음",exact=True).click()
        page.locator("#step-back").click()
        assert page.locator("[name='birth_date']").input_value()=="1995-04-15"
        page.get_by_role("button",name="다음",exact=True).click()
        page.get_by_role("button",name="다음",exact=True).click()
        with page.expect_response("**/api/match") as matching:
            page.locator("#match-button").click()
        evaluated=next(n["evaluation"] for n in matching.value.json()["notices"] if n.get("rule_model")=="songpa_20260922")
        sh_evaluated=next(n["evaluation"] for n in matching.value.json()["notices"] if n.get("rule_model")=="sh_newlywed_20260930")
        assert sh_evaluated["status"] == ("unknown" if sh_evaluated["version_stale"] else "match")
        expect(page.locator("#profile-dialog")).not_to_be_visible()
        expect(page.locator("#profile-summary-title")).to_have_text("내 조건을 확인했어요")
        page.locator("#search").fill("송파해링턴")
        assert page.locator(".notice-card").count()==1
        assert evaluated["label"] in page.locator(".notice-card").inner_text()
        page.get_by_role("button",name="자세히 보기",exact=True).click()
        dialog=page.locator("#detail-dialog")
        assert dialog.is_visible()
        assert "신혼부부 일반공급" in dialog.inner_text()
        assert ("추가 확인 필요" if evaluated["version_stale"] else "기본조건 불일치") in dialog.inner_text()
        assert "7,000만원" in dialog.inner_text()
        assert dialog.locator("a[href*='#page=']").count()>0
        page.screenshot(path=str(OUT/"detail.png"))
        page.keyboard.press("Escape")
        page.locator("#search").fill("서면 지원")
        page.get_by_role("button",name="자세히 보기",exact=True).click()
        assert "매일 09:00~17:30" in dialog.inner_text()
        assert "신혼부부 일반공급" in dialog.inner_text()
        assert dialog.locator("a[href$='#page=2']").count() > 0
        assert "본문·첨부 재확인" in dialog.inner_text()
        assert page.evaluate("document.querySelector('#detail-dialog').scrollWidth <= document.querySelector('#detail-dialog').clientWidth")
        page.screenshot(path=str(OUT/"private-detail.png"))
        page.keyboard.press("Escape")
        page.locator("#search").fill("<script>alert(1)</script>")
        assert page.get_by_text("현재 필터에 맞는 공고가 없어요.").is_visible()
        page.get_by_role("button",name="필터 초기화").click()
        page.locator("[data-provider='GH']").click()
        assert all("GH" in t for t in page.locator("#cards .provider-label").all_text_contents())
        page.get_by_role("button",name="수집 현황",exact=True).click()
        assert page.locator("#coverage-dialog").is_visible()
        page.keyboard.press("Escape")
        page.reload();page.locator(".notice-card").first.wait_for()
        assert page.locator("[name='birth_date']").input_value()==""
        page.set_viewport_size({"width":390,"height":844})
        page.screenshot(path=str(OUT/"mobile.png"))
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile horizontal overflow"
        page.locator("#results").evaluate("el => el.scrollIntoView({block: 'start'})")
        page.screenshot(path=str(OUT/"mobile-results.png"))
        page.get_by_role("button",name="자세히 보기",exact=True).first.click()
        assert page.locator("#detail-dialog").is_visible()
        assert page.evaluate("document.querySelector('#detail-dialog').scrollWidth <= document.querySelector('#detail-dialog').clientWidth"), "Dialog horizontal overflow"
        page.keyboard.press("Escape")
        page.locator("#profile-open-button").click()
        assert page.locator("#profile-dialog").bounding_box()["width"]==390, "Mobile bottom sheet must fill the screen width"
        page.screenshot(path=str(OUT/"profile-mobile.png"))
        page.locator("[name='birth_date']").fill("1997-01-15")
        page.locator("[data-marriage='planned']").click()
        expect(page.locator("#planned-field")).to_be_visible()
        page.locator("#step-next").click()
        expect(page.locator("#couple-field")).to_be_visible()
        page.locator("[name='car_mode']").select_option("simple")
        expect(page.locator("#car-value-field")).to_be_visible()
        page.locator("[name='car_value']").fill("-1")
        page.locator("#step-next").click()
        expect(page.locator(".profile-step[data-step='1']")).to_be_visible()
        page.locator("[name='car_mode']").select_option("none")
        page.locator("#step-next").click()
        expect(page.locator(".profile-step[data-step='2']")).to_be_visible()
        page.locator("#sh-extra-fields summary").click()
        expect(page.locator("[name='dual_income']")).to_be_visible()
        assert page.evaluate("document.querySelector('#profile-dialog').scrollWidth <= document.querySelector('#profile-dialog').clientWidth"), "SH extra inputs overflow"
        page.locator("[name='sh_newborn']").select_option("yes")
        page.locator("[name='sh_asset_children']").select_option("none")
        with page.expect_response("**/api/match") as invalid_family:
            page.locator("#match-button").click()
        assert invalid_family.value.status==422
        expect(page.locator("#form-error")).to_be_visible()
        page.locator("[name='sh_asset_children']").select_option("one")
        page.locator("[name='dual_income']").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT/"sh-inputs-mobile.png"))
        with page.expect_response("**/api/match") as mobile_matching:
            page.locator("#match-button").click()
        assert mobile_matching.value.status==200
        expect(page.locator("#profile-dialog")).not_to_be_visible()
        page.locator("#profile-open-button").click()
        page.locator("#reset-button").click()
        expect(page.locator("#profile-open-button")).to_have_text("내 조건 입력하기")
        assert page.locator("[name='birth_date']").input_value()==""
        page.keyboard.press("Escape")
        for width in (360,768,1024):
            page.set_viewport_size({"width":width,"height":900})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"),f"Overflow at {width}px"
            page.locator("#profile-open-button").click()
            assert page.evaluate("document.querySelector('#profile-dialog').scrollWidth <= document.querySelector('#profile-dialog').clientWidth"),f"Profile overflow at {width}px"
            page.keyboard.press("Escape")
        assert not errors, errors
        browser.close()
    print(json.dumps({"browser":"Chrome headless","desktop":"1440x1050","mobile":"390x844","additional_widths":[360,768,1024],"console_errors":errors,"checks":"three-step form, missing-input jump and focus, unknown reason filters, SH comparison and contradictory family input, back navigation, field visibility, invalid input, conditional fields, example matching, track alternatives, rent pairs, source links, dialogs, reset, local font, overflow","screenshots":str(OUT)},ensure_ascii=False))


if __name__ == "__main__":main()
