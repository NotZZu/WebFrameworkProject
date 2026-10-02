"""pytest JUnit XML → 마크다운 요약 (GitHub Actions 작업 요약/로컬 공용). 사용: python tools/ci_summary.py report.xml"""
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
suite = root if root.tag == "testsuite" else root.find("testsuite")
total = int(suite.get("tests")); fail = int(suite.get("failures")) + int(suite.get("errors"))
skipped_all = int(suite.get("skipped"))
xfail = sum(1 for tc in suite.iter("testcase") if (s := tc.find("skipped")) is not None and "TDD Red" in (s.get("message") or ""))
skipped = skipped_all - xfail
passed = total - fail - skipped_all
print("## 테스트 결과\n")
print("| 구분 | 건수 |\n|---|---|")
print(f"| ✅ 통과 | {passed} |\n| ❌ 실패 | {fail} |\n| 🔴 Red(구현 전, 기대된 실패) | {xfail} |\n| ⏭ 건너뜀 | {skipped} |")
print(f"\nGreen 진행률: {passed}/{passed + xfail} ({100 * passed / max(passed + xfail, 1):.0f}%)")
if fail:
    print("\n### 실패 목록")
    for tc in suite.iter("testcase"):
        if tc.find("failure") is not None or tc.find("error") is not None:
            print(f"- `{tc.get('classname')}::{tc.get('name')}`")
sys.exit(1 if fail else 0)
