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
    """_run_offloaded는 offload 단일 진입점(코루틴) — 6개 law.go.kr 호출처가 공유(v0.18.0 get_old_and_new 포함)."""
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


def test_contract_version_0_22_0():
    """v0.31.0: 매뉴얼 본권 26.7판 현행화(§5.23) — 데이터 판 교체(41→43절·재번호 8건) +
    manual_meta.renumbering_note 조건부 additive(get_manual_section 대상 절 한정)
    → contract 0.23.0 → 0.24.0 minor bump(v0.33.0 별권 2 additive — 입력 스키마 무변·재연결 불요)
    → 0.24.0 → 0.25.0 minor bump(v0.34.0 structure_notice additive — 입력 스키마 무변·재연결 불요)
    → 0.25.0 → 0.26.0 minor bump(v0.35.0 별권 1 학생인건비통합관리 additive — 입력 스키마 무변·재연결 불요)
    → 0.26.0 → 0.27.0 minor bump(v0.37.0 resolver 안전성 정비 — upcoming_revision·resolve_fallback_notice
    응답 additive 2종·입력 스키마 무변·재연결 불요)
    → 0.27.0 → 0.28.0 minor bump(v0.38.0 과제평가 표준지침 수록 — eval id 계열·manual_eval_unavailable·
    footer_manual_line per-source 문면·입력 스키마 무변·재연결 불요)
    → 0.28.0 → 0.29.0 minor bump(v0.39.0 별권 4 연구시설·장비비 통합관리제 운영·관리 매뉴얼 additive —
    b4 단일 레벨 id 계열·manual_b4_unavailable·장애 envelope 격리 사실 문면 정비·입력 스키마 무변·재연결 불요)
    → 0.29.0 → 0.30.0 minor bump(v0.40.0 검색·후보 경로 표준 안내 확대 — search/suggest 정규 반환
    standard_footer additive·whole-or-omit·선택 지시 3도구 확대·폴백 KISTEP 줄 교정·입력 스키마 무변·재연결 불요).
    직전 0.21.0: 출처·원문 확인 경로 정비(§5.22)."""
    from korean_rnd_regs_mcp.provision_id import CONTRACT_VERSION
    assert CONTRACT_VERSION == "0.30.0"


def test_package_version_0_40_0():
    """패키지 버전 0.40.0(검색·후보 경로 표준 안내 확대 — search_provision·suggest_review_sources
    정규 반환 standard_footer·contract 0.30.0·입력 스키마 무변=재연결 불요).
    직전 0.39.0(R5 별권 4 수록 — b4- 11단위·contract 0.29.0)."""
    from korean_rnd_regs_mcp import __version__
    assert __version__ == "0.40.0"


def test_cache_maxsize_96_v0240():
    """v0.24.0: N=60(국방 2차) 등록에 따른 detail/resolve 캐시 상한 64→96 잠금.

    근거: N=60이면 검색 fan-out 1회가 detail 캐시 60엔트리를 점유(headroom 4) —
    BP/JO 상세 조회 몇 건이면 LRU가 warm fan-out 엔트리를 축출해 다음 검색이 부분
    cold 재조회되는 성능 저하 발생. 96(headroom 36)으로 warm-hit 보존. 기능·outage
    무관(상수 2줄) — 계획 /disc 3-AI 만장일치 동승 항목."""
    from korean_rnd_regs_mcp.live_api import LawApiClient
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    assert client._detail_cache.maxsize == 96
    assert client._id_resolution_cache.maxsize == 96
    # 분리 캐시는 불변(간섭 차단 설계 유지)
    assert client._old_and_new_cache.maxsize == 16
    assert client._search_cache.maxsize == 100
