"""v0.43.0 「국가 R&D 연구비 부적정집행 사례집」(KAIA·25.5) 수록 검증.

축: ① 데이터 무결성(13단위·사례 105·FAQ 18·subsection_titles 비움) ② 로더 격리(손상·부재)
③ 검색 도달·병합·citation ④ 상세 응답(meta·KAIA footer·structure_notice) ⑤ 오류 경로
⑥ 혼합 meta(footer 혼재 문면) ⑦ 검색 희석 기준선(기존 소스 상위 보존 — 계획 /disc Codex 조건).
네트워크 호출 0(전부 로컬 데이터).
"""

import asyncio
import json
import re
from pathlib import Path

import pytest

import korean_rnd_regs_mcp.main as main_mod
import korean_rnd_regs_mcp.manual as manual_mod
from korean_rnd_regs_mcp.manual import SECTION_ID_RE, load_manual_case
from korean_rnd_regs_mcp.main import get_manual_section, search_manual


@pytest.fixture
def fresh_cache():
    manual_mod._reset_cache_for_tests()
    yield
    manual_mod._reset_cache_for_tests()


# ── 데이터 무결성 ────────────────────────────────────────────────────────────

def _payload():
    p = Path(manual_mod.__file__).parent / "manual_case.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_case_data_shape_and_ids():
    d = _payload()
    ids = [s["id"] for s in d["sections"]]
    assert ids == (
        ["case-1-1"] + [f"case-2-{i}" for i in range(1, 11)] + ["case-3-1", "case-4-1"]
    )
    assert d["meta"]["section_count"] == 13
    assert d["meta"]["source_title"] == "국가 R&D 연구비 부적정집행 사례집"
    assert d["meta"]["edition"] == "25.5"
    assert "국토교통과학기술진흥원" in d["meta"]["publisher"]
    assert d["meta"]["legal_effect"] == "not_binding"
    for s in d["sections"]:
        assert SECTION_ID_RE.match(s["id"]), s["id"]
        # 사례 표제는 본문 검색으로 도달 — subsection_titles 비움(응답 팽창 방지·계획 /disc)
        assert s["subsection_titles"] == [], s["id"]


def test_case_counts_and_faq_sequence():
    """비목별 사례 번호 1~N 연속(합계 105)·FAQ Q1~Q18 연속 — 컬럼 정렬 정합의 데이터 레벨 잠금."""
    d = _payload()
    by_id = {s["id"]: s for s in d["sections"]}
    case_re = re.compile(r"^사례 (\d+)\.\s*$", re.M)
    expected = {"case-2-1": 19, "case-2-2": 6, "case-2-3": 11, "case-2-4": 5, "case-2-5": 28,
                "case-2-6": 8, "case-2-7": 5, "case-2-8": 4, "case-2-9": 13, "case-2-10": 6}
    total = 0
    for sid, cnt in expected.items():
        text = "\n".join(p["text"] for p in by_id[sid]["pages"])
        seq = [int(m) for m in case_re.findall(text)]
        assert seq == list(range(1, cnt + 1)), sid
        total += cnt
    assert total == 105
    faq_text = "\n".join(p["text"] for p in by_id["case-3-1"]["pages"])
    qseq = [int(m) for m in re.findall(r"^Q(\d+)$", faq_text, re.M)]
    assert qseq == list(range(1, 19))


def test_case_meta_guard_facts():
    """규범성 가드 데이터 실재 — KAIA 프로세스 사실 라벨·현행 교차 확인·footer 문면·도식 노트."""
    d = _payload()
    extra = d["meta"]["law_priority_extra"]
    joined = " ".join(extra)
    assert "KAIA 국토교통R&D 프로세스 기준" in joined
    assert "정산 판정·제재처분 결정도 아닙니다" in joined
    assert "rnd_funding_standard" in joined
    assert "제재처분 가이드라인" in joined       # '부적정집행'≠제재처분 구분 안내
    assert "law.go.kr" in joined                  # 미수록 법령 1차 출처 안내
    assert "국토교통과학기술진흥원 발간" in d["meta"]["footer_manual_line"]
    assert "KAIA 홈페이지(www.kaia.re.kr)" in d["meta"]["footer_source_line"]
    sec41 = next(s for s in d["sections"] if s["id"] == "case-4-1")
    assert any("도식" in n for n in sec41["table_structure_notes"])
    # 인쇄 8 불인정 기준표의 컬럼 평탄화 고지(행 대응 확인 안내 — diff 적대검토 Codex MAJOR 반영)
    sec11 = next(s for s in d["sections"] if s["id"] == "case-1-1")
    assert any("행 대응" in n for n in sec11["table_structure_notes"])


# ── 로더 ─────────────────────────────────────────────────────────────────────

def test_load_manual_case_ok(fresh_cache):
    data = load_manual_case()
    assert not isinstance(data, manual_mod.ManualLoadError)
    assert len(data.sections) == 13
    assert "case-2-5" in data.by_id


@pytest.mark.parametrize("payload_text, tag", [
    ("[1, 2, 3]", "top_level_array"),
    ('{"meta": {}, "sections": [null, 5]}', "null_section"),
    ("{ not json", "parse_failed"),
    ('{"meta": {"section_count": 99}, "sections": [{"id": "case-1-1", "section_index": 0, '
     '"pages": [{"printed_page": 6, "text": "x"}]}]}', "count_mismatch"),
    ('{"meta": {"section_count": 1}, "sections": [{"id": "b4-0", "section_index": 0, '
     '"pages": [{"printed_page": 6, "text": "x"}]}]}', "wrong_prefix"),
    ('{"meta": {"section_count": 1, "edition": "25.5"}, "sections": [{"id": "case-1-1", '
     '"section_index": 0, "pages": [{"printed_page": 6, "text": "x"}]}]}', "missing_source_title"),
])
def test_case_corrupt_data_isolated(fresh_cache, monkeypatch, tmp_path, payload_text, tag):
    """구조 손상 case 파일이 예외 전파 없이 격리 — 기존 6소스 검색 지속·case 조회만 오류."""
    bad = tmp_path / "corrupt_case.json"
    bad.write_text(payload_text, encoding="utf-8")
    monkeypatch.setattr(manual_mod, "_CASE_DATA_PATH", bad)
    r = load_manual_case()
    assert isinstance(r, manual_mod.ManualLoadError), tag
    resp = asyncio.run(search_manual("협약 변경"))
    assert resp["errors"] == []
    assert resp["searched_sources"] == ["main", "b3", "b2", "b1", "eval", "b4"]
    assert resp["unavailable_sources"] == ["case"]
    assert resp["source_warnings"][0]["code"] == "manual_case_unavailable"
    assert "본권·별권 3·별권 2·별권 1·과제평가 표준지침·별권 4만 검색한 부분 결과" \
        in resp["source_warnings"][0]["message"]
    resp2 = asyncio.run(get_manual_section("case-1-1"))
    assert resp2["errors"][0]["code"] == "manual_case_unavailable"


def test_case_detail_fail_guidance(fresh_cache, monkeypatch, tmp_path):
    """case만 불가 — 규정 트랙(연구개발비 사용 기준)·KAIA 홈페이지 안내 + 격리 사실 문면."""
    monkeypatch.setattr(manual_mod, "_CASE_DATA_PATH", tmp_path / "no_case.json")
    resp = asyncio.run(get_manual_section("case-2-1"))
    msg = resp["errors"][0]["message"]
    assert resp["errors"][0]["code"] == "manual_case_unavailable"
    assert "「국가 R&D 연구비 부적정집행 사례집」(KAIA) 데이터 조회 불가" in msg
    assert "국가연구개발사업 연구개발비 사용 기준" in msg
    assert "KAIA 홈페이지(www.kaia.re.kr)" in msg
    assert "규정 도구(search_provision·get_provision_detail 등) 경로에는 전파되지 않습니다" in msg


# ── 검색 도달·병합 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("query, want_id", [
    ("출산전후휴가 인건비 지급", "case-3-1"),
    ("부가가치세 환급 연구비", "case-2-10"),
    ("연구비카드 개인카드 사용", "case-3-1"),
    ("위탁정산기관 연차점검", "case-4-1"),
    ("연구수당 지급 한도 사례", "case-2-6"),
])
def test_case_search_reach_top10(fresh_cache, query, want_id):
    r = asyncio.run(search_manual(query))
    assert want_id in [m["section_id"] for m in r["matches"]], query


def test_case_search_merge_fields(fresh_cache):
    r = asyncio.run(search_manual("부적정집행 사례"))
    assert r["errors"] == []
    case_matches = [m for m in r["matches"] if m["source"] == "case"]
    assert case_matches
    for m in case_matches:
        assert m["section_id"].startswith("case-")
        assert m["citation"].startswith("「국가 R&D 연구비 부적정집행 사례집」(25.5판)")
        assert m["subsection_titles"] == []
    assert "case" in r["returned_by_source"]
    assert r["scanned_sections"] == 146


# ── 상세 응답 ────────────────────────────────────────────────────────────────

def test_case_detail_full_response(fresh_cache):
    r = asyncio.run(get_manual_section("case-2-2"))
    assert "errors" not in r
    assert r["content_available"] is True
    assert r["content_format"] == "plain_text_verbatim"
    assert r["section_title"] == "학생인건비"
    assert r["chapter_no"] == 0  # 원문 로마숫자 장 — citation 장 생략 경로(b4 전례)
    assert r["citation"] == (
        "「국가 R&D 연구비 부적정집행 사례집」(25.5판) Ⅱ. 부적정집행 사례 02 학생인건비, 인쇄 p.24~28"
    )
    meta = r["manual_meta"]
    assert meta["legal_effect"] == "not_binding"
    assert "「국가 R&D 연구비 부적정집행 사례집」 25.5판" in meta["notice"]
    assert "법령 기준일 원문 미표기" in meta["notice"]
    assert "KAIA 국토교통R&D 프로세스 기준" in meta["law_priority_note"]
    # footer 2번째 줄 = 데이터 footer_source_line(KAIA 확인처·v0.43.0 diff 적대검토 Codex MAJOR 반영),
    # 3번째 줄 = 데이터 footer_manual_line(per-source 경로·v0.38.0 메커니즘)
    footer_lines = meta["standard_footer"].split("\n")
    assert footer_lines[1] == (
        "※ 「국가 R&D 연구비 부적정집행 사례집」 원문은 KAIA 홈페이지(www.kaia.re.kr)에서 확인하시기 바랍니다."
    )
    assert "KISTEP" not in meta["standard_footer"]
    assert footer_lines[2].startswith("※ 사례·해설 부분은 「국가 R&D 연구비 부적정집행 사례집」")
    assert "format_note" in r
    assert "교육·참고용 사례집" in r["format_note"]


def test_case_all_sections_within_budget(fresh_cache):
    """13단위 전건 예산 내(최대 case-2-5 9,838자) — oversized 강등 0·전문 제공."""
    data = load_manual_case()
    for sid in data.by_id:
        r = asyncio.run(get_manual_section(sid))
        assert "errors" not in r, sid
        assert r["content_available"] is True, sid
        assert r["content_format"] == "plain_text_verbatim", sid


def test_case_structure_notice_on_diagram_section(fresh_cache):
    """case-4-1(절차 도식) — structure_notice 완성형 + warnings 병존(v0.34.0 규약)."""
    r = asyncio.run(get_manual_section("case-4-1"))
    assert "structure_notice" in r
    assert r["structure_notice"].startswith("※ 표·산식 구조 안내(추출 한계):")
    assert "도식" in r["structure_notice"]
    assert any("도식" in w for w in r["warnings"])
    # 인쇄 8 기준표 평탄화 고지(case-1-1)도 완성형 블록으로 발화
    r15 = asyncio.run(get_manual_section("case-1-1"))
    assert "structure_notice" in r15
    assert "행 대응" in r15["structure_notice"]
    # 비도식·비표 절에는 structure_notice 없음
    r2 = asyncio.run(get_manual_section("case-2-1"))
    assert "structure_notice" not in r2


# ── 오류 경로 ────────────────────────────────────────────────────────────────

def test_case_invalid_and_not_found(fresh_cache):
    bad = asyncio.run(get_manual_section("case-ref-1"))
    assert bad["errors"][0]["code"] == "invalid_section_id"
    assert "case-장-절" in bad["errors"][0]["message"]
    bad2 = asyncio.run(get_manual_section("case-1"))
    assert bad2["errors"][0]["code"] == "invalid_section_id"
    nf = asyncio.run(get_manual_section("case-9-9"))
    assert nf["errors"][0]["code"] == "not_found"
    assert "case-2-1~case-2-10" in nf["errors"][0]["message"]


# ── 혼합 meta·footer ─────────────────────────────────────────────────────────

def test_case_mixed_meta_footer_line(fresh_cache):
    """본권(기본 문면)+case(커스텀 문면) 혼합 — footer 3번째 줄은 혼합 일반 문면(v0.38.0 규약)."""
    r = asyncio.run(search_manual("정산 절차"))
    srcs = {m["source"] for m in r["matches"]}
    assert {"main", "case"} <= srcs
    meta = r["manual_meta"]
    assert set(meta["sources"].keys()) >= {"main", "case"}
    assert "sources.case" in meta["provenance_note"]
    assert manual_mod.FOOTER_MANUAL_LINE_MIXED in meta["standard_footer"]
    # v0.43.0: 혼합 footer는 기본 확인처(KISTEP) 줄 유지 + KAIA 확인처 줄 병기(교체 아님)
    footer_lines = meta["standard_footer"].split("\n")
    assert footer_lines[1] == manual_mod.FOOTER_MANUAL_SOURCE_LINE
    assert any("KAIA 홈페이지(www.kaia.re.kr)" in l for l in footer_lines)


def test_case_single_source_meta(fresh_cache):
    """case 단독 반환 검색 — 단독 meta 블록·KAIA footer 문면."""
    r = asyncio.run(search_manual("부적정집행 사례"))
    assert set(m["source"] for m in r["matches"]) == {"case"}
    meta = r["manual_meta"]
    footer_lines = meta["standard_footer"].split("\n")
    assert "KAIA 홈페이지(www.kaia.re.kr)" in footer_lines[1]
    assert footer_lines[2].startswith("※ 사례·해설 부분은")


# ── 검색 희석 기준선(기존 소스 보존 — 계획 /disc Codex 조건) ─────────────────

@pytest.mark.parametrize("query, top1", [
    ("학생인건비 통합관리", "b1-1-1"),
    ("기술료 납부", "b2-2-3"),
    ("제재처분 절차", "b3-3-1"),
    ("연구개발비 사용", "3-2"),
])
def test_case_dilution_baseline_existing_top(fresh_cache, query, top1):
    """기존 대표 질의의 상위 결과에서 기존 소스 서열 보존 — 사례집 추가로 인한 잠식 0.

    top1은 main 우선 정렬 특례("학생인건비 통합관리"는 main 3-19가 1위)가 있어
    '기존 소스의 최상위 매치가 여전히 상위 10 안'으로 잠근다."""
    r = asyncio.run(search_manual(query))
    ids = [m["section_id"] for m in r["matches"]]
    assert top1 in ids, query
    # 상위 3건은 case가 아님(기존 소스 상위 서열 보존)
    assert all(m["source"] != "case" for m in r["matches"][:3]), query


def test_case_dilution_procedure_query_locked(fresh_cache):
    """'정산 절차' — case-4-1이 제목 tier 정당 매치로 진입하되 본권 1위는 유지(실측 잠금)."""
    r = asyncio.run(search_manual("정산 절차"))
    ids = [m["section_id"] for m in r["matches"]]
    assert ids[0] == "3-16"          # 본권 최상위 유지
    assert "case-4-1" in ids[:3]     # 사례집 절차 절의 정당 진입


# ── 공개 표면 잠금(diff 적대검토 Codex MAJOR 반영) ────────────────────────────

def test_server_instructions_include_case_source():
    """최상위 MCP instructions(초기화 시 호스트 공개 표면)가 사례집을 열거·안내하는지 잠금."""
    ins = main_mod._SERVER_INSTRUCTIONS
    assert "「국가 R&D 연구비 부적정집행 사례집」" in ins
    assert "본권·별권 3·별권 2·별권 1·과제평가 표준지침·별권 4·부적정집행 사례집을 함께 훑으며" in ins
    assert "KAIA 국토교통R&D 프로세스 기준" in ins


def test_existing_source_footer_second_line_unchanged(fresh_cache):
    """기존 소스 단독 응답의 footer 2번째 줄은 기본 문면(KISTEP) byte 불변 — footer_source_line
    키 부재 소스 무영향 잠금(v0.43.0 메커니즘의 무회귀 축)."""
    r = asyncio.run(get_manual_section("b4-5"))
    lines = r["manual_meta"]["standard_footer"].split("\n")
    assert lines[1] == manual_mod.FOOTER_MANUAL_SOURCE_LINE
    r2 = asyncio.run(get_manual_section("3-4"))
    lines2 = r2["manual_meta"]["standard_footer"].split("\n")
    assert lines2[1] == manual_mod.FOOTER_MANUAL_SOURCE_LINE


# ── v0.46.0: 국토교통 R&D 맥락 사례집 라우팅 보강(프롬프트-only) ──────────────

def test_case_routing_guidance_present_all_surfaces_v0460():
    """v0.46.0 surface-consistency: 국토교통 맥락 라우팅 + 검색어 구성 지시 핵심 토큰이
    3표면(_SERVER_INSTRUCTIONS·search_manual docstring·review_regulation 템플릿)에 실재.
    핵심 = ① 부처명 토큰 금지(토큰 AND 매칭 0건 회피) ② 주제어 검색 ③ 범위 사실
    (사례는 국가 R&D 전반 수집 — 국토교통부 전용 아님·publisher_note 원문 정합)."""
    sm_doc = (
        main_mod.search_manual.fn.__doc__
        if hasattr(main_mod.search_manual, "fn")
        else main_mod.search_manual.__doc__
    )
    surfaces = {
        "SERVER_INSTRUCTIONS": main_mod._SERVER_INSTRUCTIONS,
        "search_manual_docstring": sm_doc,
        "review_prompt": main_mod.review_regulation_prompt("테스트 상황"),
    }
    for name, text in surfaces.items():
        assert "부처명을 넣지" in text, f"{name}: 부처명 토큰 금지 지시 누락"
        assert "주제어" in text, f"{name}: 주제어 검색 지시 누락"
        assert "국가 R&D 전반에서 수집" in text, f"{name}: 범위 사실(전반 수집) 누락"
        assert "부적정집행" in text, f"{name}: 사례집 지칭 누락"


def test_case_scope_wording_matches_publisher_note_v0460():
    """라우팅 문면의 범위 서술이 데이터 정본(meta.publisher_note)과 모순되지 않는지 —
    v0.46.0 계획 단계에서 '국토교통 R&D 과제에서 수집' 초안이 원문과 반대되는 허위가
    될 뻔한 함정의 잠금. publisher_note가 '국가 R&D 전반에서 수집'을 유지하는 동안만
    현 문면이 유효하다(판 교체 시 이 테스트가 재검토를 강제)."""
    d = _payload()
    assert "국가 R&D 전반에서 수집" in d["meta"]["publisher_note"]


def test_case_body_ministry_token_scarcity_premise_v0460():
    """지시 문면의 사실 전제 잠금 — 사례집 본문에 부처명 표기가 희소('국토교통' 1건·
    '국토부' 0건 실측)해 부처명 토큰 AND 검색이 0건이라는 전제. 새 판 교체로 부처명이
    다수 등장하면 이 테스트가 깨져 문면 재검토를 강제한다(의도적 마찰)."""
    d = _payload()
    body = "".join(p["text"] for s in d["sections"] for p in s["pages"])
    assert body.count("국토교통") + body.count("국토부") <= 5


@pytest.mark.parametrize("ministry_query", [
    "국토교통부 부적정집행",
    "국토부 R&D 연구비 집행",        # 2026-08-08 실측 결손 질의 원문
    "국토교통부 연구개발비 사용",     # 〃
])
def test_case_ministry_query_zero_v0460(fresh_cache, ministry_query):
    """행동 전제 잠금(관측 표적 질의 매개변수화 — diff 적대검토 Codex 권고): '국토교통부'·
    '국토부' 토큰이 든 질의는 case 0건(프롬프트-only — 데이터·검색 알고리즘 무변 확인).
    빈도 임계 테스트와 달리 실제 결손 질의로 직접 잠근다. 주의: '국토교통'(부 없는 형태)
    단독 토큰은 case-4-1 도식 제목에 1건 매칭 가능 — 문면이 '0건이 되기 쉽습니다'로
    한정 서술하는 이유."""
    r = asyncio.run(search_manual(ministry_query))
    assert r["total_matched_by_source"]["case"] == 0, ministry_query


def test_case_topical_query_reaches_v0460(fresh_cache):
    """행동 전제 잠금: 주제어 질의는 case 도달(지시가 안내하는 우회 경로 실재)."""
    r_topic = asyncio.run(search_manual("연구비 부적정집행"))
    assert r_topic["total_matched_by_source"]["case"] >= 1
