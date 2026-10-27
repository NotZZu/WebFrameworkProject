"""AWS DynamoDB 구현 (서버리스 배포용).

테이블 하나, 키는 pk(문자열) + sk(문자열). 인덱스는 쓰지 않는다(인덱스 읽기는 '방금 쓴 값'이 안 보일 수 있어서,
기본 테이블의 강한 일관성 읽기만 쓴다). 프리티어의 '프로비저닝 25 읽기·25 쓰기 단위'를 넘지 않도록 테이블 하나로 끝낸다.

| 항목            | pk                    | sk                   | 설명 |
|-----------------|-----------------------|----------------------|------|
| 번호표          | COUNTER#user / app    | -                    | ADD 로 1씩 증가시켜 번호를 발급 |
| 사용자          | USER#<id>             | PROFILE              | |
| 아이디 잠금     | UNAME#<아이디>        | -                    | 같은 아이디 가입을 막는 잠금(조건부 저장) |
| 로그인 세션     | SESS#<sid>            | -                    | ttl(만료 시각) 속성으로 자동 삭제 |
| 신청 본체       | APP#<id>              | META                 | id 로 조회 |
| 신청 사본(본인) | USER#<user_id>        | APP#<시각>#<id>      | 본인 목록(최신순 조회용) |
| 신청 사본(전체) | ALL                   | APP#<시각>#<id>      | 기관 전체 목록 |
| 진행 중 잠금    | ACTIVE#<user>#<알고리즘> | -                 | 같은 알고리즘 진행 중 신청 1건 제한(DF-13) |
| 로그인 시도     | THROTTLE#<아이디>     | -                    | 실패 횟수·만료(DynamoThrottle) |
| 가명·익명 결과  | PI#<user_id>          | -                    | 사용자당 1건(마스킹된 값만, 원본 없음) |

신청의 본체·사본·잠금은 항상 한 트랜잭션으로 함께 바뀐다(쪼개면 목록과 상태가 어긋난다).
"""
import time
from datetime import datetime, timezone
from decimal import Decimal

from ..errors import DuplicateApplicationError, DuplicateUsernameError
from ..models import ActiveSession, CavpApplication, PersonalInfo, User
from .base import Store

SESSION_TTL_SECONDS = 7 * 24 * 3600
_TS = "%Y-%m-%dT%H:%M:%S.%f"
_RETRIES = 6


def table_spec(name: str) -> dict:
    """테이블 생성 정의(시험·문서 공용). 프리티어 한도 안(읽기 10·쓰기 10)의 프로비저닝 방식."""
    return {
        "TableName": name,
        "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"},
                                 {"AttributeName": "sk", "AttributeType": "S"}],
        "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        "BillingMode": "PROVISIONED",
        "ProvisionedThroughput": {"ReadCapacityUnits": 10, "WriteCapacityUnits": 10},
    }


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ts(dt: datetime) -> str:
    return dt.strftime(_TS)


def _dt(s: str) -> datetime:
    return datetime.strptime(s, _TS)


def _int(v) -> int:
    return int(v) if isinstance(v, (int, Decimal)) else int(str(v))


def _user(it) -> User:
    return User(id=_int(it["id"]), username=it["username"], password_hash=it["password_hash"],
                user_type=it["user_type"], org_code=it.get("org_code"), created_at=_dt(it["created_at"]))


def _app(it) -> CavpApplication:
    return CavpApplication(id=_int(it["id"]), user_id=_int(it["user_id"]), algorithm_type=it["algorithm_type"],
                           status=it["status"], submitted_at=_dt(it["submitted_at"]), updated_at=_dt(it["updated_at"]))


def _pinfo(it) -> PersonalInfo:
    return PersonalInfo(id=_int(it["user_id"]), user_id=_int(it["user_id"]), pseudonym_id=it.get("pseudonym_id"),
                        anonymization_level=it["level"], masked_display_value=it["masked"],
                        created_at=_dt(it["created_at"]))


def _reasons(exc) -> list:
    return [r.get("Code") for r in exc.response.get("CancellationReasons", [])]


class DynamoStore(Store):
    def __init__(self, table):
        self.table = table
        self.client = table.meta.client
        self.name = table.name

    # ---- 내부 도구 ----
    def _get(self, pk, sk="-"):
        return self.table.get_item(Key={"pk": pk, "sk": sk}, ConsistentRead=True).get("Item")

    def _next(self, counter) -> int:
        r = self.table.update_item(Key={"pk": f"COUNTER#{counter}", "sk": "-"}, UpdateExpression="ADD n :one",
                                   ExpressionAttributeValues={":one": 1}, ReturnValues="UPDATED_NEW")
        return _int(r["Attributes"]["n"])

    def _transact(self, items):
        """(성공 여부, 취소 사유 목록). 다른 트랜잭션과 겹쳤을 때(TransactionConflict)는 잠시 뒤 다시 시도한다."""
        exc = None
        for attempt in range(_RETRIES):
            try:
                self.client.transact_write_items(TransactItems=items)
                return True, []
            except self.client.exceptions.TransactionCanceledException as e:
                exc, codes = e, _reasons(e)
                if "TransactionConflict" not in codes:
                    return False, codes
                time.sleep(0.02 * (attempt + 1))
        return False, _reasons(exc)

    # ---- 사용자 ----
    def get_user(self, user_id):
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            return None
        it = self._get(f"USER#{user_id}", "PROFILE")
        return _user(it) if it else None

    def get_user_by_username(self, username):
        if not isinstance(username, str) or not username:
            return None
        lock = self._get(f"UNAME#{username}")
        return self.get_user(_int(lock["user_id"])) if lock else None

    def add_user(self, username, password_hash, user_type, org_code):
        uid, now = self._next("user"), _now()
        item = {"pk": f"USER#{uid}", "sk": "PROFILE", "id": uid, "username": username,
                "password_hash": password_hash, "user_type": user_type, "created_at": _ts(now)}
        if org_code is not None:
            item["org_code"] = org_code
        ok, codes = self._transact([
            {"Put": {"TableName": self.name, "Item": {"pk": f"UNAME#{username}", "sk": "-", "user_id": uid},
                     "ConditionExpression": "attribute_not_exists(pk)"}},
            {"Put": {"TableName": self.name, "Item": item}},
        ])
        if not ok:
            if codes and codes[0] == "ConditionalCheckFailed":
                raise DuplicateUsernameError("이미 사용 중인 아이디입니다.")
            raise RuntimeError(f"사용자 저장 실패: {codes}")
        return _user(item)

    def get_users_by_ids(self, ids) -> dict:
        out = {}
        for uid in set(ids):
            u = self.get_user(uid)
            if u is not None:
                out[uid] = u
        return out

    # ---- 로그인 세션 ----
    def add_session(self, sid, user_id):
        now = _now()
        self.table.put_item(Item={"pk": f"SESS#{sid}", "sk": "-", "sid": sid, "user_id": user_id,
                                  "created_at": _ts(now), "ttl": int(time.time()) + SESSION_TTL_SECONDS})

    def get_session(self, sid):
        if not isinstance(sid, str) or not sid:
            return None
        it = self._get(f"SESS#{sid}")
        if not it or _int(it["ttl"]) <= int(time.time()):  # 자동 삭제는 늦을 수 있으므로 만료를 직접 확인한다
            return None
        return ActiveSession(sid=it["sid"], user_id=_int(it["user_id"]), created_at=_dt(it["created_at"]))

    def delete_session(self, sid):
        if isinstance(sid, str) and sid:
            self.table.delete_item(Key={"pk": f"SESS#{sid}", "sk": "-"})

    # ---- 시험 신청 ----
    @staticmethod
    def _app_item(pk, sk, base):
        return dict(base, pk=pk, sk=sk)

    def create_application(self, user_id, algorithm_type):
        aid, now = self._next("app"), _now()
        list_sk = f"APP#{_ts(now)}#{aid:012d}"
        base = {"id": aid, "user_id": user_id, "algorithm_type": algorithm_type, "status": "submitted",
                "submitted_at": _ts(now), "updated_at": _ts(now), "list_sk": list_sk}
        put = lambda item, cond=None: {"Put": dict({"TableName": self.name, "Item": item},
                                                    **({"ConditionExpression": cond} if cond else {}))}
        ok, codes = self._transact([
            put({"pk": f"ACTIVE#{user_id}#{algorithm_type}", "sk": "-", "app_id": aid}, "attribute_not_exists(pk)"),
            put(self._app_item(f"APP#{aid}", "META", base)),
            put(self._app_item(f"USER#{user_id}", list_sk, base)),
            put(self._app_item("ALL", list_sk, base)),
        ])
        if not ok:
            if codes and codes[0] == "ConditionalCheckFailed":
                raise DuplicateApplicationError("같은 알고리즘의 진행 중인 신청이 있습니다.")
            raise RuntimeError(f"신청 저장 실패: {codes}")
        return _app(base)

    def get_application(self, application_id):
        if isinstance(application_id, bool) or not isinstance(application_id, int):
            return None
        it = self._get(f"APP#{application_id}", "META")
        return _app(it) if it else None

    def change_application_status(self, application_id, expected_status, new_status) -> bool:
        for _ in range(_RETRIES):
            meta = self._get(f"APP#{application_id}", "META") if isinstance(application_id, int) else None
            if not meta or meta["status"] != expected_status:
                return False
            now = _ts(_now())
            uid, algo, list_sk = _int(meta["user_id"]), meta["algorithm_type"], meta["list_sk"]

            def update(pk, sk):
                return {"Update": {"TableName": self.name, "Key": {"pk": pk, "sk": sk},
                                   "UpdateExpression": "SET #s = :new, updated_at = :now",
                                   "ConditionExpression": "attribute_exists(pk) AND #s = :exp",
                                   "ExpressionAttributeNames": {"#s": "status"},
                                   "ExpressionAttributeValues": {":new": new_status, ":now": now, ":exp": expected_status}}}
            items = [update(f"APP#{application_id}", "META"), update(f"USER#{uid}", list_sk), update("ALL", list_sk)]
            if new_status in ("approved", "rejected"):  # 끝난 신청은 진행 중 잠금을 푼다
                items.append({"Delete": {"TableName": self.name, "Key": {"pk": f"ACTIVE#{uid}#{algo}", "sk": "-"}}})
            ok, codes = self._transact(items)
            if ok:
                return True
            if "TransactionConflict" not in codes:
                return False  # 조건 불일치: 다른 요청이 먼저 상태를 바꿨다
        return False

    def _query_apps(self, pk, status=None):
        kw = {"KeyConditionExpression": "pk = :p AND begins_with(sk, :a)",
              "ExpressionAttributeValues": {":p": pk, ":a": "APP#"},
              "ScanIndexForward": False, "ConsistentRead": True}
        if status is not None:
            kw["FilterExpression"] = "#s = :st"
            kw["ExpressionAttributeNames"] = {"#s": "status"}
            kw["ExpressionAttributeValues"][":st"] = status
        items = []
        while True:
            r = self.table.query(**kw)
            items.extend(r["Items"])
            if "LastEvaluatedKey" not in r:
                return items
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]

    def list_applications(self, user_id, status, page, per_page):
        items = self._query_apps("ALL" if user_id is None else f"USER#{user_id}", status)
        start = (page - 1) * per_page
        return [_app(i) for i in items[start:start + per_page]], len(items)

    def all_applications(self, user_id):
        return [_app(i) for i in self._query_apps("ALL" if user_id is None else f"USER#{user_id}")]

    # ---- 검증서: 구현 전(6단계 SC-06 에서 추가). 지금은 저장되는 데이터가 없다. ----
    def list_certificates(self, user_id):
        return []

    # ---- 가명·익명 처리 결과 ----
    def get_personal_info(self, user_id):
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            return None
        it = self._get(f"PI#{user_id}")
        return _pinfo(it) if it else None

    def upsert_personal_info(self, user_id, level, new_pseudonym_id, masked_display_value):
        # 항목 하나를 한 번의 UpdateItem 으로 갱신한다: 가명 ID 는 '없을 때만' 채우므로 동시에 여러 번 불러도 하나로 유지된다.
        values = {":lv": level, ":mk": masked_display_value, ":uid": user_id, ":now": _ts(_now())}
        sets = "#lv = :lv, masked = :mk, user_id = :uid, created_at = if_not_exists(created_at, :now)"
        if level == "pseudonym":
            sets += ", pseudonym_id = if_not_exists(pseudonym_id, :pid)"
            values[":pid"] = new_pseudonym_id
            expr = "SET " + sets
        else:
            expr = "SET " + sets + " REMOVE pseudonym_id"
        r = self.table.update_item(Key={"pk": f"PI#{user_id}", "sk": "-"}, UpdateExpression=expr,
                                   ExpressionAttributeNames={"#lv": "level"}, ExpressionAttributeValues=values,
                                   ReturnValues="ALL_NEW")
        return _pinfo(r["Attributes"])


class DynamoThrottle:
    """로그인 시도 제한(DynamoDB). 아이디별로 '창(window)' 동안 최대 max_failures 번까지만 시도를 허용한다.
    검사와 기록은 조건부 UpdateItem 한 번으로 처리하므로, 여러 Lambda 가 동시에 받아도 한도를 넘지 못한다(DF-15)."""

    def __init__(self, table, max_failures=5, window_seconds=900, clock=time.time):
        """table 은 테이블 객체이거나, 호출할 때마다 (스레드에 맞는) 테이블을 돌려주는 함수."""
        self._table = table
        self.max, self.window, self.clock = max_failures, window_seconds, clock

    @property
    def table(self):
        return self._table() if callable(self._table) else self._table

    @property
    def client_errors(self):
        return self.table.meta.client.exceptions

    @staticmethod
    def _key(username):
        name = username.lower() if isinstance(username, str) else ""
        return {"pk": f"THROTTLE#{name}", "sk": "-"}

    def _row(self, username):
        return self.table.get_item(Key=self._key(username), ConsistentRead=True).get("Item")

    def is_blocked(self, username) -> bool:
        row = self._row(username)
        return bool(row and _int(row["ttl"]) > self.clock() and _int(row["cnt"]) >= self.max)

    def try_acquire(self, username) -> bool:
        key = self._key(username)
        for _ in range(4):
            now = int(self.clock())
            try:  # 1) 진행 중인 창에서 한도 미만이면 횟수를 1 올린다
                self.table.update_item(
                    Key=key, UpdateExpression="SET cnt = cnt + :one",
                    ConditionExpression="attribute_exists(pk) AND #t > :now AND cnt < :max",
                    ExpressionAttributeNames={"#t": "ttl"},
                    ExpressionAttributeValues={":one": 1, ":now": now, ":max": self.max})
                return True
            except self.client_errors.ConditionalCheckFailedException:
                pass
            try:  # 2) 창이 없거나 끝났으면 새 창을 시작한다
                self.table.update_item(
                    Key=key, UpdateExpression="SET cnt = :one, #t = :exp",
                    ConditionExpression="attribute_not_exists(pk) OR #t <= :now",
                    ExpressionAttributeNames={"#t": "ttl"},
                    ExpressionAttributeValues={":one": 1, ":now": now, ":exp": now + self.window})
                return True
            except self.client_errors.ConditionalCheckFailedException:
                pass
            row = self._row(username)  # 3) 두 경우가 아니면 한도에 도달한 상태(또는 동시에 창이 만들어져 다시 시도)
            if row and _int(row["ttl"]) > self.clock() and _int(row["cnt"]) >= self.max:
                return False
        return False

    def record_failure(self, username) -> None:
        self.try_acquire(username)

    def reset(self, username) -> None:
        self.table.delete_item(Key=self._key(username))
