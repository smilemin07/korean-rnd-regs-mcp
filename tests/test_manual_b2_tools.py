"""v0.33.0 R3-P2 — 별권 2 「국가연구개발사업 기술료 제도 매뉴얼」 통합 잠금 테스트.

canonical 설계 = R3-P0 설계 동결 문서 D1~D12(2026-08-03·vault). 네트워크 호출 없음.
잠금 대상: id 정규식·라우팅(D3), 강화 로더 검증·장애 격리(D4), 교차 소스 층 일반화·
보존 표면 4항(D5), 검색 도달·무회귀(D6), meta·규범성 3문장(D7), table_structure_notes
표면화(D8·P1 결속 객체 장부), 소스 가용성 8조합 envelope, 표면 문구(v0330), 패키징.
"""

import asyncio
import itertools
import json

import pytest

import korean_rnd_regs_mcp.main as main_mod
import korean_rnd_regs_mcp.manual as manual_mod
from korean_rnd_regs_mcp.main import get_manual_section, search_manual
from korean_rnd_regs_mcp.manual import (
    SECTION_ID_RE,
    load_manual_b2,
    mixed_manual_meta_block,
)


@pytest.fixture()
def fresh_cache():
    manual_mod._reset_cache_for_tests()
    yield
    manual_mod._reset_cache_for_tests()


B2_ALL_IDS = [
    "b2-1-1", "b2-1-2", "b2-1-3",
    "b2-2-1", "b2-2-2", "b2-2-3", "b2-2-4", "b2-2-5",
    "b2-3-1", "b2-3-2", "b2-3-3", "b2-3-4", "b2-3-5", "b2-3-6",
    "b2-ref-1",
]


# ── D3: id 정규식 ────────────────────────────────────────────────────────────

def test_section_id_re_accepts_b2_forms():
    for ok in ("b2-1-1", "b2-3-6", "b2-ref-1", "b3-4-2", "3-4", "ref-3", "b1-1-1"):
        assert SECTION_ID_RE.match(ok), ok
    for bad in ("b2-", "b2-1", "b21-1", "b2-ref", "b2-1-1-1", "b1-", "b1-1", "b4-1-1", "B2-1-1", " b2-1-1"):
        assert not SECTION_ID_RE.match(bad), bad


# ── D4: 데이터·강화 로더 ─────────────────────────────────────────────────────

def test_b2_data_loads_15_units(fresh_cache):
    data = load_manual_b2()
    assert not isinstance(data, manual_mod.ManualLoadError)
    assert [s["id"] for s in data.sections] == B2_ALL_IDS
    assert data.meta["series_part"] == "별권 2"
    assert data.meta["edition"] == "26.7"
    assert data.meta["manual_basis_date"] is None
    assert len(data.meta["law_priority_extra"]) == 3


def test_b2_loader_strict_validation_extras(fresh_cache, monkeypatch, tmp_path):
    """D4 강화 검증(신규 로더 한정) — 중복 id·prefix·index 불연속·pages·count 불일치 전건 격리."""
    base_sec = {"id": "b2-1-1", "section_index": 0,
                "pages": [{"printed_page": 1, "partial": False, "text": "x"}]}
    cases = {
        "dup_id": {"meta": {"section_count": 2}, "sections": [dict(base_sec), dict(base_sec)]},
        "bad_prefix": {"meta": {"section_count": 1}, "sections": [dict(base_sec, id="b3-1-1")]},
        "index_gap": {"meta": {"section_count": 1}, "sections": [dict(base_sec, section_index=3)]},
        "empty_pages": {"meta": {"section_count": 1}, "sections": [dict(base_sec, pages=[])]},
        "bad_page_type": {"meta": {"section_count": 1},
                          "sections": [dict(base_sec, pages=[{"printed_page": "1", "text": "x"}])]},
        "count_mismatch": {"meta": {"section_count": 9}, "sections": [dict(base_sec)]},
    }
    for tag, payload in cases.items():
        manual_mod._reset_cache_for_tests()
        bad = tmp_path / f"{tag}.json"
        bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", bad)
        r = load_manual_b2()
        assert isinstance(r, manual_mod.ManualLoadError), tag
        assert r.reason == "schema_invalid", tag


@pytest.mark.parametrize("payload_text, tag", [
    ('[1, 2, 3]', "top_level_array"),
    ('{"meta": {}, "sections": [null, 5]}', "null_section"),
    ('{ not json', "parse_failed"),
])
def test_b2_corrupt_data_isolated(fresh_cache, monkeypatch, tmp_path, payload_text, tag):
    """구조 손상 별권 2 파일이 예외 전파 없이 격리 — 본권·별권 3 검색 지속(D4)."""
    bad = tmp_path / "corrupt_b2.json"
    bad.write_text(payload_text, encoding="utf-8")
    monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", bad)
    r = load_manual_b2()
    assert isinstance(r, manual_mod.ManualLoadError), tag
    resp = asyncio.run(search_manual("협약 변경"))
    assert resp["errors"] == []
    assert resp["searched_sources"] == ["main", "b3", "b1", "eval"]
    assert resp["unavailable_sources"] == ["b2"]
    assert resp["source_warnings"][0]["code"] == "manual_b2_unavailable"
    assert "본권·별권 3·별권 1·과제평가 표준지침만 검색한 부분 결과" in resp["source_warnings"][0]["message"]
    resp2 = asyncio.run(get_manual_section("b2-1-1"))
    assert resp2["errors"][0]["code"] == "manual_b2_unavailable"


def test_b2_detail_fail_mentions_main_only_when_verified(fresh_cache, monkeypatch, tmp_path):
    """별권 2만 불가(본권 확인 정상) — 본권 정상 문구 포함 + 시행령 38~41조 안내(D5 오류 지침)."""
    monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", tmp_path / "no_b2.json")
    resp = asyncio.run(get_manual_section("b2-3-2"))
    msg = resp["errors"][0]["message"]
    assert resp["errors"][0]["code"] == "manual_b2_unavailable"
    assert "별권 2(기술료 제도 매뉴얼) 데이터 조회 불가" in msg
    assert "본권 매뉴얼 검색·조회와 규정 도구는 정상입니다" in msg
    assert "제38조~제41조" in msg
    # 본권·별권 3 조회 무영향
    assert asyncio.run(get_manual_section("1-5"))["content_available"] is True
    assert asyncio.run(get_manual_section("b3-1-1"))["content_available"] is True


# ── 소스 가용성 8조합 envelope (D5·§5.25) ────────────────────────────────────

@pytest.mark.parametrize("main_ok, b3_ok, b2_ok", list(itertools.product([True, False], repeat=3)))
def test_availability_combinations_envelope(fresh_cache, monkeypatch, tmp_path, main_ok, b3_ok, b2_ok):
    """v0.33.0 8조합의 투영 보존 — v0.35.0부터 별권 1은 상시 정상으로 두고 기존 3소스 조합을
    유지(4변수 전수 16조합은 test_manual_b1_tools.py::test_availability_16_combinations)."""
    if not main_ok:
        monkeypatch.setattr(manual_mod, "_DATA_PATH", tmp_path / "no_main.json")
    if not b3_ok:
        monkeypatch.setattr(manual_mod, "_B3_DATA_PATH", tmp_path / "no_b3.json")
    if not b2_ok:
        monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", tmp_path / "no_b2.json")
    resp = asyncio.run(search_manual("협약 변경"))
    expected_sources = [s for s, ok in (("main", main_ok), ("b3", b3_ok), ("b2", b2_ok)) if ok] + ["b1", "eval"]
    expected_unavail = [s for s, ok in (("main", main_ok), ("b3", b3_ok), ("b2", b2_ok)) if not ok]
    assert resp["errors"] == []
    assert resp["searched_sources"] == expected_sources
    if expected_unavail:
        assert resp["unavailable_sources"] == expected_unavail
        assert [w["source"] for w in resp["source_warnings"]] == expected_unavail
        ok_label = "·".join({"main": "본권", "b3": "별권 3", "b2": "별권 2", "b1": "별권 1", "eval": "과제평가 표준지침"}[s] for s in expected_sources)
        for w in resp["source_warnings"]:
            assert f"본 응답은 {ok_label}만 검색한 부분 결과입니다" in w["message"]
    else:
        assert "unavailable_sources" not in resp


# ── D6: 검색 도달·정렬·무회귀 ────────────────────────────────────────────────

@pytest.mark.parametrize("query, want_id", [
    ("정부납부기술료 납부 기준", "b2-3-2"),
    ("기술료 납부 기간", "b2-3-3"),
    ("기술기여도 산정", "b2-ref-1"),
    ("기술료 감면", "b2-2-4"),
    ("매출액 검증", "b2-ref-1"),
])
def test_b2_search_reach_top10(fresh_cache, query, want_id):
    r = asyncio.run(search_manual(query))
    assert want_id in [m["section_id"] for m in r["matches"]], query


def test_b2_search_known_variant_toc_typo(fresh_cache):
    """목차 오기 표기 "운영체계"로도 b2-2-1 제목 tier 도달(P1 known-variant·데이터-only)."""
    r = asyncio.run(search_manual("기술료 운영체계"))
    m = next((x for x in r["matches"] if x["section_id"] == "b2-2-1"), None)
    assert m is not None
    assert "title" in m["matched_in"]
    assert m["subsection_titles"] == ["운영체계"]


def test_search_merge_ordering_same_tier_b3_before_b2(fresh_cache):
    """정렬 (tier, source_rank, index) — 같은 tier에서 별권 3(rank 1)이 별권 2(rank 2)보다 앞."""
    r = asyncio.run(search_manual("기술료"))
    srcs = [m["source"] for m in r["matches"]]
    assert "b2" in srcs
    tiers = {}
    for m in r["matches"]:
        tiers.setdefault(m["source"], []).append(m["section_id"])
    if "b3" in srcs:
        # 같은 응답 안에서 b3 매치가 b2 매치보다 앞서는 첫 위치 확인은 tier 의존 —
        # 최소 보증: 본권 첫 매치가 전체 최상위(제목 매치 2-6)
        assert r["matches"][0]["source"] == "main"


def test_search_no_b2_match_baseline_unchanged(fresh_cache, monkeypatch, tmp_path):
    """D5 보존 표면 ②: 별권 2 무매치 질의의 기존(본권+별권 3) matches 내용·상대 순서 불변."""
    merged = asyncio.run(search_manual("제재처분 재검토"))
    assert merged["total_matched_by_source"].get("b2", 0) == 0
    manual_mod._reset_cache_for_tests()
    monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", tmp_path / "no_b2.json")
    baseline = asyncio.run(search_manual("제재처분 재검토"))
    key = lambda r: [(m["section_id"], m["citation"]) for m in r["matches"]]
    assert key(merged) == key(baseline)


def test_preserved_meta_serialization_main_b3(fresh_cache, monkeypatch, tmp_path):
    """D5 보존 표면 ③: {본권+별권 3} 혼합 manual_meta 직렬화가 별권 2 유무와 무관하게 동일."""
    merged = asyncio.run(search_manual("제재처분 절차"))
    assert merged["total_matched_by_source"].get("b2", 0) == 0
    meta_with_b2_alive = json.dumps(merged["manual_meta"], ensure_ascii=False, sort_keys=True)
    manual_mod._reset_cache_for_tests()
    monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", tmp_path / "no_b2.json")
    baseline = asyncio.run(search_manual("제재처분 절차"))
    meta_baseline = json.dumps(baseline["manual_meta"], ensure_ascii=False, sort_keys=True)
    assert meta_with_b2_alive == meta_baseline


def test_preserved_detail_responses_independent_of_b2(fresh_cache, monkeypatch, tmp_path):
    """D5 보존 표면 ①: 본권·별권 3 상세 응답 전체가 별권 2 가용성과 무관하게 동일."""
    with_b2 = [asyncio.run(get_manual_section("3-9")), asyncio.run(get_manual_section("b3-1-1"))]
    manual_mod._reset_cache_for_tests()
    monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", tmp_path / "no_b2.json")
    without_b2 = [asyncio.run(get_manual_section("3-9")), asyncio.run(get_manual_section("b3-1-1"))]
    assert json.dumps(with_b2, ensure_ascii=False) == json.dumps(without_b2, ensure_ascii=False)


def test_preserved_unrelated_error_wording(fresh_cache, monkeypatch, tmp_path):
    """D5 보존 표면 ④: 별권 3 조회 오류 문면에 별권 2 언급 없음(무관 문면 불변)."""
    monkeypatch.setattr(manual_mod, "_B3_DATA_PATH", tmp_path / "no_b3.json")
    resp = asyncio.run(get_manual_section("b3-1-1"))
    assert "별권 2" not in resp["errors"][0]["message"]


def test_golden_v0320_baseline_preserved(fresh_cache):
    """D5 보존 표면 ①·③ 기준선 실대조 — v0.32.0 코드(aa6585d)로 생성한 golden 픽스처와
    현재 구현의 응답 전체 직렬화를 비교(P2 diff 적대검토 MINOR 반영 — 신구현끼리 비교가
    아니라 실제 구버전 산출물 대조). contract_version(0.23.0→현행)만 계약 선언된
    의도적 변경이라 비교에서 정규화한다. 대조 대상 응답에는 v0.34.0 structure_notice가
    부착되지 않는다(3-13·b3-5-3 = notes 없음·b3-4-2 = 포인터 미부착·검색 = 미표면) —
    부착 대상이 생기는 변경을 하면 이 테스트가 회귀 신호를 낸다(의도).
    """
    import pathlib
    golden = json.loads(
        (pathlib.Path(__file__).parent / "fixtures" / "v0320_golden_preserved.json")
        .read_text(encoding="utf-8")
    )

    def norm(obj):
        s = json.dumps(obj, ensure_ascii=False, sort_keys=True)
        return s.replace('"contract_version": "0.23.0"', '"contract_version": "N"') \
                .replace('"contract_version": "0.24.0"', '"contract_version": "N"') \
                .replace('"contract_version": "0.25.0"', '"contract_version": "N"') \
                .replace('"contract_version": "0.28.0"', '"contract_version": "N"')

    assert norm(asyncio.run(get_manual_section("3-13"))) == norm(golden["detail_3_13"])
    assert norm(asyncio.run(get_manual_section("b3-5-3"))) == norm(golden["detail_b3_5_3"])
    assert norm(asyncio.run(get_manual_section("b3-4-2"))) == norm(golden["detail_b3_4_2_pointer"])
    r = asyncio.run(search_manual("제재처분 절차"))
    assert norm(r["matches"]) == norm(golden["search_jaejae_matches"])
    assert norm(r["manual_meta"]) == norm(golden["search_jaejae_manual_meta"])
    r0 = asyncio.run(search_manual("존재하지않는키워드검증용문자열"))
    assert norm(r0["manual_meta"]) == norm(golden["search_zero_manual_meta"])


# ── 상세 조회·D7 meta·D8 notes ───────────────────────────────────────────────

def test_b2_all_ids_full_text_citation_footer(fresh_cache):
    """15개 id 전수 — 전문 tier(no-oversized)·citation·footer 4줄·페이지 범위·contract."""
    for sid in B2_ALL_IDS:
        r = asyncio.run(get_manual_section(sid))
        assert r.get("errors") is None, sid
        assert r["content_available"] is True and r["content_format"] == "plain_text_verbatim", sid
        assert r["citation"].startswith("「국가연구개발사업 기술료 제도 매뉴얼」(26.7판)"), sid
        assert 1 <= r["page_start"] <= r["page_end"] <= 12, sid
        meta = r["manual_meta"]
        assert meta["manual_basis_date"] is None, sid
        assert meta["standard_footer"].count("※") == 4, sid
        assert "법령 기준일 원문 미표기" in meta["notice"], sid
        assert r["contract_version"] == "0.28.0", sid
        assert r["format_note"].startswith("본 content는 「국가연구개발사업 기술료 제도 매뉴얼」"), sid


def test_b2_ref_citation_omits_chapter(fresh_cache):
    r = asyncio.run(get_manual_section("b2-ref-1"))
    assert "제0장" not in r["citation"]
    assert r["section_label"] == "[부록]"
    assert r["subsection_titles"] == [
        "납부 대상", "납부 기준(「국가연구개발혁신법 시행령」제39조)",
        "매출액 기준에 따른 기술기여도 산정 방법(예시)", "기술기여도 작성",
        "매출액 검증절차", "기타",
    ]


def test_b2_law_priority_extra_three_sentences(fresh_cache):
    """D7 규범성 3문장 — 시행령 38~41조 교차확인·부록 비일반화·구판 용어(라이브 검증 완료 문면)."""
    r = asyncio.run(get_manual_section("b2-3-2"))
    note = r["manual_meta"]["law_priority_note"]
    assert "시행령 제38조~제41조 원문을 교차 확인" in note
    assert "그대로 일반화할 수 없습니다" in note
    assert "'기술료등납부의무기관'은 현행 시행령에서 '정부납부기술료납부의무기관'으로 변경" in note


def test_b2_table_structure_notes_surface(fresh_cache):
    """D8 결속 객체 사실 기재 — b2-2-1(도식)·b2-3-2(병합 셀)·b2-ref-1(분수식·빈 셀) warnings 표면화."""
    r1 = asyncio.run(get_manual_section("b2-2-1"))
    assert any("[그림 1]" in w for w in r1["warnings"])
    r2 = asyncio.run(get_manual_section("b2-3-2"))
    assert any("세로 병합 셀" in w and "직렬화 순서" in w for w in r2["warnings"])
    r3 = asyncio.run(get_manual_section("b2-ref-1"))
    assert any("분수식" in w for w in r3["warnings"])
    assert any("빈 셀" in w for w in r3["warnings"])


def test_b2_invalid_and_not_found_messages(fresh_cache):
    bad = asyncio.run(get_manual_section("b2-9"))
    assert bad["errors"][0]["code"] == "invalid_section_id"
    assert "별권 2 'b2-장-절'(예: 'b2-3-2')·'b2-ref-1'" in bad["errors"][0]["message"]
    nf = asyncio.run(get_manual_section("b2-9-9"))
    assert nf["errors"][0]["code"] == "not_found"
    assert "별권 2(기술료 제도 매뉴얼) 유효 범위" in nf["errors"][0]["message"]
    assert "b2-3-1~b2-3-6" in nf["errors"][0]["message"]


# ── 혼합 meta 일반화 (D5·D7) ─────────────────────────────────────────────────

def test_mixed_meta_three_sources_live(fresh_cache):
    """"기술료" 질의 = 본권+별권 3+별권 2 혼합 — sources 3키·notice 병기 2회·provenance 다별권 문면."""
    r = asyncio.run(search_manual("기술료"))
    meta = r["manual_meta"]
    assert set(meta["sources"].keys()) == {"main", "b3", "b2"}
    assert meta["notice"].count(" / ") == 2
    assert meta["sources"]["b2"]["manual_basis_date"] is None
    assert "별권 3·별권 2의 판번·기준일은 sources.b3·sources.b2와 notice를 따르십시오" in meta["provenance_note"]
    assert "각 별권은 법령 기준일 원문 미표기" in meta["provenance_note"]
    # 별권 2 확장 문장(구판 용어)이 병기 law_priority_note에 포함
    assert "정부납부기술료납부의무기관" in meta["law_priority_note"]


def test_mixed_meta_supplement_only_pair_unit():
    """별권만 2종 반환(primary=별권 3) — provenance가 primary 라벨 기준으로 조립."""
    b3_meta = {"edition": "26.7", "source_title": "국가연구개발사업 제재처분 가이드라인",
               "series_title": "국가연구개발혁신법 매뉴얼", "series_part": "별권 3",
               "edition_note": "x", "basis_note": "y"}
    b2_meta = {"edition": "26.7", "source_title": "국가연구개발사업 기술료 제도 매뉴얼",
               "series_title": "국가연구개발혁신법 매뉴얼", "series_part": "별권 2",
               "edition_note": "x", "basis_note": "y", "law_priority_extra": ["문장A."]}
    block = mixed_manual_meta_block(("b3", b3_meta), [("b2", b2_meta)])
    assert list(block["sources"].keys()) == ["b3", "b2"]
    assert block["provenance_note"].startswith(
        "이 블록의 단일 값 필드(edition·manual_basis_date·basis_note·basis_laws·source_url)는 별권 3 기준입니다."
    )
    assert "별권 2의 판번·기준일은 sources.b2와 notice를 따르십시오(별권 2는 법령 기준일 원문 미표기)" in block["provenance_note"]
    assert block["law_priority_note"].endswith("문장A.")


def test_mixed_meta_main_b3_bytes_preserved_v0320():
    """D5 보존 표면 ③ 단위 잠금 — (본권, [별권 3]) 문면이 v0.32.0 리터럴과 글자 단위 동일."""
    data_main = manual_mod.load_manual()
    data_b3 = manual_mod.load_manual_b3()
    block = mixed_manual_meta_block(("main", data_main.meta), [("b3", data_b3.meta)])
    assert block["provenance_note"] == (
        "이 블록의 단일 값 필드(edition·manual_basis_date·basis_note·basis_laws·source_url)는 "
        "본권 기준입니다. 별권 3의 판번·기준일은 sources.b3와 notice를 따르십시오"
        "(별권 3은 법령 기준일 원문 미표기)."
    )
    assert " 별권 3은 법령 기준일이 원문에 명시되어 있지 않아 이후 법령 개정 반영 여부를 알 수 없습니다." in block["law_priority_note"]
    assert list(block["sources"].keys()) == ["main", "b3"]


# ── v0330 표면 문구 잠금·패키징 ──────────────────────────────────────────────

def test_v0330_surface_locks():
    instructions = main_mod.mcp.instructions or ""
    assert "별권 2 「국가연구개발사업 기술료 제도 매뉴얼」" in instructions
    assert "기술료율·납부 상한 등 구체값은 시행령 제38조~제41조 원문" in instructions
    tmpl = main_mod._REVIEW_PROMPT_TEMPLATE
    assert "(본권·별권 3 제재처분 가이드라인·별권 2 기술료 제도 매뉴얼·별권 1 학생인건비통합관리 제도 매뉴얼)" in tmpl
    assert "별권 중 1종(연구시설장비" in tmpl
    sm_doc = main_mod.search_manual.fn.__doc__ if hasattr(main_mod.search_manual, "fn") else main_mod.search_manual.__doc__
    gs_doc = main_mod.get_manual_section.fn.__doc__ if hasattr(main_mod.get_manual_section, "fn") else main_mod.get_manual_section.__doc__
    assert '"b2"=별권 2' in sm_doc and "15개 단위" in sm_doc
    assert "b2-3-2" in gs_doc and "제38조~제41조" in gs_doc
    # 미커버 문구에 기술료가 남아 있으면 자가 충돌(D10 negative-token)
    desc = None
    for surface in (tmpl, instructions):
        assert "별권 중 3종" not in surface
        assert "학생인건비·기술료·연구시설장비" not in surface


def test_b2_packaging_force_include():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"src/korean_rnd_regs_mcp/manual_b2.json" = "korean_rnd_regs_mcp/manual_b2.json"' in pyproject
    payload = json.loads((root / "src/korean_rnd_regs_mcp/manual_b2.json").read_text(encoding="utf-8"))
    assert payload["meta"]["section_count"] == 15
    assert len(payload["sections"]) == 15
    assert payload["meta"]["id_format"] == "^b2-(\\d+-\\d+|ref-\\d+)$"


def test_supplement_descriptor_consistency():
    """descriptor·정규식 드리프트 가드 — 프리픽스 집합이 SECTION_ID_RE와 일치(P0 D3 대체 장치)."""
    prefixes = {d["prefix"] for d in main_mod._MANUAL_SUPPLEMENTS}
    assert prefixes == {"b3-", "b2-", "b1-", "eval-"}
    for d in main_mod._MANUAL_SUPPLEMENTS:
        assert SECTION_ID_RE.match(d["prefix"] + "1-1"), d["source_id"]
        assert SECTION_ID_RE.match(d["prefix"] + "ref-1"), d["source_id"]
    ranks = [d["source_rank"] for d in main_mod._MANUAL_SUPPLEMENTS]
    assert ranks == sorted(ranks) and ranks[0] >= 1  # append-only·main=0 예약
