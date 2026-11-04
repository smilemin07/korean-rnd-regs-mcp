"""v0.65.0 — 원격(HTTP) 세션 한도 가드(mcp 1.29.0 → 1.30.0 · GHSA-84m7-p3x7-pcfv).

무엇을 잠그는가(비프로그래머용): mcp 1.30.0부터 원격 서버의 세션은 30분 동안 요청이 없으면 닫히고(1800초 — 1.29.0까지는
기본값 None = 만료 없음), 동시에 열 수 있는 세션은 1만 개다(1.30.0 신설). 요청 본문 4MiB 상한은 1.29.0부터 같다.
이 서버는 그 값을 코드로 바꾸지 않는다(부팅 코드 무변 — 보안 강화 시리즈 C단계 결정). 이 테스트는 ① 설치된 mcp의 기본값이 그 셋인지 ② 실제로 만든 HTTP 앱의 세션 관리자가
그 셋을 쓰는지(lifespan 실행)를 본다. ②는 fastmcp가 관리자를 어떻게 만들든(직접·하위 클래스·인자 전달) 실제 값을 읽는다
(fastmcp 3.4.2는 직접, 3.4.11은 하위 클래스로 만든다). mcp·fastmcp를 갱신해 값이 조용히 바뀌면 여기서 먼저 실패한다.

★네트워크 0: lifespan 실행 중 외부 접속을 막는다(socket connect 차단). 세션 관리자 생성은 접속을 하지 않는다.
"""
import inspect
import socket

EXPECTED_IDLE_TIMEOUT = 1800  # 30분
EXPECTED_MAX_SESSIONS = 10_000
EXPECTED_MAX_BODY = 4 * 1024 * 1024  # 4MiB
_LIMIT_PARAMS = ("session_idle_timeout", "max_sessions", "max_request_body_size")


def test_mcp_session_manager_defaults():
    """설치된 mcp의 StreamableHTTPSessionManager 기본값 = 1800초·1만 개·4MiB(max_sessions는 1.30.0 신설, 유휴 기본값은 1.29.0까지 None)."""
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    params = inspect.signature(StreamableHTTPSessionManager.__init__).parameters
    missing = [p for p in _LIMIT_PARAMS if p not in params]
    assert not missing, f"mcp 세션 한도 인자 없음(mcp<1.30.0?): {missing}"
    assert params["session_idle_timeout"].default == EXPECTED_IDLE_TIMEOUT
    assert params["max_sessions"].default == EXPECTED_MAX_SESSIONS
    assert params["max_request_body_size"].default == EXPECTED_MAX_BODY


def test_lock_pins_mcp_1_30_0():
    """원격 서버 이미지 lock의 mcp가 1.30.0(세션 한도가 있는 판)이다. 이 테스트는 설치본이 아니라 lock 행을 본다."""
    from pathlib import Path

    lock = Path(__file__).resolve().parents[1] / "requirements.lock"
    pins = [ln.strip() for ln in lock.read_text(encoding="utf-8").splitlines() if ln.strip().lower().startswith("mcp==")]
    assert pins == ["mcp==1.30.0"], pins


def test_http_app_session_manager_effective_limits(monkeypatch):
    """실제 HTTP 앱(lifespan 실행)의 세션 관리자 유효값 = 1800초·1만 개·4MiB. 앱 코드가 한도를 바꾸지 않음을 잠근다."""
    import asyncio

    from korean_rnd_regs_mcp import main

    def _no_network(self, *a, **k):  # noqa: ARG001
        raise AssertionError("세션 한도 테스트 중 외부 접속 시도")

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    app = main.mcp.http_app(transport="streamable-http")

    async def _effective() -> tuple:
        async with app.router.lifespan_context(app):  # 세션 관리자는 lifespan 안에서 만들어진다
            managers = [
                sm for r in app.routes
                if (sm := getattr(getattr(r, "endpoint", None), "session_manager", None)) is not None
            ]
            assert len(managers) == 1, f"세션 관리자를 가진 MCP 엔드포인트 수가 1이 아님: {len(managers)}"
            sm = managers[0]
            return sm.stateless, sm.session_idle_timeout, sm.max_sessions, sm.max_request_body_size

    stateless, idle, max_sessions, max_body = asyncio.run(_effective())
    assert stateless is False  # 운영은 세션 모드(stateless 아님)
    assert idle == EXPECTED_IDLE_TIMEOUT
    assert max_sessions == EXPECTED_MAX_SESSIONS
    assert max_body == EXPECTED_MAX_BODY
