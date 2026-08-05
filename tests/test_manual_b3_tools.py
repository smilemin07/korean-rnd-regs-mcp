"""v0.32.0 R2-P2 — 별권 3 「국가연구개발사업 제재처분 가이드라인」 통합 잠금 테스트.

canonical 설계 = R2-P0 설계 동결 문서 D1~D11(2026-08-02·vault). 네트워크 호출 없음.
잠금 대상: 라우팅·정규식(D3·D6), 검색 병합·무회귀(D5), 장애 격리(D4·D5), meta 문면(D7),
규범성 확장(D8), table_structure_notes 표면화(P1 표 장부), oversized 청크, 표면 문구(v0320).
"""

import asyncio
import json

import pytest

import korean_rnd_regs_mcp.manual as manual_mod
from korean_rnd_regs_mcp.main import get_manual_section, search_manual
from korean_rnd_regs_mcp.manual import (
    SECTION_ID_RE,
    load_manual_b3,
    mixed_manual_meta_block,
)


@pytest.fixture()
def fresh_cache():
    manual_mod._reset_cache_for_tests()
    yield
    manual_mod._reset_cache_for_tests()


# ── D3: id 정규식 ────────────────────────────────────────────────────────────

def test_section_id_re_accepts_b3_forms():
    for ok in ("b3-1-1", "b3-4-2", "b3-5-5", "b3-ref-1", "3-4", "ref-3"):
        assert SECTION_ID_RE.match(ok), ok
    for bad in ("b3-", "b3-1", "b31-1", "b3-ref", "b3-1-1-1", "b4-1-1", "B3-1-1", " b3-1-1"):
        assert not SECTION_ID_RE.match(bad), bad


# ── 데이터·로더 ──────────────────────────────────────────────────────────────

def test_b3_data_loads_23_units(fresh_cache):
    data = load_manual_b3()
    assert not isinstance(data, manual_mod.ManualLoadError)
    assert len(data.sections) == 23
    ids = [s["id"] for s in data.sections]
    assert ids[0] == "b3-1-1" and ids[-1] == "b3-ref-1"
    # 로컬 section_index 0..22 (전역 index 비저장 — D4)
    assert [s["section_index"] for s in data.sections] == list(range(23))
    meta = data.meta
    assert meta["source_title"] == "국가연구개발사업 제재처분 가이드라인"
    assert meta["series_part"] == "별권 3"
    assert meta["edition"] == "26.7"
    assert meta["manual_basis_date"] is None
    assert "게시 세트" in meta["edition_note"]
    assert "준용하지 않았습니다" in meta["basis_note"]
    assert len(meta["law_priority_extra"]) == 2


# ── D6: 상세 조회 라우팅 ─────────────────────────────────────────────────────

def test_b3_detail_small_section(fresh_cache):
    r = asyncio.run(get_manual_section("b3-5-3"))
    assert r["content_available"] is True
    assert r["content_format"] == "plain_text_verbatim"
    assert r["section_title"].startswith("연구개발비 사용용도 기준 위반")
    assert r["page_start"] == 83 and r["page_end"] == 84
    assert "자진반납" in r["content"]
    # citation·format_note는 별권 문면
    assert r["citation"].startswith("「국가연구개발사업 제재처분 가이드라인」(26.7판) 제5장 3.")
    assert "별권 3" in r["format_note"]
    # renumbering_note는 별권 데이터에 없음 — 미부착(fail-safe)
    assert "renumbering_note" not in r["manual_meta"]


def test_b3_detail_appendix_citation_no_chapter(fresh_cache):
    r = asyncio.run(get_manual_section("b3-ref-1"))
    assert r["content_available"] is True
    cit = r["citation"]
    assert cit.startswith("「국가연구개발사업 제재처분 가이드라인」(26.7판) <부록>")
    assert "제0장" not in cit
    assert r["page_start"] == 88 and r["page_end"] == 89


def test_b3_oversized_pointer_and_chunks(fresh_cache):
    r = asyncio.run(get_manual_section("b3-4-2"))
    assert r["content_available"] is False
    assert r["content_format"] == "oversized_pointer"
    assert r["chunk_count"] == 2
    c1 = asyncio.run(get_manual_section("b3-4-2", chunk=1))
    c2 = asyncio.run(get_manual_section("b3-4-2", chunk=2))
    assert c1["chunk_pages"] == {"page_start": 57, "page_end": 70}
    assert c2["chunk_pages"] == {"page_start": 71, "page_end": 80}
    # 청크 재조립 무손실 (build_section_chunks 불변식)
    data = load_manual_b3()
    assert c1["content"] + c2["content"] == data.full_text["b3-4-2"]
    # 청크 citation은 청크 실수록 인쇄쪽 범위로 앵커
    assert "인쇄 p.57~70" in c1["citation"] and "인쇄 p.71~80" in c2["citation"]


def test_b3_table_structure_notes_surfaced(fresh_cache):
    """P1 표 장부 관찰 2건의 표적 고지 — 포인터·청크 분기 전부 warnings로 동반."""
    for resp in (
        asyncio.run(get_manual_section("b3-4-2")),
        asyncio.run(get_manual_section("b3-4-2", chunk=1)),
    ):
        joined = " ".join(resp["warnings"])
        assert "병합 범위" in joined and "2분의 1의 범위" in joined
        assert "감경요소/가중요소 예시표" in joined
    # 고지 없는 절에는 미부착
    r = asyncio.run(get_manual_section("b3-5-3"))
    joined = " ".join(r["warnings"])
    assert "병합 범위" not in joined


def test_b3_not_found_lists_b3_range(fresh_cache):
    r = asyncio.run(get_manual_section("b3-9-9"))
    assert r["errors"][0]["code"] == "not_found"
    msg = r["errors"][0]["message"]
    assert "b3-1-1~b3-1-3" in msg and "b3-ref-1" in msg
    # 본권 not_found는 본권 범위 유지
    r2 = asyncio.run(get_manual_section("9-9"))
    assert "3-1~3-20" in r2["errors"][0]["message"]


# ── D7: meta 문면 ────────────────────────────────────────────────────────────

def test_b3_manual_meta_wording(fresh_cache):
    r = asyncio.run(get_manual_section("b3-5-3"))
    meta = r["manual_meta"]
    assert meta["source_title"] == "국가연구개발사업 제재처분 가이드라인"
    assert meta["edition"] == "26.7"
    assert meta["manual_basis_date"] is None
    assert meta["notice"] == (
        "인용 자료: 「국가연구개발사업 제재처분 가이드라인」(국가연구개발혁신법 매뉴얼 별권 3) "
        "26.7판(판번은 게시 세트 기준) · 법령 기준일 원문 미표기"
    )
    note = meta["law_priority_note"]
    assert note.startswith("본 내용은 「국가연구개발사업 제재처분 가이드라인」(국가연구개발혁신법 매뉴얼 별권 3)의 해설이며")
    assert "법령 기준일이 원문에 명시되어 있지 않아" in note
    # D8 규범성 확장 2문장 (데이터 law_priority_extra append)
    assert "시행령 별표 6·별표 7 원문을 교차 확인" in note
    assert "제5장의 쟁점·검토결과" in note and "일반화할 수 없습니다" in note
    # footer 4줄(매뉴얼 내용 전달) — notice 줄은 별권 문면
    footer = meta["standard_footer"]
    assert footer.count("※") == 4
    assert "법령 기준일 원문 미표기" in footer


def test_main_meta_unchanged_by_b3(fresh_cache):
    """본권 meta 문면은 별권 도입 후에도 글자 단위 불변(v0.28.0~ 잠금 보호)."""
    r = asyncio.run(get_manual_section("1-5"))
    meta = r["manual_meta"]
    assert meta["notice"] == "인용 매뉴얼: 26.7판 · 법령 시행일 2026-06 기준"
    note = meta["law_priority_note"]
    assert note.startswith("본 내용은 「국가연구개발혁신법 매뉴얼」의 해설이며")
    assert "매뉴얼은 법령 시행일 2026-06 기준으로 작성되어 이후 법령 개정이 반영되지 않았을 수 있고" in note
    assert "별표 6" not in note  # 별권 확장 문장이 본권에 새지 않음
    assert "본권" not in r["format_note"] or "별권" not in r["format_note"]
    assert r["format_note"].find("본권 PDF") > 0


# ── D5: 검색 병합 ────────────────────────────────────────────────────────────

def test_search_merge_source_fields(fresh_cache):
    r = asyncio.run(search_manual("제재처분 절차"))
    assert r["errors"] == []
    assert r["searched_sources"] == ["main", "b3", "b2", "b1"]
    assert "unavailable_sources" not in r
    assert set(r["returned_by_source"]) == {"main", "b3", "b2", "b1"}
    assert sum(r["returned_by_source"].values()) == r["returned"]
    assert r["total_matched_by_source"]["b3"] >= 9  # 제3장 절 9개 제목 매치
    for m in r["matches"]:
        assert m["source"] in ("main", "b3", "b2")
        if m["source"] == "b3":
            assert m["section_id"].startswith("b3-")
            assert m["citation"].startswith("「국가연구개발사업 제재처분 가이드라인」")
    assert r["returned"] <= 10


def test_search_merge_ordering_tier_then_source(fresh_cache):
    """정렬 = (tier, source_rank, local_index) — 같은 tier에서 본권이 별권보다 앞."""
    r = asyncio.run(search_manual("기술료"))
    srcs = [m["source"] for m in r["matches"]]
    assert "main" in srcs and "b3" in srcs
    # 본권 2-6(기술료 징수·납부·사용·제목 매치)이 별권 어떤 매치보다도 앞
    first_b3 = srcs.index("b3")
    main_26 = next(i for i, m in enumerate(r["matches"]) if m["section_id"] == "2-6")
    assert main_26 < first_b3


def test_search_no_b3_match_main_results_unchanged(fresh_cache, monkeypatch, tmp_path):
    """D5 무회귀: 별권 무매치 질의의 본권 matches[] 내용·순서 = 본권 단독 검색과 동일."""
    merged = asyncio.run(search_manual("학생인건비 통합관리"))
    assert merged["total_matched_by_source"].get("b3", 0) == 0
    # 별권 로더를 강제 실패시켜 본권 단독 기준선 생성
    manual_mod._reset_cache_for_tests()
    monkeypatch.setattr(manual_mod, "_B3_DATA_PATH", tmp_path / "no_b3.json")
    baseline = asyncio.run(search_manual("학생인건비 통합관리"))
    key = lambda r: [(m["section_id"], m["citation"]) for m in r["matches"]]
    assert key(merged) == key(baseline)


def test_search_zero_hit_note_covers_both_sources(fresh_cache):
    r = asyncio.run(search_manual("존재하지않는키워드검증용문자열"))
    assert r["returned"] == 0
    assert r["scanned_sections"] == 107
    assert r["total_matched_by_source"] == {"main": 0, "b3": 0, "b2": 0, "b1": 0}
    # 0건 footer는 2줄(허위 인용 고지 차단) — 기존 규약 유지
    assert r["manual_meta"]["standard_footer"].count("※") == 2


def test_mixed_meta_block_shape():
    """mixed_manual_meta_block 단위 계약 — 병기 notice·source_titles·별권 확장 문장."""
    main_meta = {"edition": "9.9", "manual_basis_date": "2099-01", "source_title": "A매뉴얼"}
    b3_meta = {
        "edition": "9.9", "source_title": "B가이드", "series_title": "A매뉴얼", "series_part": "별권 9",
        "edition_note": "x", "basis_note": "y", "law_priority_extra": ["문장1.", "문장2."],
    }
    block = mixed_manual_meta_block(("main", main_meta), [("b9", b3_meta)], manual_content_included=True)
    assert block["source_titles"] == ["A매뉴얼", "B가이드"]
    assert " / " in block["notice"]
    assert block["law_priority_note"].endswith("문장1. 문장2.")
    assert block["standard_footer"].count("※") == 4


# ── v0320 표면 문구 잠금 ─────────────────────────────────────────────────────

def test_v0320_surface_locks():
    import korean_rnd_regs_mcp.main as main_mod
    instructions = main_mod.mcp.instructions or ""
    assert "별권 3 「국가연구개발사업 제재처분 가이드라인」" in instructions
    assert "시행령 별표 6·별표 7" in instructions
    tmpl = main_mod._REVIEW_PROMPT_TEMPLATE
    assert "(본권·별권 3 제재처분 가이드라인·별권 2 기술료 제도 매뉴얼·별권 1 학생인건비통합관리 제도 매뉴얼)" in tmpl
    # 도구 docstring — FastMCP 래핑을 우회해 원 함수 문서 확인
    sm_doc = main_mod.search_manual.fn.__doc__ if hasattr(main_mod.search_manual, "fn") else main_mod.search_manual.__doc__
    gs_doc = main_mod.get_manual_section.fn.__doc__ if hasattr(main_mod.get_manual_section, "fn") else main_mod.get_manual_section.__doc__
    assert "별권 3" in sm_doc and "source" in sm_doc
    assert "b3-4-2" in gs_doc and "별표 6" in gs_doc


def test_b3_packaging_force_include():
    """pyproject force-include에 manual_b3.json 동봉(P1 위험 1순위 = 패키징 누락)."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"src/korean_rnd_regs_mcp/manual_b3.json" = "korean_rnd_regs_mcp/manual_b3.json"' in pyproject
    # 데이터 파일 실재 + 스키마 최소 구조
    payload = json.loads((root / "src/korean_rnd_regs_mcp/manual_b3.json").read_text(encoding="utf-8"))
    assert payload["meta"]["section_count"] == 23
    assert len(payload["sections"]) == 23


# ── P2 적대검토 반영 잠금 (손상 격리·문면 정직성·절단 경계) ──────────────────

def _write_b3(tmp_path, payload_text: str):
    bad = tmp_path / "corrupt_b3.json"
    bad.write_text(payload_text, encoding="utf-8")
    return bad


@pytest.mark.parametrize("payload_text, tag", [
    ('[1, 2, 3]', "top_level_array"),
    ('{"meta": {}, "sections": [null, 5]}', "null_section"),
    ('{"meta": {"edition": "x"}, "sections": [{"id": "b3-1-1", "pages": "notalist"}]}', "pages_not_list"),
])
def test_b3_corrupt_data_isolated(fresh_cache, monkeypatch, tmp_path, payload_text, tag):
    """구조 손상 별권 파일이 예외 전파 없이 manual_b3_unavailable로 격리·본권 검색 지속(D4)."""
    monkeypatch.setattr(manual_mod, "_B3_DATA_PATH", _write_b3(tmp_path, payload_text))
    r = load_manual_b3()
    assert isinstance(r, manual_mod.ManualLoadError), tag
    assert r.reason == "schema_invalid"
    # 병합 검색은 본권만으로 정상 지속
    resp = asyncio.run(search_manual("협약 변경"))
    assert resp["errors"] == []
    assert resp["searched_sources"] == ["main", "b2", "b1"]
    assert resp["unavailable_sources"] == ["b3"]
    # 별권 상세는 격리 오류
    resp2 = asyncio.run(get_manual_section("b3-1-1"))
    assert resp2["errors"][0]["code"] == "manual_b3_unavailable"


def test_both_fail_no_false_normal_claim(fresh_cache, monkeypatch, tmp_path):
    """모두 불가 응답에 미확인 소스 "정상" 단정이 없어야 함(P2 적대검토 MAJOR 문면 잠금)."""
    monkeypatch.setattr(manual_mod, "_DATA_PATH", tmp_path / "no_main.json")
    monkeypatch.setattr(manual_mod, "_B3_DATA_PATH", tmp_path / "no_b3.json")
    monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", tmp_path / "no_b2.json")
    monkeypatch.setattr(manual_mod, "_B1_DATA_PATH", tmp_path / "no_b1.json")
    resp = asyncio.run(search_manual("협약 변경"))
    joined = " ".join(e["message"] for e in resp["errors"])
    assert "본권 매뉴얼 검색·조회와 규정 도구는 정상" not in joined
    assert "모두" in joined and "규정 도구" in joined  # 규정 도구 정상 안내는 유지(매뉴얼과 독립·항상 참)
    # 별권 상세 실패도 본권 불가 상태에선 본권 정상 단정 없음
    resp2 = asyncio.run(get_manual_section("b3-1-1"))
    assert resp2["errors"][0]["code"] == "manual_b3_unavailable"
    assert "본권 매뉴얼 검색·조회와 규정 도구는 정상" not in resp2["errors"][0]["message"]


def test_b3_detail_fail_mentions_main_only_when_verified(fresh_cache, monkeypatch, tmp_path):
    """별권만 불가(본권 확인 정상) — 이때만 본권 정상 문구 포함."""
    monkeypatch.setattr(manual_mod, "_B3_DATA_PATH", tmp_path / "no_b3.json")
    resp = asyncio.run(get_manual_section("b3-1-1"))
    assert "본권 매뉴얼 검색·조회와 규정 도구는 정상입니다" in resp["errors"][0]["message"]


def test_main_fail_b3_ok_zero_hit_meta(fresh_cache, monkeypatch, tmp_path):
    """본권 불가·별권 정상·무매치 — 별권 meta + 부분 결과 경고 유지(P2 적대검토 경계)."""
    monkeypatch.setattr(manual_mod, "_DATA_PATH", tmp_path / "no_main.json")
    resp = asyncio.run(search_manual("존재하지않는키워드검증용문자열"))
    assert resp["returned"] == 0 and resp["errors"] == []
    assert resp["searched_sources"] == ["b3", "b2", "b1"]
    assert resp["source_warnings"][0]["code"] == "manual_unavailable"
    # meta는 별권 기준(본권 meta 하드코딩 없음)
    assert resp["manual_meta"]["source_title"] == "국가연구개발사업 제재처분 가이드라인"
    assert resp["manual_meta"]["manual_basis_date"] is None


def test_budget_trim_recomputes_by_source_and_note(fresh_cache, monkeypatch):
    """예산 절단 경계 — returned_by_source·manual_meta 재계산·전멸 시 절단 note(P2 계약 정의)."""
    import korean_rnd_regs_mcp.main as main_mod
    # 아주 작은 예산으로 강제 절단 — 전멸 케이스
    monkeypatch.setattr(main_mod, "_SEARCH_RESPONSE_CHAR_BUDGET", 100)
    r = asyncio.run(search_manual("제재처분 절차"))
    assert r["returned"] == 0 and r["truncated"] is True
    assert r["total_matched"] > 0
    assert sum(r["returned_by_source"].values()) == 0
    assert "예산 초과로 전부 절단" in r["note"]
    # footer는 0건 형태(2줄 — 허위 인용 고지 차단)
    assert r["manual_meta"]["standard_footer"].count("※") == 2


def test_budget_trim_partial_keeps_consistency(fresh_cache, monkeypatch):
    """부분 절단 — 남은 매치와 returned_by_source·manual_meta 소스 구성이 일치."""
    import korean_rnd_regs_mcp.main as main_mod
    monkeypatch.setattr(main_mod, "_SEARCH_RESPONSE_CHAR_BUDGET", 6000)
    r = asyncio.run(search_manual("제재처분 절차"))
    assert 0 < r["returned"] < r["total_matched"]
    assert sum(r["returned_by_source"].values()) == r["returned"]
    srcs = {m["source"] for m in r["matches"]}
    if srcs == {"b3"}:
        assert r["manual_meta"]["source_title"] == "국가연구개발사업 제재처분 가이드라인"
    elif srcs == {"main", "b3"}:
        assert "sources" in r["manual_meta"]


def test_table_structure_notes_string_not_exploded(fresh_cache):
    """table_structure_notes가 리스트가 아니면(손상) 문자별 분해 없이 무시(P2 적대검토 경계 결함)."""
    data = load_manual_b3()
    sec = data.by_id["b3-5-4"]
    try:
        sec["table_structure_notes"] = "문자열오염"
        r = asyncio.run(get_manual_section("b3-5-4"))
        assert not any(len(w) == 1 for w in r["warnings"])
        assert "문자열오염" not in " ".join(r["warnings"])
    finally:
        sec.pop("table_structure_notes", None)


def test_mixed_meta_sources_and_provenance(fresh_cache):
    """혼합 meta의 소스별 구조 필드·provenance_note·기준일 부재 문장(P2 적대검토 MAJOR 보강)."""
    r = asyncio.run(search_manual("기술료"))
    meta = r["manual_meta"]
    assert meta["sources"]["main"]["manual_basis_date"] == "2026-06"
    assert meta["sources"]["b3"]["manual_basis_date"] is None
    assert meta["sources"]["b3"]["source_title"] == "국가연구개발사업 제재처분 가이드라인"
    assert "본권 기준입니다" in meta["provenance_note"]
    assert "별권 3은 법령 기준일이 원문에 명시되어 있지 않아" in meta["law_priority_note"]


def test_v0320_no_stale_uncovered_phrases():
    """미커버 표면 자가충돌 부재 — prompt description·README(P2 적대검토 MAJOR 잠금)."""
    import pathlib
    import korean_rnd_regs_mcp.main as main_mod
    src = pathlib.Path(main_mod.__file__).read_text(encoding="utf-8")
    assert "매뉴얼 별권 4종은 본 server 미커버" not in src
    assert "별권 4종(학생인건비·기술료·제재처분·연구시설장비)" not in src
    root = pathlib.Path(__file__).resolve().parent.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "별권 4종(학생인건비·기술료·제재처분·연구시설장비)은 미수록" not in readme
    assert "별권 4종" not in readme
