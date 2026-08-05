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
    FOOTER_LAW_LINE,
    FOOTER_MANUAL_LINE,
    FOOTER_MANUAL_SOURCE_LINE,
    MANUAL_CHUNK_CONTENT_BUDGET,
    MANUAL_DETAIL_CHAR_BUDGET,
    MANUAL_DETAIL_HEADROOM,
    ManualLoadError,
    SECTION_ID_RE,
    build_citation,
    build_section_chunks,
    build_standard_footer,
    load_manual,
    manual_meta_block,
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
    # v0.32.0(D5 장애 4조합): 본권 불가·별권 정상 → 별권만으로 부분 검색 성공 + source_warnings
    resp = asyncio.run(search_manual("협약 변경"))
    assert resp["errors"] == []
    assert resp["searched_sources"] == ["b3", "b2", "b1"]
    assert resp["unavailable_sources"] == ["main"]
    assert resp["source_warnings"][0]["code"] == "manual_unavailable"
    assert "부분 결과" in resp["source_warnings"][0]["message"]
    # 본권 상세 조회는 여전히 manual_unavailable(별권 무관)
    resp2 = asyncio.run(get_manual_section("1-1"))
    assert resp2["errors"][0]["code"] == "manual_unavailable"
    # 별권 상세 조회는 정상
    resp3 = asyncio.run(get_manual_section("b3-1-1"))
    assert resp3.get("errors") is None or resp3.get("content_available") is True


def test_both_sources_missing_error(fresh_cache, monkeypatch, tmp_path):
    """전 소스(본권·별권 3·별권 2·별권 1) 불가 — 오류 응답에 네 코드가 함께 실림(v0.35.0 16조합)."""
    monkeypatch.setattr(manual_mod, "_DATA_PATH", tmp_path / "no_main.json")
    monkeypatch.setattr(manual_mod, "_B3_DATA_PATH", tmp_path / "no_b3.json")
    monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", tmp_path / "no_b2.json")
    monkeypatch.setattr(manual_mod, "_B1_DATA_PATH", tmp_path / "no_b1.json")
    resp = asyncio.run(search_manual("협약 변경"))
    codes = {e["code"] for e in resp["errors"]}
    assert codes == {"manual_unavailable", "manual_b3_unavailable", "manual_b2_unavailable", "manual_b1_unavailable"}
    assert resp["manual_meta_available"] is False


def test_b3_file_missing_fail_safe(fresh_cache, monkeypatch, tmp_path):
    """별권 불가·본권 정상 — 본권만으로 검색 성공·별권 조회만 manual_b3_unavailable(D4·D6)."""
    monkeypatch.setattr(manual_mod, "_B3_DATA_PATH", tmp_path / "no_b3.json")
    resp = asyncio.run(search_manual("협약 변경"))
    assert resp["errors"] == []
    assert resp["searched_sources"] == ["main", "b2", "b1"]
    assert resp["unavailable_sources"] == ["b3"]
    assert resp["source_warnings"][0]["code"] == "manual_b3_unavailable"
    resp2 = asyncio.run(get_manual_section("b3-4-2"))
    assert resp2["errors"][0]["code"] == "manual_b3_unavailable"
    assert "본권 매뉴얼" in resp2["errors"][0]["message"]
    # 본권 조회 무영향 (1-5 경과 조치 — 소형 절·전문 반환)
    resp3 = asyncio.run(get_manual_section("1-5"))
    assert resp3["content_available"] is True


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
    """데이터는 ･(U+FF65) 지배 — 사용자 입력 ·(U+00B7)·ㆍ(U+318D) 모두 매칭.
    (26.7판: 연구시설･장비비 통합관리 = 3-20 — 구판 3-19에서 재번호)"""
    for q in ("연구시설·장비비 통합관리", "연구시설ㆍ장비비 통합관리"):
        r = asyncio.run(search_manual(q))
        assert "3-20" in [m["section_id"] for m in r["matches"]], q
    assert mdot_normalize("시설･장비ㆍ관리") == "시설·장비·관리"


def test_search_excerpts_raw_with_page_anchor():
    r = asyncio.run(search_manual("연구시설·장비비 통합관리"))
    m = next(x for x in r["matches"] if x["section_id"] == "3-20")
    assert m["excerpts"], "발췌가 있어야 함"
    for e in m["excerpts"]:
        assert isinstance(e["printed_page"], int)
        assert m["page_start"] <= e["printed_page"] <= m["page_end"]
    # 발췌는 raw 원문 유지 — 정규화 문자가 섞이지 않음(원문 ･ 보존)
    assert any("･" in e["text"] for e in m["excerpts"])


def test_search_zero_hit_anchor():
    r = asyncio.run(search_manual("존재하지않는키워드검증용문자열"))
    assert r["returned"] == 0 and r["total_matched"] == 0
    assert r["scanned_sections"] == 107  # 본권 43 + 별권3 23 + 별권2 15 + 별권1 26 (v0.35.0)
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
    r = asyncio.run(get_manual_section("4-2"))  # 26.7 image_only_pages [299] 실측
    assert any("299" in w and "이미지" in w for w in r["warnings"])
    r2 = asyncio.run(get_manual_section("3-7"))  # 표 다수 절(증명자료 표)
    assert any("표 포함 절" in w for w in r2["warnings"])


# ── 규범성 메타 상시 동반 ─────────────────────────────────────────────────────

def test_manual_meta_on_all_response_kinds():
    responses = [
        asyncio.run(search_manual("존재하지않는키워드검증용문자열")),
        asyncio.run(get_manual_section("3-9")),
        asyncio.run(get_manual_section("2-3")),
        asyncio.run(get_manual_section("2-3", chunk=1)),
    ]
    for r in responses:
        meta = r["manual_meta"]
        assert meta["source_type"] == "manual_explanation"
        assert meta["legal_effect"] == "not_binding"
        assert meta["edition"] == "26.7"
        assert meta["manual_basis_date"] == "2026-06"
        assert "법령·행정규칙 원문이 우선" in meta["law_priority_note"]
        assert "규정의 부재를 뜻하지 않" in meta["law_priority_note"]
        assert meta["notice"] == "인용 매뉴얼: 26.7판 · 법령 시행일 2026-06 기준"
        assert len(meta["basis_laws"]) == 4
    # 혼합 매치 질의(본권 2-6 + 별권 b3-4-2)는 병기 완성형 notice(D7)
    mixed = asyncio.run(search_manual("기술료"))
    srcs = {m["source"] for m in mixed["matches"]}
    assert srcs == {"main", "b3", "b2"}
    mnotice = mixed["manual_meta"]["notice"]
    assert mnotice.startswith("인용 매뉴얼: 26.7판 · 법령 시행일 2026-06 기준 / ")
    assert "제재처분 가이드라인" in mnotice and "법령 기준일 원문 미표기" in mnotice
    assert mixed["manual_meta"]["source_titles"] == [
        "국가연구개발혁신법 매뉴얼(본권)", "국가연구개발사업 제재처분 가이드라인",
        "국가연구개발사업 기술료 제도 매뉴얼",
    ]
    assert mixed["manual_meta"]["standard_footer"].count("※") == 4


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
    assert payload["meta"]["section_count"] == 43
    assert payload["meta"]["source_type"] == "manual_explanation"
    assert payload["meta"]["legal_effect"] == "not_binding"
    assert len(payload["sections"]) == 43


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
    assert CONTRACT_VERSION == "0.27.0"
    r = asyncio.run(search_manual("기술료"))
    assert r["contract_version"] == "0.27.0"
    r2 = asyncio.run(get_manual_section("1-4"))
    assert r2["contract_version"] == "0.27.0"


# === v0.28.0: 인용 앵커(citation) · 하단 표준 안내(standard_footer) 응답 구조화 ===


def test_citation_format_and_fields():
    """citation은 meta·section 값 조립 — 판번·장/절·제목·인쇄쪽 범위를 한 줄로."""
    data = load_manual()
    sec = data.by_id["3-4"]
    c = build_citation(data.meta, sec)
    assert c.startswith("「국가연구개발혁신법 매뉴얼(본권)」(26.7판) 제3장 ")
    assert sec["section_label"] in c and sec["section_title"] in c
    assert f"인쇄 p.{sec['page_start']}~{sec['page_end']}" in c


def test_citation_reference_section_omits_chapter_zero():
    """참고 자료(ref-N·chapter_no=0)는 '제0장'이 나오면 안 된다 — section_label이 자체 앵커."""
    data = load_manual()
    c = build_citation(data.meta, data.by_id["ref-2"])
    assert "제0장" not in c
    assert "참고 2" in c


def test_citation_page_overrides_and_missing_degrade():
    """청크는 실제 수록 인쇄쪽으로 앵커. 결측 필드는 예외 없이 해당 마디만 생략(never-raise)."""
    data = load_manual()
    sec = data.by_id["2-3"]
    assert "인쇄 p.63~70" in build_citation(data.meta, sec, 63, 70)
    assert "인쇄 p.99" in build_citation(data.meta, sec, 99, 99)  # 단일 페이지 청크
    bare = build_citation({}, {"section_title": "제목만"})
    assert "판)" not in bare and "인쇄" not in bare and "제목만" in bare


def test_standard_footer_lines_by_manual_content():
    """매뉴얼 해설을 실어 보낸 응답만 인용 고지 포함 4줄 — 아니면 법령·매뉴얼 원문 안내 2줄
    (허위 출처 고지 차단·v0.30.0 매뉴얼 원문 안내 줄 공통 삽입)."""
    four = build_standard_footer("인용 매뉴얼: 26.4판", manual_content_included=True)
    assert four.split("\n") == [
        FOOTER_LAW_LINE, FOOTER_MANUAL_SOURCE_LINE, FOOTER_MANUAL_LINE, "※ 인용 매뉴얼: 26.4판",
    ]
    two = build_standard_footer("인용 매뉴얼: 26.4판", manual_content_included=False)
    assert two == FOOTER_LAW_LINE + "\n" + FOOTER_MANUAL_SOURCE_LINE
    assert "매뉴얼 해설 부분은" not in two


def test_manual_meta_block_footer_and_note_present():
    data = load_manual()
    meta = manual_meta_block(data.meta, manual_content_included=True)
    assert meta["standard_footer"].count("\n") == 3
    assert meta["notice"] in meta["standard_footer"]  # notice 값이 그대로 3번째 줄에
    assert "그대로" in meta["standard_footer_note"]


def test_search_manual_attaches_citation_per_match():
    r = asyncio.run(search_manual("학생인건비"))
    assert r["matches"], "매치가 있어야 본 테스트가 의미 있음"
    for m in r["matches"]:
        assert m["citation"].startswith("「")
        assert "인쇄 p." in m["citation"]
    assert r["manual_meta"]["standard_footer"].count("\n") == 3  # 발췌 전달 → 인용 고지 포함 4줄


def test_search_manual_zero_hit_footer_is_law_line_only():
    r = asyncio.run(search_manual("존재하지않는단어조합xyz"))
    assert r["returned"] == 0
    assert r["manual_meta"]["standard_footer"] == FOOTER_LAW_LINE + "\n" + FOOTER_MANUAL_SOURCE_LINE


def test_get_manual_section_citation_by_branch():
    """전문=절 범위 4줄 / 포인터=본문 미전달 2줄 / 청크=chunk_pages 범위 4줄(v0.30.0 공통 2번째 줄 포함)."""
    data = load_manual()
    full = asyncio.run(get_manual_section("1-4"))
    assert full["content_format"] == "plain_text_verbatim"
    sec = data.by_id["1-4"]
    assert f"인쇄 p.{sec['page_start']}~{sec['page_end']}" in full["citation"]
    assert full["manual_meta"]["standard_footer"].count("\n") == 3

    pointer = asyncio.run(get_manual_section("2-3"))
    assert pointer["content_format"] == "oversized_pointer"
    assert pointer["citation"]  # 어느 절을 받아야 하는지의 앵커로는 제공
    assert pointer["manual_meta"]["standard_footer"] == FOOTER_LAW_LINE + "\n" + FOOTER_MANUAL_SOURCE_LINE

    chunk = asyncio.run(get_manual_section("2-3", chunk=1))
    cp = chunk["chunk_pages"]
    assert f"인쇄 p.{cp['page_start']}~{cp['page_end']}" in chunk["citation"]
    assert chunk["citation"] != pointer["citation"]  # 절 전체 범위로 넓혀 말하지 않음
    assert chunk["manual_meta"]["standard_footer"].count("\n") == 3


def test_manual_error_responses_have_no_footer_or_citation():
    """오류 응답에는 전달한 매뉴얼 내용이 0 — footer·citation 미부착(허위 고지·노이즈 차단)."""
    for resp in (
        asyncio.run(get_manual_section("BP0001")),      # invalid_section_id
        asyncio.run(get_manual_section("9-9")),          # not_found
        asyncio.run(search_manual("x")),                 # invalid_query
        asyncio.run(get_manual_section("2-3", chunk=99)),  # 청크 범위 밖
    ):
        assert resp["errors"][0]["code"] in {
            "invalid_section_id", "not_found", "invalid_query",
        }
        assert "citation" not in resp
        assert "manual_meta" not in resp


def test_v0280_no_size_tier_regression():
    """절별 size-tier 판정 잠금 — 26.7판 실측: 전문 31·포인터 12(구판 29·12)."""
    data = load_manual()
    formats = [asyncio.run(get_manual_section(s["id"]))["content_format"] for s in data.sections]
    assert formats.count("plain_text_verbatim") == 31
    assert formats.count("oversized_pointer") == 12


def test_v0280_responses_within_budget():
    """추가 필드 포함 최종 직렬화가 예산 내(전문 절 상세·검색 응답 모두)."""
    from korean_rnd_regs_mcp.main import _SEARCH_RESPONSE_CHAR_BUDGET
    data = load_manual()
    budget = MANUAL_DETAIL_CHAR_BUDGET - MANUAL_DETAIL_HEADROOM
    for s in data.sections:
        r = asyncio.run(get_manual_section(s["id"]))
        if r["content_format"] == "plain_text_verbatim":
            assert len(json.dumps(r, ensure_ascii=False)) <= budget, s["id"]
    for q in ("연구개발비", "학생인건비", "기술료 징수", "국가연구개발"):
        assert len(json.dumps(asyncio.run(search_manual(q)), ensure_ascii=False)) <= _SEARCH_RESPONSE_CHAR_BUDGET


def test_v0280_prompt_surfaces_reference_standard_footer():
    """3표면 문면 잠금: 하단 안내는 서버 완성형 참조 + 폴백 병기, 인용은 citation 지시."""
    from korean_rnd_regs_mcp.main import _SERVER_INSTRUCTIONS, review_regulation_prompt
    template = review_regulation_prompt("X")
    for surface in (_SERVER_INSTRUCTIONS, template):
        assert "standard_footer" in surface
        assert "직접 조립하지" in surface
        assert "standard_footer가 없는 경우" in surface  # 롤백 과도기 폴백 병기
        assert FOOTER_LAW_LINE in surface  # 폴백 리터럴 보존
    assert "citation 값을 그대로" in _SERVER_INSTRUCTIONS
    assert "청크 응답의 citation" in _SERVER_INSTRUCTIONS  # 확인 범위 초과 표기 차단
    assert "citation 값을 그대로" in template


def test_citation_never_raises_on_malformed_fields():
    """데이터 재생성 오류로 필드 타입이 어긋나도 예외 대신 한 줄 문자열(적대검토 지적)."""
    meta = {"source_title": 12345, "edition": ["x"]}
    sec = {"chapter_no": float("inf"), "section_label": 7, "section_title": object()}
    out = build_citation(meta, sec)
    assert isinstance(out, str) and "\n" not in out
    assert "제inf장" not in out  # OverflowError 대신 장 생략
    # 줄바꿈 포함 제목도 한 줄로 축약(지시문처럼 보이는 다중 행 삽입 차단)
    multi = build_citation({"source_title": "제목\n둘째 줄"}, {"section_title": "본문\n행"})
    assert "\n" not in multi and "제목 둘째 줄" in multi


def test_search_footer_recomputed_when_budget_pops_all_matches(monkeypatch):
    """예산 절단으로 매치가 전부 빠지면 footer도 2줄(미인용형)로 되돌아간다(허위 고지 차단 경로)."""
    from korean_rnd_regs_mcp import main as main_mod
    monkeypatch.setattr(main_mod, "_SEARCH_RESPONSE_CHAR_BUDGET", 1200)
    r = asyncio.run(search_manual("학생인건비"))
    assert r["returned"] == 0 and r["truncated"] is True
    assert r["manual_meta"]["standard_footer"] == FOOTER_LAW_LINE + "\n" + FOOTER_MANUAL_SOURCE_LINE


def test_all_pointers_and_chunks_within_budget():
    """포인터·청크 전수의 최종 직렬화가 예산 내(적대검토 지적 — 전문만 검사하던 공백)."""
    data = load_manual()
    budget = MANUAL_DETAIL_CHAR_BUDGET - MANUAL_DETAIL_HEADROOM
    checked = 0
    for s in data.sections:
        p = asyncio.run(get_manual_section(s["id"]))
        assert len(json.dumps(p, ensure_ascii=False)) <= budget, s["id"]
        if p["content_format"] != "oversized_pointer":
            continue
        for i in range(1, p["chunk_count"] + 1):
            c = asyncio.run(get_manual_section(s["id"], chunk=i))
            assert len(json.dumps(c, ensure_ascii=False)) <= MANUAL_DETAIL_CHAR_BUDGET, (s["id"], i)
            checked += 1
    assert checked >= 12  # 대형 절 12개 × 최소 1청크


def test_manual_unavailable_and_long_query_have_no_footer(fresh_cache, monkeypatch, tmp_path):
    """로더 실패·과장 query 오류에도 citation·manual_meta 미부착(적대검토 지적)."""
    long_q = asyncio.run(search_manual("가" * (_MANUAL_QUERY_MAX + 1)))
    assert "citation" not in long_q and "manual_meta" not in long_q

    monkeypatch.setattr(manual_mod, "_DATA_PATH", tmp_path / "gone.json")
    r = asyncio.run(get_manual_section("1-1"))
    assert r["errors"][0]["code"] == "manual_unavailable"
    assert "citation" not in r and "manual_meta" not in r


def test_v0280_prompt_defines_multi_response_footer_priority():
    """여러 매뉴얼 응답의 footer 값이 다를 때의 선택 규칙이 3표면에 명시(적대검토 MAJOR 해소)."""
    from korean_rnd_regs_mcp.main import _SERVER_INSTRUCTIONS, review_regulation_prompt
    template = review_regulation_prompt("X")
    for surface in (_SERVER_INSTRUCTIONS, template):
        assert "마지막 응답 값을 고르지 말고" in surface
        assert "처음 두 줄에 법령·매뉴얼 원문 확인 안내" in surface
    note = manual_meta_block(load_manual().meta, manual_content_included=True)["standard_footer_note"]
    assert "여러 개 받았다면" in note and "매뉴얼 인용 고지가 포함된 값" in note


# ── v0.30.0: 출처·원문 확인 경로 정비(source_url·매뉴얼 원문 안내 줄) ──────────

def test_v0300_source_url_and_footer_locks():
    """v0.30.0 잠금: meta.source_url 정확값·데이터 불변·구데이터 fail-safe·KISTEP 줄 문면·
    규정-매뉴얼 footer 처음 두 줄 동일(dedup)."""
    data = load_manual()
    url = "https://www.kistep.re.kr/board.es?mid=a10301000000&bid=0003&act=view&list_no=94788"
    assert data.meta["source_url"] == url  # 임베드 26.7판 게시물 — 판 갱신 시 재추출과 함께 변경
    # 데이터가 26.7판 원본에서 생성됐음을 잠금(원본 PDF 해시·절 수)
    assert data.meta["pdf_sha256"] == (
        "1b2a5089ab5f1cd168c77593bb35556479f19fb7b5e285c9ba07542a82222853"
    )
    assert data.meta["section_count"] == 43

    block = manual_meta_block(data.meta, manual_content_included=True)
    assert block["source_url"] == url

    # 구데이터(source_url 키 부재) fail-safe — 필드 생략·footer 구조는 동일
    legacy = manual_meta_block(
        {"edition": "26.4", "manual_basis_date": "2026-03"}, manual_content_included=True
    )
    assert "source_url" not in legacy
    assert legacy["standard_footer"].count("\n") == 3
    # 비문자열·빈 값도 생략(fail-safe — diff 적대검토 MINOR 반영)
    for bad in (123, ["u"], "", None):
        b = manual_meta_block({"source_url": bad}, manual_content_included=False)
        assert "source_url" not in b

    # KISTEP 줄 문면 잠금 — URL 쿼리·판번을 넣지 않는 홈페이지 안내형(Andy 확정 문안)
    assert FOOTER_MANUAL_SOURCE_LINE.startswith("※ ")
    assert "www.kistep.re.kr" in FOOTER_MANUAL_SOURCE_LINE
    assert "list_no" not in FOOTER_MANUAL_SOURCE_LINE
    assert "26.4" not in FOOTER_MANUAL_SOURCE_LINE
    assert "26.7" not in FOOTER_MANUAL_SOURCE_LINE  # 판번 미포함 원칙 — 판 갱신에도 문면 불변

    # 규정 상세 footer(2줄)와 매뉴얼 footer 처음 두 줄이 동일 문자열 — 호스트 dedup 성립
    from korean_rnd_regs_mcp.main import _attach_std_footer
    prov = _attach_std_footer({"x": 1})["standard_footer"]
    assert prov == FOOTER_LAW_LINE + "\n" + FOOTER_MANUAL_SOURCE_LINE
    assert block["standard_footer"].startswith(prov + "\n")


# ── v0.31.0: 본권 26.7판 현행화 — 재번호 잠금·renumbering_note 조건부 부착 ──────

def test_v0310_edition_locks():
    """26.7판 데이터 잠금: 판번·기준일·본문 쪽 범위·[참고] 3건·기준 법령 4건."""
    data = load_manual()
    assert data.meta["edition"] == "26.7"
    assert data.meta["manual_basis_date"] == "2026-06"
    assert data.meta["body_pages_printed"] == [1, 332]
    assert data.by_id["ref-3"]["section_title"] == "국가연구개발사업 행정서식 관리체계"
    numbers = [x["number"] for x in data.meta["basis_laws"]]
    assert "대통령령 제36291호" in numbers  # 26.7 기준표(시행령 2026-05-06 일부개정)
    assert "과학기술정보통신부고시 제2026-38호" in numbers


def test_v0310_renumbered_id_title_locks():
    """제3장 재번호 전수 잠금 — 26.4판 3-12~3-19의 주제가 3-13~3-20으로 이동(연구혁신비 신설).
    3-4는 안정 id 회귀 앵커(주제 유지)."""
    data = load_manual()
    expected = {
        "3-11": "국제공동연구개발비 및 연구개발부담비 사용용도 및 사용기준",
        "3-12": "연구혁신비 사용용도 및 사용기준",
        "3-13": "간접비 사용용도 및 사용기준",
        "3-14": "사용절차 및 사전승인대상",
        "3-15": "연구개발비 이자 사용용도",
        "3-16": "연구개발비 정산･회수 절차",
        "3-17": "간접비고시비율 산출",
        "3-18": "연구비통합관리시스템",
        "3-19": "학생인건비통합관리",
        "3-20": "연구시설･장비비 통합관리",
        "3-4": "학생인건비 사용용도 및 사용기준",
    }
    for sid, title in expected.items():
        assert data.by_id[sid]["section_title"] == title, sid


def test_v0310_renumbering_note_conditional_attach():
    """note는 get_manual_section 비오류 응답의 대상 절에만 — search·비대상 절·오류 미부착."""
    target = asyncio.run(get_manual_section("3-12"))
    note = target["manual_meta"]["renumbering_note"]
    assert "연구혁신비" in note and "search_manual" in note
    stable = asyncio.run(get_manual_section("3-4"))  # 비대상(안정 id)
    assert "renumbering_note" not in stable["manual_meta"]
    s = asyncio.run(search_manual("간접비"))
    assert "renumbering_note" not in s["manual_meta"]
    err = asyncio.run(get_manual_section("9-99"))
    assert "manual_meta" not in err


def test_v0310_renumbering_note_all_target_sections():
    """데이터의 대상 절 전수(3-12~3-20)에서 부착 — 목록과 실제 부착의 정합 잠금."""
    data = load_manual()
    ids = data.meta["renumbering_note_section_ids"]
    assert ids == ["3-12", "3-13", "3-14", "3-15", "3-16", "3-17", "3-18", "3-19", "3-20"]
    for sid in ids:
        r = asyncio.run(get_manual_section(sid))
        assert "renumbering_note" in r["manual_meta"], sid


def test_v0310_renumbering_note_pointer_and_chunk_branches(monkeypatch):
    """포인터·청크 분기에도 부착(예산 축소로 대상 절을 강제 포인터화해 라이브 경로 검증)."""
    from korean_rnd_regs_mcp import main as main_mod
    monkeypatch.setattr(main_mod, "MANUAL_DETAIL_CHAR_BUDGET", 3000)
    p = asyncio.run(get_manual_section("3-13"))
    assert p["content_format"] == "oversized_pointer"
    assert "renumbering_note" in p["manual_meta"]
    c = asyncio.run(get_manual_section("3-13", chunk=1))
    assert "renumbering_note" in c["manual_meta"]


def test_v0310_renumbering_note_fail_safe():
    """비정형 데이터(비문자열 note·비리스트 ids·키 부재)·section_id 미전달은 필드 생략."""
    for meta in (
        {"renumbering_note": 123, "renumbering_note_section_ids": ["3-12"]},
        {"renumbering_note": "n", "renumbering_note_section_ids": "3-12"},
        {"renumbering_note": "n", "renumbering_note_section_ids": [1, 2]},
        {"renumbering_note": "", "renumbering_note_section_ids": ["3-12"]},
        {},
    ):
        assert "renumbering_note" not in manual_meta_block(meta, section_id="3-12")
    ok = manual_meta_block(
        {"renumbering_note": "n", "renumbering_note_section_ids": ["3-12"]}, section_id="3-12"
    )
    assert ok["renumbering_note"] == "n"
    no_sid = manual_meta_block(
        {"renumbering_note": "n", "renumbering_note_section_ids": ["3-12"]}
    )
    assert "renumbering_note" not in no_sid  # search_manual 경로(미전달) 미부착
