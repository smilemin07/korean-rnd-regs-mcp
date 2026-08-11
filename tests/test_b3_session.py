"""v0.48.0 (B3) 가드 — thread-local keep-alive Session 재사용 + bare 의미론 보존 불변식.

네트워크 없음(requests.Session·_http_get을 fake로 대체 + 소스 정적 검사).
설계 불변식(계획 /disc 3-AI 수렴)을 잠근다:
  같은 스레드 재사용 / 스레드 간 격리 / 호출 전후 쿠키 비움 / 전송 오류 시 Session 폐기 /
  Session 생성 실패 시 bare 폴백 / lazy 생성(import·health 경로 소켓 0) /
  trust_env·adapter retry·pool sizing 기본값 불변(정적).
"""
import asyncio
import inspect
import threading
from pathlib import Path

import pytest
import requests

from korean_rnd_regs_mcp import live_api
from korean_rnd_regs_mcp.live_api import (
    LawApiError,
    _discard_thread_session,
    _http_get,
    _request_with_retry,
    _thread_http,
)


@pytest.fixture(autouse=True)
def _clean_thread_session():
    """각 테스트 전후 현재 스레드의 Session 상태를 비움 — fake Session이 타 테스트로 새지 않게."""
    _thread_http.session = None
    yield
    _thread_http.session = None


class FakeCookieJar:
    def __init__(self):
        self.items = {}
        self.clear_calls = 0

    def clear(self):
        self.clear_calls += 1
        self.items = {}


class FakeResponse:
    status_code = 200
    headers: dict = {}
    text = "<xml/>"
    content = b"<xml/>"


class FakeSession:
    """requests.Session 대역 — 생성·get·close 호출을 계수."""
    instances: list = []

    def __init__(self):
        self.cookies = FakeCookieJar()
        self.get_calls = 0
        self.closed = False
        self.cookies_at_get = []  # get 시점의 쿠키 스냅샷(사전 clear 검증)
        FakeSession.instances.append(self)

    def get(self, url, params=None, timeout=None, **kwargs):
        self.get_calls += 1
        self.cookies_at_get.append(dict(self.cookies.items))
        # 서버가 Set-Cookie를 심는 상황 시뮬레이션
        self.cookies.items["WMONID"] = "fake"
        return FakeResponse()

    def close(self):
        self.closed = True


@pytest.fixture()
def fake_session_cls(monkeypatch):
    FakeSession.instances = []
    monkeypatch.setattr(live_api.requests, "Session", FakeSession)
    return FakeSession


def test_same_thread_session_reused(fake_session_cls):
    """같은 스레드의 연속 호출은 Session 1개를 재사용(연결 재사용의 전제)."""
    _http_get("https://test.invalid/a", {"OC": "x"}, (8.0, 12.0))
    _http_get("https://test.invalid/b", {"OC": "x"}, (8.0, 12.0))
    assert len(fake_session_cls.instances) == 1
    assert fake_session_cls.instances[0].get_calls == 2


def test_cross_thread_session_isolated(fake_session_cls):
    """다른 스레드는 다른 Session — 전역 공유 Session(스레드 경합) 금지 불변식."""
    def worker():
        _http_get("https://test.invalid/t", {"OC": "x"}, (8.0, 12.0))
        _thread_http.session = None  # worker 스레드 정리

    _http_get("https://test.invalid/m", {"OC": "x"}, (8.0, 12.0))
    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert len(fake_session_cls.instances) == 2


def test_cookies_cleared_before_and_after_each_call(fake_session_cls):
    """호출 직전·직후 쿠키 비움 — bare requests.get(빈 쿠키 시작)과 요청 동일성 유지 +
    사용자(oc) 간 쿠키 이월 차단. 서버가 Set-Cookie를 심어도 다음 호출은 빈 쿠키로 시작."""
    _http_get("https://test.invalid/a", {"OC": "u1"}, (8.0, 12.0))
    sess = fake_session_cls.instances[0]
    assert sess.cookies.items == {}, "호출 종료 후 쿠키가 남아 있음(finally clear 실패)"
    _http_get("https://test.invalid/b", {"OC": "u2"}, (8.0, 12.0))
    # 두 번째 get 시점에 첫 호출의 쿠키가 보이면 안 됨(사전 clear 검증)
    assert sess.cookies_at_get[1] == {}, "이전 호출 쿠키가 다음 요청으로 이월됨"
    assert sess.cookies.clear_calls >= 3  # 1회차 후 1 + 2회차 전 1·후 1(신규 Session은 빈 jar라 사전 clear 생략)


def test_cookie_clear_failure_fails_closed(fake_session_cls):
    """쿠키 clear() 실패 시 해당 Session 폐기(fail-closed) — 격리 불변식이 clear 실패에도 유지.
    (diff 적대검토 Codex MINOR: 종전 fail-open[예외 삼키고 같은 Session 계속]의 이월 반례 차단.)"""
    _http_get("https://test.invalid/a", {"OC": "u1"}, (8.0, 12.0))
    s1 = fake_session_cls.instances[0]

    def broken_clear():
        raise RuntimeError("jar corrupted")

    s1.cookies.clear = broken_clear  # 사전 clear가 실패하는 상황 주입
    _http_get("https://test.invalid/b", {"OC": "u2"}, (8.0, 12.0))
    assert len(fake_session_cls.instances) == 2, "clear 실패 Session을 폐기하고 새 Session이어야 함"
    assert s1.closed is True
    s2 = fake_session_cls.instances[1]
    assert s2.cookies_at_get[0] == {}, "새 Session은 빈 쿠키로 시작해야 함(이월 차단)"


def test_post_call_clear_failure_fails_closed(fake_session_cls):
    """사후(finally) clear() 실패 시에도 Session 폐기 + 반환 Response는 무손상.
    (Codex 재검증 비차단 보강점 — 사전 실패 테스트만으로는 finally 경로 미커버.)"""
    _http_get("https://test.invalid/a", {"OC": "u1"}, (8.0, 12.0))  # 사후 clear #1(성공)
    s1 = fake_session_cls.instances[0]
    orig_clear = s1.cookies.clear
    n = {"c": 1}

    def counting_clear():
        n["c"] += 1
        if n["c"] == 3:  # 2회차 호출의 사후 clear에서만 실패(사전 #2는 성공)
            raise RuntimeError("boom on post-clear")
        orig_clear()

    s1.cookies.clear = counting_clear
    resp = _http_get("https://test.invalid/b", {"OC": "u2"}, (8.0, 12.0))
    assert resp.status_code == 200, "폐기가 반환 Response를 훼손하면 안 됨(stream=False·본문 기적재)"
    assert s1.closed is True
    assert getattr(_thread_http, "session", None) is None


def test_request_exception_discards_session_then_retry_uses_fresh(fake_session_cls, monkeypatch):
    """전송 오류(RequestException) 시 해당 Session 폐기 — 다음 attempt는 새 Session(새 연결 풀).
    stale keep-alive(서버측 idle 종료 후 재사용 실패) 격리 경로."""
    monkeypatch.setattr(live_api.time, "sleep", lambda s: None)  # backoff 대기 제거

    fail_first = {"n": 0}

    def flaky_get(self, url, params=None, timeout=None, **kwargs):
        fail_first["n"] += 1
        if fail_first["n"] == 1:
            raise requests.exceptions.ConnectionError("stale keep-alive")
        return FakeResponse()

    monkeypatch.setattr(FakeSession, "get", flaky_get)
    resp = _request_with_retry("https://test.invalid", {"OC": "x"}, max_retries=2)
    assert resp.status_code == 200
    assert len(fake_session_cls.instances) == 2, "폐기 후 새 Session으로 재시도해야 함"
    assert fake_session_cls.instances[0].closed is True
    assert fake_session_cls.instances[1].closed is False


def test_session_creation_failure_falls_back_to_bare_get(monkeypatch):
    """Session 생성 실패(이론 경계) 시 이번 attempt는 bare requests.get으로 폴백."""
    calls = {"bare": 0}

    def bare_get(url, params=None, timeout=None, **kwargs):
        calls["bare"] += 1
        return FakeResponse()

    def broken_session():
        raise RuntimeError("session construction failed")

    monkeypatch.setattr(live_api.requests, "Session", broken_session)
    monkeypatch.setattr(live_api.requests, "get", bare_get)
    resp = _http_get("https://test.invalid", {"OC": "x"}, (8.0, 12.0))
    assert resp.status_code == 200
    assert calls["bare"] == 1
    assert getattr(_thread_http, "session", None) is None


def test_discard_is_never_raise():
    """_discard_thread_session은 close 예외에도 침묵(never-raise) + 상태 초기화."""
    class BadClose:
        def close(self):
            raise RuntimeError("boom")

    _thread_http.session = BadClose()
    _discard_thread_session()  # 예외 없이 통과해야 함
    assert getattr(_thread_http, "session", None) is None
    _discard_thread_session()  # 세션 부재 시에도 no-op


def test_lazy_no_session_on_import_or_health():
    """import·health 경로에서 Session 미생성 — 부팅·transport 비의존(outage 회피) 불변식."""
    from korean_rnd_regs_mcp import main as main_module
    assert getattr(_thread_http, "session", None) is None
    asyncio.run(main_module.health())
    assert getattr(_thread_http, "session", None) is None


def test_static_single_network_seam_and_no_adapter_tuning():
    """정적 게이트: ①실 네트워크 GET 진입점은 _http_get 하나(폴백 requests.get 1회 포함)
    ②adapter retry·pool sizing·trust_env 튜닝 부재(requests 기본값 의미론 유지)
    ③_request_with_retry가 seam(_http_get)을 사용하고 전송 오류 시 폐기를 호출."""
    raw = Path(live_api.__file__).read_text(encoding="utf-8")
    # 주석 줄 제외한 코드 표면만 검사(설계 주석의 용어 언급은 위반이 아님)
    src = "\n".join(
        ln for ln in raw.splitlines() if not ln.strip().startswith("#")
    )
    assert src.count("requests.get(") == 1, "bare requests.get은 _http_get 폴백 1곳만 허용"
    assert src.count("sess.get(") == 1, "Session GET은 _http_get 안 1곳만 허용"
    for banned in ("HTTPAdapter", ".mount(", "max_retries=Retry", "trust_env",
                   "requests.request(", "requests.post(", "sess.request(", "sess.post("):
        assert banned not in src, f"requests 기본값 의미론 변경·seam 우회 금지 토큰 발견: {banned}"
    retry_src = inspect.getsource(_request_with_retry)
    assert "_http_get(" in retry_src
    assert "_discard_thread_session()" in retry_src
    http_get_src = inspect.getsource(_http_get)
    for banned in ("sess.params", "sess.headers", "sess.auth"):
        assert banned not in http_get_src, f"Session 공유 상태 저장 금지: {banned}"


def test_key_masking_preserved_on_session_path(fake_session_cls, monkeypatch):
    """Session 경로에서도 오류 문면은 예외 타입명만 — OC 키·URL 누설 차단 무회귀."""
    monkeypatch.setattr(live_api.time, "sleep", lambda s: None)
    fake_key = "fake_secret_key_b3_2099"

    def leaky_get(self, url, params=None, timeout=None, **kwargs):
        raise requests.exceptions.ConnectionError(f"boom url OC={fake_key}")

    monkeypatch.setattr(FakeSession, "get", leaky_get)
    with pytest.raises(LawApiError) as ei:
        _request_with_retry("https://test.invalid", {"OC": fake_key}, max_retries=1)
    msg = str(ei.value)
    assert fake_key not in msg
    assert "OC=" not in msg
    assert "ConnectionError" in msg
