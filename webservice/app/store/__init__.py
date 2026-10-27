"""저장소 계층. 서비스 코드는 데이터베이스 종류를 모르고 이 인터페이스만 사용한다.

- SqlStore: SQLAlchemy(SQLite·PostgreSQL 등). 로컬 개발·시험과 기존 서버 배포에 쓴다.
- DynamoStore: AWS DynamoDB. 서버리스(Lambda) 배포에 쓴다(boto3 는 쓸 때만 불러온다).

두 구현은 같은 계약 시험(tests/contract)을 통과해야 한다. 반환 값은 app.models 의 객체이다
(DynamoDB 구현은 DB 에 연결되지 않은 객체를 만들어 돌려준다).
"""
from .base import Store, as_store
from .sql import SqlStore

__all__ = ["Store", "SqlStore", "as_store"]
