const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const PER = 10;
let page = 1, pages = 1, selected = null, isAll = false;
async function api(url, opt) {
  const r = await fetch(url, opt);
  if (r.status === 401) { location.href = "/"; throw new Error("auth"); }
  return r;
}
async function loadList() {
  const st = $("status-filter").value;
  const d = await (await api(`/api/cavp/applications?page=${page}&per_page=${PER}` + (st ? `&status=${st}` : ""))).json();
  isAll = d.scope === "all";
  $("owner-th").hidden = !isAll;
  if (isAll) $("scope-note").textContent = "기관 계정: 전체 신청을 심사할 수 있습니다. 행을 누르면 상세가 보입니다.";
  pages = Math.max(1, Math.ceil(d.total / PER));
  if (page > pages) { page = pages; return loadList(); }
  $("apps-body").innerHTML = d.items.length ? d.items.map(a =>
    `<tr class="item${selected === a.id ? " sel" : ""}" data-id="${a.id}"><td>#${a.id}</td><td>${esc(a.algorithm_type)}</td>` +
    (isAll ? `<td>${esc(a.owner || "")}</td>` : "") +
    `<td>${esc(a.submitted_at)}</td><td><span class="badge s-${a.status}">${esc(a.status_label)}</span></td></tr>`).join("")
    : `<tr><td colspan="${isAll ? 5 : 4}" class="empty">아직 신청 내역이 없습니다.</td></tr>`;
  $("total-count").textContent = `총 ${d.total}건`;
  $("page-info").textContent = `${page} / ${pages}`;
  $("prev").disabled = page <= 1; $("next").disabled = page >= pages;
}
function showDetail(a) {
  selected = a.id;
  $("detail-empty").hidden = true; $("detail-body").hidden = false;
  const cancelled = a.status === "cancelled";
  const idx = {submitted: 0, reviewing: 1, approved: 2, rejected: 2, cancelled: 1}[a.status];
  const last = a.status === "rejected" ? "반려" : "승인 완료";
  const names = cancelled ? ["접수", "취소"] : ["접수", "심사", last];
  $("steps").innerHTML = names.map((n, i) =>
    `<div class="step ${i < idx ? "done" : ""} ${i === idx ? "now" : ""} ${i === idx && (a.status === "rejected" || cancelled) ? "bad" : ""}">${i + 1}. ${n}</div>`).join("");
  $("d-id").textContent = "#" + a.id; $("d-algo").textContent = a.algorithm_type;
  $("detail-status").textContent = a.status_label;
  $("d-owner-t").hidden = $("d-owner").hidden = !isAll; $("d-owner").textContent = a.owner || "";
  $("d-sub").textContent = a.submitted_at; $("d-upd").textContent = a.updated_at;
  const set = (id, show) => { const b = $(id); if (b) b.hidden = !show; };
  set("act-review", a.status === "submitted");
  set("act-approve", a.status === "reviewing"); set("act-reject", a.status === "reviewing");
  set("act-cancel", a.status === "submitted"); set("cancel-confirm", false);
  document.querySelectorAll("#apps-body tr.item").forEach(r => r.classList.toggle("sel", Number(r.dataset.id) === a.id));
}
async function select(id) {
  const r = await api(`/api/cavp/applications/${id}`);
  if (r.ok) { $("detail-msg").textContent = ""; showDetail(await r.json()); }
}
async function change(status) {
  const msg = $("detail-msg");
  const r = await api(`/api/cavp/applications/${selected}/status`, {method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({status})});
  const d = await r.json();
  if (r.ok) { msg.style.color = "#137333"; msg.textContent = "상태를 변경했습니다."; showDetail(d); await loadList(); }
  else {
    await select(selected); await loadList();  // 최신 상태를 먼저 불러온 뒤(불러오면 안내문이 지워진다) 오류를 보여 준다
    msg.style.color = "#d93025"; msg.textContent = (d.error && d.error.message) || "변경하지 못했습니다.";
  }
}
async function cancelApp() {
  const msg = $("detail-msg");
  const r = await api(`/api/cavp/applications/${selected}/cancel`, {method: "POST"});
  const d = await r.json();
  if (r.ok) { msg.style.color = "#137333"; msg.textContent = "신청을 취소했습니다."; showDetail(d); await loadList(); }
  else {
    await select(selected); await loadList();  // 최신 상태를 먼저 불러온 뒤(불러오면 안내문이 지워진다) 오류를 보여 준다
    msg.style.color = "#d93025"; msg.textContent = (d.error && d.error.message) || "취소하지 못했습니다.";
  }
}
$("apps-body").onclick = e => { const tr = e.target.closest("tr.item"); if (tr) select(Number(tr.dataset.id)); };
$("status-filter").onchange = () => { page = 1; loadList(); };
$("prev").onclick = () => { page--; loadList(); };
$("next").onclick = () => { page++; loadList(); };
for (const [id, st] of [["act-review", "reviewing"], ["act-approve", "approved"], ["act-reject", "rejected"]]) {
  const b = $(id); if (b) b.onclick = () => change(st);
}
if ($("act-cancel")) {
  $("act-cancel").onclick = () => { $("act-cancel").hidden = true; $("cancel-confirm").hidden = false; };
  $("act-cancel-no").onclick = () => { $("cancel-confirm").hidden = true; $("act-cancel").hidden = false; };
  $("act-cancel-yes").onclick = cancelApp;
}
$("logout").onclick = async () => { await fetch("/api/auth/logout", {method: "POST"}); location.href = "/"; };
loadList();
