const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function say(text, kind) { const m = $("apply-msg"); m.textContent = text; m.className = kind; }
async function api(url, opt) {
  const r = await fetch(url, opt);
  if (r.status === 401) { location.href = "/"; throw new Error("auth"); }
  return r;
}
async function loadAlgorithms() {
  const d = await (await api("/api/cavp/algorithms")).json();
  $("algorithm").innerHTML += d.algorithms.map(a => `<option value="${esc(a)}">${esc(a)}</option>`).join("");
}
async function loadList() {
  const d = await (await api("/api/cavp/applications?per_page=50")).json();
  $("my-apps-body").innerHTML = d.items.length ? d.items.map(a =>
    `<tr><td>#${a.id}</td><td>${esc(a.algorithm_type)}</td><td>${esc(a.submitted_at)}</td>` +
    `<td><span class="badge s-${a.status}">${esc(a.status_label)}</span></td></tr>`).join("")
    : `<tr><td colspan="4" class="empty">아직 신청 내역이 없습니다.</td></tr>`;
}
$("submit-app").onclick = async () => {
  const algo = $("algorithm").value;
  if (!algo) return say("시험 대상 알고리즘을 선택해 주세요.", "err");
  $("submit-app").disabled = true;
  try {
    const r = await api("/api/cavp/applications", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({algorithm_type: algo})});
    const d = await r.json();
    if (r.status === 201) { say(`${algo} 시험 신청이 접수되었습니다. (신청 번호 #${d.id})`, "ok"); await loadList(); }
    else if (r.status === 409) say("같은 알고리즘의 진행 중인 신청이 있습니다. 완료된 뒤 다시 신청해 주세요.", "err");
    else say((d.error && d.error.message) || "신청하지 못했습니다. 잠시 후 다시 시도해 주세요.", "err");
  } catch (e) { if (e.message !== "auth") say("네트워크 오류가 발생했습니다.", "err"); }
  finally { $("submit-app").disabled = false; }
};
$("logout").onclick = async () => { await fetch("/api/auth/logout", {method: "POST"}); location.href = "/"; };
loadAlgorithms(); loadList();
