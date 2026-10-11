#!/bin/bash
# main 브랜치에 새 커밋이 있으면 받아서 컨테이너를 다시 빌드·기동한다. (systemd 타이머가 3분마다 실행)
# main 에는 CI 시험을 전부 통과한 코드만 병합되므로, 이 스크립트는 '검증된 코드만 배포'하는 역할을 한다.
# 사용: update.sh [--force]
set -euo pipefail
cd /opt/app/repo
git fetch -q origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
FORCE="${1:-}"
if [ "$LOCAL" = "$REMOTE" ] && [ "$FORCE" != "--force" ]; then exit 0; fi
# 서비스·배포 코드가 바뀐 경우만 다시 빌드 (시험 진척도 파일만 바뀐 경우는 건너뜀)
CHANGED=$(git diff --name-only "$LOCAL" "$REMOTE" | grep -E '^(webservice/|deploy/|\.dockerignore)' | grep -vE '^webservice/tracker/' || true)
git reset -q --hard origin/main
if [ -n "$CHANGED" ] || [ "$FORCE" = "--force" ]; then
  echo "[$(date -Is)] 배포: ${LOCAL:0:7} -> ${REMOTE:0:7}"
  cd deploy
  docker compose --env-file /opt/app/.env up -d --build
  docker image prune -f >/dev/null
fi
