"""AWS Lambda 진입점 — 함수 URL(payload format 2.0) 이벤트를 Flask(WSGI) 요청으로 바꿔 실행한다.

Lambda 환경변수: STORE_BACKEND=dynamodb, DYNAMODB_TABLE, SECRET_KEY, PSEUDONYM_SECRET,
  (선택) ORIGIN_VERIFY — CloudFront 가 붙여 주는 비밀 헤더(x-origin-verify) 값. 설정하면 이 헤더가 없는 직접 호출은 403.
핸들러 지정: lambda_handler.handler
"""
import base64
import hmac
import io
import os
from urllib.parse import urlencode

from werkzeug.wrappers import Response

_app = None


def _get_app():
    global _app
    if _app is None:  # 콜드 스타트 때 한 번만 만든다
        from app import create_app
        _app = create_app({"STORE_BACKEND": os.environ.get("STORE_BACKEND", "dynamodb")})
    return _app


def _response(status, body, content_type="text/plain; charset=utf-8"):
    return {"statusCode": status, "headers": {"content-type": content_type}, "body": body}


def build_environ(event):
    http = event["requestContext"]["http"]
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = event.get("body") or ""
    raw = base64.b64decode(body) if event.get("isBase64Encoded") else body.encode("utf-8")
    environ = {
        "REQUEST_METHOD": http["method"],
        "SCRIPT_NAME": "",
        "PATH_INFO": event.get("rawPath", "/"),
        "QUERY_STRING": event.get("rawQueryString", ""),
        "SERVER_NAME": headers.get("host", "lambda"),
        "SERVER_PORT": "443",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "REMOTE_ADDR": http.get("sourceIp", ""),
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": headers.get("x-forwarded-proto", "https"),
        "wsgi.input": io.BytesIO(raw),
        "wsgi.errors": io.StringIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "CONTENT_LENGTH": str(len(raw)),
    }
    for name, value in headers.items():
        if name == "content-type":
            environ["CONTENT_TYPE"] = value
        elif name != "content-length":
            environ["HTTP_" + name.upper().replace("-", "_")] = value
    if event.get("cookies"):  # 함수 URL 은 쿠키를 헤더에서 떼어 따로 준다
        environ["HTTP_COOKIE"] = "; ".join(event["cookies"])
    return environ


def handler(event, context=None):
    secret = os.environ.get("ORIGIN_VERIFY", "")
    if secret:
        given = (event.get("headers") or {}).get("x-origin-verify", "")
        if not hmac.compare_digest(given.encode(), secret.encode()):
            return _response(403, "forbidden")
    try:
        app = _get_app()
        res = Response.from_app(app.wsgi_app, build_environ(event))
    except Exception:  # 설정 오류 등 — 상세는 CloudWatch 로그로만 남긴다
        import traceback
        traceback.print_exc()
        return _response(500, "internal error")
    out = {"statusCode": res.status_code, "headers": {}, "cookies": []}
    for key, value in res.headers:
        if key.lower() == "set-cookie":
            out["cookies"].append(value)
        else:  # 같은 이름이 여러 번이면 쉼표로 합친다
            k = key.lower()
            out["headers"][k] = f"{out['headers'][k]},{value}" if k in out["headers"] else value
    data = res.get_data()
    ctype = res.mimetype or ""
    if ctype.startswith("text/") or ctype in ("application/json", "application/javascript", "image/svg+xml"):
        out["body"] = data.decode("utf-8")
    else:
        out["body"] = base64.b64encode(data).decode("ascii")
        out["isBase64Encoded"] = True
    return out
