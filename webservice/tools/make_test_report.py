"""시험결과서 자동 생성: JUnit XML + 케이스 레지스트리(cases.json) → 케이스 ID별 결과 HTML/마크다운.
사용: python tools/make_test_report.py report.xml cases.json test-artifacts/시험결과서.html
(시험계획서의 케이스 ID 와 1:1 대응 — 산출물 'T단계 시험결과서'의 근거 자료)"""
import datetime
import html
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

xml_path, cases_path, out_path = sys.argv[1:4]
cases = json.load(open(cases_path, encoding="utf-8"))
by_func = {(c["module"], c["func"].split(".")[-1]): c for c in cases}
res = defaultdict(lambda: {"pass": 0, "fail": 0, "red": 0, "skip": 0})
suite = ET.parse(xml_path).getroot()
suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
for tc in suite.iter("testcase"):
    c = by_func.get((tc.get("classname"), tc.get("name").split("[")[0]))
    if not c:
        continue
    r = res[c["id"]]
    sk = tc.find("skipped")
    if tc.find("failure") is not None or tc.find("error") is not None:
        r["fail"] += 1
    elif sk is not None and "TDD Red" in (sk.get("message") or ""):
        r["red"] += 1
    elif sk is not None:
        r["skip"] += 1
    else:
        r["pass"] += 1


def status(r):
    if r["fail"]:
        return "FAIL"
    if r["red"]:
        return "RED"
    return "PASS" if r["pass"] else "SKIP"


rows = [(c, status(res[c["id"]]), res[c["id"]]) for c in cases if c["id"] in res]
cnt = {s: sum(1 for _, st, _ in rows if st == s) for s in ("PASS", "RED", "FAIL", "SKIP")}
color = {"PASS": "#137333", "RED": "#b3261e", "FAIL": "#b3261e", "SKIP": "#6b7488"}
label = {"PASS": "✅ 통과", "RED": "🔴 Red(구현 전)", "FAIL": "❌ 실패", "SKIP": "⏭ 건너뜀"}
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
body = "".join(
    f"<tr><td>{c['id']}</td><td>{c['req']}</td><td>{html.escape(c['title'])}</td>"
    f"<td style='color:{color[st]};font-weight:700'>{label[st]}</td><td>{r['pass'] + r['fail'] + r['red']}</td></tr>"
    for c, st, r in rows)
doc = f"""<!doctype html><meta charset="utf-8"><title>시험결과서</title>
<style>body{{font-family:system-ui,'Malgun Gothic',sans-serif;margin:32px;color:#1e2761}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #dfe3ee;padding:6px 10px;font-size:13px;text-align:left}}th{{background:#1e2761;color:#fff}}</style>
<h1>시험결과서 (자동 생성)</h1><p>생성: {now} · 케이스 {len(rows)}건 — 통과 {cnt['PASS']} · Red {cnt['RED']} · 실패 {cnt['FAIL']} · 건너뜀 {cnt['SKIP']}</p>
<table><tr><th>케이스 ID</th><th>요구사항</th><th>시험 항목</th><th>결과</th><th>실행 건수</th></tr>{body}</table>"""
Path(out_path).parent.mkdir(parents=True, exist_ok=True)
Path(out_path).write_text(doc, encoding="utf-8")
print(f"<details><summary>케이스별 결과 ({len(rows)}건) — 통과 {cnt['PASS']} · Red {cnt['RED']} · 실패 {cnt['FAIL']}</summary>\n")
print("| ID | 요구사항 | 결과 |\n|---|---|---|")
for c, st, _ in rows:
    print(f"| {c['id']} | {c['req']} | {label[st]} |")
print("\n</details>")
