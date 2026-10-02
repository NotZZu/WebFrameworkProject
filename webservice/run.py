"""웹 서비스 실행: python run.py  → http://127.0.0.1:5000
환경변수: DATABASE_URL(기본 sqlite:///app.db), SECRET_KEY, PORT(기본 5000), HOST(기본 127.0.0.1)
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")),
            debug=os.environ.get("FLASK_DEBUG") == "1")
