"""일별 이용 현황 집계 — v0.61.0.

무엇을 하는가(비프로그래머용): 원격(HTTP) 서버에서 하루(KST) 동안의
  - users: 도구를 써서 결과를 받은 서로 다른 API Key 수. 키 없음·health만 부른 경우·결과가 없는 호출
    (없는 도구·인자 오류·도구 예외)은 빠진다. 그날 인증 실패(auth_failed)로 결과를 받지 못한 키는 그날 내내 빠진다
    (일부 트랙만 인증 오류인 키는 결과를 받으므로 이용자 — 2026-10-27 diff 검토에서 정의로 확정).
  - http_requests: 서버 입구에 도착한 모든 HTTP 요청 수(연결 유지 요청 포함)
  - tool_calls: 도구 호출 수(결과가 없는 호출 포함)
를 메모리에서 세고, 10분 구간이 바뀐 뒤 첫 요청과 부팅·자정 뒤 첫 요청 때 서버 로그에 숫자 한 줄을 남긴다.
줄은 그 시점까지의 누적값이다. 마지막 줄 이후 프로세스가 끝나기 전까지의 요청은 로그에 남지 않는다.

개인정보·보안 원칙(2026-10-26·27 Redteam 검토):
  - 로그에는 날짜·숫자·부팅 표지·줄 번호만 남긴다. 키·키의 해시·IP·검색어·도구 이름은 쓰지 않는다.
  - 이용자 구분은 메모리 안에서만, 그날의 무작위 값(salt)으로 만든 HMAC으로 한다. salt와 집합은
    날짜가 바뀐 뒤 첫 요청 때와 재시작 때 버린다. 그래서 재시작이 있은 날의 이용자 수는 부팅별 값의 범위로만 알 수 있다.
  - 집계 실패는 절대 요청을 실패시키지 않는다(모든 진입점 never-raise).
  - stdio(로컬) 실행에서는 켜지지 않는다(enable()은 --http 경로에서만 호출).
  - 도구 호출은 끝난 시각의 날짜에 넣는다(HTTP 요청은 도착 시각 — 자정을 걸친 호출은 두 날에 나뉠 수 있음).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("rnd-regs-mcp")

_KST = timezone(timedelta(hours=9))
_KEY_SET_CAP = 10_000  # 이용자·실패 키 집합 합계 상한(약 16바이트 × 1만). 넘으면 더 세지 않고 saturated=1.
_EXCLUDED_FROM_USERS = frozenset({"health"})
_BUCKET_MINUTES = 10

# note_tool_call의 outcome 값
OUTCOME_OK = "ok"
OUTCOME_AUTH_FAILED = "auth_failed"
OUTCOME_NO_RESULT = "no_result"


class _UsageStats:
    def __init__(self, now: datetime | None = None) -> None:
        self._lock = threading.Lock()
        self._enabled = False
        self._boot = secrets.token_hex(4)
        self._seq = 0
        self._reset_day((now or datetime.now(_KST)).astimezone(_KST))

    # --- 내부 상태 ---------------------------------------------------------
    def _reset_day(self, now: datetime) -> None:
        self._date = now.date()
        self._bucket: tuple[int, int] | None = None  # None = 다음 요청 때 바로 한 줄
        self._salt = secrets.token_bytes(32)
        self._users: set[bytes] = set()
        self._failed: set[bytes] = set()
        self._saturated = False
        self._http_requests = 0
        self._tool_calls = 0

    def _line(self, final: bool) -> str:
        self._seq += 1
        return (
            f"event=daily_usage date={self._date.isoformat()} final={int(final)} boot={self._boot} "
            f"seq={self._seq} users={len(self._users)} http_requests={self._http_requests} "
            f"tool_calls={self._tool_calls} saturated={int(self._saturated)}"
        )

    def _before_count(self, now: datetime) -> list[str]:
        """날짜가 넘어갔으면 전날 최종 줄을 만들고 새 날로 넘어간다(잠금 안·세기 전).

        시계가 뒤로 보정돼 이전 날짜가 오면 넘어가지 않고 지금 날짜에 센다(이미 센 날을 지우지 않게).
        """
        if now.date() > self._date:
            line = self._line(final=True)
            self._reset_day(now)
            return [line]
        return []

    def _after_count(self, now: datetime) -> list[str]:
        """10분 구간이 바뀌었으면 현재 요청까지 포함한 중간 줄을 만든다(잠금 안·센 뒤)."""
        bucket = (now.hour, now.minute // _BUCKET_MINUTES)
        if bucket != self._bucket:
            self._bucket = bucket
            return [self._line(final=False)]
        return []

    def _digest(self, api_key: str) -> bytes:
        return hmac.new(self._salt, api_key.encode("utf-8"), hashlib.sha256).digest()[:16]

    def _room(self) -> bool:
        if len(self._users) + len(self._failed) < _KEY_SET_CAP:
            return True
        self._saturated = True
        return False

    # --- 공개 진입점(전부 never-raise) -------------------------------------
    def enable(self) -> None:
        self._enabled = True

    def note_http_request(self, now: datetime | None = None) -> None:
        if not self._enabled:
            return
        try:
            now = (now or datetime.now(_KST)).astimezone(_KST)
            with self._lock:
                lines = self._before_count(now)
                self._http_requests += 1
                lines += self._after_count(now)
            for line in lines:
                logger.info(line)
        except Exception:  # noqa: BLE001 — 집계가 요청을 막지 않게
            pass

    def note_tool_call(self, tool_name: str, api_key: str, outcome: str,
                       now: datetime | None = None) -> None:
        if not self._enabled:
            return
        try:
            now = (now or datetime.now(_KST)).astimezone(_KST)
            with self._lock:
                lines = self._before_count(now)
                self._tool_calls += 1
                if api_key and tool_name not in _EXCLUDED_FROM_USERS:
                    digest = self._digest(api_key)
                    if outcome == OUTCOME_AUTH_FAILED:
                        self._users.discard(digest)
                        if digest not in self._failed and self._room():
                            self._failed.add(digest)
                    elif outcome == OUTCOME_OK and digest not in self._failed and digest not in self._users:
                        if self._room():
                            self._users.add(digest)
                lines += self._after_count(now)
            for line in lines:
                logger.info(line)
        except Exception:  # noqa: BLE001
            pass

    def snapshot(self) -> dict:
        """테스트·진단용 — 숫자만 돌려준다."""
        with self._lock:
            return {"date": self._date.isoformat(), "boot": self._boot, "seq": self._seq,
                    "users": len(self._users), "http_requests": self._http_requests,
                    "tool_calls": self._tool_calls, "saturated": self._saturated}


def classify_result(result: object) -> str:
    """도구 결과 → outcome. never-raise.

    결과 없음(없는 도구·인자 오류·도구 예외로 call_next가 예외를 냄) = no_result.
    errors에 auth_failed가 있고 받은 결과(results·candidates)가 비었으면 auth_failed.
    (일부 트랙만 막힌 키는 결과를 받으므로 이용자로 센다.)
    """
    try:
        if result is None:
            return OUTCOME_NO_RESULT
        sc = getattr(result, "structured_content", None)
        if not isinstance(sc, dict):
            return OUTCOME_OK
        errors = sc.get("errors")
        if not isinstance(errors, list):
            return OUTCOME_OK
        if any(isinstance(e, dict) and e.get("code") == "auth_failed" for e in errors):
            if not any(sc.get(k) for k in ("results", "candidates")):
                return OUTCOME_AUTH_FAILED
        return OUTCOME_OK
    except Exception:  # noqa: BLE001
        return OUTCOME_OK


try:
    stats = _UsageStats()
except Exception:  # noqa: BLE001 — 생성 실패 시 집계 없이 서버는 그대로(enable해도 꺼진 객체처럼 동작)
    class _Disabled:
        def enable(self) -> None: ...
        def note_http_request(self, *a, **k) -> None: ...
        def note_tool_call(self, *a, **k) -> None: ...
        def snapshot(self) -> dict:
            return {}
    stats = _Disabled()  # type: ignore[assignment]
