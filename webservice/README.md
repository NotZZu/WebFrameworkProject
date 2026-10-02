# 자동화 검증시스템 웹 서비스 (TDD 진행 중)

현재 구현 완료: **SC-01 로그인/회원가입** (AuthService, /api/auth/*). 나머지 화면은 시험 코드(Red)만 있습니다.

## 실행 (Python 3.10+)
```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py                      # → http://127.0.0.1:5000  (DB 파일: app.db 자동 생성)
```
환경변수: `PORT`, `HOST`, `DATABASE_URL`, `SECRET_KEY`, `FLASK_DEBUG=1`(자동 재시작)

## 시험
```bash
pytest                              # 전체 (현재 83 통과 · 171 실패(미구현 화면) · 3 건너뜀)
pytest tests/unit/test_auth_service.py tests/integration/test_api_auth.py   # SC-01 범위
pip install playwright && playwright install chromium
pytest tests/e2e                    # 브라우저 E2E (ST-01)
python scripts/export_cases.py      # @case 메타데이터 → cases.json
```

## 구조
`app/services/*` 서비스 · `app/api/*` REST API · `app/pages.py`+`app/templates` 화면 · `tests/{unit,integration,e2e}`

## 시험 관리 엑셀
`python tools/update_tracker.py --run` → `tracker/테스트관리.xlsx` 갱신 (대시보드 / 케이스관리 / 케이스별결과 / 실행이력). 노란 칸(화면·우선순위·비고)만 직접 수정.
