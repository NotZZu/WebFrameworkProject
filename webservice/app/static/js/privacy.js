const $ = id => document.getElementById(id);
const LEVELS = {pseudonym: "가명 처리", anonymous: "익명 처리"};
function say(text, kind) { const m = $("privacy-msg"); m.textContent = text; m.className = kind; }
async function api(url, opt) {
  const r = await fetch(url, opt);
  if (r.status === 401) { location.href = "/"; throw new Error("auth"); }
  return r;
}
function show(d) {
  $("result-empty").hidden = true; $("result").hidden = false;
  $("result-level").textContent = LEVELS[d.level] || d.level;
  $("result-display").textContent = d.display;
  $("result-pid").textContent = d.pseudonym_id || "없음 (익명)";
}
async function loadMine() {
  const r = await api("/api/privacy/me");
  if (r.status === 200) show(await r.json());
}
$("submit-privacy").onclick = async () => {
  const mode = document.querySelector("input[name=mode]:checked").value;
  const name = $("name").value.trim(), birthdate = $("birthdate").value;
  if (!name) return say("이름을 입력해 주세요.", "err");
  if (!birthdate) return say("생년월일을 입력해 주세요.", "err");
  $("submit-privacy").disabled = true;
  try {
    const r = await api("/api/privacy/process", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({mode, name, birthdate})});
    const d = await r.json();
    if (r.status === 200) { show(d); say(LEVELS[d.level] + "가 완료되었습니다. 입력한 원본은 저장되지 않았습니다.", "ok"); $("name").value = ""; $("birthdate").value = ""; }
    else say((d.error && d.error.message) || "처리하지 못했습니다. 잠시 후 다시 시도해 주세요.", "err");
  } catch (e) { if (e.message !== "auth") say("네트워크 오류가 발생했습니다.", "err"); }
  finally { $("submit-privacy").disabled = false; }
};
$("logout").onclick = async () => { await fetch("/api/auth/logout", {method: "POST"}); location.href = "/"; };
loadMine();
