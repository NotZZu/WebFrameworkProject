"""로그인 시도 제한(DF-02). 아이디별로 연속 실패를 세어 일정 횟수를 넘으면 잠시 막는다.

- 없는 아이디도 똑같이 센다(계정 존재 여부를 응답으로 드러내지 않기 위해).
- 프로세스 메모리에 둔다: 서비스는 gunicorn 워커 1개로 돌고, 재시작하면 초기화된다.
"""
import threading
import time


class LoginThrottle:
    def __init__(self, max_failures=5, window_seconds=900, max_keys=10000, clock=time.monotonic):
        self.max_failures, self.window, self.max_keys, self.clock = max_failures, window_seconds, max_keys, clock
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(username) -> str:
        return username.lower() if isinstance(username, str) else ""

    def _recent(self, key, now):
        recent = [t for t in self._fails.get(key, []) if now - t < self.window]
        if recent:
            self._fails[key] = recent
        else:
            self._fails.pop(key, None)
        return recent

    def is_blocked(self, username) -> bool:
        with self._lock:
            return len(self._recent(self._key(username), self.clock())) >= self.max_failures

    def try_acquire(self, username) -> bool:
        """시도 한 번을 '검사 + 기록'을 한 번에 처리한다. 막혀 있으면 False.
        동시에 들어온 요청도 비밀번호를 확인하기 전에 이 자리를 먼저 차지해야 하므로 한도를 넘길 수 없다(DF-15)."""
        with self._lock:
            now = self.clock()
            key = self._key(username)
            if len(self._recent(key, now)) >= self.max_failures:
                return False
            self._add(key, now)
            return True

    def _add(self, key, now) -> None:
        if len(self._fails) >= self.max_keys:
            for k in list(self._fails):
                self._recent(k, now)
            if len(self._fails) >= self.max_keys:
                self._fails.pop(next(iter(self._fails)))
        self._fails.setdefault(key, []).append(now)

    def record_failure(self, username) -> None:
        with self._lock:
            self._add(self._key(username), self.clock())

    def reset(self, username) -> None:
        with self._lock:
            self._fails.pop(self._key(username), None)
