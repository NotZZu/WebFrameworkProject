# 자동화 검증시스템 서비스 개선 및 확장 기능 개발

[![CI](https://github.com/NotZZu/WebFrameworkProject/actions/workflows/ci.yml/badge.svg)](https://github.com/NotZZu/WebFrameworkProject/actions/workflows/ci.yml)

인하공업전문대학 컴퓨터정보공학과(심화) **웹프레임워크** 교과목 팀별(1인) 프로젝트.

ETRI 부설 국가보안기술연구소가 발주한 실제 과업지시서 「자동화 검증시스템 서비스 개선 및 확장 기능 개발」을 벤치마킹하여, 축소된 웹 서비스 프로토타입과 **Selenium 기반 웹 테스트 자동화 프레임워크**를 15주간 1인이 구현하는 학습 프로젝트입니다.

- 팀원: 이상현 (학번 202647026) — 1인 팀, 전 역할 단독 수행
- 개발 기간: 15주 (분석 → 설계 → 구현 → 테스트 → 안정화)
- 핵심 목표: Selenium/POM 기반 테스트 자동화 프레임워크 구축, 반복 회귀 테스트 자동화

## 문서

| 문서 | 설명 | 원본 파일 |
|---|---|---|
| [`docs/rfp-original.md`](docs/rfp-original.md) | 원본 과업지시서 전문 (텍스트 추출본) | [HWP](assets/original/rfp-original.hwp) |
| [`docs/team-plan.md`](docs/team-plan.md) | 팀별 계획서 — 목적, 주요 기능, 15주 개발계획, 산출물, 기대효과 | [PPTX](assets/original/team-plan.pptx) · [PDF](assets/pdf/team-plan.pdf) |
| [`docs/requirements.md`](docs/requirements.md) | 요구사항 정의서 — 기능/비기능 요구사항, 우선순위(MoSCoW), 추적 매트릭스 | [DOCX](assets/original/requirements.docx) · [PDF](assets/pdf/requirements.pdf) |
| [`docs/system-design.md`](docs/system-design.md) | 시스템 설계서(v1.1) — 아키텍처, 클래스/컴포넌트 설계, 화면/DB/API 설계, 데이터 전환·초기데이터 설계, 요구사항 매핑 | [DOCX](assets/original/system-design.docx) · [PDF](assets/pdf/system-design.pdf) |
| 화면설계 · ERD (GitHub Pages) | 주요 화면 목업 5종(SC-01,02,04,06,07) 및 데이터베이스 ERD | https://notzzu.github.io/WebFrameworkProject/#screen-design |
| 사용자중심설계서 | 사용자 유형/페르소나, 사용자 시나리오, 유스케이스(UC-01~06), 화면 흐름도, 사용성 설계 원칙, 예외상황 UX | [DOCX](assets/original/ucd.docx) · [PDF](assets/pdf/ucd.pdf) |
| 시험계획서 | 총괄시험계획, 시스템/통합 시험 시나리오, 단위시험 케이스 통합 문서 | [DOCX](assets/original/testplan.docx) · [PDF](assets/pdf/testplan.pdf) |

발표용 웹페이지(GitHub Pages)에서는 위 원본 문서를 마크다운 요약과 함께 뷰어로 바로 열람할 수 있습니다: https://notzzu.github.io/WebFrameworkProject/

## 프로젝트 범위 (요약)

**포함**: 로그인, 가명·익명처리 모의, CAVP 신청/조회, 검증서 이력/위변조 표시(더미 데이터) + POM 기반 테스트 자동화, 회귀 스위트, HTML 리포트

**제외**: 실제 암호모듈 시험 로직, 실 개인정보 DB 연동, 운영 배포, 성능/부하 전문 테스트

자세한 내용은 [`docs/requirements.md`](docs/requirements.md)를 참고하세요.

## 개발 단계

| 단계 | 기간 | 핵심 활동 |
|---|---|---|
| 분석 | 1~2주 | 과업지시서 분석, 범위/일정 확정, 기술스택 선정, 요구사항 정의서 작성 |
| 설계 | 3~5주 | 웹 서비스 화면·DB 설계, 테스트 시나리오/케이스 설계, POM 아키텍처 설계 |
| 구현 | 6~10주 | 웹 서비스 핵심 기능 구현, Selenium 테스트 스크립트/프레임워크 구현 |
| 테스트 | 11~13주 | 단위/연동 테스트 자동화 실행, 결함 수정, 회귀 테스트 재실행 |
| 안정화 | 14~15주 | 결과 보완, 최종 점검, 매뉴얼·산출물 정리, 발표자료 준비 |

진행 상황과 세부 작업은 이 저장소의 [Issues](../../issues)에서 관리합니다.

## 개발 방식 (TDD + 자동 병합)

1. 서브 브랜치(`feature/*`, `fix/*`)에서 개발 → `python webservice/tools/ship.py "커밋 메시지"` 로 푸시
2. GitHub Actions 가 main 과 합친 상태로 단위·통합·브라우저 E2E 테스트 자동 실행
3. **전부 통과하면 main 에 자동 병합**(실패하면 병합되지 않고 브랜치 유지)
4. 병합 후 `python webservice/tools/ship.py --sync` 로 로컬 main 최신화

아직 구현하지 않은 케이스는 `webservice/tests/red_cases.txt` 에 등록(기대된 실패, xfail strict). 구현해서 통과하면 목록에서 삭제합니다. 목록에 남은 케이스가 예기치 않게 통과해도 CI 가 실패하므로 목록 관리가 강제됩니다.

CI 가 추가로 수행하는 것: 커밋 메시지 규칙 검사 · 커버리지 하한선(`webservice/tools/coverage_floor.txt`, 올리기만 가능) · 케이스 ID별 **시험결과서(HTML)** 와 브라우저 E2E 스크린샷을 결과물(Artifacts)로 보관.
