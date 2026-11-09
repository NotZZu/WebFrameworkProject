const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const PAGE = document.body.dataset.page;
const PER = 10;
let page = 1, total = 0, items = [], selected = null;
async function api(url, opt) {
  const r = await fetch(url, opt);
  if (r.status === 401) { location.href = "/"; throw new Error("auth"); }
  return r;
}
const badge = c => `<span class="badge t-${esc(c.tamper_status)}">${esc(c.tamper_label)}</span>`;
function pager() {
  const pages = Math.max(1, Math.ceil(total / PER));
  $("page-info").textContent = `${page} / ${pages}`;
  $("prev").disabled = page <= 1; $("next").disabled = page >= pages;
}
async function load() {
  const d = await (await api(`/api/certificates?page=${page}&per_page=${PER}`)).json();
  items = d.items; total = d.total; pager();
  if (PAGE === "tamper") renderTamper(); else renderHistory();
}
function renderHistory() {
  $("certs-body").innerHTML = items.length ? items.map(c =>
    `<tr class="item${selected === c.id ? " sel" : ""}" data-id="${c.id}"><td>CV-${String(c.id).padStart(4, "0")}</td><td>#${c.application_id}</td>` +
    `<td>${esc(c.algorithm_type)}</td><td>${esc(c.cert_type)}</td><td>${esc(c.issued_at)}</td><td>${badge(c)}</td></tr>`).join("")
    : `<tr><td colspan="6" class="empty">발급된 검증서가 없습니다.</td></tr>`;
  document.querySelectorAll("#certs-body tr.item").forEach(tr => tr.onclick = () => select(Number(tr.dataset.id)));
}
function select(id) {
  selected = id;
  const c = items.find(x => x.id === id); if (!c) return;
  $("cert-detail-panel").hidden = false; $("detail-msg").textContent = "";
  $("cert-detail").innerHTML = `<dt>검증서 번호</dt><dd>CV-${String(c.id).padStart(4, "0")}</dd><dt>시험 신청 / 알고리즘</dt><dd>#${c.application_id} · ${esc(c.algorithm_type)}</dd>` +
    `<dt>유형</dt><dd>${esc(c.cert_type)}</dd><dt>발급일시</dt><dd>${esc(c.issued_at)}</dd>` + (c.owner ? `<dt>신청자</dt><dd>${esc(c.owner)}</dd>` : "") +
    `<dt>위변조 상태</dt><dd id="detail-status">${badge(c)}</dd>`;
  renderHistory();
}
function renderTamper() {
  $("tamper-body").innerHTML = items.length ? items.map(c =>
    `<tr class="item${c.tamper_status === "suspected" ? " bad" : ""}" data-id="${c.id}"><td>CV-${String(c.id).padStart(4, "0")}</td><td>${esc(c.algorithm_type)}</td><td>${esc(c.cert_type)}</td>` +
    `<td>${esc(c.issued_at)}</td><td class="st">${badge(c)}</td><td><button class="btn sm ghost verify" type="button" data-id="${c.id}">검증</button></td></tr>`).join("")
    : `<tr><td colspan="6" class="empty">발급된 검증서가 없습니다.</td></tr>`;
  document.querySelectorAll("#tamper-body button.verify").forEach(b => b.onclick = e => { e.stopPropagation(); verify(Number(b.dataset.id), true); });
  summary();
}
async function summary() {
  const d = await (await api("/api/dashboard")).json();
  const t = d.certificates.total, s = d.certificates.suspected;
  $("kpi-total").textContent = t; $("kpi-suspected").textContent = s; $("kpi-normal").textContent = t - s;
  $("kpi-bad-box").classList.toggle("hot", s > 0);
}
async function verify(id, quiet) {
  const r = await api(`/api/certificates/${id}/verify`);
  const c = await r.json();
  if (r.status !== 200) { const m = PAGE === "tamper" ? $("tamper-msg") : $("detail-msg"); m.textContent = (c.error && c.error.message) || "검증하지 못했습니다."; m.className = "err"; return null; }
  const i = items.findIndex(x => x.id === id); if (i >= 0) items[i] = c;
  if (PAGE === "tamper") { renderTamper(); if (!quiet) return c; $("tamper-msg").className = c.tamper_status === "suspected" ? "err" : "ok";
    $("tamper-msg").textContent = `CV-${String(id).padStart(4, "0")}: ${c.tamper_label}`; }
  else { select(id); $("detail-msg").textContent = `검증 결과: ${c.tamper_label}`; $("detail-msg").style.color = c.tamper_status === "suspected" ? "var(--warn)" : "#137333"; }
  return c;
}
$("prev").onclick = () => { page--; load(); };
$("next").onclick = () => { page++; load(); };
if (PAGE === "tamper") {
  $("verify-all").onclick = async () => {
    $("verify-all").disabled = true; let bad = 0;
    for (const c of items.slice()) { const r = await verify(c.id, false); if (r && r.tamper_status === "suspected") bad++; }
    $("tamper-msg").className = bad ? "err" : "ok";
    $("tamper-msg").textContent = bad ? `검증 완료: 위변조 의심 ${bad}건이 있습니다.` : "검증 완료: 모두 정상입니다.";
    $("verify-all").disabled = false;
  };
} else {
  $("verify-one").onclick = () => selected && verify(selected, true);
}
if ($("issue-submit")) {
  const say = (t, k) => { $("issue-msg").textContent = t; $("issue-msg").className = k; };
  async function loadIssuable() {
    const apps = (await (await api("/api/cavp/applications?status=approved&per_page=50")).json()).items;
    const have = new Set((await (await api("/api/certificates?per_page=50")).json()).items.map(c => c.application_id));
    $("issue-app").innerHTML = `<option value="">발급할 신청을 선택하세요</option>` +
      apps.filter(a => !have.has(a.id)).map(a => `<option value="${a.id}">#${a.id} ${esc(a.algorithm_type)} (${esc(a.owner)})</option>`).join("");
  }
  $("issue-submit").onclick = async () => {
    const id = $("issue-app").value, content = $("issue-content").value;
    if (!id) return say("발급할 신청을 선택해 주세요.", "err");
    if (!content.trim()) return say("검증서 내용을 입력해 주세요.", "err");
    $("issue-submit").disabled = true;
    try {
      const r = await api(`/api/cavp/applications/${id}/certificate`, {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({cert_type: $("issue-type").value, content})});
      const d = await r.json();
      if (r.status === 201) { say(`검증서 CV-${String(d.id).padStart(4, "0")} 가 발급되었습니다.`, "ok"); $("issue-content").value = ""; page = 1; await load(); await loadIssuable(); }
      else if (r.status === 409) say("이미 발급되었거나 승인되지 않은 신청입니다.", "err");
      else say((d.error && d.error.message) || "발급하지 못했습니다.", "err");
    } catch (e) { if (e.message !== "auth") say("네트워크 오류가 발생했습니다.", "err"); }
    finally { $("issue-submit").disabled = false; }
  };
  loadIssuable();
}
$("logout").onclick = async () => { await fetch("/api/auth/logout", {method: "POST"}); location.href = "/"; };
load();
