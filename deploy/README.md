# AWS 배포 가이드

한 대의 EC2(프리티어 우선)에서 **웹 서비스(포트 80)** 와 **시험 시연 페이지(포트 8080)** 를 서로 다른 Docker 컨테이너로 운영합니다.
내 PC 가 꺼져 있어도 인터넷 주소로 접속할 수 있고, main 브랜치가 갱신되면 서버가 3분 안에 자동으로 새 버전으로 바뀝니다.

```
GitHub main (CI 시험 전부 통과한 코드만 병합)
      │  3분마다 git fetch → 서비스·배포 코드가 바뀌었으면 재빌드
      ▼
EC2 (Amazon Linux 2023, Docker Compose)
 ├─ service  :80    Flask + gunicorn, 데이터는 /opt/app-data/service (SQLite, 재시작해도 유지)
 └─ demo     :8080  시험 시연 서버(pytest + Chromium 실행), 서비스 데이터에 접근하지 않음
```

## 1. 최초 배포 (한 번만, 약 10분)

1. AWS 콘솔에 로그인하고 오른쪽 위 리전을 **아시아 태평양(서울) ap-northeast-2** 로 바꿉니다.
2. **CloudFormation → 스택 생성 → 새 리소스 사용 → 템플릿 파일 업로드** 에서 이 폴더의 `cloudformation.yml` 을 올립니다.
3. 스택 이름 `verification-system`, 파라미터는 기본값 그대로 두고 다음으로 진행합니다.
   - 마지막 화면에서 *"IAM 리소스를 생성할 수 있음을 승인합니다"* 에 체크해야 합니다(서버 관리용 SSM 역할 생성).
4. 스택이 `CREATE_COMPLETE` 가 되면 **출력** 탭에서 `ServiceUrl`, `DemoUrl` 을 확인합니다.
5. 서버 안에서 이미지를 빌드하므로 **스택 완료 후 8~15분** 더 기다린 뒤 접속하세요(브라우저 이미지 빌드가 가장 오래 걸립니다).

> 메모리가 모자라 시험 시연이 중간에 멈추면 파라미터 `InstanceType` 을 `t3.small` 로 바꿔 스택을 업데이트하세요(프리티어 대상이 아닐 수 있음).

## 2. 이후 업데이트

따로 할 일이 없습니다. 기능을 개발해 push → CI 통과 → main 자동 병합 → **3분 안에 서버 자동 반영**.
즉시 반영하려면 서버에서 `sudo /opt/app/repo/deploy/update.sh --force`.

## 3. 상태 확인 · 문제 해결

- 콘솔 **EC2 → 인스턴스 → 연결 → Session Manager** 로 접속(SSH 포트는 닫혀 있음).
- 최초 구성 로그: `sudo tail -f /var/log/app-bootstrap.log`
- 컨테이너 상태: `sudo docker ps` / 로그: `sudo docker logs deploy-service-1`, `sudo docker logs deploy-demo-1`
- 상태 확인 주소: `http://<IP>/healthz`, `http://<IP>:8080/healthz`

## 4. 보안·비용 메모

- 비밀키(`SECRET_KEY`, `PSEUDONYM_SECRET`)는 서버에서 처음 한 번 무작위로 생성해 `/opt/app/.env`(권한 600)에만 보관합니다. 저장소에는 없습니다.
- 현재는 도메인·HTTPS 없이 IP 로 접속하는 시연용 구성입니다(비밀번호는 서버에서 bcrypt 로만 저장되지만 전송은 HTTP). 도메인을 연결하면 HTTPS 로 확장할 수 있습니다.
- 인스턴스·고정 IP·디스크가 과금 대상입니다. 프리티어/크레딧 범위를 AWS 콘솔의 *결제 → 프리티어* 에서 확인하세요. **발표가 끝나면 스택을 삭제**하면 모든 리소스가 함께 정리됩니다.
- 시험 시연 서버는 한 번에 한 건만 실행하며 제한 시간(7분)이 있습니다.
