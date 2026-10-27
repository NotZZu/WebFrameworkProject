"""도구 시험: 배포 파일(deploy/, requirements-lambda.txt) — 요금이 생길 수 있는 구성이 다시 섞여 들어오지 않도록 CI 에서 걸러낸다."""
import pathlib
import re
import subprocess
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy"
pytestmark = pytest.mark.skipif(not DEPLOY.exists(), reason="배포 파일(deploy/) 없음")


def test_옛_EC2_구성_파일이_남아있지_않다():
    for name in ("cloudformation.yml", "bootstrap.sh", "update.sh", "docker-compose.yml", "Dockerfile.service",
                 "Dockerfile.demo", "service.env"):
        assert not (DEPLOY / name).exists(), f"{name}: 요금이 생길 수 있는 EC2 구성은 쓰지 않는다"


def test_배포_파일에_유료_자원_이름이_없다():
    text = "\n".join(p.read_text(encoding="utf-8") for p in (DEPLOY / "build_lambda.sh", ))
    text += (ROOT / "webservice" / "requirements-lambda.txt").read_text(encoding="utf-8")
    for word in ("ElasticIP", "AWS::EC2", "AWS::RDS", "NatGateway", "ApiGateway"):
        assert word not in text


def test_빌드_스크립트_문법과_Lambda용_바퀴_지정():
    script = DEPLOY / "build_lambda.sh"
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0
    body = script.read_text(encoding="utf-8")
    assert "manylinux2014_x86_64" in body and "--python-version 3.12" in body and "--only-binary=:all:" in body


def test_Lambda_requirements에_boto3가_없다():
    reqs = (ROOT / "webservice" / "requirements-lambda.txt").read_text(encoding="utf-8")
    names = {re.split(r"[<>=!~ ]", ln)[0].lower() for ln in reqs.splitlines() if ln.strip() and not ln.startswith("#")}
    assert {"flask", "sqlalchemy", "bcrypt"} <= names and "boto3" not in names


def test_안내서에_무료_범위_설정이_모두_있다():
    doc = (DEPLOY / "README.md").read_text(encoding="utf-8")
    for must in ("프로비저닝", "10", "TTL", "ttl", "lambda_handler.handler", "python3.12", "x86_64", "AuthType", "NONE",
                 "CachingDisabled", "예산", "SECRET_KEY", "PSEUDONYM_SECRET", "DYNAMODB_TABLE", "삭제"):
        assert must in doc, f"deploy/README.md 에 '{must}' 설명이 있어야 한다"
    assert not re.search(r"(AKIA|aws_secret_access_key\s*=\s*\S{20})", doc)


def test_zip을_만들면_핸들러와_앱이_들어있다(tmp_path):
    out = tmp_path / "l.zip"
    r = subprocess.run(["bash", str(DEPLOY / "build_lambda.sh"), str(out)], capture_output=True, text=True, timeout=240)
    if r.returncode != 0 and ("Could not find a version" in r.stderr or "Connection" in r.stderr or "No matching" in r.stderr):
        pytest.skip("패키지 내려받기 불가(오프라인)")
    assert r.returncode == 0, r.stderr
    names = set(zipfile.ZipFile(out).namelist())
    assert "lambda_handler.py" in names and "app/__init__.py" in names
    assert not any(n.startswith("boto3/") for n in names)
