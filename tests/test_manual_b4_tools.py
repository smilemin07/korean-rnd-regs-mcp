"""v0.39.0 R5 — 혁신법 매뉴얼 별권 4 「연구시설･장비비 통합관리제 운영･관리 매뉴얼」 수록 테스트.

장 없는 평면 편제 최초 소스(단일 레벨 id b4-0~b4-9·b4-ref-1) — 로더 강화 검증·라우팅·검색 병합·
citation(장 생략 경로)·기본 footer 문면·붙임 스냅샷 사실 라벨·oversized 청크·격리·descriptor 정합을
잠근다. 기존 5소스 무회귀·가용성 전수(2^6=64)는 test_manual_b1_tools.py::test_availability_64_combinations.
"""
import asyncio
import json
import pathlib

import pytest

import korean_rnd_regs_mcp.main as main_mod
import korean_rnd_regs_mcp.manual as manual_mod
from korean_rnd_regs_mcp.main import get_manual_section, search_manual
from korean_rnd_regs_mcp.manual import SECTION_ID_RE, load_manual_b4

B4_ALL_IDS = [
    "b4-0", "b4-1", "b4-2", "b4-3", "b4-4", "b4-5",
    "b4-6", "b4-7", "b4-8", "b4-9", "b4-ref-1",
]


@pytest.fixture
def fresh_cache():
    manual_mod._reset_cache_for_tests()
    yield
    manual_mod._reset_cache_for_tests()


# ── 로더·데이터 계약 ─────────────────────────────────────────────────────────

def test_b4_loader_ok_and_shape(fresh_cache):
    data = load_manual_b4()
    assert not isinstance(data, manual_mod.ManualLoadError)
    assert len(data.sections) == 11
    assert data.meta["section_count"] == 11
    assert data.meta["source_title"] == "연구시설･장비비 통합관리제 운영･관리 매뉴얼"
    assert data.meta["series_title"] == "국가연구개발혁신법 매뉴얼"
    assert data.meta["series_part"] == "별권 4"
    assert data.meta["edition"] == "26.7"
    assert data.meta["manual_basis_date"] is None
    assert [s["id"] for s in data.sections] == B4_ALL_IDS
    total = sum(s["char_count"] for s in data.sections)
    assert total == 39297  # 2026-08-06 추출 실측 잠금(판 교체 시 갱신 신호)
    # 평면 편제 — 전 단위 chapter_no=0(citation 장 생략 경로)
    assert all(s["chapter_no"] == 0 for s in data.sections)


def test_b4_meta_fact_lines_locked(fresh_cache):
    """붙임 스냅샷 사실 기재 잠금 — 스냅샷 범위 분리(계획 /disc Codex 조건 ①)·판번≠현행화·
    실측 문구 차이 예시·별지 서식 안내."""
    data = load_manual_b4()
    # basis_note: 고시 발췌 스냅샷 귀속 + 타 발췌 확인 불가 분리 + 규정 트랙 유도
    assert "제2023-49호(2023.12.28.)" in data.meta["basis_note"]
    assert "확인 불가" in data.meta["basis_note"]
    assert "rnd_funding_standard" in data.meta["basis_note"]
    # edition_note: 게시 세트 판번이 내용 현행화를 뜻하지 않음(KISTEP 표지만 변경 안내)
    assert "표지만" in data.meta["edition_note"]
    assert "현행화를 뜻하지 않습니다" in data.meta["edition_note"]
    # law_priority_extra 3문장: 제7장 교차 확인·붙임 구판 실측 사실·별지 서식
    extra = data.meta["law_priority_extra"]
    assert len(extra) == 3
    assert any("제7장(제100조~제111조)" in x for x in extra)
    assert any("제2023-49호(2023.12.28.)" in x and "참여연구자" in x for x in extra)
    assert any("별지 제13호~제17호서식" in x for x in extra)
    # 시리즈 소스 — per-source footer 문면 없음(기본 문면 사용·eval과 구분)
    assert not data.meta.get("footer_manual_line")


def test_section_id_regex_accepts_b4_single_level():
    """b4 단일 레벨 형태 수용 + 2레벨 거부(장 없는 평면 편제 — 계획 /disc 3/3)."""
    for ok in ("b4-0", "b4-1", "b4-9", "b4-ref-1", "b4-99"):
        assert SECTION_ID_RE.match(ok), ok  # b4-99는 형식 유효 → not_found 경로(의도 동작)
    for bad in ("b4-", "b4-1-1", "b4-ref", "b4-ref-", "b40-1", "B4-1", " b4-1"):
        assert not SECTION_ID_RE.match(bad), bad


# ── 상세 조회 표면 ───────────────────────────────────────────────────────────

def test_b4_detail_citation_and_meta(fresh_cache):
    r = asyncio.run(get_manual_section("b4-5"))
    assert r["content_available"] is True
    assert r["content_format"] == "plain_text_verbatim"
    # 장 없는 편제 — "제N장" 없이 로마숫자 label + 제목(chapter_no=0 생략 경로)
    assert r["citation"] == (
        "「연구시설･장비비 통합관리제 운영･관리 매뉴얼」(26.7판) "
        "Ⅴ. 통합 연구시설･장비비의 계상･지급･적립, 인쇄 p.14~17"
    )
    assert "제0장" not in r["citation"]
    meta = r["manual_meta"]
    assert meta["notice"] == (
        "인용 자료: 「연구시설･장비비 통합관리제 운영･관리 매뉴얼」(국가연구개발혁신법 매뉴얼 별권 4) "
        "26.7판(판번은 게시 세트 기준) · 법령 기준일 원문 미표기"
    )
    assert meta["manual_basis_date"] is None
    assert r["format_note"].startswith("본 content는 「연구시설･장비비 통합관리제 운영･관리 매뉴얼」")
    # 규범성 사실 문장 — 붙임 스냅샷 안내가 정확 1회(중복·누락 잠금)
    note = meta["law_priority_note"]
    assert note.count("제2023-49호(2023.12.28.)") == 1
    assert note.count("제7장(제100조~제111조)") == 1


def test_b4_intro_and_annex_citation_labels(fresh_cache):
    r0 = asyncio.run(get_manual_section("b4-0"))
    assert r0["citation"] == (
        "「연구시설･장비비 통합관리제 운영･관리 매뉴얼」(26.7판) "
        "연구시설･장비비 통합관리제 개요, 인쇄 p.3"
    )
    assert r0["section_label"] == "" and r0["content_available"] is True
    ra = asyncio.run(get_manual_section("b4-ref-1"))
    assert ra["citation"] == (
        "「연구시설･장비비 통합관리제 운영･관리 매뉴얼」(26.7판) "
        "붙임 연구시설･장비비 통합관리제 관련 규정, 인쇄 p.32~50"
    )


def test_b4_footer_default_series_line(fresh_cache):
    """b4는 혁신법 매뉴얼 시리즈 — footer 3번째 줄이 기본 문면(per-source 아님·4줄)."""
    r = asyncio.run(get_manual_section("b4-1"))
    footer = r["manual_meta"]["standard_footer"]
    lines = footer.split("\n")
    assert len(lines) == 4
    assert lines[2] == (
        "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다. "
        "매뉴얼은 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다."
    )


def test_b4_annex_pointer_chunks_roundtrip_and_tier_note(fresh_cache):
    """b4-ref-1(붙임 14,217자) — 상세 = 포인터 + 청크 2 무손실 재조립.
    ★검색 oversized 플래그는 본문 크기 기준(False)·상세 tier는 응답 전체 기준(포인터) —
    판정 기준 차이는 본권 2-5·eval-3-2와 동형의 pre-existing 거동(2026-08-06 실측·§5.30 문서화)."""
    r = asyncio.run(get_manual_section("b4-ref-1"))
    assert r["content_format"] == "oversized_pointer"
    assert r["content_available"] is False
    n = r["chunk_count"]
    assert n == 2
    parts = []
    for i in range(1, n + 1):
        c = asyncio.run(get_manual_section("b4-ref-1", chunk=i))
        assert c["content_format"] == "plain_text_verbatim"
        assert len(json.dumps(c, ensure_ascii=False)) <= manual_mod.MANUAL_DETAIL_CHAR_BUDGET
        parts.append(c["content"])
    data = load_manual_b4()
    assert "".join(parts) == data.full_text["b4-ref-1"]
    # 포인터 응답 footer 2줄 규약(본문 미전달 — 허위 인용 고지 차단)
    assert r["manual_meta"]["standard_footer"].count("※") == 2
    # 검색 쪽 표면: 같은 절의 oversized 플래그는 본문 크기 기준 False(판정 기준 차이 잠금)
    s = asyncio.run(search_manual("통합관리제 관련 규정"))
    annex_hits = [m for m in s["matches"] if m["section_id"] == "b4-ref-1"]
    assert annex_hits and annex_hits[0]["oversized"] is False


def test_b4_all_ids_serve(fresh_cache):
    """11개 id 전수 — b4-ref-1 포인터 외 전 단위 전문·contract·인쇄쪽 범위 3~50."""
    for sid in B4_ALL_IDS:
        r = asyncio.run(get_manual_section(sid))
        assert r.get("errors") is None, sid
        assert r["contract_version"] == "0.30.0", sid
        assert 3 <= r["page_start"] <= r["page_end"] <= 50, sid
        if sid == "b4-ref-1":
            assert r["content_available"] is False, sid
        else:
            assert r["content_available"] is True, sid
            assert r["content_format"] == "plain_text_verbatim", sid
            assert r["manual_meta"]["standard_footer"].count("※") == 4, sid


# ── 참고 박스 병합·검색 도달 ─────────────────────────────────────────────────

def test_b4_reference_boxes_merged_with_subsection_titles(fresh_cache):
    """참고 1·2(Ⅱ 인터리브)·참고 3(Ⅵ) 병합 — subsection_titles 등재·본문 실재(계획 /disc 3/3)."""
    data = load_manual_b4()
    b42 = data.by_id["b4-2"]
    assert b42["subsection_titles"] == [
        "참고1 공공기관의 운영에 관한 법률에 따른 연구개발 목적기관이란?",
        "참고2 연구시설･장비비 통합관리기관 전산시스템 구축요건",
    ]
    b46 = data.by_id["b4-6"]
    assert b46["subsection_titles"] == ["참고3 ZEUS 국가연구시설･장비 정보 연계"]
    # 참고 본문이 부모 절 content에 원문 순서로 실재
    assert "연구개발 목적기관" in data.full_text["b4-2"]
    assert "api.zeus.go.kr" in data.full_text["b4-6"]


def test_b4_reference_title_queries_reach_parent(fresh_cache):
    """참고 제목 질의가 부모 절로 도달(subsection_titles 제목 인덱스 — Codex 조건)."""
    r = asyncio.run(search_manual("연구개발 목적기관"))
    assert any(m["section_id"] == "b4-2" and m["source"] == "b4" for m in r["matches"])
    r2 = asyncio.run(search_manual("ZEUS 정보 연계"))
    assert any(m["section_id"] == "b4-6" and m["source"] == "b4" for m in r2["matches"])


def test_b4_search_merge_and_citation(fresh_cache):
    r = asyncio.run(search_manual("연구시설 장비비 통합관리계정"))
    assert r["errors"] == []
    assert r["searched_sources"] == ["main", "b3", "b2", "b1", "eval", "b4"]
    assert r["scanned_sections"] == 133
    b4_hits = [m for m in r["matches"] if m["source"] == "b4"]
    assert b4_hits
    for m in b4_hits:
        assert m["section_id"].startswith("b4-")
        assert m["citation"].startswith("「연구시설･장비비 통합관리제 운영･관리 매뉴얼」(26.7판)")


def test_b4_mixed_meta_with_main(fresh_cache):
    """본권+별권 4 혼합 meta — sources 병기·provenance 별권 4 안내·footer는 기본 문면(시리즈 혼합)."""
    r = asyncio.run(search_manual("연구시설 장비비 통합관리계정"))
    meta = r["manual_meta"]
    assert set(meta["sources"].keys()) >= {"main", "b4"}
    assert "sources.b4" in meta["provenance_note"]
    assert "별권 4" in meta["provenance_note"]
    assert "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다." in meta["standard_footer"]
    # 붙임 스냅샷 사실 문장이 병기 note에 1회만
    assert meta["law_priority_note"].count("제2023-49호(2023.12.28.)") == 1


# ── 오류 경로 ────────────────────────────────────────────────────────────────

def test_b4_invalid_and_not_found_messages(fresh_cache):
    bad = asyncio.run(get_manual_section("b4-1-1"))
    assert bad["errors"][0]["code"] == "invalid_section_id"
    assert "'b4-1-1'형은 유효하지 않음" in bad["errors"][0]["message"]
    nf = asyncio.run(get_manual_section("b4-99"))
    assert nf["errors"][0]["code"] == "not_found"
    assert "별권 4(연구시설·장비비 통합관리제 운영·관리 매뉴얼) 유효 범위" in nf["errors"][0]["message"]
    assert "b4-1~b4-9" in nf["errors"][0]["message"] and "b4-0" in nf["errors"][0]["message"]


def test_b4_corrupt_data_isolated(fresh_cache, monkeypatch, tmp_path):
    """구조 손상 b4 파일이 예외 전파 없이 격리 — 기존 5소스 검색 지속·b4 조회만 오류."""
    bad = tmp_path / "corrupt_b4.json"
    bad.write_text('{"meta": {}, "sections": [null]}', encoding="utf-8")
    monkeypatch.setattr(manual_mod, "_B4_DATA_PATH", bad)
    r = load_manual_b4()
    assert isinstance(r, manual_mod.ManualLoadError)
    resp = asyncio.run(search_manual("협약 변경"))
    assert resp["errors"] == []
    assert resp["searched_sources"] == ["main", "b3", "b2", "b1", "eval"]
    assert resp["unavailable_sources"] == ["b4"]
    assert resp["source_warnings"][0]["code"] == "manual_b4_unavailable"
    assert "본권·별권 3·별권 2·별권 1·과제평가 표준지침만 검색한 부분 결과" in resp["source_warnings"][0]["message"]
    resp2 = asyncio.run(get_manual_section("b4-5"))
    msg = resp2["errors"][0]["message"]
    assert resp2["errors"][0]["code"] == "manual_b4_unavailable"
    assert "별권 4(연구시설·장비비 통합관리제 운영·관리 매뉴얼) 데이터 조회 불가" in msg
    assert "제100조~제111조" in msg
    # v0.39.0 격리 사실 문면(미확인 "정상" 단정 없음)
    assert "본권 매뉴얼 데이터는 정상 로드되었습니다" in msg
    assert "규정 도구(search_provision·get_provision_detail 등) 경로에는 전파되지 않습니다" in msg
    assert "규정 도구는 정상입니다" not in msg
    # 기존 소스 조회 무영향
    assert asyncio.run(get_manual_section("1-5"))["content_available"] is True
    assert asyncio.run(get_manual_section("eval-1-1"))["content_available"] is True


def test_b4_descriptor_appended_last(fresh_cache):
    descs = main_mod._MANUAL_SUPPLEMENTS
    b4 = descs[-1]
    assert b4["source_id"] == "b4" and b4["source_rank"] == 5 and b4["prefix"] == "b4-"
    assert b4["error_code"] == "manual_b4_unavailable"
    assert "연구시설·장비비 통합관리제 운영·관리 매뉴얼" in b4["label"]
    assert "제100조~제111조" in b4["unavailable_guidance"]
    assert "b4-0" in b4["valid_range"] and "b4-ref-1" in b4["valid_range"]


# ── 보존 표면(희석 기준선) ───────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "학생인건비 통합관리",   # b4 무매치 기대 축 — 학생인건비 트랙 잠식 0
    "기술료 납부",
    "제재처분 절차",
    "특별평가 사유",
    "협약 변경",
    "연구개발비 사용",
])
def test_existing_sources_baseline_preserved_v0390(fresh_cache, monkeypatch, tmp_path, query):
    """보존 표면 — 기존 대표 질의의 기존 소스 matches가 b4 유무와 무관하게 접두 보존
    (절대 잠식 0이 아니라 '기존 소스 매치 서열 보존' 모델 — 계획 /disc Codex 판정 모델)."""
    merged = asyncio.run(search_manual(query))
    manual_mod._reset_cache_for_tests()
    monkeypatch.setattr(manual_mod, "_B4_DATA_PATH", tmp_path / "no_b4.json")
    baseline = asyncio.run(search_manual(query))
    key = lambda r: [(m["section_id"], m["citation"]) for m in r["matches"] if m["source"] != "b4"]
    merged_existing = key(merged)
    baseline_all = key(baseline)
    assert merged_existing == baseline_all[: len(merged_existing)], query
    if merged["total_matched_by_source"].get("b4", 0) == 0:
        assert merged_existing == baseline_all, query  # b4 무매치면 완전 동일


def test_b4_no_student_track_dilution(fresh_cache):
    """학생인건비 대표 질의에서 b4 반환 잠식 0(두 통합관리제의 트랙 분리 실측 잠금).
    b4 본문에 '학생인건비' 부수 언급(비목 표·시행령 발췌)이 있어 total 매치는 0이 아니나,
    본문-only tier + rank 5 정렬로 cap 10 반환에는 진입하지 못한다(2026-08-06 실측)."""
    r = asyncio.run(search_manual("학생인건비 통합관리"))
    assert r["returned_by_source"].get("b4", 0) == 0
    assert all(m["source"] != "b4" for m in r["matches"])


# ── 데이터 무결성·표·출처 ────────────────────────────────────────────────────

def test_b4_data_recomputed_integrity(fresh_cache):
    """자기신고 필드가 아니라 재계산으로 잠금 — char_count 재계산 합·인쇄 3~50 완전 커버리지·
    절 내 단조성·page_start/end 정합(v0.38.0 Codex MAJOR 규약 재사용)."""
    data = load_manual_b4()
    covered = []
    recomputed_total = 0
    for s in data.sections:
        pages = s["pages"]
        printed = [p["printed_page"] for p in pages]
        assert printed == sorted(printed), s["id"]
        assert s["page_start"] == printed[0] and s["page_end"] == printed[-1], s["id"]
        full = "\n".join(p["text"] for p in pages)
        assert s["char_count"] == len(full), s["id"]
        recomputed_total += len(full)
        covered.extend(printed)
    assert recomputed_total == 39297
    assert sorted(set(covered)) == list(range(3, 51))  # 인쇄 3~50 완전 커버(누락·중복 쪽 0)
    assert len(covered) == len(set(covered))           # 공유 쪽 없음(전 단위 쪽 경계 시작)


def test_b4_table_pages_recorded(fresh_cache):
    """table_pages 실질 표 기록(행≥2 AND 열≥2 필터) — 2026-08-06 실측 잠금."""
    data = load_manual_b4()
    tp = {s["id"]: s["table_pages"] for s in data.sections}
    assert tp["b4-1"] == [4]           # 용어 표
    assert tp["b4-2"] == [9]           # 참고2 전산시스템 구축요건 표
    assert 33 in tp["b4-ref-1"] and 50 in tp["b4-ref-1"]  # 붙임 양식·서식 표
    assert tp["b4-0"] == []
    assert sum(len(v) for v in tp.values()) == 20


def test_b4_source_url_and_sha256(fresh_cache):
    """source_url = 별권 1~3과 같은 26.7 게시물 canonical 경로 + 승인 원본 sha256 잠금."""
    data = load_manual_b4()
    assert data.meta["source_url"] == (
        "https://www.kistep.re.kr/board.es?mid=a10301000000&bid=0003&act=view&list_no=94788"
    )
    assert data.meta["pdf_sha256"] == (
        "41ecb2d753169c7d02c139014b83b8cafaa4cf0f6c0ceed610b2a95fba780e97"
    )


def test_b4_packaging_force_include():
    root = pathlib.Path(__file__).resolve().parent.parent
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"src/korean_rnd_regs_mcp/manual_b4.json" = "korean_rnd_regs_mcp/manual_b4.json"' in pyproject
    payload = json.loads((root / "src/korean_rnd_regs_mcp/manual_b4.json").read_text(encoding="utf-8"))
    assert payload["meta"]["section_count"] == 11
    assert len(payload["sections"]) == 11
    assert payload["meta"]["id_format"] == "^b4-(\\d+|ref-\\d+)$"
    assert "간지" in payload["meta"]["excluded_note"]
    assert "인쇄 3~50" in payload["meta"]["excluded_note"]


def test_b4_loader_strict_validation_cases(fresh_cache, monkeypatch, tmp_path):
    """b1 강화 로더 규약의 b4 전개(diff 적대검토 Codex 커버리지 지적 반영) — 손상 유형별
    schema_invalid 격리."""
    base_sec = {"id": "b4-0", "section_index": 0,
                "pages": [{"printed_page": 3, "partial": False, "text": "x"}]}
    cases = {
        "dup_id": {"meta": {"section_count": 2}, "sections": [dict(base_sec), dict(base_sec)]},
        "bad_prefix": {"meta": {"section_count": 1}, "sections": [dict(base_sec, id="b1-1-1")]},
        "two_level_id": {"meta": {"section_count": 1}, "sections": [dict(base_sec, id="b4-1-1")]},
        "index_gap": {"meta": {"section_count": 1}, "sections": [dict(base_sec, section_index=3)]},
        "empty_pages": {"meta": {"section_count": 1}, "sections": [dict(base_sec, pages=[])]},
        "bad_page_type": {"meta": {"section_count": 1},
                          "sections": [dict(base_sec, pages=[{"printed_page": "3", "text": "x"}])]},
        "bool_page": {"meta": {"section_count": 1},
                      "sections": [dict(base_sec, pages=[{"printed_page": True, "partial": False, "text": "x"}])]},
        "count_mismatch": {"meta": {"section_count": 9}, "sections": [dict(base_sec)]},
    }
    for tag, payload in cases.items():
        manual_mod._reset_cache_for_tests()
        bad = tmp_path / f"{tag}.json"
        bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(manual_mod, "_B4_DATA_PATH", bad)
        r = load_manual_b4()
        assert isinstance(r, manual_mod.ManualLoadError), tag
        assert r.reason == "schema_invalid", tag


def test_review_prompt_description_covers_b4(fresh_cache):
    """★등록 prompt(prompts/list) description 잠금(diff 적대검토 Codex MAJOR 반영) —
    템플릿 본문과 별개의 공개 표면이라 별도 잠금. 별권 4·표준지침 포함·허위 미커버 부재."""
    prompts = asyncio.run(main_mod.mcp.list_prompts())
    desc = next(p for p in prompts if p.name == "review_regulation").description
    assert "별권 4 연구시설･장비비 통합관리제 운영･관리 매뉴얼" in desc
    assert "「국가연구개발 과제평가 표준지침」" in desc
    assert "별권 중 1종" not in desc and "연구시설장비)은 본 server 미커버" not in desc
