"""웹 서비스 실행: python run.py  → http://127.0.0.1:5000
환경변수: DATABASE_URL(기본 sqlite:///app.db), SECRET_KEY·PSEUDONYM_SECRET(필수), PORT(기본 5000), HOST(기본 127.0.0.1),
  COOKIE_SECURE(기본 1; 로컬 HTTP 개발은 0), FLASK_DEBUG=1 이면 개발용 기본 키로도 기동
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")),
            debug=os.environ.get("FLASK_DEBUG") == "1")
