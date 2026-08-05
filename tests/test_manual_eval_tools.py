"""v0.38.0 「국가연구개발 과제평가 표준지침」(25.12) 수록 테스트.

매뉴얼 트랙 최초의 비(非)혁신법-매뉴얼 독립 소스(eval-) — 로더 강화 검증·라우팅·검색 병합·
citation·per-source footer 문면·oversized 청크·격리·descriptor 정합을 잠근다.
기존 4소스 무회귀·가용성 전수(2^5=32)는 test_manual_b1_tools.py::test_availability_32_combinations.
"""
import asyncio
import json

import pytest

import korean_rnd_regs_mcp.main as main_mod
import korean_rnd_regs_mcp.manual as manual_mod
from korean_rnd_regs_mcp.main import get_manual_section, search_manual
from korean_rnd_regs_mcp.manual import SECTION_ID_RE, load_manual_eval


@pytest.fixture
def fresh_cache():
    manual_mod._reset_cache_for_tests()
    yield
    manual_mod._reset_cache_for_tests()


# ── 로더·데이터 계약 ─────────────────────────────────────────────────────────

def test_eval_loader_ok_and_shape(fresh_cache):
    data = load_manual_eval()
    assert not isinstance(data, manual_mod.ManualLoadError)
    assert len(data.sections) == 15
    assert data.meta["section_count"] == 15
    assert data.meta["source_title"] == "국가연구개발 과제평가 표준지침"
    assert data.meta["edition"] == "25.12"
    assert data.meta["manual_basis_date"] is None
    assert data.meta["source_type"] == "government_standard_guideline"
    ids = [s["id"] for s in data.sections]
    assert ids == [
        "eval-1-1", "eval-1-2", "eval-1-3", "eval-1-4", "eval-1-5",
        "eval-2-1", "eval-3-1", "eval-3-2", "eval-3-3",
        "eval-ref-1", "eval-ref-2", "eval-ref-3", "eval-ref-4", "eval-ref-5", "eval-ref-6",
    ]
    total = sum(s["char_count"] for s in data.sections)
    assert total == 54507  # 2026-08-06 추출 실측 잠금(판 교체 시 갱신 신호)


def test_eval_meta_fact_lines_locked(fresh_cache):
    """문서 성격 사실 기재 잠금 — 개정(안) 표기·법적 근거·부처 평가지침 위계(계획 /disc B 채택)."""
    data = load_manual_eval()
    assert "개정(안)" in data.meta["edition_note"]
    assert "연구성과평가법 제13조" in data.meta["basis_note"]
    assert any("소관 부처·전문기관의 평가지침" in x for x in data.meta["law_priority_extra"])
    assert any("개정(안)" in x for x in data.meta["law_priority_extra"])
    assert data.meta["footer_manual_line"].startswith("※ 지침 해설 부분은 「국가연구개발 과제평가 표준지침」")


def test_section_id_regex_accepts_eval_series():
    for ok in ("eval-1-1", "eval-3-3", "eval-ref-1", "eval-ref-6"):
        assert SECTION_ID_RE.match(ok), ok
    for bad in ("eval-", "eval-1", "eval-1-1-1", "eval-ref-", "evalx-1-1"):
        assert not SECTION_ID_RE.match(bad), bad


# ── 상세 조회 표면 ───────────────────────────────────────────────────────────

def test_eval_detail_citation_and_meta(fresh_cache):
    r = asyncio.run(get_manual_section("eval-1-1"))
    assert r["content_available"] is True
    assert r["content_format"] == "plain_text_verbatim"
    assert r["citation"] == "「국가연구개발 과제평가 표준지침」(25.12판) 제1장 1. 법적근거, 인쇄 p.1"
    assert "연구성과평가법 제13조" in r["content"]
    meta = r["manual_meta"]
    assert meta["notice"] == (
        "인용 자료: 「국가연구개발 과제평가 표준지침」 25.12판"
        "(판번은 인쇄·발행 연월(2025.12) 표기 기준) · 법령 기준일 원문 미표기"
    )
    assert meta["source_type"] == "government_standard_guideline"
    assert meta["legal_effect"] == "not_binding"
    assert "개정(안)" in meta["law_priority_note"]
    assert "소관 부처·전문기관의 평가지침" in meta["law_priority_note"]


def test_eval_footer_per_source_line(fresh_cache):
    """footer 4줄 — 3번째 줄이 per-source 문면(출처 오귀속 차단)·기존 소스는 기본 문면 불변."""
    r = asyncio.run(get_manual_section("eval-2-1"))
    footer = r["manual_meta"]["standard_footer"]
    lines = footer.split("\n")
    assert len(lines) == 4
    assert lines[2] == (
        "※ 지침 해설 부분은 「국가연구개발 과제평가 표준지침」을 참고한 설명입니다. "
        "이 지침은 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다."
    )
    assert "「국가연구개발혁신법 매뉴얼」을 참고한 설명" not in footer
    # 기존 소스(본권 소형 절 1-5 — 전문 반환) footer 3번째 줄 불변(보존 표면)
    r2 = asyncio.run(get_manual_section("1-5"))
    assert r2["content_available"] is True
    assert "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다." in \
        r2["manual_meta"]["standard_footer"]


def test_eval_oversized_section_chunks_roundtrip(fresh_cache):
    """eval-3-3(18,644자) — 포인터 + 청크 무손실 재조립·청크 citation은 실제 담은 쪽만."""
    r = asyncio.run(get_manual_section("eval-3-3"))
    assert r["content_format"] == "oversized_pointer"
    n = r["chunk_count"]
    assert n >= 2
    parts = []
    for i in range(1, n + 1):
        c = asyncio.run(get_manual_section("eval-3-3", chunk=i))
        assert c["content_format"] == "plain_text_verbatim"
        assert len(json.dumps(c, ensure_ascii=False)) <= manual_mod.MANUAL_DETAIL_CHAR_BUDGET
        parts.append(c["content"])
    data = load_manual_eval()
    assert "".join(parts) == data.full_text["eval-3-3"]


def test_eval_subsection_titles_reach_search(fresh_cache):
    """eval-3-3 하위 평가 단계(선정/단계/특별/최종)가 subsection_titles로 검색 도달."""
    r = asyncio.run(search_manual("특별평가 절차"))
    assert r["errors"] == []
    eval_hits = [m for m in r["matches"] if m["source"] == "eval"]
    assert any(m["section_id"] == "eval-3-3" for m in eval_hits)


def test_eval_search_merge_and_citation(fresh_cache):
    r = asyncio.run(search_manual("과제평가 표준지침"))
    assert r["errors"] == []
    assert "eval" in r["searched_sources"]
    eval_hits = [m for m in r["matches"] if m["source"] == "eval"]
    assert eval_hits
    for m in eval_hits:
        assert m["section_id"].startswith("eval-")
        assert m["citation"].startswith("「국가연구개발 과제평가 표준지침」(25.12판)")


def test_eval_qna_reachable(fresh_cache):
    """참고 6(과제평가 Q&A) 도달 — 실무 최다 빈도 표면."""
    r = asyncio.run(get_manual_section("eval-ref-6"))
    assert r["content_available"] is True
    assert r["citation"] == "「국가연구개발 과제평가 표준지침」(25.12판) 참고 6 과제평가 Q&A, 인쇄 p.54~60"


# ── 격리·descriptor ──────────────────────────────────────────────────────────

def test_eval_corrupt_data_isolated(fresh_cache, monkeypatch, tmp_path):
    """구조 손상 eval 파일이 예외 전파 없이 격리 — 기존 4소스 검색 지속(Codex 공유 실패점 검증)."""
    bad = tmp_path / "corrupt_eval.json"
    bad.write_text('{"meta": {}, "sections": [null]}', encoding="utf-8")
    monkeypatch.setattr(manual_mod, "_EVAL_DATA_PATH", bad)
    r = load_manual_eval()
    assert isinstance(r, manual_mod.ManualLoadError)
    resp = asyncio.run(search_manual("협약 변경"))
    assert resp["errors"] == []
    assert resp["searched_sources"] == ["main", "b3", "b2", "b1"]
    assert resp["unavailable_sources"] == ["eval"]
    assert resp["source_warnings"][0]["code"] == "manual_eval_unavailable"
    resp2 = asyncio.run(get_manual_section("eval-1-1"))
    assert resp2["errors"][0]["code"] == "manual_eval_unavailable"
    assert "과제평가 근거가 필요하면" in resp2["errors"][0]["message"]


def test_eval_descriptor_appended_last(fresh_cache):
    descs = main_mod._MANUAL_SUPPLEMENTS
    ev = descs[-1]
    assert ev["source_id"] == "eval" and ev["source_rank"] == 4 and ev["prefix"] == "eval-"
    assert ev["error_code"] == "manual_eval_unavailable"
    assert "국가연구개발 과제평가 표준지침" in ev["label"]
    assert "eval-1-1~eval-1-5" in ev["valid_range"] and "eval-ref-1~eval-ref-6" in ev["valid_range"]


def test_eval_unknown_section_not_found(fresh_cache):
    """형식 유효·실재하지 않는 id — not_found + 유효 범위 안내(기존 규약 동형)."""
    r = asyncio.run(get_manual_section("eval-9-9"))
    assert r["errors"][0]["code"] == "not_found"
    assert "eval-1-1~eval-1-5" in r["errors"][0]["message"]


@pytest.mark.parametrize("query", [
    "학생인건비 통합관리",   # eval 무매치 — 완전 동일 기대
    "학생인건비 이자",       # 희석 기준선 실측 5종(2026-08-06) — eval 잠식 0 잠금
    "기술료 납부",
    "제재처분 절차",
    "협약 변경",
    "연구개발비 사용",
])
def test_existing_sources_baseline_preserved(fresh_cache, monkeypatch, tmp_path, query):
    """보존 표면 — 기존 대표 질의의 기존 소스 matches가 eval 유무와 무관하게 접두 보존
    (diff 적대검토 Gemini MAJOR 반영: 실측 주장 5종 전체를 자동 잠금 — 기존 소스 매치의
    상대 순서·내용이 baseline의 접두이고, eval 매치는 뒤가 아닌 자기 관련도 위치에만 삽입될
    수 있으므로 '기존 소스 매치 서열 보존'으로 검증)."""
    merged = asyncio.run(search_manual(query))
    manual_mod._reset_cache_for_tests()
    monkeypatch.setattr(manual_mod, "_EVAL_DATA_PATH", tmp_path / "no_eval.json")
    baseline = asyncio.run(search_manual(query))
    key = lambda r: [(m["section_id"], m["citation"]) for m in r["matches"] if m["source"] != "eval"]
    merged_existing = key(merged)
    baseline_all = key(baseline)
    # 기존 소스 매치는 baseline 서열의 접두(cap 10에 의한 하위 밀림만 허용 — 설계된 거동)
    assert merged_existing == baseline_all[: len(merged_existing)], query
    if merged["total_matched_by_source"].get("eval", 0) == 0:
        assert merged_existing == baseline_all, query  # eval 무매치면 완전 동일


# === v0.38.0 diff 적대검토 2차 반영(Codex) — 재계산 검증·혼합 footer·표 표면 ===


def test_eval_data_recomputed_integrity(fresh_cache):
    """자기신고 필드가 아니라 재계산으로 잠금(Codex MAJOR 반영) — char_count 재계산 합·
    페이지 1~60 완전 커버리지·절 내 단조성·page_start/end 정합."""
    data = load_manual_eval()
    covered = []
    recomputed_total = 0
    for s in data.sections:
        pages = s["pages"]
        printed = [p["printed_page"] for p in pages]
        assert printed == sorted(printed), s["id"]                    # 절 내 단조
        assert s["page_start"] == printed[0] and s["page_end"] == printed[-1], s["id"]
        full = "\n".join(p["text"] for p in pages)
        assert s["char_count"] == len(full), s["id"]                  # 자기신고 ≠ 실측 차단
        recomputed_total += len(full)
        covered.extend(printed)
    assert recomputed_total == 54507                                   # 재계산 합 잠금
    assert sorted(set(covered)) == list(range(1, 61))                  # 인쇄 1~60 완전 커버(누락 0)


def test_eval_table_pages_recorded(fresh_cache):
    """table_pages 실질 표 기록(Codex MAJOR 반영 — 전 절 빈 배열이면 표 경고 표면이 죽음).
    실사 4쪽 기준: p.24(2×2·7×2)·p.51(5×5) 포함·p.5(1×2 박스)·p.13(1×2) 제외."""
    data = load_manual_eval()
    tp = {s["id"]: s["table_pages"] for s in data.sections}
    assert 24 in tp["eval-3-2"]
    assert 51 in tp["eval-ref-4"]
    assert 5 not in tp["eval-1-5"] and 5 not in tp["eval-1-4"]
    assert 13 not in tp["eval-3-1"]
    assert sum(len(v) for v in tp.values()) == 37                     # 2026-08-06 실측 잠금


def test_eval_source_url_is_kaia_edition_page(fresh_cache):
    """source_url 판 정합(Codex MAJOR 반영 — 24.4판 msit 게시물 오지정 차단): 25.12판이 실재
    게시된 KAIA 목록. 게시 PDF sha256 = 승인 원본과 byte-identical 대조 완료(2026-08-06)."""
    data = load_manual_eval()
    assert data.meta["source_url"].startswith("https://www.kaia.re.kr/")
    assert "msit.go.kr" not in data.meta["source_url"]
    assert data.meta["pdf_sha256"] == "9cee1d9a6b451cb47c35a81fedea017dcd7d02e04174b8288441e7f7e9de7b81"


def test_mixed_search_footer_uses_generic_line(fresh_cache):
    """혼합 검색(main+eval) footer 3번째 줄 = 일반 지칭 문면(Codex MAJOR 반영 — primary 문면만
    쓰면 eval 발췌가 혁신법 매뉴얼로 오귀속). 기존 시리즈-only 혼합은 기본 문면 불변."""
    r = asyncio.run(search_manual("특별평가 절차"))
    srcs = set(r["total_matched_by_source"])
    assert r["total_matched_by_source"].get("eval", 0) > 0
    assert r["total_matched_by_source"].get("main", 0) > 0
    footer = r["manual_meta"]["standard_footer"]
    assert "※ 매뉴얼·지침 해설 부분은 아래에 표기된 인용 자료들을 참고한 설명입니다." in footer
    assert "「국가연구개발혁신법 매뉴얼」을 참고한 설명" not in footer
    # 시리즈-only 혼합(main+b3 — eval 무매치)은 기존 기본 문면 보존
    r2 = asyncio.run(search_manual("제재처분 가이드라인"))
    if r2["total_matched_by_source"].get("eval", 0) == 0 and len([s for s in r2["total_matched_by_source"] if r2["total_matched_by_source"][s] > 0]) >= 2:
        assert "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다." in r2["manual_meta"]["standard_footer"]
