"""v0.35.0 R4-P2 — 별권 1 「학생인건비통합관리 제도 매뉴얼」 통합 잠금 테스트.

canonical 설계 = R4-P0 설계 동결 문서 D1~D14(2026-08-05·vault). 네트워크 호출 없음.
잠금 대상: id 정규식·라우팅(D9), 강화 로더 검증·장애 격리(D9), 소스 가용성 16조합
전수(D10), 검색 도달·희석 무회귀(D11), b1-ref-3 청크·structure_notice(D12), meta·규범성
2문장·1회 출현(D5·D6), table_structure_notes 표면화(D4), v0.34.0 golden 실대조(보존 표면),
표면 문구(v0350), 패키징.
"""

import asyncio
import itertools
import json
import pathlib

import pytest

import korean_rnd_regs_mcp.main as main_mod
import korean_rnd_regs_mcp.manual as manual_mod
from korean_rnd_regs_mcp.main import get_manual_section, search_manual
from korean_rnd_regs_mcp.manual import (
    SECTION_ID_RE,
    STRUCTURE_NOTICE_CHUNK_LINE,
    load_manual_b1,
)


@pytest.fixture()
def fresh_cache():
    manual_mod._reset_cache_for_tests()
    yield
    manual_mod._reset_cache_for_tests()


B1_ALL_IDS = [
    "b1-1-1", "b1-1-2", "b1-1-3",
    "b1-2-1", "b1-2-2", "b1-2-3", "b1-2-4", "b1-2-5", "b1-2-6", "b1-2-7",
    "b1-3-1", "b1-3-2", "b1-3-3", "b1-3-4", "b1-3-5", "b1-3-6", "b1-3-7", "b1-3-8",
    "b1-4-1", "b1-4-2", "b1-4-3", "b1-4-4",
    "b1-5-1",
    "b1-ref-1", "b1-ref-2", "b1-ref-3",
]


# ── D9: id 정규식·descriptor ─────────────────────────────────────────────────

def test_section_id_re_accepts_b1_forms():
    for ok in ("b1-1-1", "b1-5-1", "b1-ref-1", "b1-ref-3", "b2-3-2", "b3-4-2", "3-4", "ref-3"):
        assert SECTION_ID_RE.match(ok), ok
    for bad in ("b1-", "b1-1", "b11-1", "b1-ref", "b1-1-1-1", "b4-1-1", "B1-1-1", " b1-1-1"):
        assert not SECTION_ID_RE.match(bad), bad


def test_supplement_descriptor_b1_appended():
    """descriptor append-only(D9) — b1이 마지막·rank 3·오류코드·프리픽스 정합."""
    descs = main_mod._MANUAL_SUPPLEMENTS
    assert [d["source_id"] for d in descs] == ["b3", "b2", "b1"]
    assert [d["source_rank"] for d in descs] == [1, 2, 3]
    b1 = descs[-1]
    assert b1["prefix"] == "b1-"
    assert b1["error_code"] == "manual_b1_unavailable"
    assert "학생인건비통합관리 제도 매뉴얼" in b1["label"]
    assert "제86조~제99조" in b1["unavailable_guidance"]
    assert "b1-5-1" in b1["valid_range"] and "b1-ref-1~b1-ref-3" in b1["valid_range"]


# ── D9: 데이터·강화 로더 ─────────────────────────────────────────────────────

def test_b1_data_loads_26_units(fresh_cache):
    data = load_manual_b1()
    assert not isinstance(data, manual_mod.ManualLoadError)
    assert [s["id"] for s in data.sections] == B1_ALL_IDS
    assert data.meta["series_part"] == "별권 1"
    assert data.meta["source_title"] == "학생인건비통합관리 제도 매뉴얼"
    assert data.meta["edition"] == "26.7"
    assert data.meta["manual_basis_date"] is None
    assert "제2026-5호" in data.meta["basis_note"]  # 원문 표기 사실 기재(D6)
    assert len(data.meta["law_priority_extra"]) == 2
    # FAQ 단일 유닛(D1) — Q1~Q9 subsection_titles 등재
    faq = data.by_id["b1-5-1"]
    assert faq["section_title"] == "FAQ" and faq["chapter_no"] == 5
    assert len(faq["subsection_titles"]) == 9
    assert faq["subsection_titles"][0].startswith("Q1.")
    # 참고1 known-variant(목차 표기) 등재
    ref1 = data.by_id["b1-ref-1"]
    assert ref1["subsection_titles"] == ["학생인건비통합관리기관 지정 현황"]


def test_b1_loader_strict_validation_extras(fresh_cache, monkeypatch, tmp_path):
    base_sec = {"id": "b1-1-1", "section_index": 0,
                "pages": [{"printed_page": 1, "partial": False, "text": "x"}]}
    cases = {
        "dup_id": {"meta": {"section_count": 2}, "sections": [dict(base_sec), dict(base_sec)]},
        "bad_prefix": {"meta": {"section_count": 1}, "sections": [dict(base_sec, id="b2-1-1")]},
        "index_gap": {"meta": {"section_count": 1}, "sections": [dict(base_sec, section_index=3)]},
        "empty_pages": {"meta": {"section_count": 1}, "sections": [dict(base_sec, pages=[])]},
        "bad_page_type": {"meta": {"section_count": 1},
                          "sections": [dict(base_sec, pages=[{"printed_page": "1", "text": "x"}])]},
        "count_mismatch": {"meta": {"section_count": 9}, "sections": [dict(base_sec)]},
        # diff 적대검토 Codex 반영 — prefix는 맞으나 라우팅 정규식 불일치 id·bool 쪽 번호 거부
        "unroutable_id": {"meta": {"section_count": 1}, "sections": [dict(base_sec, id="b1-not-routable")]},
        "bool_page": {"meta": {"section_count": 1},
                      "sections": [dict(base_sec, pages=[{"printed_page": True, "partial": False, "text": "x"}])]},
    }
    for tag, payload in cases.items():
        manual_mod._reset_cache_for_tests()
        bad = tmp_path / f"{tag}.json"
        bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(manual_mod, "_B1_DATA_PATH", bad)
        r = load_manual_b1()
        assert isinstance(r, manual_mod.ManualLoadError), tag
        assert r.reason == "schema_invalid", tag


@pytest.mark.parametrize("payload_text, tag", [
    ('[1, 2, 3]', "top_level_array"),
    ('{"meta": {}, "sections": [null, 5]}', "null_section"),
    ('{ not json', "parse_failed"),
])
def test_b1_corrupt_data_isolated(fresh_cache, monkeypatch, tmp_path, payload_text, tag):
    """구조 손상 별권 1 파일이 예외 전파 없이 격리 — 본권·별권 3·별권 2 검색 지속(D9)."""
    bad = tmp_path / "corrupt_b1.json"
    bad.write_text(payload_text, encoding="utf-8")
    monkeypatch.setattr(manual_mod, "_B1_DATA_PATH", bad)
    r = load_manual_b1()
    assert isinstance(r, manual_mod.ManualLoadError), tag
    resp = asyncio.run(search_manual("협약 변경"))
    assert resp["errors"] == []
    assert resp["searched_sources"] == ["main", "b3", "b2"]
    assert resp["unavailable_sources"] == ["b1"]
    assert resp["source_warnings"][0]["code"] == "manual_b1_unavailable"
    assert "본권·별권 3·별권 2만 검색한 부분 결과" in resp["source_warnings"][0]["message"]
    resp2 = asyncio.run(get_manual_section("b1-1-1"))
    assert resp2["errors"][0]["code"] == "manual_b1_unavailable"


def test_b1_detail_fail_mentions_main_only_when_verified(fresh_cache, monkeypatch, tmp_path):
    """별권 1만 불가(본권 확인 정상) — 본권 정상 문구 + 제86조~제99조 규정 트랙 안내(D9)."""
    monkeypatch.setattr(manual_mod, "_B1_DATA_PATH", tmp_path / "no_b1.json")
    resp = asyncio.run(get_manual_section("b1-3-4"))
    msg = resp["errors"][0]["message"]
    assert resp["errors"][0]["code"] == "manual_b1_unavailable"
    assert "별권 1(학생인건비통합관리 제도 매뉴얼) 데이터 조회 불가" in msg
    assert "본권 매뉴얼 검색·조회와 규정 도구는 정상입니다" in msg
    assert "제86조~제99조" in msg
    # 본권·별권 3·별권 2 조회 무영향
    assert asyncio.run(get_manual_section("1-5"))["content_available"] is True
    assert asyncio.run(get_manual_section("b3-1-1"))["content_available"] is True
    assert asyncio.run(get_manual_section("b2-1-1"))["content_available"] is True


# ── D10: 소스 가용성 16조합 전수 ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "main_ok, b3_ok, b2_ok, b1_ok", list(itertools.product([True, False], repeat=4))
)
def test_availability_16_combinations(fresh_cache, monkeypatch, tmp_path, main_ok, b3_ok, b2_ok, b1_ok):
    """4소스 boolean 전수(D10) — 대표 조합이 놓치는 '전부 실패 vs 일부 실패' 조립 분기·
    오류 순서·부분 결과 문면을 전 조합에서 잠금."""
    if not main_ok:
        monkeypatch.setattr(manual_mod, "_DATA_PATH", tmp_path / "no_main.json")
    if not b3_ok:
        monkeypatch.setattr(manual_mod, "_B3_DATA_PATH", tmp_path / "no_b3.json")
    if not b2_ok:
        monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", tmp_path / "no_b2.json")
    if not b1_ok:
        monkeypatch.setattr(manual_mod, "_B1_DATA_PATH", tmp_path / "no_b1.json")
    resp = asyncio.run(search_manual("협약 변경"))
    flags = (("main", main_ok), ("b3", b3_ok), ("b2", b2_ok), ("b1", b1_ok))
    expected_sources = [s for s, ok in flags if ok]
    expected_unavail = [s for s, ok in flags if not ok]
    if not expected_sources:
        codes = [e["code"] for e in resp["errors"]]
        assert codes == [
            "manual_unavailable", "manual_b3_unavailable",
            "manual_b2_unavailable", "manual_b1_unavailable",
        ]
        # 종합 안내는 계약 규약상 "마지막 오류"에 부착(§5.24) — 별권 1 추가로 부착처가
        # b2에서 b1으로 이동(v0.33.0에서 b3→b2 이동과 동일 전례·§5.27 명시). 기존 3소스
        # 오류는 자기 소스 상태만 말하는 순수 문면으로 잠금(diff 적대검토 Codex 반영).
        for e in resp["errors"][:-1]:
            assert "모두" not in e["message"], e["code"]
            assert "(reason:" in e["message"], e["code"]
        assert "본권·별권 3·별권 2·별권 1 매뉴얼 데이터가 모두 로드 불가" in resp["errors"][-1]["message"]
        assert "규정 도구(search_provision·get_provision_detail 등)는 정상" in resp["errors"][-1]["message"]
        assert resp["manual_meta_available"] is False
        return
    assert resp["errors"] == []
    assert resp["searched_sources"] == expected_sources
    if expected_unavail:
        assert resp["unavailable_sources"] == expected_unavail
        assert [w["source"] for w in resp["source_warnings"]] == expected_unavail
        labels = {"main": "본권", "b3": "별권 3", "b2": "별권 2", "b1": "별권 1"}
        ok_label = "·".join(labels[s] for s in expected_sources)
        for w in resp["source_warnings"]:
            assert f"본 응답은 {ok_label}만 검색한 부분 결과입니다" in w["message"]
    else:
        assert "unavailable_sources" not in resp


# ── D11: 검색 도달·정렬·희석 무회귀 ──────────────────────────────────────────

@pytest.mark.parametrize("query, want_id", [
    ("학생인건비 계상기준 설정", "b1-2-3"),
    ("학생인건비 이자 처리", "b1-3-6"),
    ("계정별 학생인건비 잔액 처리", "b1-3-5"),
    ("학생인건비 이관", "b1-3-7"),
    ("통합관리기관 지정 및 관리유형 변경", "b1-4-1"),
    ("학생인건비통합관리기관 지정 현황", "b1-ref-1"),
    ("연구개발기관계정 표준 운영 가이드라인", "b1-ref-2"),
    ("학생인건비통합관리 점검 자료집", "b1-ref-3"),
])
def test_b1_search_reach_top10(fresh_cache, query, want_id):
    r = asyncio.run(search_manual(query))
    assert want_id in [m["section_id"] for m in r["matches"]], query


def test_b1_faq_reach_via_subsection_title(fresh_cache):
    """FAQ 단일 유닛(D1) — Q줄 subsection_titles로 제목 tier 도달."""
    r = asyncio.run(search_manual("학생인건비계상률"))
    m = next((x for x in r["matches"] if x["section_id"] == "b1-5-1"), None)
    assert m is not None
    assert "title" in m["matched_in"]


def test_b1_search_main_title_tier_precedes(fresh_cache):
    """"학생인건비" — 본권 3-4(제3장 제4절 학생인건비)가 제목 tier·rank 0으로 최상위 유지."""
    r = asyncio.run(search_manual("학생인건비"))
    assert r["matches"][0]["source"] == "main"
    assert r["matches"][0]["section_id"] == "3-4"
    # 같은 tier 안에서 rank 순(main=0 < b1=3) — b1 매치는 본권 제목 매치보다 뒤
    srcs = [m["source"] for m in r["matches"]]
    assert "b1" in srcs


def test_search_no_b1_match_baseline_unchanged(fresh_cache, monkeypatch, tmp_path):
    """희석 무회귀(D11-①): 별권 1 무매치 질의의 기존(본권+별권 3+별권 2) matches
    내용·상대 순서가 별권 1 유무와 무관하게 불변."""
    for query in ("제재처분 재검토", "정부납부기술료 납부 기준", "제재부가금 납부", "기술기여도 산정"):
        manual_mod._reset_cache_for_tests()
        merged = asyncio.run(search_manual(query))
        assert merged["total_matched_by_source"].get("b1", 0) == 0, query
        manual_mod._reset_cache_for_tests()
        monkeypatch.setattr(manual_mod, "_B1_DATA_PATH", tmp_path / "no_b1.json")
        baseline = asyncio.run(search_manual(query))
        monkeypatch.undo()
        # match 객체 전체 직렬화 비교(발췌·계측 포함 — (id, citation) 축약 비교는 내용 드리프트를
        # 놓침·diff 적대검토 Codex 반영)
        key = lambda r: json.dumps(r["matches"], ensure_ascii=False, sort_keys=True)
        assert key(merged) == key(baseline), query
        assert merged["returned"] >= 1, query  # 공허 통과 방지


def test_search_b1_match_existing_prefix_preserved(fresh_cache, monkeypatch, tmp_path):
    """희석 실측 게이트(D11-③ 유매치 질의 형): 별권 1 매치 질의에서 기존 소스 매치의
    상대 순서가 보존되고(필터 결과 = baseline 접두), 최상위 필수 절(baseline 1·2위)은
    cap 10 안에 그대로 유지. cap에 따른 하위 매치 밀림은 병합 검색의 설계된 거동
    (b3·b2 수록 전례와 동일)이며, 이 실측이 quota 선제 도입 불요 판정의 근거."""
    for query in ("학생인건비", "학생인건비 지급"):
        manual_mod._reset_cache_for_tests()
        monkeypatch.setattr(manual_mod, "_B1_DATA_PATH", tmp_path / "no_b1.json")
        baseline = asyncio.run(search_manual(query))
        base_ids = [m["section_id"] for m in baseline["matches"]]
        monkeypatch.undo()
        manual_mod._reset_cache_for_tests()
        merged = asyncio.run(search_manual(query))
        filtered_ids = [m["section_id"] for m in merged["matches"] if m["source"] != "b1"]
        # 공허 통과 방지 + 기존 소스 매치는 baseline의 접두를 그대로 보존(순서 교란·중간 탈락
        # 없음 — diff 적대검토 Codex 반영: 빈 filtered·OR 약화 제거)
        assert len(filtered_ids) >= 2, query
        assert filtered_ids == base_ids[:len(filtered_ids)], query
        # 최상위 필수 절(baseline 1·2위)은 기존 소스 기준으로 그대로 생존
        assert filtered_ids[:2] == base_ids[:2], query
        # 소스별 계수 정합·cap·반복 결정론
        assert sum(merged["returned_by_source"].values()) == merged["returned"] <= 10
        again = asyncio.run(search_manual(query))
        assert json.dumps(merged, ensure_ascii=False) == json.dumps(again, ensure_ascii=False)


def test_preserved_detail_responses_independent_of_b1(fresh_cache, monkeypatch, tmp_path):
    """보존 표면(D11-②): 본권·별권 3·별권 2 상세 응답 전체가 별권 1 가용성과 무관하게 동일."""
    ids = ["3-9", "b3-1-1", "b2-3-2"]
    with_b1 = [asyncio.run(get_manual_section(sid)) for sid in ids]
    manual_mod._reset_cache_for_tests()
    monkeypatch.setattr(manual_mod, "_B1_DATA_PATH", tmp_path / "no_b1.json")
    without_b1 = [asyncio.run(get_manual_section(sid)) for sid in ids]
    assert json.dumps(with_b1, ensure_ascii=False) == json.dumps(without_b1, ensure_ascii=False)


def test_preserved_unrelated_error_wording(fresh_cache, monkeypatch, tmp_path):
    """기존 별권 오류 문면에 별권 1 언급 없음(무관 문면 불변)."""
    monkeypatch.setattr(manual_mod, "_B3_DATA_PATH", tmp_path / "no_b3.json")
    monkeypatch.setattr(manual_mod, "_B2_DATA_PATH", tmp_path / "no_b2.json")
    for sid in ("b3-1-1", "b2-1-1"):
        resp = asyncio.run(get_manual_section(sid))
        assert "별권 1" not in resp["errors"][0]["message"], sid


def test_golden_v0340_baseline_preserved(fresh_cache):
    """보존 표면 기준선 실대조 — v0.34.0 코드(0468b13)로 생성한 golden 픽스처와 현재 구현의
    응답 직렬화를 비교(신구현끼리 비교가 아니라 실제 구버전 산출물 대조 — v0320 golden 전례).
    contract_version(0.25.0→현행)만 계약 선언된 의도적 변경이라 정규화한다.
    "기술료" 검색은 별권 1 무매치 질의라 matches·manual_meta가 byte 동일해야 한다."""
    golden = json.loads(
        (pathlib.Path(__file__).parent / "fixtures" / "v0340_golden_preserved.json")
        .read_text(encoding="utf-8")
    )

    def norm(obj):
        s = json.dumps(obj, ensure_ascii=False, sort_keys=True)
        return s.replace('"contract_version": "0.25.0"', '"contract_version": "N"') \
                .replace('"contract_version": "0.26.0"', '"contract_version": "N"')

    assert norm(asyncio.run(get_manual_section("3-13"))) == norm(golden["detail_3_13"])
    assert norm(asyncio.run(get_manual_section("b3-5-3"))) == norm(golden["detail_b3_5_3"])
    assert norm(asyncio.run(get_manual_section("b2-3-2"))) == norm(golden["detail_b2_3_2"])
    assert norm(asyncio.run(get_manual_section("b2-ref-1"))) == norm(golden["detail_b2_ref_1"])
    r = asyncio.run(search_manual("기술료"))
    # b1은 body 매치 1건(b1-3-4 "기술료 보상금")이 있으나 제목 tier cap에 밀려 미반환 —
    # 반환 matches·meta는 v0.34.0과 byte 동일해야 한다.
    assert r["returned_by_source"].get("b1", 0) == 0
    assert norm(r["matches"]) == norm(golden["search_gisulryo_matches"])
    assert norm(r["manual_meta"]) == norm(golden["search_gisulryo_manual_meta"])
    r0 = asyncio.run(search_manual("존재하지않는키워드검증용문자열"))
    assert norm(r0["manual_meta"]) == norm(golden["search_zero_manual_meta"])


# ── 상세 조회·D5·D6 meta·D4 notes ────────────────────────────────────────────

def test_b1_all_ids_citation_footer(fresh_cache):
    """26개 id 전수 — 25개 전문 tier + b1-ref-3 포인터·citation·footer 4줄·contract."""
    for sid in B1_ALL_IDS:
        r = asyncio.run(get_manual_section(sid))
        assert r.get("errors") is None, sid
        assert r["citation"].startswith("「학생인건비통합관리 제도 매뉴얼」(26.7판)"), sid
        meta = r["manual_meta"]
        assert meta["manual_basis_date"] is None, sid
        assert "법령 기준일 원문 미표기" in meta["notice"], sid
        assert r["contract_version"] == "0.26.0", sid
        assert r["format_note"].startswith("본 content는 「학생인건비통합관리 제도 매뉴얼」"), sid
        if sid == "b1-ref-3":
            # 포인터 응답 = 본문 미전달 → footer 2줄 규약(허위 인용 고지 차단)
            assert r["content_available"] is False, sid
            assert r["content_format"] == "oversized_pointer", sid
            assert r["chunk_count"] == 3, sid
            assert meta["standard_footer"].count("※") == 2, sid
        else:
            assert r["content_available"] is True, sid
            assert r["content_format"] == "plain_text_verbatim", sid
            assert 3 <= r["page_start"] <= r["page_end"] <= 91, sid
            assert meta["standard_footer"].count("※") == 4, sid


def test_b1_ref_citation_omits_chapter(fresh_cache):
    r = asyncio.run(get_manual_section("b1-ref-1"))
    assert "제0장" not in r["citation"]
    assert r["section_label"] == "참고1"
    r2 = asyncio.run(get_manual_section("b1-5-1"))
    # FAQ 유닛 label은 빈 문자열(D1) — citation "제5장 FAQ FAQ" 중복 방지(결측 마디 생략)
    assert r2["section_label"] == ""
    assert "제5장 FAQ," in r2["citation"] and "FAQ FAQ" not in r2["citation"]


def test_b1_law_priority_extra_two_sentences_once(fresh_cache):
    """D5·D6 규범성 2문장 — rnd_funding_standard 교차 확인 + 제75조 이자 처리 구판 안내.
    각 문장이 law_priority_note에 정확 1회만 출현(중복·누락 잠금)."""
    r = asyncio.run(get_manual_section("b1-3-6"))
    note = r["manual_meta"]["law_priority_note"]
    assert note.count("연구개발비 사용 기준(rnd_funding_standard) 현행 원문을 교차 확인") == 1
    assert note.count("제75조제2항제1호로 이동") == 1
    assert "이자 처리 서술(제3장 6절)" in note
    # 무관 절 응답에도 소스 meta라 동반되지만(별권 2 전례) 1회만
    r2 = asyncio.run(get_manual_section("b1-4-3"))
    assert r2["manual_meta"]["law_priority_note"].count("제75조제2항제1호로 이동") == 1
    # 혼합 검색(b1 매치 포함)에서도 병기 note에 1회만
    rs = asyncio.run(search_manual("학생인건비 이자"))
    assert any(m["source"] == "b1" for m in rs["matches"])
    assert rs["manual_meta"]["law_priority_note"].count("제75조제2항제1호로 이동") == 1


def test_b1_basis_note_fact_only(fresh_cache):
    """D6 — basis_note가 제2026-5호를 원문 표기로 사실 기재(현행성 단정 금지 문면)."""
    r = asyncio.run(get_manual_section("b1-1-1"))
    meta = r["manual_meta"]
    assert "제2026-5호" in meta["basis_note"]
    assert "현행" in meta["basis_note"]  # 현행 확인 경로 안내
    assert "rnd_funding_standard" in meta["basis_note"]


def test_b1_table_structure_notes_surface(fresh_cache):
    """D4 결속 객체 사실 기재 — 4절 warnings + 본문 전달 응답의 structure_notice 부착(v0.34.0 표면)."""
    r1 = asyncio.run(get_manual_section("b1-1-3"))
    assert any("지급 개념도" in w for w in r1["warnings"])
    assert r1["structure_notice"].startswith("※ 표·산식 구조 안내(추출 한계):")
    assert "structure_notice_note" in r1
    r2 = asyncio.run(get_manual_section("b1-3-4"))
    assert any("<표 3-1>" in w for w in r2["warnings"])
    assert "지급체계" in r2["structure_notice"]
    r3 = asyncio.run(get_manual_section("b1-ref-1"))
    assert any("연구책임자단위(13개)" in w for w in r3["warnings"])
    assert "structure_notice" in r3
    # b1-ref-3 포인터 응답에는 미부착(본문 미전달 — v0.34.0 계약)
    r4 = asyncio.run(get_manual_section("b1-ref-3"))
    assert "structure_notice" not in r4
    # 구조 고지 없는 절은 미부착
    r5 = asyncio.run(get_manual_section("b1-2-3"))
    assert "structure_notice" not in r5


def test_b1_ref3_chunks_lossless_notice_budget(fresh_cache):
    """D12 — b1-ref-3 청크 3개: 무손실 재조립·각 청크 structure_notice+절 전체 기준 줄·16k 예산."""
    data = load_manual_b1()
    full = data.full_text["b1-ref-3"]
    texts = []
    for i in (1, 2, 3):
        r = asyncio.run(get_manual_section("b1-ref-3", chunk=i))
        assert r.get("errors") is None, i
        assert r["chunk_index"] == i and r["chunk_count"] == 3
        texts.append(r["content"])
        assert r["structure_notice"].startswith("※ 표·산식 구조 안내(추출 한계):"), i
        assert STRUCTURE_NOTICE_CHUNK_LINE in r["structure_notice"], i
        assert len(json.dumps(r, ensure_ascii=False)) <= 16000, i
    assert "".join(texts) == full
    bad = asyncio.run(get_manual_section("b1-ref-3", chunk=4))
    assert bad["errors"][0]["code"] == "not_found"


def test_b1_invalid_and_not_found_messages(fresh_cache):
    bad = asyncio.run(get_manual_section("b1-9"))
    assert bad["errors"][0]["code"] == "invalid_section_id"
    assert "별권 1 'b1-장-절'(예: 'b1-3-4')·'b1-ref-N'(예: 'b1-ref-1')" in bad["errors"][0]["message"]
    nf = asyncio.run(get_manual_section("b1-9-9"))
    assert nf["errors"][0]["code"] == "not_found"
    assert "별권 1(학생인건비통합관리 제도 매뉴얼) 유효 범위" in nf["errors"][0]["message"]
    assert "b1-3-1~b1-3-8" in nf["errors"][0]["message"]


def test_mixed_meta_main_b1_pair(fresh_cache):
    """본권+별권 1 혼합 meta — sources 2키·notice 병기·provenance 별권 1 안내(D5 일반화 재사용)."""
    r = asyncio.run(search_manual("학생인건비 지급"))
    meta = r["manual_meta"]
    assert set(meta["sources"].keys()) >= {"main", "b1"}
    assert meta["sources"]["b1"]["manual_basis_date"] is None
    assert "sources.b1" in meta["provenance_note"]
    assert "별권 1" in meta["provenance_note"]


# ── v0350 표면 문구 잠금·패키징 ──────────────────────────────────────────────

def test_v0350_surface_locks():
    instructions = main_mod.mcp.instructions or ""
    assert "별권 1 「학생인건비통합관리 제도 매뉴얼」" in instructions
    assert "학생인건비 계상기준·지급액 등 구체값은 연구개발비 사용 기준 원문" in instructions
    tmpl = main_mod._REVIEW_PROMPT_TEMPLATE
    assert "(본권·별권 3 제재처분 가이드라인·별권 2 기술료 제도 매뉴얼·별권 1 학생인건비통합관리 제도 매뉴얼)" in tmpl
    assert "별권 중 1종(연구시설장비" in tmpl
    sm_doc = main_mod.search_manual.fn.__doc__ if hasattr(main_mod.search_manual, "fn") else main_mod.search_manual.__doc__
    gs_doc = main_mod.get_manual_section.fn.__doc__ if hasattr(main_mod.get_manual_section, "fn") else main_mod.get_manual_section.__doc__
    assert '"b1"=별권 1' in sm_doc and "26개 단위" in sm_doc
    assert "b1-3-4" in gs_doc and "rnd_funding_standard" in gs_doc
    # 자가충돌 잔존 방지: 구 미커버 문면이 남아 있으면 안 됨
    for surface in (tmpl, instructions):
        assert "별권 중 2종" not in surface
        assert "학생인건비·연구시설장비" not in surface


def test_manual_data_source_url_identical_across_files():
    """4개 매뉴얼 데이터 파일의 source_url 동일성(같은 26.7 게시물 canonical 경로 —
    diff 적대검토 Codex BLOCKING 반영: b1이 다른 board 경로로 수록됐던 결함의 재발 방지)."""
    root = pathlib.Path(__file__).resolve().parent.parent / "src" / "korean_rnd_regs_mcp"
    urls = {
        name: json.loads((root / name).read_text(encoding="utf-8"))["meta"]["source_url"]
        for name in ("manual_body.json", "manual_b3.json", "manual_b2.json", "manual_b1.json")
    }
    assert len(set(urls.values())) == 1, urls
    assert urls["manual_b1.json"] == (
        "https://www.kistep.re.kr/board.es?mid=a10301000000&bid=0003&act=view&list_no=94788"
    )


def test_b1_packaging_force_include():
    root = pathlib.Path(__file__).resolve().parent.parent
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"src/korean_rnd_regs_mcp/manual_b1.json" = "korean_rnd_regs_mcp/manual_b1.json"' in pyproject
    payload = json.loads((root / "src/korean_rnd_regs_mcp/manual_b1.json").read_text(encoding="utf-8"))
    assert payload["meta"]["section_count"] == 26
    assert len(payload["sections"]) == 26
    assert payload["meta"]["id_format"] == "^b1-(\\d+-\\d+|ref-\\d+)$"
    # D2·D3 분할 스냅샷 — 간지·blank 미수록·본문 3~91
    assert payload["meta"]["body_pages_printed"] == [1, 91]
    assert "간지" in payload["meta"]["excluded_note"]
