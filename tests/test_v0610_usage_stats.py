"""v0.61.0 일별 이용 현황 집계 — 네트워크 0."""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from korean_rnd_regs_mcp import main, usage_stats
from korean_rnd_regs_mcp.usage_stats import (
    OUTCOME_AUTH_FAILED,
    OUTCOME_NO_RESULT,
    OUTCOME_OK,
    _UsageStats,
    classify_result,
)

KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 10, 27, 9, 5, tzinfo=KST)
SECRET_KEY = "honggildong-test-key"
LINE_RE = re.compile(
    r"event=daily_usage date=\d{4}-\d{2}-\d{2} final=[01] boot=[0-9a-f]{8} seq=\d+ users=\d+ "
    r"http_requests=\d+ tool_calls=\d+ saturated=[01]"
)


def _enabled(now=T0):
    s = _UsageStats(now=now)
    s.enable()
    return s


def _lines(caplog):
    return [r.getMessage() for r in caplog.records if "event=daily_usage" in r.getMessage()]


def test_disabled_counts_nothing():
    s = _UsageStats(now=T0)
    s.note_http_request(now=T0)
    s.note_tool_call("search_provision", SECRET_KEY, OUTCOME_OK, now=T0)
    snap = s.snapshot()
    assert (snap["http_requests"], snap["tool_calls"], snap["users"]) == (0, 0, 0)


def test_users_distinct_and_exclusions():
    s = _enabled()
    s.note_tool_call("search_provision", "keyA", OUTCOME_OK, now=T0)
    s.note_tool_call("get_provision_detail", "keyA", OUTCOME_OK, now=T0)  # 같은 키 → 1명
    s.note_tool_call("search_manual", "keyB", OUTCOME_OK, now=T0)
    s.note_tool_call("search_provision", "", OUTCOME_OK, now=T0)           # 키 없음 → 제외
    s.note_tool_call("search_provision", "wrong", OUTCOME_AUTH_FAILED, now=T0)  # 인증 실패 → 제외
    s.note_tool_call("health", "keyC", OUTCOME_OK, now=T0)                 # health만 → 제외
    s.note_tool_call("no_such_tool", "keyD", OUTCOME_NO_RESULT, now=T0)    # 결과 없음 → 제외
    snap = s.snapshot()
    assert snap["users"] == 2
    assert snap["tool_calls"] == 7


def test_auth_failed_removes_key_for_the_day():
    s = _enabled()
    s.note_tool_call("list_rule_sets", "wrong", OUTCOME_OK, now=T0)        # 틀린 키도 목록은 결과가 옴
    assert s.snapshot()["users"] == 1
    s.note_tool_call("search_provision", "wrong", OUTCOME_AUTH_FAILED, now=T0)
    assert s.snapshot()["users"] == 0
    s.note_tool_call("search_manual", "wrong", OUTCOME_OK, now=T0)          # 그날은 다시 들어오지 않음
    assert s.snapshot()["users"] == 0
    s.note_tool_call("search_manual", "wrong", OUTCOME_OK, now=T0 + timedelta(days=1))  # 다음 날은 새로 셈
    assert s.snapshot()["users"] == 1


def test_first_request_after_boot_writes_a_line(caplog):
    s = _enabled()
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        s.note_http_request(now=T0)
    lines = _lines(caplog)
    assert len(lines) == 1 and "final=0" in lines[0] and "http_requests=1" in lines[0] and "seq=1" in lines[0]


def test_ten_minute_buckets_and_midnight(caplog):
    s = _enabled()
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        s.note_http_request(now=T0)                                     # 09:05 첫 줄
        s.note_tool_call("search_provision", "keyA", OUTCOME_OK, now=T0)
        s.note_http_request(now=T0.replace(minute=9))                   # 같은 구간 → 줄 없음
        assert len(_lines(caplog)) == 1
        s.note_http_request(now=T0.replace(minute=10))                  # 09:10 새 구간 → 현재 요청 포함
        s.note_http_request(now=datetime(2026, 10, 28, 0, 3, tzinfo=KST))  # 날짜 바뀜 → 전날 최종 + 새 날 첫 줄
    lines = _lines(caplog)
    assert len(lines) == 4
    assert "final=0" in lines[1] and "users=1" in lines[1] and "http_requests=3" in lines[1] and "seq=2" in lines[1]
    assert "date=2026-10-27 final=1" in lines[2] and "http_requests=3" in lines[2] and "tool_calls=1" in lines[2]
    assert "date=2026-10-28 final=0" in lines[3] and "http_requests=1" in lines[3] and "seq=4" in lines[3]
    assert all(LINE_RE.fullmatch(x) for x in lines)
    snap = s.snapshot()
    assert snap["date"] == "2026-10-28" and snap["users"] == 0


def test_midnight_rotates_salt():
    s = _enabled()
    s.note_tool_call("search_provision", "keyA", OUTCOME_OK, now=T0)
    salt_before = s._salt
    s.note_tool_call("search_provision", "keyA", OUTCOME_OK, now=T0 + timedelta(days=1))
    assert s._salt != salt_before
    assert s.snapshot()["users"] == 1


def test_boot_is_8_hex():
    assert re.fullmatch(r"[0-9a-f]{8}", _UsageStats(now=T0)._boot)


def test_log_has_no_key_hash_or_tool_name(caplog):
    s = _enabled()
    evil = "no_such_tool\nevent=daily_usage date=2026-10-27 users=999"
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        s.note_tool_call("search_provision", SECRET_KEY, OUTCOME_OK, now=T0)
        s.note_tool_call(evil, SECRET_KEY, OUTCOME_NO_RESULT, now=T0 + timedelta(minutes=20))
        s.note_http_request(now=T0 + timedelta(days=1))
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "daily_usage" in text
    assert SECRET_KEY not in text
    assert "no_such_tool" not in text and "search_provision" not in text
    assert s._digest(SECRET_KEY).hex() not in text
    assert "oc=" not in text
    assert all(LINE_RE.fullmatch(x) for x in _lines(caplog))


def test_key_set_cap_sets_saturated(monkeypatch):
    monkeypatch.setattr(usage_stats, "_KEY_SET_CAP", 2)
    s = _enabled()
    for k in ("a", "b", "c"):
        s.note_tool_call("search_provision", k, OUTCOME_OK, now=T0)
    snap = s.snapshot()
    assert snap["users"] == 2 and snap["saturated"] is True


def test_never_raises_on_bad_input():
    s = _enabled()
    s.note_tool_call(None, None, None, now=T0)  # type: ignore[arg-type]
    s.note_http_request(now="not-a-datetime")   # type: ignore[arg-type]


def test_classify_result():
    sc = lambda d: SimpleNamespace(structured_content=d)  # noqa: E731
    assert classify_result(None) == OUTCOME_NO_RESULT
    assert classify_result(sc({"errors": [{"code": "auth_failed"}]})) == OUTCOME_AUTH_FAILED
    assert classify_result(sc({"errors": [{"code": "auth_failed"}], "results": []})) == OUTCOME_AUTH_FAILED
    # 일부 트랙만 막힌 키는 결과를 받으므로 이용자
    assert classify_result(sc({"errors": [{"code": "auth_failed"}], "results": [{"x": 1}]})) == OUTCOME_OK
    assert classify_result(sc({"errors": [{"code": "auth_failed"}], "candidates": [{"x": 1}]})) == OUTCOME_OK
    assert classify_result(sc({"errors": [{"code": "timeout"}]})) == OUTCOME_OK
    assert classify_result(sc({"results": []})) == OUTCOME_OK
    assert classify_result(sc("x")) == OUTCOME_OK
    assert classify_result(SimpleNamespace()) == OUTCOME_OK


def _ctx(name):
    return SimpleNamespace(message=SimpleNamespace(name=name))


def test_middleware_passes_result_and_counts(monkeypatch):
    s = _enabled()
    monkeypatch.setattr(main, "_usage_stats", s)
    sentinel = SimpleNamespace(structured_content={"results": []})

    async def call_next(ctx):
        return sentinel

    token = main._request_api_key.set("keyA")
    try:
        out = asyncio.run(main._UsageMiddleware().on_call_tool(_ctx("search_provision"), call_next))
    finally:
        main._request_api_key.reset(token)
    assert out is sentinel
    assert s.snapshot()["tool_calls"] == 1 and s.snapshot()["users"] == 1


def test_middleware_counting_error_does_not_change_result(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("counting failed")

    monkeypatch.setattr(main._usage_stats, "note_tool_call", boom)
    sentinel = SimpleNamespace(structured_content={})

    async def call_next(ctx):
        return sentinel

    out = asyncio.run(main._UsageMiddleware().on_call_tool(_ctx("health"), call_next))
    assert out is sentinel


def test_middleware_propagates_tool_exception_unchanged(monkeypatch):
    s = _enabled()
    monkeypatch.setattr(main, "_usage_stats", s)

    async def call_next(ctx):
        raise ValueError("tool failed")

    token = main._request_api_key.set("keyA")
    try:
        with pytest.raises(ValueError, match="tool failed"):
            asyncio.run(main._UsageMiddleware().on_call_tool(_ctx("search_provision"), call_next))
    finally:
        main._request_api_key.reset(token)
    assert s.snapshot()["tool_calls"] == 1 and s.snapshot()["users"] == 0


def test_stdio_import_registers_no_usage_middleware():
    """새 프로세스에서 import만 하면(=stdio 경로) 미들웨어 미등록·집계 꺼짐. 다른 테스트의 _run_http 호출과 격리."""
    import subprocess
    import sys

    code = (
        "import korean_rnd_regs_mcp.main as m;"
        "print(any(isinstance(x, m._UsageMiddleware) for x in m.mcp.middleware), m._usage_stats._enabled)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip().splitlines()[-1] == "False False"


def test_run_http_registers_middleware_once(monkeypatch):
    async def fake_run_http_async(**kwargs):
        return None

    monkeypatch.setattr(main.mcp, "run_http_async", fake_run_http_async)
    before = list(main.mcp.middleware)
    was_enabled = main._usage_stats._enabled
    try:
        asyncio.run(main._run_http("127.0.0.1", 18080))
        asyncio.run(main._run_http("127.0.0.1", 18080))
        assert sum(isinstance(m, main._UsageMiddleware) for m in main.mcp.middleware) == 1
        assert main._usage_stats._enabled is True
    finally:
        main.mcp.middleware[:] = before
        main._usage_stats._enabled = was_enabled


def test_ocmiddleware_counts_http_requests(monkeypatch):
    s = _enabled()
    monkeypatch.setattr(main, "_usage_stats", s)

    async def app(scope, receive, send):
        return None

    mw = main._OCKeyMiddleware(app)
    asyncio.run(mw({"type": "http", "query_string": b"oc=x"}, None, None))
    asyncio.run(mw({"type": "lifespan"}, None, None))
    assert s.snapshot()["http_requests"] == 1


def test_inprocess_fastmcp_chain_failures_keep_results(monkeypatch):
    """실제 FastMCP 체인: 정상·없는 도구·인자 오류가 모두 세지고, 응답은 집계 전과 같다."""
    from fastmcp import Client

    s = _enabled()
    monkeypatch.setattr(main, "_usage_stats", s)
    before = list(main.mcp.middleware)
    # 다른 테스트의 _run_http 호출이 남긴 집계 미들웨어를 빼고 하나만 둔다(이중 집계 방지)
    main.mcp.middleware[:] = [m for m in before if not isinstance(m, main._UsageMiddleware)]
    main.mcp.add_middleware(main._UsageMiddleware())
    token = main._request_api_key.set("keyA")
    try:
        async def run():
            async with Client(main.mcp) as c:
                ok = await c.call_tool("list_rule_sets", {})
                missing = await c.call_tool("no_such_tool", {}, raise_on_error=False)
                bad = await c.call_tool("get_manual_section", {"section_id": 123, "extra": 1},
                                        raise_on_error=False)
                return ok, missing, bad
        ok, missing, bad = asyncio.run(run())
    finally:
        main._request_api_key.reset(token)
        main.mcp.middleware[:] = before
    assert not ok.is_error
    assert missing.is_error and bad.is_error
    snap = s.snapshot()
    assert snap["tool_calls"] == 3
    assert snap["users"] == 1  # 정상 호출 1건의 키만. 없는 도구·인자 오류는 이용자를 늘리지 않음


def test_clock_going_back_does_not_reset_day():
    s = _enabled()
    s.note_tool_call("search_provision", "keyA", OUTCOME_OK, now=T0)
    s.note_http_request(now=T0 - timedelta(days=1))  # 시계 보정으로 전날 시각
    snap = s.snapshot()
    assert snap["date"] == "2026-10-27" and snap["users"] == 1 and snap["http_requests"] == 1


def test_cap_counts_failed_set_and_auth_failed_still_removes(monkeypatch):
    monkeypatch.setattr(usage_stats, "_KEY_SET_CAP", 2)
    s = _enabled()
    s.note_tool_call("search_provision", "a", OUTCOME_OK, now=T0)
    s.note_tool_call("search_provision", "bad", OUTCOME_AUTH_FAILED, now=T0)   # 실패 집합 1 → 합계 2
    s.note_tool_call("search_provision", "c", OUTCOME_OK, now=T0)              # 상한 → 세지 않음
    assert s.snapshot()["users"] == 1 and s.snapshot()["saturated"] is True
    s.note_tool_call("search_provision", "a", OUTCOME_AUTH_FAILED, now=T0)     # 상한이어도 제거는 됨
    assert s.snapshot()["users"] == 0
