"""테스트 코드의 @case 메타데이터를 JSON 으로 내보낸다 (시험계획서 생성용).

사용: python scripts/export_cases.py [출력경로]   (기본: cases.json)
각 케이스의 pytest 실행 건수(파라미터 확장 포함)도 함께 센다.
"""
import importlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.case_registry import REGISTRY  # noqa: E402

for mod in sorted(p for p in (ROOT / "tests").rglob("test_*.py")):
    importlib.import_module(".".join(mod.relative_to(ROOT).with_suffix("").parts))

out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "case", "-p", "no:cacheprovider"],
                     cwd=ROOT, capture_output=True, text=True).stdout
runs = Counter()
for line in out.splitlines():
    if "::" in line:
        path, func = line.split("::")[0], line.split("::")[1].split("[")[0]
        runs[path.replace("/", ".").removesuffix(".py") + ":" + func] += 1

cases = []
for c in sorted(REGISTRY.values(), key=lambda c: c["id"]):
    cases.append({**c, "runs": runs.get(c["module"] + ":" + c["func"].split(".")[-1], 1)})
dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "cases.json"
dest.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(cases)} cases, {sum(c['runs'] for c in cases)} test runs -> {dest}")
