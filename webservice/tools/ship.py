"""개발 내용을 서브 브랜치로 올린다. 이후 테스트·병합은 GitHub Actions 가 자동 수행.

사용 (저장소 어디서든):
  python webservice/tools/ship.py "feat: SC-02 대시보드" -b feature/sc02-dashboard
  python webservice/tools/ship.py "fix: 로그인 오류 수정"            # 브랜치명 자동 생성
  python webservice/tools/ship.py --sync                            # 병합 후 main 최신화
옵션: --skip-tests 사전 로컬 테스트 생략
"""
import argparse
import datetime
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "webservice"


def run(*cmd, cwd=ROOT, check=True):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=check)


def out(*cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("message", nargs="?")
    ap.add_argument("-b", "--branch")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--sync", action="store_true")
    a = ap.parse_args()

    if a.sync:
        run("git", "checkout", "main")
        run("git", "pull", "--ff-only")
        run("git", "fetch", "--prune")
        return 0
    if not a.message:
        ap.error("커밋 메시지가 필요합니다.")

    if not a.skip_tests:
        print("== 사전 점검: 로컬 테스트 ==")
        if run(sys.executable, "-m", "pytest", "-q", cwd=WEB, check=False).returncode != 0:
            print("로컬 테스트 실패 — 올리지 않습니다. (--skip-tests 로 건너뛸 수 있음)")
            return 1

    import re
    if not re.match(r"^(feat|fix|test|docs|refactor|chore|ci|style|perf)(\([^)]+\))?!?: .{2,}", a.message):
        print("커밋 메시지는 'feat: 설명' / 'fix: 설명' 형식이어야 합니다 (feat|fix|test|docs|refactor|chore|ci|style|perf).")
        return 1
    current = out("git", "rev-parse", "--abbrev-ref", "HEAD")
    branch = a.branch or (current if current.startswith(("feature/", "fix/")) else
                          "feature/" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    if branch != current:
        run("git", "checkout", "-B", branch)
    run("git", "add", "-A")
    if out("git", "status", "--porcelain"):
        run("git", "commit", "-m", a.message)
    else:
        print("커밋할 변경 사항이 없습니다. 기존 커밋을 그대로 올립니다.")
    run("git", "push", "-u", "origin", branch)
    print(f"\n✔ '{branch}' 푸시 완료 → GitHub Actions 가 테스트 후 통과 시 main 에 자동 병합합니다.")
    print("  진행 확인: 저장소의 Actions 탭 / 병합 후 `python webservice/tools/ship.py --sync`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
