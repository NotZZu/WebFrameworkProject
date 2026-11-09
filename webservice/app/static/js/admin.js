const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const LABELS = {submitted: "접수 대기", reviewing: "시험 진행중", approved: "시험 완료", rejected: "반려", cancelled: "취소"};
const STATUS_ORDER = ["submitted", "reviewing", "approved", "rejected", "cancelled"];
const ALGO_ORDER = ["AES", "SHA-2", "SHA-3", "HMAC", "RSA", "ECDSA", "DRBG"];
function bars(obj, order, labels) {
  const max = Math.max(1, ...Object.values(obj));
  return order.filter(k => k in obj).map(k => { const n = obj[k]; return `<tr><td>${esc(labels ? labels[k] : k)}</td><td class="bar"><div style="width:${Math.round(n / max * 100)}%"></div></td><td class="num">${n}</td></tr>`; }).join("");
}
async function load() {
  const r = await fetch("/api/admin/summary");
  if (r.status === 401) { location.href = "/"; return; }
  if (r.status === 403) { location.href = "/dashboard"; return; }
  const d = await r.json();
  const a = d.applications;
  $("kpi-total").textContent = a.total;
  $("kpi-in-progress").textContent = a.in_progress;
  $("kpi-pending").textContent = a.pending_review;
  $("kpi-suspected").textContent = d.certificates.suspected;
  if (d.certificates.suspected > 0) { $("kpi-suspected").classList.add("alert"); $("kpi-suspected-card").classList.add("hot"); }
  $("status-body").innerHTML = bars(a.by_status, STATUS_ORDER, LABELS);
  $("algo-body").innerHTML = bars(a.by_algorithm, ALGO_ORDER);
  $("attention").innerHTML = d.attention.length
    ? d.attention.map(n => `<li class="${n.type === "warning" ? "warning" : "info"}" style="padding:10px 12px;border-radius:10px;margin-bottom:8px;font-size:13px;line-height:1.5;${n.type === "warning" ? "background:var(--warnbg);color:var(--warn);font-weight:700" : ""}">${esc(n.message)}</li>`).join("")
    : `<li class="empty">주의할 항목이 없습니다.</li>`;
  $("recent-body").innerHTML = d.recent_applications.length ? d.recent_applications.map(x =>
    `<tr><td>#${x.id}</td><td>${esc(x.algorithm_type)}</td><td>${esc(x.owner || "")}</td><td>${esc(x.submitted_at)}</td>` +
    `<td><span class="badge s-${x.status}">${esc(x.status_label)}</span></td></tr>`).join("")
    : `<tr><td colspan="5" class="empty">아직 신청 내역이 없습니다.</td></tr>`;
}
$("logout").onclick = async () => { await fetch("/api/auth/logout", {method: "POST"}); location.href = "/"; };
load();
