# 배포 안내 — 요금이 청구되지 않는 서버리스 구성

AWS **상시 무료(Always Free)** 서비스만 씁니다. 서버(EC2), 고정 IP, 디스크(EBS), S3, API Gateway 는 쓰지 않습니다.

```
사용자 → CloudFront(무료 1TB·1천만 요청) → Lambda 함수 URL(무료 100만 요청) → DynamoDB(무료 25GB, 프로비저닝 10/10)
```

| 서비스 | 쓰는 이유 | 무료 한도(매월·상시) | 주의 |
|---|---|---|---|
| Lambda | Flask 앱 실행 | 100만 요청, 40만 GB-초 | 함수 URL 이용 시 별도 요금 없음 |
| DynamoDB | 사용자·세션·신청 저장 | 25GB, 읽기/쓰기 용량 합계 25 | **프로비저닝 모드만 무료**(온디맨드는 요금 발생) |
| CloudFront | HTTPS 주소와 전달 | 1TB 전송, 1천만 요청 | |
| 예산(Budgets) | 이상 징후 알림 | 무료 | |

## 1. 준비 — 배포 파일 만들기

저장소 루트에서 `bash deploy/build_lambda.sh` → `lambda.zip` (약 5MB). AWS 계정 없이 만들 수 있습니다.

## 2. 옛 구성 삭제 (요금 차단)

CloudFormation 콘솔 → 스택 `verification-system` → **삭제**. 삭제 후 EC2·Elastic IP·EBS 가 모두 사라졌는지 EC2 콘솔에서 확인합니다.

## 3. DynamoDB 표 만들기 (리전: 서울 ap-northeast-2)

1. 표 이름 `verification-system`, 파티션 키 `pk`(문자열), 정렬 키 `sk`(문자열)
2. 설정 → **사용자 지정 설정** → 용량 모드 **프로비저닝**, 읽기 **10**, 쓰기 **10**, **Auto Scaling 끔**
3. 보조 인덱스는 만들지 않습니다(용량 합계가 늘어납니다).
4. 만든 뒤 표 → 추가 설정 → **TTL** 켜기, 속성 이름 `ttl` (만료된 세션·시도 기록 자동 삭제)

## 4. Lambda 함수 만들기

1. 함수 이름 `verification-system`, 런타임 **python3.12**, 아키텍처 **x86_64**
2. 코드 → 업로드 → `lambda.zip` (5MB 이하라 S3 없이 직접 올립니다)
3. 런타임 설정 → 핸들러 `lambda_handler.handler`
4. 구성 → 일반 구성: 메모리 512MB, 제한 시간 15초
5. 구성 → 환경 변수
   - `STORE_BACKEND` = `dynamodb`
   - `DYNAMODB_TABLE` = `verification-system`
   - `SECRET_KEY` = 임의의 긴 문자열(32자 이상)
   - `PSEUDONYM_SECRET` = 위와 다른 임의의 긴 문자열
   - `ORIGIN_VERIFY` = 또 다른 임의 문자열(5-3 의 헤더 값과 같아야 함)
6. 구성 → 권한 → 실행 역할에 인라인 정책 추가: 대상 표 하나에 대해서만
   `dynamodb:GetItem, PutItem, UpdateItem, DeleteItem, Query, TransactWriteItems, BatchGetItem` 허용
7. 구성 → 함수 URL 만들기 → 인증 유형(AuthType) **NONE**
   (CloudFront 의 OAC(AWS_IAM)는 브라우저가 보내는 JSON POST 에서 서명 불일치가 나서 쓰지 않습니다. 대신 `ORIGIN_VERIFY` 비밀 헤더로 CloudFront 를 거치지 않은 호출을 막습니다.)
8. 가능하면 구성 → 동시성 → **예약된 동시성 5** (새 계정은 허용되지 않을 수 있습니다. 안 되면 건너뜁니다.)

## 5. CloudFront 배포 만들기

1. 오리진: 함수 URL 의 호스트 이름(`https://` 와 끝 `/` 제외), 프로토콜 HTTPS 만
2. 오리진 사용자 지정 헤더: 이름 `x-origin-verify`, 값 = 4-5 의 `ORIGIN_VERIFY`
3. 동작(기본): 뷰어 프로토콜 **Redirect HTTP to HTTPS**, 허용 메서드 **GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE**,
   캐시 정책 **CachingDisabled**, 오리진 요청 정책은 **직접 만든 정책**(헤더 없음, 쿠키 전체, 쿼리스트링 전체). 관리형 `AllViewerExceptHostHeader` 를 쓰면 Lambda 함수 URL 이 CloudFront 경유 요청만 AccessDenied(403, `{"Message":null}`)로 거절했습니다(실제 배포에서 확인)
4. 요금제는 **무료(Free)** 를 고릅니다. WAF 는 켜지 않습니다(유료).
5. 배포 완료 후 `https://dXXXX.cloudfront.net` 가 서비스 주소입니다.

## 6. 요금 안전장치

- Billing → **예산** → 월 예산 **0.01달러**, 실제 사용액이 0.01달러를 넘으면 이메일 알림
- Billing → 무료 한도 알림(Free tier usage alerts) 켜기
- Cost Explorer 에서 서비스별 비용이 0 인지 주 1회 확인

## 7. 배포 후 점검 목록

| # | 점검 | 기대 결과 |
|---|---|---|
| 1 | `https://<주소>/healthz` | 200 |
| 2 | Lambda 함수 URL 을 **직접** 호출 | 403 (CloudFront 를 거쳐야만 통과) |
| 3 | 회원가입 → 로그인 → 내 정보 | 모두 성공, 쿠키에 Secure·HttpOnly |
| 4 | 로그아웃 후 이전 쿠키로 내 정보 | 401 |
| 5 | 틀린 비밀번호 5회 | 잠금(429), 15분 뒤 해제 |
| 6 | 같은 알고리즘 시험 신청 2회 | 두 번째는 409 |
| 7 | 시험 기관으로 승인 → 같은 신청 재승인 | 두 번째는 409 |
| 8 | 새로고침 후 로그인 유지 | 유지(세션이 DynamoDB 에 저장됨) |
| 9 | DynamoDB 표 항목 수·용량 모드 | 프로비저닝 10/10, 항목 생성됨 |
| 10 | 다음 날 Cost Explorer | 0달러 |

## 8. 한계

- 실제 AWS 에서의 동작은 위 점검 목록으로 확인해야 합니다. 자동 시험은 AWS 를 흉내 내는 도구(moto)로 합니다.
- 첫 요청은 1~2초 느릴 수 있습니다(콜드 스타트).
- 누군가 대량으로 호출하면 무료 한도를 넘을 수 있습니다. 예산 알림과 예약된 동시성이 방어선이며, 알림이 오면 함수 URL 을 비활성화하세요.
- 인증서·개인정보 저장은 아직 DynamoDB 에 구현되지 않았습니다(6단계에서 추가).

## 9. 업데이트·삭제

- 코드 수정 후: `bash deploy/build_lambda.sh` → Lambda 콘솔에서 다시 업로드
- 전체 삭제: CloudFront(비활성화 후 삭제) → Lambda → DynamoDB 순서
