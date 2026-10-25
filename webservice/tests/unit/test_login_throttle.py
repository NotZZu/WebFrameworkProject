"""단위시험 — 로그인 시도 제한(DF-02 수정 검증)."""
from app.throttle import LoginThrottle
from tests.case_registry import case


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@case("UT-ATK-01", "FR-01", "LoginThrottle: 5회 실패 전까지는 막지 않고 5회째부터 차단", "4회 실패 후 차단 아님, 5회 후 차단", "boundary")
def test_blocks_at_limit():
    th = LoginThrottle(max_failures=5, window_seconds=900, clock=Clock())
    for _ in range(4):
        th.record_failure("alice01")
    assert not th.is_blocked("alice01")
    th.record_failure("alice01")
    assert th.is_blocked("alice01")


@case("UT-ATK-02", "FR-01", "LoginThrottle: 시간이 지나면 풀리고, 성공하면 초기화되며, 아이디는 대소문자 무관/서로 독립",
      "15분 경과 후 해제, reset 후 해제, ALICE01 도 같은 계정으로 계산, 다른 아이디는 영향 없음", "boundary")
def test_expiry_reset_and_isolation():
    clock = Clock()
    th = LoginThrottle(max_failures=3, window_seconds=900, clock=clock)
    for _ in range(3):
        th.record_failure("ALICE01")
    assert th.is_blocked("alice01") and not th.is_blocked("bob0001")
    clock.t = 901
    assert not th.is_blocked("alice01")
    for _ in range(3):
        th.record_failure("alice01")
    th.reset("alice01")
    assert not th.is_blocked("alice01")


@case("UT-ATK-03", "FR-01", "LoginThrottle: 서로 다른 아이디를 대량으로 시도해도 기억하는 개수가 상한을 넘지 않음", "max_keys 이하로 유지", "boundary")
def test_memory_is_bounded():
    th = LoginThrottle(max_failures=5, max_keys=100, clock=Clock())
    for i in range(1000):
        th.record_failure(f"user{i}")
    assert len(th._fails) <= 100


@case("UT-ATK-04", "FR-01", "LoginThrottle.try_acquire: 검사와 기록이 한 번에 처리되어 한도(5)를 넘는 시도는 모두 거부",
      "처음 5번은 True, 이후는 False, 아이디가 달라도 대소문자 무관, reset 후 다시 허용", "security")
def test_try_acquire_is_atomic_gate():
    th = LoginThrottle(max_failures=5, window_seconds=900, clock=Clock())
    assert [th.try_acquire("Victim01") for _ in range(8)] == [True] * 5 + [False] * 3
    assert th.try_acquire("other001")
    th.reset("victim01")
    assert th.try_acquire("VICTIM01")
