"""R1-P2(v0.27.0·contract 0.18.0) — 매뉴얼 트랙 도구 2종 단위 테스트.

네트워크 0(로컬 manual_body.json만). 계획 /disc 3-AI 종합 테스트 목록 기반:
로더(lazy·import 미로드·동시성 1회 파싱·fail-safe 3종) / 검색(토큰 AND·정규화·발췌 raw·
0건 앵커·예산·cap) / 상세(size-tier·페이지 경계 청크·재조립 무손실·오류 코드) /
규범성 메타 상시 / 패키징(force-include·sdist) / 상수 parity·contract 잠금.
"""

import asyncio
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from korean_rnd_regs_mcp import manual as manual_mod
from korean_rnd_regs_mcp.main import (
    _MANUAL_QUERY_MAX,
    get_manual_section,
    search_manual,
)
from korean_rnd_regs_mcp.manual import (
    MANUAL_CHUNK_CONTENT_BUDGET,
    MANUAL_DETAIL_CHAR_BUDGET,
    MANUAL_DETAIL_HEADROOM,
    ManualLoadError,
    SECTION_ID_RE,
    build_section_chunks,
    load_manual,
    mdot_normalize,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "src" / "korean_rnd_regs_mcp" / "manual_body.json"


@pytest.fixture
def fresh_cache():
    """캐시 초기화 — 테스트 간 로더 상태 격리(종료 시에도 초기화해 오염 방지)."""
    manual_mod._reset_cache_for_tests()
    yield
    manual_mod._reset_cache_for_tests()


# ── 로더 ──────────────────────────────────────────────────────────────────────

def test_import_does_not_load_manual_data():
    """import 시 데이터 미로드(부팅 무접촉 — outage 격리 핵심). 서브프로세스로 격리 검증."""
    code = (
        "import sys; sys.path.insert(0, 'src'); "
        "import korean_rnd_regs_mcp.main; import korean_rnd_regs_mcp.manual as m; "
        "print(m._CACHE is None)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO_ROOT, timeout=120,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "True"


def test_lazy_load_concurrent_single_parse(fresh_cache, monkeypatch):
    """동시 최초 호출 8건 → 실제 파싱은 1회(double-checked locking)."""
    calls = {"n": 0}
    real = manual_mod._load_uncached

    def counting():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(manual_mod, "_load_uncached", counting)
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda _: load_manual(), range(8)))
    assert calls["n"] == 1
    assert all(r is results[0] for r in results)


def test_file_missing_fail_safe(fresh_cache, monkeypatch, tmp_path):
    monkeypatch.setattr(manual_mod, "_DATA_PATH", tmp_path / "no_such.json")
    r = load_manual()
    assert isinstance(r, ManualLoadError) and r.reason == "file_missing"
    resp = asyncio.run(search_manual("협약 변경"))
    assert resp["errors"][0]["code"] == "manual_unavailable"
    assert resp["manual_meta_available"] is False
    assert "manual_meta" not in resp  # 판번·기준일 하드코딩 금지(확인 불가 처리)
    resp2 = asyncio.run(get_manual_section("1-1"))
    assert resp2["errors"][0]["code"] == "manual_unavailable"


def test_json_parse_failed_fail_safe(fresh_cache, monkeypatch, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(manual_mod, "_DATA_PATH", bad)
    r = load_manual()
    assert isinstance(r, ManualLoadError) and r.reason == "json_parse_failed"


def test_schema_invalid_fail_safe(fresh_cache, monkeypatch, tmp_path):
    bad = tmp_path / "empty.json"
    bad.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(manual_mod, "_DATA_PATH", bad)
    r = load_manual()
    assert isinstance(r, ManualLoadError) and r.reason == "schema_invalid"


# ── 검색 ──────────────────────────────────────────────────────────────────────

def test_search_invalid_query_short():
    r = asyncio.run(search_manual("x"))
    assert r["errors"][0]["code"] == "invalid_query"
    assert r["matches"] == []


def test_search_invalid_query_too_long():
    r = asyncio.run(search_manual("가" * (_MANUAL_QUERY_MAX + 1)))
    assert r["errors"][0]["code"] == "invalid_query"
    assert str(_MANUAL_QUERY_MAX) in r["errors"][0]["message"]


def test_search_single_token_title_first():
    r = asyncio.run(search_manual("기술료"))
    assert r["returned"] >= 1 and r["errors"] == []
    top = r["matches"][0]
    assert top["section_id"] == "2-6"  # 제2장 제6절 기술료 징수･납부･사용 (제목 매치 최상위)
    assert "title" in top["matched_in"]


def test_search_token_and():
    r = asyncio.run(search_manual("협약 변경"))
    ids = [m["section_id"] for m in r["matches"]]
    assert ids[0] == "2-3"  # 연구개발과제의 협약


def test_search_middle_dot_normalization():
    """데이터는 ･(U+FF65) 지배 — 사용자 입력 ·(U+00B7)·ㆍ(U+318D) 모두 매칭."""
    for q in ("연구시설·장비비 통합관리", "연구시설ㆍ장비비 통합관리"):
        r = asyncio.run(search_manual(q))
        assert "3-19" in [m["section_id"] for m in r["matches"]], q
    assert mdot_normalize("시설･장비ㆍ관리") == "시설·장비·관리"


def test_search_excerpts_raw_with_page_anchor():
    r = asyncio.run(search_manual("연구시설·장비비 통합관리"))
    m = next(x for x in r["matches"] if x["section_id"] == "3-19")
    assert m["excerpts"], "발췌가 있어야 함"
    for e in m["excerpts"]:
        assert isinstance(e["printed_page"], int)
        assert m["page_start"] <= e["printed_page"] <= m["page_end"]
    # 발췌는 raw 원문 유지 — 정규화 문자가 섞이지 않음(원문 ･ 보존)
    assert any("･" in e["text"] for e in m["excerpts"])


def test_search_zero_hit_anchor():
    r = asyncio.run(search_manual("존재하지않는키워드검증용문자열"))
    assert r["returned"] == 0 and r["total_matched"] == 0
    assert r["scanned_sections"] == 41
    assert "규정의 부재를 뜻하지 않" in r["note"]
    assert r["manual_meta"]["legal_effect"] == "not_binding"


def test_search_cap_and_budget():
    r = asyncio.run(search_manual("연구개발"))  # 광역 — 다수 절 매치
    assert r["returned"] <= 10
    assert r["total_matched"] >= r["returned"]
    if r["total_matched"] > r["returned"]:
        assert r["truncated"] is True
    assert len(json.dumps(r, ensure_ascii=False)) <= 16000


# ── 상세 ──────────────────────────────────────────────────────────────────────

def test_detail_small_section_full():
    r = asyncio.run(get_manual_section("3-9"))
    assert r["content_format"] == "plain_text_verbatim"
    assert r["is_complete"] is True and r["content_available"] is True
    data = load_manual()
    assert r["content"] == data.full_text["3-9"]
    assert r["page_start"] == 243 and r["page_end"] == 244
    assert len(json.dumps(r, ensure_ascii=False)) <= MANUAL_DETAIL_CHAR_BUDGET


def test_detail_oversized_pointer():
    r = asyncio.run(get_manual_section("2-3"))  # 27.8k자 최대 절
    assert r["content_format"] == "oversized_pointer"
    assert r["content_available"] is False and r["is_complete"] is False
    assert r["chunk_count"] >= 2
    assert "chunk" in r["required_action"]
    assert r["omitted_reason"] == "oversized_tool_response"
    assert len(json.dumps(r, ensure_ascii=False)) <= MANUAL_DETAIL_CHAR_BUDGET


def test_detail_chunk_pages_and_budget():
    p = asyncio.run(get_manual_section("2-3"))
    for i in range(1, p["chunk_count"] + 1):
        c = asyncio.run(get_manual_section("2-3", chunk=i))
        assert c["content_format"] == "plain_text_verbatim"
        assert c["is_complete"] is False
        assert c["chunk_index"] == i and c["chunk_count"] == p["chunk_count"]
        assert c["chunk_pages"]["page_start"] <= c["chunk_pages"]["page_end"]
        esc = len(json.dumps(c["content"], ensure_ascii=False)) - 2
        assert esc <= MANUAL_CHUNK_CONTENT_BUDGET
        assert len(json.dumps(c, ensure_ascii=False)) <= MANUAL_DETAIL_CHAR_BUDGET


def test_detail_chunk_reassembly_lossless():
    """페이지 경계 청크의 "".join == 절 전문 — 16k 초과 12절 전수 검증(annex 불변식 동형)."""
    data = load_manual()
    checked = 0
    for sec in data.sections:
        full = data.full_text[sec["id"]]
        if len(json.dumps(full, ensure_ascii=False)) <= MANUAL_DETAIL_CHAR_BUDGET - MANUAL_DETAIL_HEADROOM:
            continue
        chunks = build_section_chunks(sec)
        assert "".join(c["text"] for c in chunks) == full, sec["id"]
        assert chunks[0]["page_start"] == sec["page_start"]
        assert chunks[-1]["page_end"] == sec["page_end"]
        checked += 1
    assert checked >= 10  # 실측 12절 — 데이터 개정 대비 하한


def test_detail_chunk_out_of_range():
    r = asyncio.run(get_manual_section("2-3", chunk=99))
    assert r["errors"][0]["code"] == "not_found"
    assert r["chunk_count"] >= 2


def test_detail_small_section_chunk_ignored_with_warning():
    r = asyncio.run(get_manual_section("3-9", chunk=1))
    assert r["content_format"] == "plain_text_verbatim"
    assert any("chunk 무시" in w for w in r["warnings"])


def test_detail_invalid_section_id():
    for bad in ("BP0001", "1_1", "", "ref-", "law:283849:JO0003", "1-1-1"):
        r = asyncio.run(get_manual_section(bad))
        assert r["errors"][0]["code"] == "invalid_section_id", bad


def test_detail_not_found_well_formed():
    for missing in ("9-99", "ref-9"):
        r = asyncio.run(get_manual_section(missing))
        assert r["errors"][0]["code"] == "not_found", missing
        assert "search_manual" in r["errors"][0]["message"]


def test_detail_table_image_warnings():
    r = asyncio.run(get_manual_section("4-2"))  # image_only_pages [293] 실측
    assert any("293" in w and "이미지" in w for w in r["warnings"])
    r2 = asyncio.run(get_manual_section("3-7"))  # 표 다수 절(증명자료 표)
    assert any("표 포함 절" in w for w in r2["warnings"])


# ── 규범성 메타 상시 동반 ─────────────────────────────────────────────────────

def test_manual_meta_on_all_response_kinds():
    responses = [
        asyncio.run(search_manual("기술료")),
        asyncio.run(search_manual("존재하지않는키워드검증용문자열")),
        asyncio.run(get_manual_section("3-9")),
        asyncio.run(get_manual_section("2-3")),
        asyncio.run(get_manual_section("2-3", chunk=1)),
    ]
    for r in responses:
        meta = r["manual_meta"]
        assert meta["source_type"] == "manual_explanation"
        assert meta["legal_effect"] == "not_binding"
        assert meta["edition"] == "26.4"
        assert meta["manual_basis_date"] == "2026-03"
        assert "법령·행정규칙 원문이 우선" in meta["law_priority_note"]
        assert "규정의 부재를 뜻하지 않" in meta["law_priority_note"]
        assert meta["notice"] == "인용 매뉴얼: 26.4판 · 법령 시행일 2026-03 기준"
        assert len(meta["basis_laws"]) == 4


def test_manual_meta_notice_from_data_not_hardcoded():
    """notice는 데이터 meta에서 조립(하드코딩 금지) — edition 부재 시 판번 생략."""
    from korean_rnd_regs_mcp.manual import manual_meta_block
    block = manual_meta_block({"manual_basis_date": "2027-03"})
    assert block["notice"] == "인용 매뉴얼: 법령 시행일 2027-03 기준"
    assert block["edition"] is None
    block2 = manual_meta_block({})
    assert "확인 불가" in block2["notice"]


# ── 패키징·상수·contract ──────────────────────────────────────────────────────

def test_data_file_shipped_and_valid():
    assert DATA_PATH.exists()
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    assert payload["meta"]["section_count"] == 41
    assert payload["meta"]["source_type"] == "manual_explanation"
    assert payload["meta"]["legal_effect"] == "not_binding"
    assert len(payload["sections"]) == 41


def test_pyproject_packaging_includes_manual_json():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"src/korean_rnd_regs_mcp/manual_body.json" = "korean_rnd_regs_mcp/manual_body.json"' in text
    assert '"src/korean_rnd_regs_mcp/**/*.json",' in text  # sdist include


def test_section_id_regex_lock():
    for ok in ("1-1", "3-19", "5-2", "ref-1", "ref-2"):
        assert SECTION_ID_RE.match(ok), ok
    for bad in ("BP0001", "1-1-1", "ref-", "01a", "-1", "1-", "ref-x"):
        assert not SECTION_ID_RE.match(bad), bad


def test_budget_constants_parity_with_annex():
    """manual 예산 상수는 annex 상수와 동일 값·동일 사상(계획 /disc — 변경 시 양쪽 함께)."""
    from korean_rnd_regs_mcp import main as main_mod
    assert MANUAL_DETAIL_CHAR_BUDGET == main_mod._ANNEX_DETAIL_CHAR_BUDGET
    assert MANUAL_DETAIL_HEADROOM == main_mod._ANNEX_DETAIL_HEADROOM
    assert MANUAL_CHUNK_CONTENT_BUDGET == main_mod._ANNEX_CHUNK_CONTENT_BUDGET


def test_manual_responses_carry_contract_version():
    from korean_rnd_regs_mcp.provision_id import CONTRACT_VERSION
    assert CONTRACT_VERSION == "0.18.0"
    r = asyncio.run(search_manual("기술료"))
    assert r["contract_version"] == "0.18.0"
    r2 = asyncio.run(get_manual_section("1-4"))
    assert r2["contract_version"] == "0.18.0"
