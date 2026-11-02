"""v0.64.0 「요청 증폭·과부하 차단」 가드 — 네트워크 0(HTTP 계층을 가짜로 바꾼다).

잠그는 불변식:
  B1 새 키 확인 관문(HTTP 요청만)
    1) 틀린 키: 법령정보센터 요청 1건 → auth_failed, 300초 동안 같은 키는 요청 0건.
    2) 키를 바꿔 가며 보내도 키마다 1건, 최근 60초 확인 시작 수와 동시 확인 수에 상한(넘으면 rate_limited·요청 0).
    3) 같은 새 키의 동시 요청은 확인 1건을 공유한다(통과·인증 실패·일시 오류 모두). 기다리던 요청이 취소돼도
       확인은 끝까지 간다.
    4) 일시 오류(네트워크·429·시간 초과)는 무효로 기억하지 않는다(10초만 재확인 억제).
    5) 확인 검색은 innovation_act의 resolve 검색과 같은 호출이라, 통과한 키의 resolve는 추가 요청 0건.
    6) 가짜 키는 키별 클라이언트 풀에 들어가지 않아 실사용자 클라이언트를 밀어내지 못한다.
    7) stdio(HTTP 아님)는 관여하지 않는다. 256자 초과 키는 저장 없이 auth_failed.
    8) 확인을 통과했던 키가 모든 규정에서 인증 실패면 무효로 옮긴다(일부 규정만 실패하면 그대로).
  B2 길이 상한
    9) search_provision query 200자 초과 → invalid_query(요청 0건). suggest 키워드 100자 초과는 버린다.
"""
import asyncio
from unittest.mock import MagicMock

import pytest

import korean_rnd_regs_mcp.live_api as LA
from korean_rnd_regs_mcp import main as M
from korean_rnd_regs_mcp.live_api import (
    AUTH_FAILED_BODY_MESSAGE, LawApiError, ResolvedDocId, _MAX_RETRIES, _REQUEST_TIMEOUT,
)

_AUTH_BODY = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n'
    "<result>사용자 정보 검증에 실패하였습니다.</result>\n<msg>x</msg>\n</Response>\n"
)
_OK_BODY = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<LawSearch><target>law</target><totalCnt>1</totalCnt>'
    "<law><법령일련번호>285767</법령일련번호><법령ID>14069</법령ID><법령명한글>국가연구개발혁신법</법령명한글>"
    "<법령구분명>법률</법령구분명><소관부처명>과학기술정보통신부</소관부처명>"
    "<시행일자>20260611</시행일자><공포일자>20260311</공포일자></law></LawSearch>"
)
_ZERO_BODY = '<LawSearch><target>law</target><totalCnt>0</totalCnt></LawSearch>'


class _Resp:
    def __init__(self, text):
        self.status_code, self.text, self.content = 200, text, text.encode()
        self.headers = {"Content-Type": "application/xml;charset=UTF-8"}


@pytest.fixture(autouse=True)
def _reset_gate(monkeypatch):
    for d in (M._verified_keys, M._invalid_keys, M._transient_keys, M._key_check_inflight, M._client_by_key):
        d.clear()
    M._key_check_times.clear()
    M._key_probe_threads = 0
    yield
    for d in (M._verified_keys, M._invalid_keys, M._transient_keys, M._key_check_inflight, M._client_by_key):
        d.clear()
    M._key_check_times.clear()


@pytest.fixture
def upstream(monkeypatch):
    """HTTP 계층 가짜. behavior[OC] = "ok" | "auth" | "zero" | "net" | "429" | "slow". 요청은 calls에 (OC, target, retries)."""
    state = {"behavior": {}, "calls": []}

    def fake(url, params, max_retries=_MAX_RETRIES, timeout=_REQUEST_TIMEOUT):
        oc = params.get("OC")
        state["calls"].append((oc, params.get("target"), max_retries))
        b = state["behavior"].get(oc, "auth")
        if b == "ok":
            return _Resp(_OK_BODY)
        if b == "zero":
            return _Resp(_ZERO_BODY)
        if b == "net":
            raise LawApiError("parse_failed", "네트워크 오류 (재시도 1회 실패, 종류=ConnectionError)")
        if b == "429":
            raise LawApiError("rate_limited", "HTTP 429 after 1 retries")
        if b == "slow":
            import time as _t
            _t.sleep(0.5)
            return _Resp(_OK_BODY)
        return _Resp(_AUTH_BODY)
    monkeypatch.setattr(LA, "_request_with_retry", fake)
    monkeypatch.setattr(LA, "DEFAULT_LAW_API_URL", "https://test.invalid/DRF")
    return state


def _http(key, coro_fn):
    async def run():
        t1 = M._is_http_request.set(True)
        t2 = M._request_api_key.set(key)
        try:
            return await coro_fn()
        finally:
            M._request_api_key.reset(t2)
            M._is_http_request.reset(t1)
    return asyncio.run(run())


def _code(r):
    return r["errors"][0]["code"]


# ── 1) 틀린 키: 1건 → 이후 0건
def test_wrong_key_one_request_then_zero(upstream):
    r1 = _http("BAD1", lambda: M.search_provision("간접비 기준"))
    assert _code(r1) == "auth_failed" and r1["results"] == []
    assert r1["errors"][0]["message"] == AUTH_FAILED_BODY_MESSAGE
    assert len(upstream["calls"]) == 1
    oc, target, retries = upstream["calls"][0]
    assert (oc, target, retries) == ("BAD1", "law", 1)  # 재시도 없는 1회 전송
    r2 = _http("BAD1", lambda: M.search_provision("협약 변경"))
    r3 = _http("BAD1", lambda: M.get_provision_detail("law:290757:JO0015"))
    r4 = _http("BAD1", lambda: M.suggest_review_sources("간접비 검토", ["간접비"]))
    assert _code(r2) == _code(r3) == _code(r4) == "auth_failed"
    assert len(upstream["calls"]) == 1
    assert "BAD1" not in M._client_by_key


# ── 2) 키 회전·상한
def test_rotating_keys_one_each(upstream):
    for k in ("R1", "R2", "R3"):
        _http(k, lambda: M.search_provision("간접비 기준"))
    assert [c[0] for c in upstream["calls"]] == ["R1", "R2", "R3"]


def test_per_minute_cap_rejects_without_request(upstream, monkeypatch):
    monkeypatch.setattr(M, "_KEY_GATE_CHECKS_PER_MIN", 2)
    _http("C1", lambda: M.search_provision("간접비 기준"))
    _http("C2", lambda: M.search_provision("간접비 기준"))
    r = _http("C3", lambda: M.search_provision("간접비 기준"))
    assert _code(r) == "rate_limited" and r["results"] == []
    assert r["errors"][0]["message"] == M._KEY_GATE_BUSY_MESSAGE
    assert len(upstream["calls"]) == 2
    assert "C3" not in M._invalid_keys and "C3" not in M._transient_keys  # 거절은 기억하지 않는다
    assert len(M._key_check_times) == 2  # 거절은 확인 시작으로 세지 않는다


def test_cap_window_expires(upstream, monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(M.time, "monotonic", lambda: t[0])
    monkeypatch.setattr(M, "_KEY_GATE_CHECKS_PER_MIN", 1)
    _http("W1", lambda: M.search_provision("간접비 기준"))
    assert _code(_http("W2", lambda: M.search_provision("간접비 기준"))) == "rate_limited"
    t[0] += 60.0
    assert _code(_http("W2", lambda: M.search_provision("간접비 기준"))) == "auth_failed"
    assert [c[0] for c in upstream["calls"]] == ["W1", "W2"]


def test_concurrency_cap(upstream, monkeypatch):
    monkeypatch.setattr(M, "_KEY_GATE_CONCURRENCY", 1)
    upstream["behavior"]["S1"] = "slow"

    async def run():
        async def one(k):
            t1 = M._is_http_request.set(True); t2 = M._request_api_key.set(k)
            try:
                return await M._key_gate()
            finally:
                M._request_api_key.reset(t2); M._is_http_request.reset(t1)
        return await asyncio.gather(one("S1"), one("S2"))
    a, b = asyncio.run(run())
    assert a is None  # S1 통과
    assert b is not None and _code(b) == "rate_limited"
    assert [c[0] for c in upstream["calls"]] == ["S1"]


# ── 3) 같은 새 키 동시 요청은 확인 1건 공유
@pytest.mark.parametrize("behavior,expect", [("ok", None), ("auth", "auth_failed"), ("net", "parse_failed")])
def test_concurrent_same_key_single_probe(upstream, behavior, expect):
    upstream["behavior"]["SAME"] = behavior

    async def run():
        t1 = M._is_http_request.set(True); t2 = M._request_api_key.set("SAME")
        try:
            return await asyncio.gather(*[M._key_gate() for _ in range(5)])
        finally:
            M._request_api_key.reset(t2); M._is_http_request.reset(t1)
    results = asyncio.run(run())
    assert len(upstream["calls"]) == 1
    for r in results:
        assert (r is None) if expect is None else (_code(r) == expect)


def test_waiter_cancel_does_not_cancel_probe(upstream):
    upstream["behavior"]["CX"] = "slow"

    async def run():
        t1 = M._is_http_request.set(True); t2 = M._request_api_key.set("CX")
        try:
            first = asyncio.ensure_future(M._key_gate())
            await asyncio.sleep(0.05)
            second = asyncio.ensure_future(M._key_gate())
            await asyncio.sleep(0.05)
            first.cancel()
            return await second
        finally:
            M._request_api_key.reset(t2); M._is_http_request.reset(t1)
    assert asyncio.run(run()) is None
    assert len(upstream["calls"]) == 1 and "CX" in M._verified_keys


# ── 4) 일시 오류는 무효로 기억하지 않는다
@pytest.mark.parametrize("behavior,code", [("net", "parse_failed"), ("429", "rate_limited")])
def test_transient_not_cached_as_invalid(upstream, behavior, code):
    upstream["behavior"]["T1"] = behavior
    r1 = _http("T1", lambda: M.search_provision("간접비 기준"))
    assert _code(r1) == code and r1["errors"][0]["message"] == M._KEY_GATE_TRANSIENT_MESSAGE
    assert "T1" not in M._invalid_keys and "T1" not in M._verified_keys
    r2 = _http("T1", lambda: M.search_provision("간접비 기준"))  # 10초 안 = 요청 없이 같은 안내
    assert _code(r2) == code and len(upstream["calls"]) == 1
    M._transient_keys.clear()  # 10초 경과와 같다
    upstream["behavior"]["T1"] = "ok"
    assert _http("T1", lambda: M._key_gate()) is None
    assert len(upstream["calls"]) == 2


def test_probe_timeout_is_transient(upstream, monkeypatch):
    monkeypatch.setattr(M, "_FANOUT_BUDGET_S", 0.1)
    upstream["behavior"]["TO"] = "slow"
    r = _http("TO", lambda: M.search_provision("간접비 기준"))
    assert _code(r) == "parse_failed"
    assert "TO" in M._transient_keys and "TO" not in M._invalid_keys


def test_zero_rows_counts_as_valid(upstream):
    upstream["behavior"]["Z1"] = "zero"
    assert _http("Z1", lambda: M._key_gate()) is None
    assert "Z1" in M._verified_keys


# ── 5) 확인 검색 = resolve 검색(추가 요청 0)
def test_probe_warms_resolve_cache(upstream):
    upstream["behavior"]["GOOD"] = "ok"
    assert _http("GOOD", lambda: M._key_gate()) is None
    assert len(upstream["calls"]) == 1
    client = M._client_by_key["GOOD"]
    rs = next(r for r in M.load_manifest() if r.id == "innovation_act")
    res = client.resolve_latest_doc_id(rs.title, rs.api_target.value, rs.api_doc_id, rs.ministry)
    assert res.doc_id == "285767"
    assert len(upstream["calls"]) == 1  # resolve 검색이 확인 응답을 그대로 썼다
    # 이미 통과한 키는 요청 없이 통과
    assert _http("GOOD", lambda: M._key_gate()) is None and len(upstream["calls"]) == 1


# ── 6) 가짜 키가 실사용자 클라이언트를 밀어내지 못한다
def test_fake_keys_do_not_evict_real_client(upstream, monkeypatch):
    upstream["behavior"]["REAL"] = "ok"
    _http("REAL", lambda: M._key_gate())
    real_client = M._client_by_key["REAL"]
    monkeypatch.setattr(M, "_KEY_GATE_CHECKS_PER_MIN", 10_000)
    for i in range(150):
        _http(f"FAKE{i}", lambda: M._key_gate())
    assert M._client_by_key.get("REAL") is real_client
    assert len(M._client_by_key) == 1


# ── 7) stdio·긴 키
def test_stdio_untouched(upstream):
    t = M._request_api_key.set("ANY")
    try:
        assert asyncio.run(M._key_gate()) is None
    finally:
        M._request_api_key.reset(t)
    assert upstream["calls"] == []


def test_overlong_key_rejected_without_storage(upstream):
    k = "K" * 257
    r = _http(k, lambda: M.search_provision("간접비 기준"))
    assert _code(r) == "auth_failed" and upstream["calls"] == []
    assert k not in M._invalid_keys and k not in M._verified_keys


# ── 8) 통과했던 키의 전면 인증 실패 → 무효
def _auth_everywhere_client():
    c = MagicMock()
    c.resolve_latest_doc_id.return_value = ResolvedDocId(
        doc_id="1", effective_date="", is_updated=False, manifest_doc_id="1",
        resolve_failed=True, resolve_error_code="auth_failed")
    err = LawApiError("auth_failed", AUTH_FAILED_BODY_MESSAGE)
    c.get_law_detail_staged.side_effect = err
    c.get_admin_rule_detail.side_effect = err
    return c


def test_verified_key_demoted_when_all_rules_auth_fail(upstream):
    M._mark_key_verified("WAS_OK")
    M._client_by_key["WAS_OK"] = _auth_everywhere_client()
    r = _http("WAS_OK", lambda: M.search_provision("간접비 기준"))
    assert any(e["code"] == "auth_failed" for e in r["errors"])
    assert "WAS_OK" in M._invalid_keys and "WAS_OK" not in M._verified_keys
    assert "WAS_OK" not in M._client_by_key  # 실패 기억이 쌓인 클라이언트도 뺀다(Grok)


def test_partial_auth_key_kept(upstream):
    c = _auth_everywhere_client()
    c.resolve_latest_doc_id.return_value = ResolvedDocId(
        doc_id="1", effective_date="", is_updated=False, manifest_doc_id="1")
    c.get_law_detail_staged.side_effect = None
    c.get_law_detail_staged.return_value = ({"articles": [], "annexes": []}, "law")
    M._mark_key_verified("PARTIAL")
    M._client_by_key["PARTIAL"] = c
    r = _http("PARTIAL", lambda: M.search_provision("간접비 기준"))
    assert any(e["code"] == "auth_failed" for e in r["errors"])  # 행정규칙만 실패
    assert "PARTIAL" in M._verified_keys and "PARTIAL" not in M._invalid_keys


# ── 9) 길이 상한
def test_long_query_invalid_without_request(upstream):
    r = _http("BADQ", lambda: M.search_provision("가" * 201))
    assert _code(r) == "invalid_query" and r["results"] == [] and upstream["calls"] == []
    assert "200" in r["errors"][0]["message"]
    r200 = asyncio.run(M.search_provision("나" * 200, ))  # stdio·200자는 통과(관문 없음) — 상한 경계
    assert all(e["code"] != "invalid_query" for e in r200.get("errors", []))


def test_suggest_drops_overlong_keywords():
    assert M._sanitize_keywords(["가" * 101, "간접비"]) == ["간접비"]
    assert M._sanitize_keywords(["가" * 100]) == ["가" * 100]
    assert M._sanitize_keywords(["가" * 101]) == []


# ── diff 적대검토 반영(2026-11-02)
def test_concurrency_slot_held_until_thread_finishes(upstream, monkeypatch):
    """시간 초과로 기다림을 끊어도 검색 스레드가 끝날 때까지 동시 확인 수에 남는다(Codex·Gemini)."""
    monkeypatch.setattr(M, "_FANOUT_BUDGET_S", 0.1)
    monkeypatch.setattr(M, "_KEY_GATE_CONCURRENCY", 1)
    upstream["behavior"]["SLOWA"] = "slow"   # 0.5초 걸리는 스레드

    async def run():
        t1 = M._is_http_request.set(True)
        try:
            t2 = M._request_api_key.set("SLOWA")
            a = await M._key_gate()                    # 0.1초에 시간 초과로 반환(스레드는 계속)
            M._request_api_key.reset(t2)
            t3 = M._request_api_key.set("NEXTB")
            b = await M._key_gate()                    # 스레드가 아직 돌아 슬롯 없음
            M._request_api_key.reset(t3)
            await asyncio.sleep(0.6)                   # 스레드 종료 → 슬롯 반환
            t4 = M._request_api_key.set("NEXTC")
            c = await M._key_gate()
            M._request_api_key.reset(t4)
            return a, b, c
        finally:
            M._is_http_request.reset(t1)
    a, b, c = asyncio.run(run())
    assert _code(a) == "parse_failed"
    assert _code(b) == "rate_limited"
    assert _code(c) == "auth_failed"
    assert M._key_probe_threads == 0


def test_no_demotion_when_timeouts_mixed_with_auth(upstream):
    """법령 시간 초과 + 행정규칙 인증 실패가 섞이면 무효로 옮기지 않는다(Codex·Gemini)."""
    c = _auth_everywhere_client()
    c.get_law_detail_staged.side_effect = LawApiError("parse_failed", "네트워크 오류 (재시도 2회 실패, 종류=ReadTimeout)")
    M._mark_key_verified("MIXED")
    M._client_by_key["MIXED"] = c
    _http("MIXED", lambda: M.search_provision("간접비 기준"))
    assert "MIXED" in M._verified_keys and "MIXED" not in M._invalid_keys


def test_task_cancelled_before_start_releases_waiters(upstream):
    """확인 Task가 시작 전에 취소돼도 대기 요청이 영원히 기다리지 않는다(Gemini)."""
    upstream["behavior"]["CANC"] = "ok"

    async def run():
        t1 = M._is_http_request.set(True); t2 = M._request_api_key.set("CANC")
        try:
            g = asyncio.ensure_future(M._key_gate())
            await asyncio.sleep(0)            # _key_gate가 Task를 만들고 shield에서 기다림
            for t in list(M._key_probe_tasks):
                t.cancel()
            return await asyncio.wait_for(g, timeout=2)
        finally:
            M._request_api_key.reset(t2); M._is_http_request.reset(t1)
    r = asyncio.run(run())
    assert r is not None and _code(r) == "parse_failed"
    assert "CANC" not in M._key_check_inflight and M._key_probe_threads == 0


def test_fallback_keywords_capped_both_paths():
    """suggest의 두 추출 경로가 같은 상한(앞 2,000자·키워드 100자)을 쓴다(Fable F2)."""
    long_tok = "가" * 5000
    q = "협약 변경 " + long_tok
    kws = M._fallback_keywords(q)
    assert all(len(k) <= M._SUGGEST_KEYWORD_MAX for k in kws)
    q2 = ("나" * 2500) + " 간접비"
    assert "간접비" not in M._fallback_keywords(q2)   # 2,000자 뒤는 보지 않는다
    import inspect
    src = inspect.getsource(M.suggest_review_sources)
    assert "_extract_keywords(" not in src and src.count("_fallback_keywords(question)") == 2


def test_capped_rejection_skips_manifest(upstream, monkeypatch):
    """상한으로 거절할 때는 manifest를 읽지 않는다(Fable F1)."""
    monkeypatch.setattr(M, "_KEY_GATE_CHECKS_PER_MIN", 0)
    calls = []
    monkeypatch.setattr(M, "_key_gate_probe_rule", lambda: calls.append(1))
    r = _http("CAPX", lambda: M._key_gate())
    assert _code(r) == "rate_limited" and calls == []
