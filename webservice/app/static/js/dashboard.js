const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function load() {
  const r = await fetch("/api/dashboard");
  if (r.status === 401) { location.href = "/"; return; }
  const d = await r.json();
  $("kpi-in-progress").textContent = d.applications.in_progress;
  $("kpi-certificates").textContent = d.certificates.total;
  $("kpi-suspected").textContent = d.certificates.suspected;
  $("kpi-privacy").textContent = d.privacy.processed ? 1 : 0;
  if (d.certificates.suspected > 0) { $("kpi-suspected").classList.add("alert"); $("kpi-suspected-card").classList.add("hot"); }
  if (d.scope === "all") $("scope-note").textContent = "기관 계정: 전체 신청·검증서 현황입니다.";
  const rows = d.recent_applications;
  $("recent-body").innerHTML = rows.length ? rows.map(a =>
    `<tr><td>#${a.id}</td><td>${esc(a.algorithm_type)}</td><td>${a.submitted_at}</td>` +
    `<td><span class="badge s-${a.status}">${esc(a.status_label)}</span></td></tr>`).join("")
    : `<tr><td colspan="4" id="recent-empty">아직 신청 내역이 없습니다.</td></tr>`;
  $("notifications").innerHTML = d.notifications.length
    ? d.notifications.map(n => `<li class="${n.type}">${esc(n.message)}</li>`).join("")
    : `<li class="empty">새 알림이 없습니다.</li>`;
}
$("logout").onclick = async () => { await fetch("/api/auth/logout", {method: "POST"}); location.href = "/"; };
load();
