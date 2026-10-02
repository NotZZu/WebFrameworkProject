"""커밋 메시지 규칙 검사(Conventional Commits). 사용: python tools/check_commits.py <기준ref> <끝ref>
형식: type(scope)?: 설명  — type ∈ feat|fix|test|docs|refactor|chore|ci|style|perf. 병합 커밋은 제외."""
import re
import subprocess
import sys

PATTERN = re.compile(r"^(feat|fix|test|docs|refactor|chore|ci|style|perf)(\([^)]+\))?!?: .{2,}")
base, head = sys.argv[1], sys.argv[2]
log = subprocess.run(["git", "log", "--no-merges", "--format=%h%x09%s", f"{base}..{head}"],
                     capture_output=True, text=True, check=True).stdout.strip().splitlines()
bad = [l for l in log if not PATTERN.match(l.split("\t", 1)[1])]
for l in bad:
    print(f"::error::커밋 메시지 형식 위반: {l}  (예: 'feat: SC-02 대시보드 추가')")
print(f"검사 {len(log)}건, 위반 {len(bad)}건")
sys.exit(1 if bad else 0)
