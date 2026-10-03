"use strict";
const savedKey = "zipfit:saved:v1";
let savedIds = new Set(), compareIds = new Set(), storageAvailable = true, activeNoticeId = null;
try {
  const raw = localStorage.getItem(savedKey);
  const values = raw && raw.length <= 50000 ? JSON.parse(raw) : [];
  if (Array.isArray(values)) savedIds = new Set(values.filter(v => typeof v === "string" && v.length < 200).slice(0, 200));
} catch { storageAvailable = false; }

function savedControls(n) {
  return `<div class="notice-tools"><button type="button" class="small-button" data-save="${e(n.id)}" aria-pressed="${savedIds.has(n.id)}" aria-label="${e(n.title)} ${savedIds.has(n.id) ? '찜 해제' : '찜하기'}">${savedIds.has(n.id) ? '♥ 찜한 공고' : '♡ 찜하기'}</button><button type="button" class="small-button" data-compare="${e(n.id)}" aria-pressed="${compareIds.has(n.id)}">${compareIds.has(n.id) ? '비교 선택됨' : '비교 담기'}</button></div>`;
}

function updateSavedUI() {
  $("#saved-count").textContent = savedIds.size;
  $("#compare-count").textContent = compareIds.size;
  $("#compare-bar").hidden = compareIds.size === 0;
  $("#compare-open").disabled = compareIds.size < 2;
  $("#saved-help").textContent = storageAvailable ? "찜은 이 브라우저에 공고 번호만 저장해요. 개인정보는 저장하지 않아요." : "브라우저 저장을 사용할 수 없어 이번 방문 동안만 찜을 유지해요.";
  const unavailable = data ? [...savedIds].filter(id=>!data.notices.some(n=>n.id===id)).length : 0;
  if (unavailable) $("#saved-help").textContent += ` 저장한 공고 중 ${unavailable}건은 현재 자료에서 찾을 수 없어요.`;
}

function coverageExtras() {
  const d=data.discovery, s=data.schedule_refresh;
  return `<section class="detail-section"><h3>수집 누락 점검</h3>${d ? `<p>최근 확대 탐색 ${koreaTime(d.checked_at)}<br>이번 범위에서 확인 ${d.found_ids}건 · 신규 발견 ${d.new_ids}건<br>이번 범위에서 재발견하지 못한 진행·일정 미확인 후보 ${(d.unseen_active_ids || []).length}건</p><ul>${d.sources.map(s=>`<li>${e(providerNames[s.provider])}: 경로별 최대 ${s.max_pages_per_lane}페이지${s.lookback_days ? ` · 최근 ${s.lookback_days}일` : ''} · ${s.records}건${s.errors.length ? ' · 일부 수집 실패' : ''}</li>`).join('')}</ul><p>${e(d.scope)} 목록에서 찾지 못한 기존 공고도 보관하며, 삭제나 종료로 추정하지 않아요.</p>` : '<p>확대 탐색 결과가 아직 없어요.</p>'}<p>최근 목록은 약 6시간 간격, 확대 탐색은 주 1회 실행을 시도해요. 예약 실행은 지연될 수 있어요.</p>${s ? `<p>LH 일정 재확인 ${koreaTime(s.checked_at)}: ${s.attempted}건 중 ${s.extracted}건 추출 · ${s.errors}건 재확인 필요. 확인된 공급 유형별 접수 기간만 표시하며 서류·발표 일정은 제외해요.</p>` : ''}</section>`;
}

function withinBudget(o) {
  return (profile.deposit_budget == null || o.deposit <= profile.deposit_budget) && (profile.monthly_rent_budget == null || o.monthly_rent <= profile.monthly_rent_budget);
}

function noticePrices(n) {
  if (n.evaluation.version_stale) return [];
  return [...(n.housing_units || []), ...n.evaluation.rent_options.filter(o => o.track_status !== "mismatch")];
}

function openCompare() {
  const rows = data.notices.filter(n => compareIds.has(n.id));
  if (rows.length < 2) return;
  const cells = fn => rows.map(n => `<td>${fn(n)}</td>`).join("");
  const price = n => {
    const o = noticePrices(n).filter(withinBudget).sort((a,b) => a.deposit-b.deposit)[0];
    return o ? `보증금 ${money(o.deposit)}<br>월세 ${money(o.monthly_rent)}<br><small>${e(o.address || o.unit || '')} ${o.area}㎡ · 같은 조합 예시</small>` : "금액 미확인 또는 입력 예산에 맞는 조합 없음";
  };
  $("#compare-content").innerHTML = `<h2 id="compare-title" tabindex="-1">관심 공고 비교</h2><p>금액은 한 가지 조합의 예시예요. 관리비·보증료는 별도이며 최종 자격은 원문을 확인해 주세요.</p><p class="scroll-hint">표를 좌우로 넘기면 다른 공고를 볼 수 있어요 →</p><div class="table-scroll" tabindex="0" aria-label="공고 비교표, 좌우로 이동"><table class="compare-table"><thead><tr><th scope="col">항목</th>${rows.map(n=>`<th scope="col">${e(n.title)}</th>`).join('')}</tr></thead><tbody><tr><th scope="row">기관 / 지역</th>${cells(n=>`${e(providerNames[n.provider])}<br>${e(n.region)}`)}</tr><tr><th scope="row">신청 기간</th>${cells(n=>`${e(n.schedule.label)}<br>${e(scheduleText(n))}`)}</tr><tr><th scope="row">내 조건</th>${cells(n=>`${statusBadge(n.evaluation)}<p>${n.evaluation.missing_fields.map(f=>e(f.label)).join(' · ')}</p>`)}</tr><tr><th scope="row">보증금 / 월세</th>${cells(price)}</tr><tr><th scope="row">확인하기</th>${cells(n=>`<button class="text-button" data-compare-detail="${e(n.id)}">상세 보기</button> · <a href="${safeURL(n.url)}" target="_blank" rel="noopener noreferrer">공식 원문 ↗</a>`)}</tr></tbody></table></div>`;
  $("#compare-dialog").showModal();
  $("#compare-title").focus({preventScroll:true});$("#compare-dialog").scrollTop=0;
}

function extraDetail(n) {
  const windows = n.application_windows || [];
  const canCalendar = ["open", "upcoming"].includes(n.schedule.state) && !n.evaluation.version_stale && (windows.length || n.application_start && n.application_end);
  const missing = n.evaluation.missing_fields || [];
  return `<section class="detail-section">${savedControls(n)}${canCalendar ? `<button class="secondary-button calendar-button" data-calendar="${e(n.id)}">캘린더에 신청 일정 저장</button><p class="field-help">ICS 파일을 개인 캘린더로 가져올 수 있어요. 저장 후 공고 변경은 자동 반영되지 않아요.</p>` : ''}${missing.length ? `<button class="primary-button" data-needed="${e(n.id)}">이 공고에 필요한 정보 ${missing.length}개 입력</button>` : ''}${windows.length ? `<h3>공급 유형별 접수 기간</h3>${windows.map(w=>`<p><strong>${e(w.label)}</strong><br>${e(w.start)} ~ ${e(w.end)}<br>${e(w.hours_note || '')}</p>`).join('')}<p class="field-help">기관 상세 확인 ${koreaTime(n.schedule_source?.checked_at)} · 서류제출·발표 일정과 구분한 신청 기간이에요.</p>` : ''}</section>${n.housing_units?.length ? `<section class="detail-section"><h3>${n.evaluation.version_stale ? '보관 당시의' : '공급목록의'} 주택 ${n.housing_units.length}호</h3><p>선택한 주택의 주소·전용면적·보증금을 함께 확인해요. 실제 공급 여부와 동호수 배정은 공고 절차를 따릅니다.</p><label>동네·주소·주택명<input id="unit-query" type="search" placeholder="예: 고양시, 백석동" autocomplete="off"></label><div class="form-row unit-area"><label>최소 전용면적 ㎡<input id="unit-area-min" type="number" min="0" step="any" inputmode="decimal" placeholder="제한 없음"></label><label>최대 전용면적 ㎡<input id="unit-area-max" type="number" min="0" step="any" inputmode="decimal" placeholder="제한 없음"></label></div><label class="inline-check"><input id="unit-budget-only" type="checkbox">입력한 예산에 맞는 주택만</label><p id="unit-budget-help" class="field-help"></p><div id="unit-results"></div><p><a href="/api/housing-document/${encodeURIComponent(n.id)}">검토한 공급목록 엑셀 다운로드 ↗</a> · <a href="${safeURL(n.housing_document.url)}" target="_blank" rel="noopener noreferrer">최신 공급목록 ↗</a></p><p class="field-help">전세 월세는 0원, 관리비는 별도예요. 금액은 계약 시 변경될 수 있어요.</p></section>` : ''}`;
}

function renderUnits() {
  const n = data?.notices.find(n=>n.id===activeNoticeId);
  if (!n?.housing_units?.length || !$("#unit-results")) return;
  const query = $("#unit-query").value.trim().toLowerCase();
  const budget = $("#unit-budget-only").checked;
  const hasBudget = profile.deposit_budget != null || profile.monthly_rent_budget != null;
  const minInput=$("#unit-area-min"), maxInput=$("#unit-area-max");
  const minArea=minInput.value==='' ? 0 : Number(minInput.value), maxArea=maxInput.value==='' ? Infinity : Number(maxInput.value);
  if (!minInput.validity.valid || !maxInput.validity.valid || minArea > maxArea) {
    $("#unit-results").innerHTML='<p role="status">면적은 0 이상의 숫자로, 최소 면적이 최대 면적보다 작거나 같게 입력해 주세요.</p>';return;
  }
  const rows = n.housing_units.filter(u => u.area >= minArea && u.area <= maxArea && `${u.address} ${u.name}`.toLowerCase().includes(query) && (!budget || !hasBudget || withinBudget(u)));
  $("#unit-budget-help").textContent = hasBudget ? "내 조건에 입력한 보증금·월세 상한을 함께 적용해요. 자격 판정과는 별개예요." : "예산을 입력하지 않았어요. 내 조건에서 보증금·월세 상한을 정하면 비교할 수 있어요.";
  $("#unit-results").innerHTML = `<p>${rows.length}호</p>${rows.length ? `<div class="table-scroll"><table class="rent-table housing-table"><thead><tr><th>주소 / 주택</th><th>전용면적</th><th>보증금 / 월세</th><th>원문 위치</th></tr></thead><tbody>${rows.map(u=>`<tr><td>${e(u.address)}<br>${e(u.name)} ${e(u.building)}동 ${e(u.room)}호</td><td>${u.area}㎡</td><td>${money(u.deposit)}<br>${money(u.monthly_rent)}</td><td>${e(u.source_sheet)}<br>${u.source_row}행</td></tr>`).join('')}</tbody></table></div>` : '<p>이 주소·예산 조건에 맞는 주택이 없어요. 검색어나 예산을 조정해 주세요.</p>'}`;
}

function openQuick() {
  const f = $("#quick-form");
  for (const input of [...f.elements]) if (input.name && form.elements[input.name]) {
    const original = form.elements[input.name];
    if (input.type === "checkbox") input.checked = original.checked;
    else input.value = original.value;
  }
  $("#quick-error").hidden = true;
  $("#quick-dialog").showModal();
}

function openNeeded(n) {
  const container = $("#needed-fields");container.replaceChildren();
  for (const item of n.evaluation.missing_fields) {
    const original = form.elements[item.field];
    if (!original) continue;
    const label = document.createElement("label");label.textContent=item.label;
    const input = original.cloneNode(true);input.removeAttribute('id');input.classList.remove('sr-only');input.removeAttribute('tabindex');
    if (input.type === "checkbox") input.checked=original.checked; else input.value=original.value;
    label.append(input);container.append(label);
    const help = original.closest('label')?.nextElementSibling;
    if (help?.classList.contains('field-help')) container.append(help.cloneNode(true));
    if (moneyFields.includes(item.field)) { const hint=document.createElement('small');hint.textContent='입력 단위: 만원';label.append(hint); }
  }
  $("#needed-context").textContent=n.title+' · 공고일 '+n.reference_date+' 기준으로 확인해 주세요.';
  $("#needed-form").dataset.noticeId=n.id;
  $("#needed-error").hidden=true;
  $("#detail-dialog").close();$("#needed-dialog").showModal();
}

document.addEventListener("click", async event => {
  const save = event.target.closest('[data-save]');
  if (save) {
    const id=save.dataset.save;
    if (savedIds.has(id)) savedIds.delete(id);
    else if (savedIds.size < 200) savedIds.add(id);
    else { toast('찜은 최대 200개까지 저장할 수 있어요.');return; }
    try { localStorage.setItem(savedKey,JSON.stringify([...savedIds]));storageAvailable=true; } catch {storageAvailable=false;}
    render();if($("#detail-dialog").open) { $("#detail-dialog").close();openDetail(activeNoticeId); }
    updateSavedUI();
  }
  const compare=event.target.closest('[data-compare]');
  if(compare) {
    const id=compare.dataset.compare;
    if(compareIds.has(id))compareIds.delete(id);else if(compareIds.size<3)compareIds.add(id);else {toast('한 번에 3개까지 비교할 수 있어요.');return;}
    render();updateSavedUI();
    $$(`[data-compare]`).forEach(b=>{b.setAttribute('aria-pressed',String(compareIds.has(b.dataset.compare)));b.textContent=compareIds.has(b.dataset.compare)?'비교 선택됨':'비교 담기';});
  }
  const needed=event.target.closest('[data-needed]');if(needed)openNeeded(data.notices.find(n=>n.id===needed.dataset.needed));
  const detail=event.target.closest('[data-compare-detail]');if(detail){$("#compare-dialog").close();openDetail(detail.dataset.compareDetail);}
  const calendar=event.target.closest('[data-calendar]');
  if(calendar) {
    calendar.disabled=true;
    try {
      const r=await fetch('/api/calendar/'+encodeURIComponent(calendar.dataset.calendar));
      if(!r.ok)throw new Error((await r.json()).detail || '일정을 다시 확인해 주세요.');
      const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download='zipfit-application.ics';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch(error){toast(error.message);}finally{calendar.disabled=false;}
  }
});
document.addEventListener('input',event=>{if(['unit-query','unit-area-min','unit-area-max'].includes(event.target.id))renderUnits();});
document.addEventListener('change',event=>{if(event.target.id==='unit-budget-only')renderUnits();});
document.addEventListener('DOMContentLoaded',()=>{
  $("#quick-open").addEventListener('click',openQuick);
  $("#quick-full").addEventListener('click',()=>{$('#quick-dialog').close();openProfile();});
  $("#compare-open").addEventListener('click',openCompare);
  $("#compare-clear").addEventListener('click',()=>{compareIds.clear();render();updateSavedUI();});
  $("#saved-open").addEventListener('click',()=>{$('#saved-only').checked=!$('#saved-only').checked;render();$('#results').scrollIntoView({block:'start'});});
  for (const id of ['quick','needed']) {
    $('#'+id+'-form').addEventListener('submit',async event=>{
      event.preventDefault();const f=event.currentTarget;
      for(const input of [...f.elements])if(input.name&&form.elements[input.name]) {
        const original=form.elements[input.name];if(input.type==='checkbox')original.checked=input.checked;else original.value=input.value;
      }
      conditionalFields();const button=f.querySelector('[type=submit]');button.disabled=true;
      const ok=await load(readProfile());button.disabled=false;
      if(ok){$('#'+id+'-dialog').close();if(id==='needed')openDetail(f.dataset.noticeId);}
      else{$('#'+id+'-error').textContent=$('#form-error').textContent;$('#'+id+'-error').hidden=false;}
    });
  }
  $('#needed-dialog').addEventListener('close',()=>$('#needed-fields').replaceChildren());
});
