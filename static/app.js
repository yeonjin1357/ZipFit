"use strict";
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const form = $("#profile-form");
const providerNames = { LH: "LH", SH: "SH", GH: "GH", SEOUL_YOUTH: "청년안심주택", APPLYHOME: "청약홈" };
const regions = ["서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"];
const regionAliases = { 충북: "충청북", 충남: "충청남", 경북: "경상북", 경남: "경상남", 전북: "전라북", 전남: "전라남" };
let data = null, provider = "", limit = 18, matched = false, profile = {}, sequence = 0, profileStep = 0, toastTimer;
const moneyFields = ["car_value", "gh_car_value", "monthly_income_self", "monthly_income_household", "monthly_income_parents", "assets_self", "assets_household", "deposit_budget", "monthly_rent_budget"];
const escapeHTML = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const e = escapeHTML;
const money = (n) => `${(n / 10000).toLocaleString("ko-KR", { maximumFractionDigits: 4 })}만원`;
const shortDate = (v) => v ? v.slice(0, 10).replaceAll("-", ".") : "확인 필요";
const koreaTime = (v) => v ? new Date(v).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "미확인";
const safeURL = (v) => { try { const u = new URL(v); return u.protocol === "https:" ? e(u.href) : "#"; } catch { return "#"; } };
const pdfURL = (n, page) => `/api/documents/${encodeURIComponent(n.id)}${page ? `#page=${page}` : ""}`;
const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#${name}"/></svg>`;
const statusBadge = (ev) => `<span class="status-badge ${e(ev.status)}">${icon(ev.status === "match" ? "check" : "info")}${e(ev.label || {match:"기본조건 일치",conditional:"조건부 검토",unknown:"추가 확인 필요",mismatch:"기본조건 불일치"}[ev.status])}</span>`;

for (const select of $$(".region-options")) for (const region of regions) select.add(new Option(region, region));
form.elements.birth_date.max = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Seoul" });

function conditionalFields() {
  $("#marriage-date-field").hidden = form.elements.marriage.value !== "married";
  $("#planned-field").hidden = $("#couple-field").hidden = form.elements.marriage.value !== "planned";
  $("#car-value-field").hidden = form.elements.car_mode.value !== "simple";
  for (const button of $$("[data-marriage]")) button.setAttribute("aria-pressed", String(button.dataset.marriage === form.elements.marriage.value));
}
form.addEventListener("change", conditionalFields);

const stepCopy = [
  ["먼저, 기본 정보를<br>알려주세요", "모르는 항목은 비워둬도 괜찮아요."],
  ["지금의 주거 조건을<br>확인해볼게요", "공고마다 무주택을 확인하는 가족 범위가 달라요."],
  ["소득과 예산을 알려주면<br>더 자세히 비교할 수 있어요", "선택 항목이에요. 아는 정보만 입력해 주세요."]
];

function setStep(step, focus = true) {
  profileStep = Math.max(0, Math.min(2, step));
  for (const panel of $$(".profile-step")) panel.hidden = Number(panel.dataset.step) !== profileStep;
  for (const item of $$("[data-step-indicator]")) {
    const active = Number(item.dataset.stepIndicator) === profileStep;
    item.classList.toggle("current", active);
    if (active) item.setAttribute("aria-current", "step"); else item.removeAttribute("aria-current");
  }
  $("#profile-title").innerHTML = stepCopy[profileStep][0];
  $("#profile-description").textContent = stepCopy[profileStep][1];
  $("#step-back").hidden = profileStep === 0;
  $("#step-next").hidden = profileStep === 2;
  $("#match-button").hidden = profileStep !== 2;
  $("#profile-scroll").scrollTop = 0;
  if (focus) $("#profile-title").focus({ preventScroll: true });
}

function validateStep(all = false) {
  const inputs = all ? $$('input, select', form) : $$(`.profile-step[data-step="${profileStep}"] input, .profile-step[data-step="${profileStep}"] select`, form);
  const invalid = inputs.find(input => !input.validity.valid && !input.closest("label[hidden]"));
  if (!invalid) return true;
  setStep(Number(invalid.closest(".profile-step").dataset.step));
  const details = invalid.closest("details"); if (details) details.open = true;
  invalid.reportValidity();
  return false;
}

function openProfile(step = 0) {
  $("#form-error").hidden = true;
  conditionalFields();
  $("#profile-dialog").showModal();
  setStep(step);
}

function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message; $("#toast").hidden = false;
  toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 3500);
}

function updateSummary() {
  const title = $("#profile-summary-title"), copy = $("#profile-summary-copy"), values = $("#profile-summary-values");
  title.innerHTML = matched ? "내 조건을 확인했어요" : "내 조건에 맞는 공고를 <br>함께 찾아볼까요?";
  copy.innerHTML = matched ? "조건이 바뀌면 언제든 다시 비교해보세요." : "나이, 소득, 무주택 여부를 입력하면 <br>검토한 공고의 조건을 비교해드려요.";
  values.hidden = !matched;
  if (matched) {
    const marriage = { single: "미혼", planned: "결혼 예정", married: "혼인 중", unknown: "미입력" }[profile.marriage || "unknown"];
    const items = [["혼인 상태", marriage], ["거주지", profile.residence || "미입력"], ["희망 보증금", profile.deposit_budget == null ? "상한 없음" : `${money(profile.deposit_budget)}까지`]];
    values.innerHTML = items.map(([label,value]) => `<div><dt>${label}</dt><dd>${e(value)}</dd></div>`).join("");
  } else values.innerHTML = "";
  $("#profile-open-button").textContent = matched ? "내 조건 수정하기" : "내 조건 입력하기";
}

for (const button of $$("[data-profile-open]")) button.addEventListener("click", () => openProfile());
for (const button of $$("[data-marriage]")) button.addEventListener("click", () => {
  form.elements.marriage.value = form.elements.marriage.value === button.dataset.marriage ? "unknown" : button.dataset.marriage;
  conditionalFields();
});
$("#step-next").addEventListener("click", () => { if (validateStep()) setStep(profileStep + 1); });
$("#step-back").addEventListener("click", () => setStep(profileStep - 1));

function readProfile() {
  const out = {};
  for (const [key, value] of new FormData(form)) {
    if (key === "reference_confirmed") out[key] = true;
    else if (moneyFields.includes(key)) out[key] = value === "" ? null : Math.round(Number(value) * 10000);
    else if (key === "household_size") out[key] = value === "" ? null : Number(value);
    else if (key.endsWith("_date")) out[key] = value || null;
    else out[key] = value;
  }
  out.reference_confirmed = !!out.reference_confirmed;
  if (out.marriage !== "married") out.marriage_date = null;
  if (out.marriage !== "planned") { out.marriage_before_movein = "unknown"; out.couple_homeless = "unknown"; }
  if (out.car_mode !== "simple") out.car_value = null;
  return out;
}

async function load(payload) {
  const requestId = ++sequence;
  $("#match-button").disabled = true;
  $("#cards").setAttribute("aria-busy", "true");
  $("#form-error").hidden = true;
  try {
    const res = await fetch(payload ? "/api/match" : "/api/notices", payload ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: payload }) } : {});
    if (!res.ok) {
      const body = await res.json();
      const detail = typeof body.detail === "string" ? body.detail : body.detail?.map(d => d.msg).join(" / ");
      throw new Error(detail || "조건을 확인하지 못했어요. 입력값을 확인해 주세요.");
    }
    const result = await res.json();
    if (requestId !== sequence) return;
    data = result; profile = payload || {}; matched = !!payload; limit = 18;
    const c = data.coverage;
    $("#coverage-summary").textContent = `${c.source_posts}건의 원본 게시물을 모았어요.\n조건 비교는 ${c.reviewed_notices}개 공고 · ${c.reviewed_tracks}개 유형을 지원해요. 나머지는 추가 확인이 필요해요.`;
    updateSummary();
    render();
    return true;
  } catch (error) {
    if (requestId !== sequence) return;
    $("#form-error").textContent = error.message;
    $("#form-error").hidden = false;
    if ($("#profile-dialog").open) $("#form-error").scrollIntoView({ block: "nearest" });
    if (!data) $("#cards").innerHTML = `<div class="empty"><strong>공고를 불러오지 못했어요.</strong><p>잠시 후 다시 시도해 주세요.</p><button id="retry-load">다시 시도</button></div>`;
    else if (!$("#profile-dialog").open) toast(error.message);
    return false;
  } finally {
    if (requestId === sequence) { $("#match-button").disabled = false; $("#cards").setAttribute("aria-busy", "false"); }
  }
}

form.addEventListener("submit", async ev => {
  ev.preventDefault();
  if (profileStep < 2) { if (validateStep()) setStep(profileStep + 1); return; }
  if (!validateStep(true)) return;
  const success = await load(readProfile());
  if (success) {
    $("#profile-dialog").close();
    toast("입력한 조건으로 공고를 비교했어요");
    if (window.innerWidth < 801) $("#results").scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }
});
$("#example-button").addEventListener("click", () => {
  form.reset();
  const example = { birth_date: "1995-04-15", marriage: "married", marriage_date: "2024-05-01", marriage_total_within_7_years: "yes", korean: "yes", residence: "서울", self_homeless: "yes", household_homeless: "yes", occupants_homeless: "yes", car_mode: "none", monthly_income_household: "775", household_size: "2", assets_household: "15000", deposit_budget: "8000", monthly_rent_budget: "100", sh_newborn: "no", sh_single_parent: "no", dual_income: "yes", benefit_certificate: "no", sh_asset_children: "none" };
  for (const [key,value] of Object.entries(example)) form.elements[key].value = value;
  form.elements.reference_confirmed.checked = true;
  conditionalFields();
  $$(".input-details", form).forEach(el => el.open = true);
  $("#result-announcement").textContent = "예시 조건을 입력했어요. 혼인 중인 2인 가구, 부부 월소득 775만원입니다. 입력 내용을 확인한 뒤 비교해 주세요.";
  openProfile();
});
$("#reset-button").addEventListener("click", () => {
  form.reset(); conditionalFields(); setStep(0); resetFilters(); load();
});

function filtered() {
  const query = $("#search").value.trim().toLocaleLowerCase();
  const region = $("#region-filter").value;
  const eligibility = $("#eligibility-filter").value;
  const notices = data.notices.filter(n => {
    if ($("#saved-only").checked && !savedIds.has(n.id)) return false;
    if ($("#schedule-filter").value !== 'all' && $("#schedule-filter").value !== n.schedule.state) return false;
    const prices = noticePrices(n), budgetFilter = $("#budget-filter").value;
    if (budgetFilter === 'within' && !prices.some(withinBudget)) return false;
    if (budgetFilter === 'unknown' && prices.length) return false;
    if (provider && n.provider !== provider) return false;
    if (!$("#show-other").checked && n.kind !== "recruitment") return false;
    if (!$("#saved-only").checked && !$("#show-closed").checked && ["closed", "superseded"].includes(n.schedule.state)) return false;
    if (query && !`${n.title} ${n.region} ${n.housing_type} ${(n.housing_units || []).map(u=>u.address+' '+u.name).join(' ')}`.toLocaleLowerCase().includes(query)) return false;
    // Unknown location remains discoverable; it is not a proven mismatch.
    if (region && n.region !== "지역 확인 필요" && n.region !== "전국" && !n.region.includes(" 외") && !n.region.includes(region) && !n.region.includes(regionAliases[region] || region)) return false;
    if (eligibility === "possible" && !["match","conditional"].includes(n.evaluation.status)) return false;
    if (["unknown","mismatch"].includes(eligibility) && eligibility !== n.evaluation.status) return false;
    if (["needs_input","unreviewed","stale"].includes(eligibility) && eligibility !== n.evaluation.unknown_reason) return false;
    return true;
  });
  const sort = $("#sort").value;
  const rank = { match: 0, conditional: 1, unknown: 2, mismatch: 3 };
  return notices.sort((a,b) => {
    if (sort === "recommended") {
      const state = rank[a.evaluation.status] - rank[b.evaluation.status];
      if (state) return state;
      if (!!a.rule_model !== !!b.rule_model) return a.rule_model ? -1 : 1;
      if (a.schedule.state !== b.schedule.state) {
        const order = {open:0,upcoming:1,unknown:2,closed:3,superseded:4};
        return order[a.schedule.state] - order[b.schedule.state];
      }
    }
    if (sort === "closing") {
      const delta = (a.application_end || a.listed_closing_date || "9999").localeCompare(b.application_end || b.listed_closing_date || "9999");
      if (delta) return delta;
    }
    return (b.published_date || "").localeCompare(a.published_date || "") || a.id.localeCompare(b.id);
  });
}

function card(n) {
  const ev = n.evaluation;
  const option = noticePrices(n).filter(withinBudget).sort((a,b) => a.deposit-b.deposit)[0];
  const price = option ? `<div class="price-preview"><span>보증금 <strong>${money(option.deposit)}</strong></span><span>월세 <strong>${money(option.monthly_rent)}</strong></span><span class="dim">${option.area}㎡ · 한 가지 조합 예시</span></div>` : "";
  const providerIcon = ["LH", "SH", "GH"].includes(n.provider) ? e(n.provider) : icon(n.provider === "SEOUL_YOUTH" ? "home" : "building");
  const category = n.housing_type.replace("청년안심주택 · ", "");
  const scheduleLabel = n.schedule.label;
  return `<article class="notice-card ${n.rule_model ? "reviewed" : ""}">
    <div class="card-top"><div class="provider-identity"><span class="provider-icon ${e(n.provider)}" aria-hidden="true">${providerIcon}</span><div><span class="provider-label">${e(providerNames[n.provider])}</span><span class="notice-category">${e(category)}${n.rule_model ? " · 조건 비교 지원" : ""}</span></div></div><span class="schedule-label ${e(n.schedule.state)}">${e(scheduleLabel)}</span></div>
    <h3><button class="card-title-button" data-detail="${e(n.id)}">${e(n.title)}</button></h3>
    <div class="card-meta"><span>${e(n.region)}</span><span>공고 ${shortDate(n.published_date)}</span></div><p class="card-date">${e(scheduleText(n))}</p>${price}
    ${savedControls(n)}<div class="card-bottom">${statusBadge(ev)}<button class="card-action" data-detail="${e(n.id)}">자세히 보기${icon("chevron-right")}</button></div>
  </article>`;
}

function scheduleText(n) {
  if (n.schedule.changed) return "공고 정보가 변경됐어요. 최신 접수 일정을 확인해 주세요.";
  if (n.application_windows?.length) return n.application_windows.map(w=>`${w.label}: ${shortDate(w.start)} ~ ${shortDate(w.end)}`).join(' / ');
  if (n.application_text) return `신청 ${n.application_text}${n.schedule.date_only ? " · 접수 시간은 원문 확인" : ""}`;
  if (n.listed_application_date) return `목록에 기재된 신청일 ${shortDate(n.listed_application_date)} · 전체 기간 확인 필요`;
  if (n.listed_closing_date) return `목록 마감 ${shortDate(n.listed_closing_date)} · 전체 접수 일정 확인 필요`;
  return "신청 일정은 원문에서 확인해 주세요";
}

function render() {
  if (!data) return;
  const notices = filtered();
  $("#result-count").textContent = notices.length;
  $("#result-context").textContent = matched ? "입력한 기본조건을 비교한 결과예요. 최종 자격과 접수 일정은 원문을 확인해 주세요." : "조건을 입력하면 검토한 공고의 신청 조건을 비교할 수 있어요.";
  if ($("#region-filter").value) $("#result-context").textContent += " 지역 미확인·복수지역 공고는 누락을 줄이기 위해 함께 표시해요.";
  $("#cards").innerHTML = notices.length ? notices.slice(0, limit).map(card).join("") : `<div class="empty"><strong>현재 필터에 맞는 공고가 없어요.</strong><p>‘추가 확인 필요’ 공고도 살펴보세요.<br>희망 지역이나 기관 필터를 넓히면 더 많은 공고를 볼 수 있어요.</p><button id="clear-filters">필터 초기화</button></div>`;
  $("#load-more").hidden = notices.length <= limit;
  $("#result-announcement").textContent = `조건에 맞춰 표시한 공고 ${notices.length}건. ${Math.min(limit,notices.length)}건을 보여드려요.`;
  if ($("#saved-only").checked) $("#result-context").textContent += " 찜한 공고는 종료된 공고도 함께 보여요.";
  if ($("#budget-filter").value === 'within') $("#result-context").textContent += profile.deposit_budget == null && profile.monthly_rent_budget == null ? " 예산 미입력: 금액이 확인된 공고를 보여요. 내 조건에서 상한을 입력해 주세요." : " 같은 보증금·월세 조합을 기준으로 비교해요. 금액 미확인 공고는 제외했어요.";
  updateSavedUI();
}
function resetFilters() {
  $("#saved-only").checked=false; $("#schedule-filter").value='all'; $("#budget-filter").value='all';
  provider = ""; $("#search").value = ""; $("#region-filter").value = ""; $("#eligibility-filter").value = "all"; $("#show-closed").checked = false; $("#show-other").checked = false;
  for (const b of $$("[data-provider]")) { b.classList.toggle("selected", b.dataset.provider === ""); b.setAttribute("aria-pressed", String(b.dataset.provider === "")); }
  limit = 18; render();
}
for (const el of $$("#search, #region-filter, #eligibility-filter, #show-closed, #show-other, #sort, #saved-only, #schedule-filter, #budget-filter")) el.addEventListener(el.id === "search" ? "input" : "change", () => { limit = 18; render(); });
for (const b of $$("[data-provider]")) b.addEventListener("click", () => {
  provider = b.dataset.provider; limit = 18;
  for (const tab of $$("[data-provider]")) { const on = tab === b; tab.classList.toggle("selected",on); tab.setAttribute("aria-pressed",String(on)); } render();
});
$("#load-more").addEventListener("click", () => { limit += 18; render(); });

function openDetail(id) {
  const n = data.notices.find(n => n.id === id); if (!n) return;
  activeNoticeId = id;
  const ev = n.evaluation;
  const trackNames = Object.fromEntries(ev.tracks.map(t => [t.id,t.name]));
  const checks = ev.tracks.map(t => `<details class="track" ${t.status !== "mismatch" ? "open" : ""}><summary>${e(t.name)}${statusBadge(t)}</summary><div class="check-list">${t.checks.map(c => `<div class="check-row"><span class="check-icon ${e(c.state)}">${{pass:"✓",fail:"−",unknown:"?",conditional:"◇"}[c.state]}</span><div class="check-copy"><strong>${e(c.label)}</strong><p>${e(c.reason)}</p>${c.input_needed && !ev.version_stale ? `<button class="text-button field-link" data-profile-field="${e(c.field)}" type="button">이 정보 입력하기 →</button>` : ""}</div>${c.page && n.document ? `<a href="${pdfURL(n,c.page)}" target="_blank" rel="noopener noreferrer">PDF ${c.page}쪽 ↗</a>` : ""}</div>`).join("")}</div></details>`).join("");
  const options = ev.rent_options.filter(o => o.track_status !== "mismatch");
  const rentPages = [...new Set(options.map(o => o.page).filter(Boolean))];
  const budgetSet = profile.deposit_budget != null || profile.monthly_rent_budget != null;
  const prices = options.length ? `<div class="table-scroll"><table class="rent-table"><thead><tr><th>공급유형 / 면적</th><th>보증금</th><th>월세</th>${budgetSet ? "<th>예산</th>" : ""}</tr></thead><tbody>${options.map(o=>`<tr class="${!o.within_budget ? "over-budget" : ""}"><td>${e(trackNames[o.track])}<br><span class="dim">${o.unit ? e(o.unit) + " · " : ""}${o.area}㎡</span></td><td>${money(o.deposit)}</td><td>${money(o.monthly_rent)}</td>${budgetSet ? `<td>${o.within_budget ? "범위 내" : "예산 초과"}</td>` : ""}</tr>`).join("")}</tbody></table></div><p>보증금과 월세는 같은 행의 조합이에요. 관리비·보증료 별도. ${rentPages.map(p => `<a href="${pdfURL(n,p)}" target="_blank" rel="noopener noreferrer">공고문 ${p}쪽 ↗</a>`).join(" · ")}</p>` : `<p>${ev.rent_options.length ? "기본조건이 일치하는 공급 유형을 찾지 못했어요. 전체 금액은 원문에서 확인할 수 있어요." : (n.housing_units?.length ? "아래 공급목록에서 주택별 주소·면적·금액을 확인해 주세요." : "주택별 보증금·월세를 아직 구조화하지 않았어요. 원문과 공급주택 목록을 확인해 주세요.")}</p>`;
  const superseded = n.superseded_by ? data.notices.find(x=>x.id===n.superseded_by) : null;
  const correctionURL = superseded?.url || n.correction_url;
  const needed = ev.missing_fields?.length ? `<div class="missing-inputs"><strong>이 정보를 더 알려주면 비교할 수 있어요</strong><button type="button" class="primary-button" data-needed="${e(n.id)}">이 공고에 필요한 정보 ${ev.missing_fields.length}개 입력</button><div>${ev.missing_fields.map(f=>`<button type="button" data-profile-field="${e(f.field)}">${e(f.label)}${icon("chevron-right")}</button>`).join("")}</div></div>` : "";
  $("#detail-content").innerHTML = `<div class="detail-header"><div class="tags"><span class="provider-label">${e(providerNames[n.provider])}</span><span class="subtle-tag">${e(n.region)}</span><span class="schedule-label">${e(n.schedule.label)}</span></div><h2 id="detail-title" tabindex="-1">${e(n.title)}</h2><p>공고일 ${shortDate(n.published_date)} ${n.reference_date ? ` · 자격 판단 기준일 ${shortDate(n.reference_date)}` : ""}<br>${e(scheduleText(n))}</p></div>
    <div class="detail-links"><a href="${safeURL(n.url)}" target="_blank" rel="noopener noreferrer">공식 공고 확인 ↗</a>${n.document ? `<a href="${pdfURL(n)}" target="_blank" rel="noopener noreferrer">검토한 공고문 PDF ↗</a>` : ""}${correctionURL ? `<a href="${safeURL(correctionURL)}" target="_blank" rel="noopener noreferrer">정정 공고로 이동 ↗</a>` : ""}</div>
    <div class="detail-alert">${e(ev.scope)}${n.schedule.state === "closed" ? " 이 공고의 접수 기간은 종료됐어요." : ""}${ev.version_stale ? " 기존 판정은 보류하고 원문의 최신 버전 확인을 요청해요." : ""}</div>
    ${needed}<section class="detail-section"><h3>공급 유형별 조건 비교</h3>${checks || '<p>이 공고는 현재 목록 탐색만 지원해요. 자격 규칙을 검토 중이에요.</p>'}</section>
    <section class="detail-section"><h3>${ev.version_stale ? "검토 당시 보증금과 월세" : "보증금과 월세"}</h3>${ev.version_stale ? "<p>보관한 공고문 기준 금액이에요. 현재 금액은 최신 원문에서 확인해 주세요.</p>" : ""}${prices}</section>
    ${n.notes.length ? `<section class="detail-section"><h3>신청 전에 함께 확인해 주세요</h3><ul>${n.notes.map(t=>`<li>${e(t)}</li>`).join("")}</ul></section>` : ""}
    <section class="detail-section"><h3>이 정보의 출처</h3><p>목록 확인: ${koreaTime(n.observed_at)} (한국시간)<br>${n.rule_reviewed_at ? `기본조건 검토: ${koreaTime(n.rule_reviewed_at)}<br>` : ""}${n.source_verification ? `본문·첨부 재확인: ${koreaTime(n.source_verification.checked_at)} · ${e({unchanged:"검토본과 일치",changed:"변경 발견",error:"확인 실패",missing_baseline:"비교 기준 검토 필요"}[n.source_verification.state] || "확인 필요")}<br>` : ""}${n.document ? `PDF 보관본 확인: ${koreaTime(n.document.checked_at)}<br>쪽수는 PDF 파일의 첫 페이지부터 센 번호예요.<br>` : ""}공식 원문에 정정·취소가 있을 수 있어요. 신청 직전 최신 공고를 확인해 주세요.</p></section>`;
  $("#detail-content").insertAdjacentHTML('beforeend',extraDetail(n));
  renderUnits();
  $("#detail-dialog").showModal();
  $("#detail-title").focus({preventScroll:true});$("#detail-dialog").scrollTop=0;
}

function openCoverage() {
  if (!data) return;
  const c = data.coverage;
  $("#coverage-content").innerHTML = `<div class="detail-header"><h2 id="coverage-title">지금 어디까지 확인했나요?</h2><p>목록 수집과 자격 판정은 지원 범위가 달라요.</p></div><div class="detail-alert">원본 게시물 ${c.source_posts}건 · 모집 후보 ${c.recruitment_candidates}건<br>자동 기본조건 비교: ${c.reviewed_notices}개 공고 / ${c.reviewed_tracks}개 공급 유형</div>${data.sources.map(s=>`<div class="source-row"><div><strong>${e(s.label)}</strong><p>마지막 정상 수집 ${koreaTime(s.last_success)}<br>${e(s.scope)}${s.last_error ? `<br>최근 갱신 실패: ${e(s.last_error)}. 기존 자료를 유지해요.` : ""}</p></div><span class="source-count">${s.count}<small>건</small></span></div>`).join("")}${coverageExtras()}<section class="detail-section"><h3>현재 지원 범위</h3><ul><li>송파해링턴타워, LH 서울·경기북부·경기남부·제주 든든전세, SH 신혼·신생아 매입임대Ⅱ, 서면 지원 더뷰 드림아파트, GH Care Hub의 검토한 기본조건을 비교해요. 종료된 공고도 지원 건수에 포함돼요.</li><li>LH 서울·경기북부의 검토한 공급목록 190호는 주소·전용면적·보증금·월세를 함께 확인하고 예산으로 좁힐 수 있어요.</li><li>나머지 공고는 기관·지역·제목·일정으로 탐색할 수 있어요. 자격을 자동 확정하지 않아요.</li><li>모집 후보 분류는 제목 기반이므로 결과 발표나 비주거 공고가 일부 섞일 수 있어요.</li><li>청약홈에 등록된 민간임대와 서울 청년안심주택을 포함하며 모든 민간사업자 공고를 포괄하지 않아요.</li><li>최근 목록은 약 6시간 간격으로 갱신을 시도해요. 검토된 공고는 본문·첨부도 재확인하며, 변경·확인 실패 또는 24시간 초과 시 판정을 보류해요. 예약 실행은 지연될 수 있어요.</li><li>페이지를 새로고침하면 입력한 개인정보가 사라져요. 외부 AI 호출·가입·결제는 없어요.</li></ul></section>`;
  $("#coverage-dialog").showModal();
}
$("#coverage-open").addEventListener("click",openCoverage);
$("#coverage-open-2").addEventListener("click",openCoverage);
document.addEventListener("click", ev => {
  const fieldLink = ev.target.closest("[data-profile-field]");
  if (fieldLink) {
    const input = form.elements[fieldLink.dataset.profileField];
    if (input) {
      $("#detail-dialog").close();
      openProfile(Number(input.closest(".profile-step").dataset.step));
      const details = input.closest("details"); if (details) details.open = true;
      const target = input.name === "marriage" ? $("[data-marriage]") : input;
      target.scrollIntoView({ block: "center" }); target.focus({ preventScroll: true });
    }
  }
  const detail = ev.target.closest("[data-detail]"); if (detail) openDetail(detail.dataset.detail);
  const close = ev.target.closest("[data-close]"); if (close) document.getElementById(close.dataset.close).close();
  if (ev.target.id === "clear-filters") resetFilters();
  if (ev.target.id === "retry-load") load();
});
conditionalFields();
load();
