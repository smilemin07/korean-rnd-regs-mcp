"""v0.9.1 (B2) 가드 — fan-out 전용 bounded executor + TTLCache thread-safety.

네트워크 없음(상수·소스 정적 검사·lock 존재만). 동시성 corruption은 비결정이라
단위테스트로 직접 재현하지 않고, 설계 불변(락이 모든 cache touch를 감싸고 network는
절대 lock 밖)을 정적 게이트로 박제한다.
"""
import inspect
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from korean_rnd_regs_mcp import live_api
from korean_rnd_regs_mcp import main as main_module
from korean_rnd_regs_mcp.live_api import LawApiClient


def test_fanout_executor_configured():
    """전용 ThreadPoolExecutor가 _FANOUT_MAX_WORKERS(32)로 구성 — 사이징/원복 회귀 방지."""
    assert main_module._FANOUT_MAX_WORKERS == 32
    assert isinstance(main_module._FANOUT_EXECUTOR, ThreadPoolExecutor)
    assert main_module._FANOUT_EXECUTOR._max_workers == main_module._FANOUT_MAX_WORKERS


def test_run_offloaded_is_single_coroutine_entrypoint():
    """_run_offloaded는 offload 단일 진입점(코루틴) — 5개 law.go.kr 호출처가 공유."""
    assert inspect.iscoroutinefunction(main_module._run_offloaded)


def test_no_asyncio_to_thread_calls_in_main_source():
    """정적 게이트: main.py에 asyncio.to_thread 실호출 0건 — 전 offload가 전용 executor 경유.
    (docstring의 'asyncio.to_thread 등가' 언급은 바로 뒤 '(' 없음이라 미매칭.)"""
    src = Path(main_module.__file__).read_text(encoding="utf-8")
    assert "asyncio.to_thread(" not in src


def test_client_has_cache_lock():
    """LawApiClient가 캐시 직렬화용 lock 보유(acquire/release) — TTLCache thread-safety 전제. 네트워크 미발생."""
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    assert hasattr(client, "_cache_lock")
    assert hasattr(client._cache_lock, "acquire")
    assert hasattr(client._cache_lock, "release")


def test_cache_lock_never_wraps_network_or_parse():
    """★정적 게이트(Codex R2 권고): `with self._cache_lock:` 블록 안에 network(_request_with_retry)·
    XML 파싱(_parse_xml)·requests.* 가 들어가면 최악 ~82s 점유로 전체 캐시 경로가 막힌다.
    각 lock 블록 본문에 금지 토큰이 없는지 들여쓰기 기반으로 정적 검사."""
    lines = Path(live_api.__file__).read_text(encoding="utf-8").splitlines()
    forbidden = ("_request_with_retry(", "_parse_xml(", "requests.get(", "requests.post(")
    lock_blocks = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("with self._cache_lock:"):
            lock_blocks += 1
            indent = len(line) - len(line.lstrip())
            j = i + 1
            while j < len(lines):
                body = lines[j]
                if body.strip() == "":
                    j += 1
                    continue
                body_indent = len(body) - len(body.lstrip())
                if body_indent <= indent:
                    break  # 블록 종료(dedent)
                assert not any(tok in body for tok in forbidden), (
                    f"live_api.py:{j + 1} — network/parse가 _cache_lock 블록 안에 있음: {body.strip()!r}"
                )
                j += 1
    # 락 블록이 실제로 존재해야 함(구현이 사라지면 가드도 무의미해지는 것 방지)
    assert lock_blocks >= 8, f"_cache_lock 블록이 {lock_blocks}개뿐 — 캐시 touch 직렬화 누락 의심"


def test_contract_version_unchanged_0_9_0():
    """v0.9.1은 내부 동시성만 — 응답 schema 무변 → contract_version 0.9.0 유지."""
    from korean_rnd_regs_mcp.provision_id import CONTRACT_VERSION
    assert CONTRACT_VERSION == "0.9.0"


def test_package_version_0_10_0():
    """패키지 버전 0.10.0(major=규정 확대: 가운데 숫자 +1)."""
    from korean_rnd_regs_mcp import __version__
    assert __version__ == "0.10.0"
