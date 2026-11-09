const $ = id => document.getElementById(id);
let mode = "login", type = "individual";
function render() {
  const su = mode === "signup";
  $("title").textContent = su ? "회원가입" : "로그인";
  $("sub").textContent = su ? "사용자 유형을 선택하고 정보를 입력하세요" : "사용자 유형을 선택하고 로그인하세요";
  $("submit").textContent = su ? "가입하기" : "로그인";
  $("switch-text").textContent = su ? "이미 계정이 있으신가요?" : "계정이 없으신가요?";
  $("switch").textContent = su ? "로그인" : "회원가입";
  $("signup-only").hidden = !su; $("pwhint").hidden = !su;
  $("org-wrap").hidden = !(su && type !== "individual");
  $("password").autocomplete = su ? "new-password" : "current-password";
  $("msg").textContent = ""; $("msg").className = "err";
  document.querySelectorAll("#tabs button").forEach(b => b.setAttribute("aria-pressed", b.dataset.type === type));
}
document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => { type = b.dataset.type; render(); });
$("switch").onclick = () => { mode = mode === "login" ? "signup" : "login"; render(); };
$("switch").onkeydown = e => { if (e.key === "Enter" || e.key === " ") $("switch").click(); };
function fail(t) { $("msg").className = "err"; $("msg").textContent = t; }
async function post(url, body) {
  const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  let data = {}; try { data = await r.json(); } catch (_) {}
  return {ok: r.ok, status: r.status, data};
}
$("form").onsubmit = async e => {
  e.preventDefault();
  const username = $("username").value.trim(), password = $("password").value;
  if (!username || !password) return fail("아이디와 비밀번호를 입력해 주세요.");
  $("submit").disabled = true; $("msg").textContent = "";
  try {
    if (mode === "signup") {
      if (password !== $("password2").value) return fail("비밀번호 확인이 일치하지 않습니다.");
      const body = {username, password, user_type: type};
      if (type !== "individual") body.org_code = $("org_code").value;
      const r = await post("/api/auth/signup", body);
      if (!r.ok) return fail(r.data.error ? r.data.error.message : "가입에 실패했습니다.");
      mode = "login"; render();
      $("msg").className = "ok"; $("msg").textContent = "가입이 완료되었습니다. 로그인해 주세요.";
      $("password").value = ""; return;
    }
    const r = await post("/api/auth/login", {username, password});
    if (!r.ok) return fail(r.data.error ? r.data.error.message : "로그인에 실패했습니다.");
    if (r.data.user_type !== type) {
      await post("/api/auth/logout", {});
      return fail("선택한 사용자 유형과 계정 유형이 다릅니다.");
    }
    location.href = "/dashboard";
  } catch (_) { fail("서버에 연결할 수 없습니다."); }
  finally { $("submit").disabled = false; }
};
render();
