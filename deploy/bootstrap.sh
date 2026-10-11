#!/bin/bash
# EC2 최초 1회 구성: 스왑, Docker, 저장소 클론, 환경변수 생성, 자동 업데이트 타이머, 첫 기동.
# 사용: SERVICE_IP=<공인 IP> REPO_URL=<저장소> bash bootstrap.sh   (CloudFormation UserData 에서 호출)
set -euxo pipefail
exec > >(tee -a /var/log/app-bootstrap.log) 2>&1
REPO_URL="${REPO_URL:-https://github.com/NotZZu/WebFrameworkProject.git}"
SERVICE_IP="${SERVICE_IP:-localhost}"

# 1) 스왑 2GB (프리티어 1GB 메모리에서 브라우저 시험 실행을 위해)
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 2) Docker + Compose
dnf install -y docker git
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# 3) 저장소와 환경변수 (비밀키는 서버에서만 생성, 저장소에 두지 않음)
mkdir -p /opt/app /opt/app-data/service
[ -d /opt/app/repo/.git ] || git clone --depth 50 "$REPO_URL" /opt/app/repo
if [ ! -f /opt/app/.env ]; then
  {
    echo "SECRET_KEY=$(openssl rand -hex 32)"
    echo "PSEUDONYM_SECRET=$(openssl rand -hex 32)"
    echo "SERVICE_URL=http://${SERVICE_IP}"
  } > /opt/app/.env
  chmod 600 /opt/app/.env
fi
chmod +x /opt/app/repo/deploy/update.sh

# 4) 3분마다 main 의 새 커밋을 받아 자동 배포
cat > /etc/systemd/system/app-update.service <<'UNIT'
[Unit]
Description=Pull main and redeploy containers
[Service]
Type=oneshot
ExecStart=/opt/app/repo/deploy/update.sh
UNIT
cat > /etc/systemd/system/app-update.timer <<'UNIT'
[Unit]
Description=Auto-deploy every 3 minutes
[Timer]
OnBootSec=3min
OnUnitActiveSec=3min
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now app-update.timer

# 5) 첫 기동
/opt/app/repo/deploy/update.sh --force
echo "bootstrap 완료"
