#!/usr/bin/env bash
# Lambda 배포용 zip 만들기:  bash deploy/build_lambda.sh [출력파일(기본 lambda.zip)]
# Lambda(python3.12, x86_64)에서 돌도록 맞는 바퀴(wheel)만 받아 담는다. AWS 계정·자격 증명은 필요 없다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(realpath -m "${1:-$ROOT/lambda.zip}")"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

python3 -m pip install --quiet --no-compile --target "$BUILD" \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all: \
  -r "$ROOT/webservice/requirements-lambda.txt"
cp -r "$ROOT/webservice/app" "$ROOT/webservice/lambda_handler.py" "$BUILD/"
find "$BUILD" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$BUILD" -name "*.dist-info" -type d -prune -exec rm -rf {} +
rm -f "$OUT"
(cd "$BUILD" && python3 -c "
import os, sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w', zipfile.ZIP_DEFLATED) as z:
    for d, _, fs in os.walk('.'):
        for f in fs:
            p = os.path.join(d, f); z.write(p, os.path.relpath(p, '.'))
" "$OUT")
echo "만들었습니다: $OUT ($(du -h "$OUT" | cut -f1))"
