"""Unit tests for search_provision / get_provision_detail / suggest_review_sources.

LawApiClient를 mock하여 네트워크 없이 도구 동작·키 누설 차단·응답 shape 검증.
GitHub Actions에서 별도 통합 테스트 (@pytest.mark.network) 도입 예정.
"""
import asyncio
import json
import types
from unittest.mock import MagicMock

import pytest

from korean_rnd_regs_mcp import main as main_module
from korean_rnd_regs_mcp.live_api import LawApiClient, LawApiError, ResolvedDocId
from korean_rnd_regs_mcp.main import (
    _DEGRADED_NOTE_CLIENT_FB,
    _DEGRADED_NOTE_EMPTY,
    _DEGRADED_NOTE_FALLBACK,
    _RECALL_DIRECTIVE,
    _admrul_version_meta,
    _append_overflow_candidates,
    _extract_keywords,
    _make_snippet,
    _overflow_label,
    _relevance_sort_key,
    _resolve_effective_date,
    _revision_notice,
    _sanitize_keywords,
    _select_capped_candidates,
    _shorten_snippet,
    _strip_particle,
    _title_hits,
    _title_token_match,
    get_provision_detail,
    list_rule_sets,
    search_provision,
    suggest_review_sources,
)

_FAKE_KEY = "fake_secret_key_xyz_2099"


@pytest.fixture
def mock_client(monkeypatch):
    """LawApiClient를 mock으로 대체. api_key는 fake value로 설정."""
    client = MagicMock(spec=LawApiClient)
    client.base_url = "https://test.invalid"
    client.api_key = _FAKE_KEY
    client.get_law_detail.return_value = {
        "법령ID": "013774",
        "법령일련번호": "283849",
        "법령명한글": "국가연구개발혁신법",
        "법령구분명": "법률",
        "소관부처명": "과학기술정보통신부",
        "시행일자": "20260611",
        "공포일자": "20240227",
        "articles": [
            {
                "조문번호": "15",
                "조문제목": "특별평가",
                "조문내용": "제15조(특별평가) 특별평가 본문...",
                "structured": {
                    "title": "제15조(특별평가)",
                    "paragraphs": [
                        {
                            "number": "①",
                            "text": "중앙행정기관의 장은 다음 각 호...",
                            "source_text": "① 중앙행정기관의 장은 다음 각 호...",
                            "subparagraphs": [
                                {"number": "1.", "text": "부정행위 발생", "source_text": "1. 부정행위 발생"},
                            ],
                        },
                    ],
                },
            },
            {
                "조문번호": "21",
                "조문제목": "간접비계상",
                "조문내용": "제21조 간접비 본문...",
                "structured": {"title": "제21조(간접비계상)", "paragraphs": []},
            },
        ],
    }
    client.get_admin_rule_detail.return_value = {
        "행정규칙ID": "abc",
        "행정규칙일련번호": "2100000278740",
        "행정규칙명": "연구개발비 사용 기준",
        "articles": [],
        "annexes": [
            {
                "별표번호": "1",
                "별표제목": "기본사업연구개발비계상기준",
                "별표내용": "별표 본문 — 간접비 관련 기준",
                "별표서식파일링크": "/LSW/flDownload.do?flSeq=164083923",
            },
        ],
    }
    def _resolve_passthrough(title, api_target, manifest_doc_id, ministry=None):
        return ResolvedDocId(
            doc_id=manifest_doc_id,
            effective_date="",
            is_updated=False,
            manifest_doc_id=manifest_doc_id,
        )
    client.resolve_latest_doc_id.side_effect = _resolve_passthrough
    monkeypatch.setattr(main_module, "_client_instance", client)
    return client


# === _strip_particle / _extract_keywords 단위 ===
def test_strip_particle_basic():
    assert _strip_particle("특별평가를") == "특별평가"
    assert _strip_particle("간접비를") == "간접비"
    assert _strip_particle("시행령은") == "시행령"


def test_strip_particle_keeps_short_words():
    # 조사 strip 시 길이 < 2 되면 원본 유지
    assert _strip_particle("이") == "이"
    assert _strip_particle("것은") == "것은"  # "것"만 남으면 1자, 원본 유지


def test_strip_particle_keeps_noun_ending_in_ga():
    """회귀: '특별평가'의 끝 '가'를 조사로 잘못 strip하지 않아야 함."""
    assert _strip_particle("특별평가") == "특별평가"
    assert _strip_particle("정의") == "정의"  # '의'도 stay
    assert _strip_particle("기준에") == "기준에"  # '에'도 stay
    assert _strip_particle("연구개발비") == "연구개발비"  # '비' = noun, not particle


def test_extract_keywords_strips_particles():
    result = _extract_keywords("특별평가를 받으려면 어떤 절차가 필요한가요?")
    assert "특별평가" in result


def test_extract_keywords_filters_stopwords():
    result = _extract_keywords("어떤 경우에 필요합니까")
    # stopwords 모두 제거됨
    assert "어떤" not in result
    assert "경우" not in result
    assert "필요합니까" not in result


# === _make_snippet ===
def test_make_snippet_short_content_returned_as_is():
    assert _make_snippet("짧은 내용", "내용") == "짧은 내용"


def test_make_snippet_match_in_middle_returns_window():
    text = "앞부분" + "X" * 1500 + "키워드" + "Y" * 1500
    snippet = _make_snippet(text, "키워드", max_len=200)
    assert "키워드" in snippet
    assert len(snippet) <= 210  # 200 + ellipsis 2개


def test_make_snippet_no_match_returns_prefix():
    text = "X" * 3000
    snippet = _make_snippet(text, "없는키워드", max_len=200)
    assert snippet == text[:200]


# === search_provision ===
def test_search_provision_empty_query_returns_invalid(mock_client):
    """회귀: empty/공백/1글자 query는 invalid_query error 반환."""
    for q in ["", " ", "  ", "법"]:
        result = asyncio.run(search_provision(q))
        assert result["total"] == 0, f"{q!r}: should not match"
        assert "errors" in result
        assert result["errors"][0]["code"] == "invalid_query"
        assert "disclaimer" in result


def test_search_provision_response_shape(mock_client):
    result = asyncio.run(search_provision("특별평가"))
    assert "query" in result
    assert "total" in result
    assert "returned" in result
    assert "truncated" in result
    assert "contract_version" in result
    assert "disclaimer" in result
    assert "results" in result
    assert isinstance(result["results"], list)
    assert result["returned"] <= result["total"]


def test_search_provision_finds_article(mock_client):
    result = asyncio.run(search_provision("특별평가"))
    # mock가 모든 law(3건)에 같은 articles 반환 → JO0015 매칭 3개
    assert result["total"] >= 1
    jo0015_matches = [r for r in result["results"] if r["unit_id"] == "JO0015"]
    assert len(jo0015_matches) >= 1
    assert jo0015_matches[0]["unit_type"] == "article"
    assert jo0015_matches[0]["title"] == "특별평가"


def test_search_provision_no_key_leak(mock_client):
    """회귀: 도구 응답에 API key 원문·prefix·OC= 미포함."""
    result = asyncio.run(search_provision("특별평가"))
    response_str = json.dumps(result, ensure_ascii=False)
    assert _FAKE_KEY not in response_str
    assert _FAKE_KEY[:6] not in response_str
    assert "OC=" not in response_str


def test_search_provision_no_key_leak_on_error(mock_client, monkeypatch):
    """Defense-in-depth: LawApiError message에 우연히 키가 섞여도 도구 응답에서 redacted.

    Source(_request_with_retry)는 이미 type name만 사용하지만, main.py의 _sanitize_error_message가
    second layer로 LAW_API_KEY 값을 redact하는지 검증.
    """
    monkeypatch.setenv("LAW_API_KEY", _FAKE_KEY)
    mock_client.get_law_detail.side_effect = LawApiError(
        "parse_failed", f"가짜 오류 mentioning {_FAKE_KEY}"
    )
    result = asyncio.run(search_provision("test"))
    response_str = json.dumps(result, ensure_ascii=False)
    assert _FAKE_KEY not in response_str, f"defense층 sanitize 실패: {response_str[:300]}"
    assert "REDACTED" in response_str or "errors" in result, "sanitize 마커 또는 errors 키 부재"


def test_sanitize_error_message_redacts_per_user_key(mock_client, monkeypatch):
    """HTTP 모드: per-user OC key가 에러 메시지에 포함되어도 redact."""
    per_user_key = "USER_SECRET_OC_KEY_99"
    from korean_rnd_regs_mcp.main import _request_api_key
    token = _request_api_key.set(per_user_key)
    try:
        mock_client.get_law_detail.side_effect = LawApiError(
            "parse_failed", f"오류 {per_user_key}"
        )
        result = asyncio.run(search_provision("test"))
        response_str = json.dumps(result, ensure_ascii=False)
        assert per_user_key not in response_str
    finally:
        _request_api_key.reset(token)


# === get_provision_detail ===
def test_get_provision_detail_invalid_format_returns_errors_list(mock_client):
    result = asyncio.run(get_provision_detail("bad:format:too:many"))
    assert "errors" in result
    assert isinstance(result["errors"], list)
    assert result["errors"][0]["code"] == "invalid_provision_id"
    assert "disclaimer" in result
    assert "contract_version" in result


def test_get_provision_detail_not_in_manifest_returns_errors_list(mock_client):
    result = asyncio.run(get_provision_detail("law:999999"))
    assert "errors" in result
    assert result["errors"][0]["code"] == "not_found"
    assert "disclaimer" in result


def test_get_provision_detail_article(mock_client):
    result = asyncio.run(get_provision_detail("law:283849:JO0015"))
    assert result["unit_type"] == "article"
    assert result["unit_id"] == "JO0015"
    assert result["title"] == "특별평가"
    assert "제15조" in result["content"]
    assert "disclaimer" in result
    assert "contract_version" in result


def test_get_provision_detail_annex_attached_url_is_absolute(mock_client):
    result = asyncio.run(get_provision_detail("admrul:2100000278740:BP0001"))
    assert result["unit_type"] == "annex"
    assert result["attached_file_url"].startswith("https://www.law.go.kr/LSW/")
    assert "disclaimer" in result


def test_get_provision_detail_document_level_includes_disclaimer(mock_client):
    result = asyncio.run(get_provision_detail("law:283849"))
    assert result["unit_type"] == "document"
    assert "articles_count" in result
    assert "disclaimer" in result


def test_get_provision_detail_no_key_leak(mock_client):
    result = asyncio.run(get_provision_detail("law:283849:JO0015"))
    response_str = json.dumps(result, ensure_ascii=False)
    assert _FAKE_KEY not in response_str
    assert _FAKE_KEY[:6] not in response_str


def test_get_provision_detail_no_per_user_oc_key_leak(mock_client, monkeypatch):
    """회귀(작업1 gap c): per-user OC key(contextvar 경로)가 정상 응답에 미포함."""
    from korean_rnd_regs_mcp.main import _request_api_key
    per_user_oc = "PER_USER_OC_FAKE_7788"
    # contextvar 설정 시 _get_client가 per-user 클라이언트를 찾으므로 mock을 주입(네트워크 없음)
    monkeypatch.setitem(main_module._client_by_key, per_user_oc, mock_client)
    token = _request_api_key.set(per_user_oc)
    try:
        result = asyncio.run(get_provision_detail("law:283849:JO0015"))
        response_str = json.dumps(result, ensure_ascii=False)
        assert per_user_oc not in response_str
        assert per_user_oc[:6] not in response_str
    finally:
        _request_api_key.reset(token)


# === LLM 환각 방어 (article_structure + format_instructions) ===
def test_get_provision_detail_article_includes_verbatim_metadata(mock_client):
    """회귀: content가 verbatim임을 명시하는 metadata 포함."""
    result = asyncio.run(get_provision_detail("law:283849:JO0015"))
    assert result.get("content_format") == "plain_text_verbatim"
    assert "format_instructions" in result
    instructions = result["format_instructions"]
    # 핵심 지시 키워드 확인
    assert "verbatim" in instructions.lower() or "그대로" in instructions
    assert "임의" in instructions  # "임의 부제·요약·paraphrase 금지"
    assert "번호" in instructions  # 항·호 번호 stripping 금지


def test_get_provision_detail_article_includes_article_structure(mock_client):
    """회귀: machine-readable nested hierarchy."""
    result = asyncio.run(get_provision_detail("law:283849:JO0015"))
    structure = result.get("article_structure")
    assert structure is not None
    assert "title" in structure
    assert "paragraphs" in structure
    # mock에서 ①항 1개 + 1호 1개 정의
    paragraphs = structure["paragraphs"]
    assert len(paragraphs) >= 1
    p = paragraphs[0]
    assert "number" in p and "text" in p and "source_text" in p
    assert p["number"] == "①"
    # number prefix가 text에서는 stripped (source_text에는 유지)
    assert p["text"].startswith("중앙행정기관") or p["text"].startswith("①")
    assert p["source_text"].startswith("①")
    if p.get("subparagraphs"):
        sub = p["subparagraphs"][0]
        assert "number" in sub and "text" in sub and "source_text" in sub


def test_build_paragraph_strips_number_prefix():
    """_build_paragraph 헬퍼: number 분리 + source_text 보존."""
    import xml.etree.ElementTree as ET

    from korean_rnd_regs_mcp.live_api import _build_paragraph

    xml = """
    <항>
      <항번호>①</항번호>
      <항내용>① 중앙행정기관의 장은 ...</항내용>
      <호>
        <호번호>1.</호번호>
        <호내용>1.  부정행위 발생</호내용>
      </호>
    </항>
    """
    elem = ET.fromstring(xml)
    result = _build_paragraph(elem)
    assert result["number"] == "①"
    assert result["text"] == "중앙행정기관의 장은 ..."  # ① stripped
    assert result["source_text"] == "① 중앙행정기관의 장은 ..."  # 원문 보존
    assert len(result["subparagraphs"]) == 1
    sub = result["subparagraphs"][0]
    assert sub["number"] == "1."
    assert sub["text"] == "부정행위 발생"  # "1." stripped (lstrip로 공백도)
    assert sub["source_text"] == "1.  부정행위 발생"


# === suggest_review_sources ===
def test_suggest_review_sources_extracts_keywords_after_particle_strip(mock_client):
    result = asyncio.run(suggest_review_sources("특별평가를 받으려면 어떤 절차?"))
    assert "특별평가" in result["extracted_keywords"]


def test_suggest_review_sources_response_shape(mock_client):
    result = asyncio.run(suggest_review_sources("특별평가"))
    assert "question" in result
    assert "extracted_keywords" in result
    assert "recommended_review_order" in result
    assert "candidates" in result
    assert "disclaimer" in result
    assert "contract_version" in result
    assert "overflow_candidates" in result      # v0.1.8 — 항상 포함
    assert "overflow_truncated" in result
    assert isinstance(result["overflow_candidates"], list)
    assert isinstance(result["overflow_truncated"], bool)


def test_suggest_review_sources_hierarchy_sorted(mock_client):
    result = asyncio.run(suggest_review_sources("특별평가"))
    # candidates는 hierarchy_rank 오름차순
    if len(result["candidates"]) >= 2:
        ranks = []
        for c in result["candidates"]:
            doc_type, doc_id = c["provision_id"].split(":")[:2]
            # mock 매칭 — 어차피 manifest 항목 기반으로 정렬됨
        # 단순 형식만 검증: review_order의 rank가 정렬되어 있는지
        rank_list = [o["rank"] for o in result["recommended_review_order"]]
        assert rank_list == sorted(rank_list)


def test_suggest_review_sources_no_key_leak(mock_client):
    result = asyncio.run(suggest_review_sources("특별평가"))
    response_str = json.dumps(result, ensure_ascii=False)
    assert _FAKE_KEY not in response_str


def test_suggest_review_sources_no_per_user_oc_key_leak(mock_client, monkeypatch):
    """회귀(작업1 gap c): per-user OC key(contextvar 경로)가 suggest 응답에 미포함."""
    from korean_rnd_regs_mcp.main import _request_api_key
    per_user_oc = "PER_USER_OC_FAKE_7788"
    monkeypatch.setitem(main_module._client_by_key, per_user_oc, mock_client)
    token = _request_api_key.set(per_user_oc)
    try:
        result = asyncio.run(suggest_review_sources("특별평가"))
        response_str = json.dumps(result, ensure_ascii=False)
        assert per_user_oc not in response_str
        assert per_user_oc[:6] not in response_str
    finally:
        _request_api_key.reset(token)


def test_suggest_review_sources_propagates_search_errors(mock_client):
    """회귀: 내부 search_provision 실패를 errors로 전파 (매칭 없음으로 위장 금지)."""
    mock_client.get_law_detail.side_effect = LawApiError("parse_failed", "synthetic error")
    mock_client.get_admin_rule_detail.side_effect = LawApiError("parse_failed", "synthetic error")
    result = asyncio.run(suggest_review_sources("특별평가"))
    assert "errors" in result, "search 실패가 suggest_review_sources errors로 전파되어야 함"
    assert len(result["errors"]) >= 1
    # error에 keyword 정보 포함
    assert any("keyword" in e for e in result["errors"])


# === A축: LLM 키워드 위임 (v0.1.5) ===
def test_sanitize_keywords_normalizes():
    """문자열만·strip·2자 이상·순서 보존 dedupe."""
    out = _sanitize_keywords(["  특별평가  ", "특별평가", "동시수행", "x", "  ", 1, None, "연구개발비"])
    assert out == ["특별평가", "동시수행", "연구개발비"]


def test_sanitize_keywords_truncates_to_10():
    out = _sanitize_keywords([f"키워드{i}" for i in range(15)])
    assert len(out) == 10
    assert out == [f"키워드{i}" for i in range(10)]


def test_sanitize_keywords_none_and_all_invalid():
    assert _sanitize_keywords(None) == []
    assert _sanitize_keywords([]) == []
    assert _sanitize_keywords(["x", " ", 1]) == []


def test_suggest_review_sources_uses_client_keywords(mock_client):
    """keywords 제공 시 그대로 우선 사용 + keyword_source=client."""
    result = asyncio.run(suggest_review_sources("아무 상황 설명", keywords=["특별평가"]))
    assert result["keyword_source"] == "client"
    assert result["extracted_keywords"] == ["특별평가"]
    assert len(result["candidates"]) >= 1


def test_suggest_review_sources_fallback_when_no_keywords(mock_client):
    """keywords 미제공 → 규칙 추출 fallback (기존 동작 유지)."""
    result = asyncio.run(suggest_review_sources("특별평가"))
    assert result["keyword_source"] == "fallback"
    assert "특별평가" in result["extracted_keywords"]


def test_suggest_review_sources_empty_or_invalid_keywords_fall_back(mock_client):
    """빈 배열·전부 무효 → fallback (silent 0건 방지)."""
    r1 = asyncio.run(suggest_review_sources("특별평가", keywords=[]))
    r2 = asyncio.run(suggest_review_sources("특별평가", keywords=["x", " "]))
    assert r1["keyword_source"] == "fallback"
    assert r2["keyword_source"] == "fallback"
    assert "특별평가" in r1["extracted_keywords"]


def test_suggest_review_sources_client_zero_hit_post_fallback(mock_client):
    """client 키워드가 0건 + 오류 없음 → 규칙 추출로 보강(client+fallback)."""
    result = asyncio.run(
        suggest_review_sources("특별평가 절차", keywords=["절대로없는키워드zzz"])
    )
    assert result["keyword_source"] == "client+fallback"
    assert "특별평가" in result["extracted_keywords"]
    assert len(result["candidates"]) >= 1


def test_suggest_review_sources_keyword_source_on_empty(mock_client):
    """추출 결과 전무(한글 없음)면 빈 응답에도 keyword_source 포함."""
    result = asyncio.run(suggest_review_sources("abc 123 ???"))
    assert result["keyword_source"] == "fallback"
    assert result["extracted_keywords"] == []
    assert result["candidates"] == []


def test_suggest_review_sources_empty_path_includes_overflow_fields(mock_client):
    """v0.1.8 회귀(Blocking 1): no-keyword early-return에도 overflow 필드 항상 포함(contract 0.3.0)."""
    result = asyncio.run(suggest_review_sources("abc 123 ???"))   # 유효 키워드 0건 → early return
    assert result["overflow_candidates"] == []
    assert result["overflow_truncated"] is False


# === v0.1.9: degraded note 명령형 신호 + 호스트 위임 강화 ===
def test_suggest_fallback_note_is_degraded_directive(mock_client):
    """v0.1.9(#1): fallback(무키워드)이면 note가 [degraded] 마커 + 재호출 명령(_RECALL_DIRECTIVE) 포함."""
    result = asyncio.run(suggest_review_sources("특별평가"))
    assert result["keyword_source"] == "fallback"
    assert "note" in result
    # v0.2.5: 25개 규정 확대로 mock 환경에서 cap 초과(truncation note 결합) 가능 —
    # degraded note가 선두에 그대로 오는지로 검증(결합 형식은 별도 테스트가 고정)
    assert result["note"].startswith(_DEGRADED_NOTE_FALLBACK)
    assert "[degraded]" in result["note"]
    assert _RECALL_DIRECTIVE in result["note"]


def test_suggest_fallback_still_returns_candidates_not_withheld(mock_client):
    """v0.1.9(#1, M2 soft-gate 핵심 회귀): degraded여도 candidates를 보류하지 않고 그대로 반환."""
    result = asyncio.run(suggest_review_sources("특별평가"))
    assert result["keyword_source"] == "fallback"
    assert len(result["candidates"]) >= 1  # 보류(hard-gate) 아님 — M3 미채택 보증


def test_suggest_empty_note_is_degraded(mock_client):
    """v0.1.9(#1, A-3): 무키워드 early-return(후보 0건)에도 degraded 재호출 지시 note 부착."""
    result = asyncio.run(suggest_review_sources("abc 123 ???"))
    assert result["candidates"] == []
    assert result["note"] == _DEGRADED_NOTE_EMPTY
    assert "[degraded]" in result["note"]
    assert _RECALL_DIRECTIVE in result["note"]


def test_suggest_client_fallback_note_is_degraded(mock_client):
    """v0.1.9(#1, A-2): client+fallback(제공 keywords 0건→대체 검색)에도 degraded note 부착."""
    result = asyncio.run(
        suggest_review_sources("특별평가 절차", keywords=["절대로없는키워드zzz"])
    )
    assert result["keyword_source"] == "client+fallback"
    assert "note" in result
    assert _DEGRADED_NOTE_CLIENT_FB in result["note"]
    assert "[degraded]" in result["note"]


def test_suggest_client_keywords_no_degraded_note(mock_client):
    """v0.1.9(#1): 정상 client 경로는 degraded 신호를 붙이지 않음(불필요한 재호출 유도 방지)."""
    result = asyncio.run(suggest_review_sources("아무 상황 설명", keywords=["특별평가"]))
    assert result["keyword_source"] == "client"
    assert "[degraded]" not in result.get("note", "")


def test_suggest_degraded_note_contract_version_unchanged(mock_client):
    """suggest 응답에 현행 contract_version(0.7.0) 포함."""
    result = asyncio.run(suggest_review_sources("특별평가"))
    assert result["contract_version"] == "0.7.0"


def test_suggest_fallback_and_truncated_notes_space_joined(mock_client):
    """v0.2.2(④): fallback+truncated 결합 경로 전용 회귀 — degraded note 선두 + truncation 안내가
    단일 공백으로 결합(v0.1.9 라이브 확인 거동, 기존 테스트는 각 note 단독 경로만 커버)."""
    result = asyncio.run(suggest_review_sources("간접비 특별평가"))  # 무키워드 → fallback, 후보 cap 초과 → truncated
    assert result["keyword_source"] == "fallback"
    assert result["truncated"] is True
    note = result["note"]
    assert note.startswith(_DEGRADED_NOTE_FALLBACK + " ")  # degraded가 선두 + 단일 공백 결합
    assert _RECALL_DIRECTIVE in note                       # 재호출 지시 보존
    assert note.count("[degraded]") == 1                   # 마커 중복 없음
    assert "overflow_candidates" in note                   # truncation 안내(drill-down 지시) 보존
    assert len(note) > len(_DEGRADED_NOTE_FALLBACK)        # 두 안내가 모두 포함됨


# === B축: 출력 크기 상한 (v0.1.5) ===
def test_select_capped_candidates_under_max_returns_input():
    cands = [{"provision_id": f"p{i}", "rule_set_id": "rs", "matched_keywords": ["k"]} for i in range(5)]
    out = _select_capped_candidates(cands, ["k"], lambda c: 1)
    assert out == cands  # max_n 이하 — 그대로 반환


def test_select_capped_candidates_guarantees_each_document():
    """문서별 최소 1건 보장: 법률이 후보를 다수 차지해도 하위 문서(rsC·rsD) 누락 안 됨."""
    used = ["k0", "k1"]
    cands = []
    for i in range(10):
        cands.append({"provision_id": f"a{i:02d}", "rule_set_id": "rsA", "matched_keywords": ["k0"]})
    for i in range(5):
        cands.append({"provision_id": f"b{i:02d}", "rule_set_id": "rsB", "matched_keywords": ["k1"]})
    cands.append({"provision_id": "c00", "rule_set_id": "rsC", "matched_keywords": ["k1"]})
    cands.append({"provision_id": "d00", "rule_set_id": "rsD", "matched_keywords": []})  # priority 999
    rank_map = {"rsA": 1, "rsB": 2, "rsC": 3, "rsD": 4}
    rank_of = lambda c: rank_map[c["rule_set_id"]]
    capped = _select_capped_candidates(cands, used, rank_of)  # 17건 > 15
    assert len(capped) == 15
    pids = {c["provision_id"] for c in capped}
    assert "c00" in pids and "d00" in pids  # 단일 후보 하위 문서 보존
    ranks = [rank_of(c) for c in capped]
    assert ranks == sorted(ranks)  # 출력은 (rank, provision_id) 정렬


def test_select_capped_candidates_document_overflow():
    """매칭 문서가 max_n 초과면 위계 상위 문서만 남고 하위 문서는 탈락(전부 보장 불가)."""
    used = ["k"]
    cands = [{"provision_id": f"p{i:02d}", "rule_set_id": f"rs{i:02d}", "matched_keywords": ["k"]}
             for i in range(20)]
    rank_of = lambda c: int(c["rule_set_id"][2:]) + 1  # rs00->1 ... rs19->20
    capped = _select_capped_candidates(cands, used, rank_of)  # 문서 20개 > 15
    assert len(capped) == 15
    docs = {c["rule_set_id"] for c in capped}
    assert docs == {f"rs{i:02d}" for i in range(15)}  # 위계 상위 15개(rs00~rs14) 정확히, rs15~rs19 탈락


def test_shorten_snippet_boundary():
    """경계: ≤300 그대로, >300이면 말줄임표 포함 최종 300자."""
    assert _shorten_snippet("가" * 299) == "가" * 299
    assert _shorten_snippet("가" * 300) == "가" * 300       # 300 정확히는 미단축
    out = _shorten_snippet("가" * 301)
    assert len(out) == 300 and out.endswith("...")          # 301 → 297자 + "..."


def test_select_capped_candidates_prefers_title_match():
    """v0.1.7: 제목 매칭 후보가 match_count만 높은 무관 후보를 제치고 보존(같은 문서·낮은 pid여도)."""
    used = ["협약", "변경", "승인"]
    cands = [
        {"provision_id": f"law:1:JO{i:04d}", "rule_set_id": "rsA",
         "matched_keywords": ["협약", "변경", "승인"], "title": "무관 제목"}  # match_count 3, title_hits 0
        for i in range(18)
    ]
    cands.append({"provision_id": "law:1:JO9999", "rule_set_id": "rsA",
                  "matched_keywords": ["변경"], "title": "협약의 변경"})  # match_count 1, title_hits 1
    capped = _select_capped_candidates(cands, used, lambda c: 1)
    assert len(capped) == 15
    pids = {c["provision_id"] for c in capped}
    assert "law:1:JO9999" in pids  # title_hits 우선 → match_count·pid 불리해도 보존


def test_title_token_match_token_and_and_literal():
    """v0.1.7: 제목 매칭은 search_provision 의미 재사용 — 다중토큰 AND / 단일 리터럴."""
    assert _title_token_match("협약 변경", "연구개발과제협약의 변경 등") is True
    assert _title_token_match("협약 변경", "연구개발과제 협약 등") is False   # '변경' 없음
    assert _title_token_match("연구개발과제협약", "연구개발과제협약의 변경 등") is True
    assert _title_token_match("사전승인", "사전 승인 대상") is False           # 리터럴, 공백 불일치
    assert _title_token_match("사전 승인", "사전 승인 대상") is True            # 2토큰 AND
    assert _title_token_match("협약", "수익의 납부") is False
    assert _title_token_match("", "제목") is False


def test_title_hits_counts_distinct_origin():
    """v0.1.7: title_hits = 제목 매칭 origin 키워드 distinct 수(동의어 변형 미포함)."""
    c = {"title": "연구개발과제협약의 변경 등",
         "matched_keywords": ["협약 변경", "연구개발과제협약", "정부지원연구개발비"]}
    assert _title_hits(c) == 2
    c2 = {"title": "수익의 납부", "matched_keywords": ["협약 변경", "연구개발과제협약"]}
    assert _title_hits(c2) == 0
    assert _title_hits({"matched_keywords": ["협약"]}) == 0  # title 없음 방어
    assert _title_hits({"title": "협약의 변경", "matched_keywords": None}) == 0  # None 방어(내부 불변식 위반 입력)


def test_select_capped_tie_breaks_by_provision_id_not_priority():
    """v0.1.7: title_hits·match_count 동률이면 priority(키워드 순서)가 아니라 provision_id로 결정.

    제11조(협약, 뒤 키워드 매칭) vs 제33조(제재, 앞 키워드 매칭) — priority 제거로 낮은 번호(제11조)가 보존.
    """
    used = ["정부지원연구개발비", "협약 변경"]  # 정부지원연구개발비가 앞(idx0)
    cands = [
        {"provision_id": "law:283849:JO0033", "rule_set_id": "act",
         "matched_keywords": ["정부지원연구개발비"], "title": "제재처분의 절차"},
        {"provision_id": "law:283849:JO0011", "rule_set_id": "act",
         "matched_keywords": ["협약 변경"], "title": "연구개발과제 협약 등"},
    ]
    for i in range(20):
        cands.append({"provision_id": f"x:1:JO{i:04d}", "rule_set_id": "other",
                      "matched_keywords": ["정부지원연구개발비"], "title": "무관"})
    rank_of = lambda c: 1 if c["rule_set_id"] == "act" else 2
    capped = _select_capped_candidates(cands, used, rank_of)
    pids = {c["provision_id"] for c in capped}
    assert "law:283849:JO0011" in pids  # priority 제거 → pid tie-break(0011<0033)로 보존


def test_select_capped_no_score_field_leak():
    """v0.1.7: 내부 점수(title_hits 등)가 후보 dict에 누설되지 않음."""
    cands = [{"provision_id": f"p{i:02d}", "rule_set_id": "rs",
              "matched_keywords": ["k"], "title": "협약의 변경"} for i in range(20)]
    out = _select_capped_candidates(cands, ["k"], lambda c: 1)
    for c in out:
        assert set(c.keys()) <= {"provision_id", "rule_set_id", "matched_keywords", "title"}


def test_suggest_review_sources_caps_candidates(mock_client):
    """전체 후보가 상한 초과 시 returned=15·truncated=True·note 추가 (2키워드로 27후보 유도)."""
    result = asyncio.run(suggest_review_sources("간접비 특별평가", keywords=["간접비", "특별평가"]))
    assert result["total"] > 15
    assert result["returned"] == 15
    assert len(result["candidates"]) == 15
    assert result["truncated"] is True
    assert "note" in result
    assert len(result["recommended_review_order"]) >= 1  # review_order는 전체 기준 유지


def test_suggest_review_sources_snippet_truncated(mock_client):
    """반환 후보 snippet은 _SUGGEST_SNIPPET_MAX(최종 길이) 이하로 단축."""
    mock_client.get_law_detail.return_value["articles"][0]["조문내용"] = (
        "제15조(특별평가) " + ("특별평가 관련 본문 내용 " * 60)
    )
    result = asyncio.run(suggest_review_sources("특별평가", keywords=["특별평가"]))
    snippets = [c["snippet"] for c in result["candidates"]]
    assert snippets
    assert all(len(s) <= 300 for s in snippets)
    assert any(s.endswith("...") for s in snippets)


def test_suggest_review_sources_cap_fields_no_key_leak(mock_client):
    """cap/truncated/note/overflow 추가 후에도 키 누설 없음 (전체 응답 직렬화 검사)."""
    result = asyncio.run(suggest_review_sources("간접비", keywords=["간접비"]))
    assert _FAKE_KEY not in json.dumps(result, ensure_ascii=False)


# === overflow_candidates (v0.1.8) ===
def _ov_cand(pid, mk, title="제목", doc="문서", unit="JO0001", rsid="rs"):
    return {"provision_id": pid, "rule_set_id": rsid, "matched_keywords": mk,
            "title": title, "document_title": doc, "unit_id": unit}


def test_overflow_label_format():
    c = _ov_cand("admrul:1:JO0074", ["k"], title="사전 승인 절차",
                 doc="국가연구개발사업 연구개발비 사용 기준", unit="JO0074")
    assert _overflow_label(c) == "국가연구개발사업 연구개발비 사용 기준 제74조(사전 승인 절차)"
    c2 = _ov_cand("admrul:1:BP0001", ["k"], title="서식", doc="지침", unit="BP0001")
    assert _overflow_label(c2) == "지침 별표 1(서식)"
    c3 = {"provision_id": "law:1", "document_title": "혁신법", "title": "전체", "unit_id": None}
    assert _overflow_label(c3) == "혁신법 (전체)"   # document-level — unit 라벨 없음


def test_append_overflow_basic_shape_and_disjoint():
    candidates = [_ov_cand(f"x:1:JO{i:04d}", ["k"], unit=f"JO{i:04d}") for i in range(20)]
    capped = candidates[:15]
    resp = {"candidates": [{"provision_id": c["provision_id"]} for c in capped]}
    _append_overflow_candidates(resp, candidates, capped, lambda c: 1)
    assert isinstance(resp["overflow_candidates"], list) and resp["overflow_candidates"]
    capped_ids = {c["provision_id"] for c in capped}
    for it in resp["overflow_candidates"]:
        assert set(it.keys()) == {"provision_id", "label"}      # 제목(label)+provision_id만
        assert it["provision_id"] not in capped_ids             # cap과 disjoint
        assert isinstance(it["label"], str) and it["label"]
    assert resp["overflow_truncated"] is False                  # 5건 모두 수록(예산·cap 여유)


def test_append_overflow_relevance_order():
    """overflow 정렬 = _relevance_key (제목매칭 우선) — cap 선별과 동일 기준."""
    base = [_ov_cand(f"x:1:JO{i:04d}", ["k"], title="무관", unit=f"JO{i:04d}") for i in range(15)]
    hi = _ov_cand("x:1:JO9001", ["협약 변경"], title="협약의 변경", unit="JO9001")  # title_hits 1
    lo = _ov_cand("x:1:JO9002", ["k"], title="무관", unit="JO9002")                # title_hits 0
    candidates = base + [lo, hi]      # 17건, cap 앞 15
    capped = base
    resp = {"candidates": []}
    _append_overflow_candidates(resp, candidates, capped, lambda c: 1)
    ids = [it["provision_id"] for it in resp["overflow_candidates"]]
    assert ids.index("x:1:JO9001") < ids.index("x:1:JO9002")   # title_hits 높은 쪽이 선두


def test_append_overflow_cap_max():
    n = main_module._OVERFLOW_CANDIDATES_MAX
    candidates = [_ov_cand(f"x:1:JO{i:04d}", ["k"], unit=f"JO{i:04d}") for i in range(15 + n + 10)]
    capped = candidates[:15]
    resp = {"candidates": []}
    _append_overflow_candidates(resp, candidates, capped, lambda c: 1)
    assert len(resp["overflow_candidates"]) <= n
    assert resp["overflow_truncated"] is True                   # cap 초과분 누락


def test_append_overflow_char_budget_enforced():
    """outage 핵심: base 우선 + 전체 응답 ≤ _SUGGEST_RESPONSE_CHAR_BUDGET 강제, 초과분은 overflow_truncated."""
    budget = main_module._SUGGEST_RESPONSE_CHAR_BUDGET
    resp = {"candidates": [{"snippet": "가" * (budget - 300)}]}   # base를 예산 근처로
    overflow = [_ov_cand(f"x:1:JO{i:04d}", ["k"], title="긴제목" * 20, doc="문서" * 20,
                         unit=f"JO{i:04d}") for i in range(25)]
    candidates = [{"provision_id": "kept", "rule_set_id": "rs"}] + overflow
    capped = [{"provision_id": "kept", "rule_set_id": "rs"}]
    _append_overflow_candidates(resp, candidates, capped, lambda c: 1)
    assert len(json.dumps(resp, ensure_ascii=False)) <= budget   # 절대 예산 초과 안 함
    assert resp["overflow_truncated"] is True                    # 예산으로 일부 누락


def test_append_overflow_empty_when_none():
    candidates = [_ov_cand(f"x:1:JO{i:04d}", ["k"], unit=f"JO{i:04d}") for i in range(5)]
    capped = candidates                                          # 전부 cap 안 → overflow 없음
    resp = {"candidates": []}
    _append_overflow_candidates(resp, candidates, capped, lambda c: 1)
    assert resp["overflow_candidates"] == []
    assert resp["overflow_truncated"] is False


def test_append_overflow_base_over_budget_yields_empty():
    """v0.1.8 회귀(Blocking 2): base가 단독으로 예산 초과면 overflow는 한 건도 안 넣고(전체를 줄이지 않음),
    overflow가 있었으면 overflow_truncated=True. 예산이 'overflow 추가분 게이트'임을 고정."""
    budget = main_module._SUGGEST_RESPONSE_CHAR_BUDGET
    resp = {"question": "가" * (budget + 100)}                   # base 단독으로 예산 초과
    overflow = [_ov_cand(f"x:1:JO{i:04d}", ["k"], unit=f"JO{i:04d}") for i in range(3)]
    candidates = [{"provision_id": "kept", "rule_set_id": "rs"}] + overflow
    capped = [{"provision_id": "kept", "rule_set_id": "rs"}]
    _append_overflow_candidates(resp, candidates, capped, lambda c: 1)
    assert resp["overflow_candidates"] == []                     # 한 건도 못 넣음
    assert resp["overflow_truncated"] is True                    # overflow 존재했으나 전량 누락


def test_suggest_overflow_fields_via_mock(mock_client):
    """통합: suggest 응답에 overflow 필드 존재, truncated 시 candidates와 disjoint."""
    result = asyncio.run(suggest_review_sources("간접비 특별평가", keywords=["간접비", "특별평가"]))
    assert isinstance(result["overflow_candidates"], list)
    assert isinstance(result["overflow_truncated"], bool)
    if result["truncated"]:
        cand_ids = {c["provision_id"] for c in result["candidates"]}
        for it in result["overflow_candidates"]:
            assert set(it.keys()) == {"provision_id", "label"}
            assert it["provision_id"] not in cand_ids


# === B축 사후 리뷰 보강 (경계·결정성·방어·결합 경로) ===
def test_select_capped_candidates_exact_max_returns_input():
    """경계: 후보가 정확히 max_n(15)이면 그대로 반환(len <= max_n, cap 미발동)."""
    cands = [{"provision_id": f"p{i:02d}", "rule_set_id": "rs", "matched_keywords": ["k"]} for i in range(15)]
    out = _select_capped_candidates(cands, ["k"], lambda c: 1)
    assert out == cands
    assert len(out) == 15


def test_select_capped_candidates_just_over_max_drops_one():
    """경계: max_n+1(16)이면 위계 하위 1건만 탈락하여 15건."""
    cands = [{"provision_id": f"p{i:02d}", "rule_set_id": f"rs{i:02d}", "matched_keywords": ["k"]}
             for i in range(16)]
    out = _select_capped_candidates(cands, ["k"], lambda c: int(c["rule_set_id"][2:]))
    assert len(out) == 15
    docs = {c["rule_set_id"] for c in out}
    assert "rs15" not in docs  # rank 최하위(15) 탈락


def test_select_capped_candidates_rank_tie_overflow_deterministic():
    """rank 전부 동률 + 문서 초과여도 (rank, _priority, provision_id)로 완전 결정적 — 입력 순서 무관."""
    used = ["k"]
    cands = [{"provision_id": f"p{i:02d}", "rule_set_id": f"rs{i:02d}", "matched_keywords": ["k"]}
             for i in range(20)]
    rank_of = lambda c: 5  # 전부 동률
    out1 = _select_capped_candidates([dict(c) for c in cands], used, rank_of)
    out2 = _select_capped_candidates(list(reversed([dict(c) for c in cands])), used, rank_of)
    ids1 = [c["provision_id"] for c in out1]
    ids2 = [c["provision_id"] for c in out2]
    assert len(out1) == 15
    assert ids1 == ids2  # 입력 순서 뒤집어도 동일 = 결정적
    assert ids1 == [f"p{i:02d}" for i in range(15)]  # 최저 provision_id 15개 생존


def test_shorten_snippet_none_and_empty_safe():
    """방어(F3): snippet 값이 None·빈 문자열이어도 크래시 없이 ''."""
    assert _shorten_snippet(None) == ""
    assert _shorten_snippet("") == ""


def test_suggest_review_sources_truncated_fields_consistent(mock_client):
    """불변식: returned == min(total, 15), truncated == (total > 15), note 존재 == truncated."""
    result = asyncio.run(suggest_review_sources("간접비 특별평가", keywords=["간접비", "특별평가"]))
    assert result["returned"] == min(result["total"], 15)
    assert result["truncated"] is (result["total"] > 15)
    assert ("note" in result) is result["truncated"]


def test_suggest_review_sources_client_fallback_then_cap(mock_client):
    """결합 경로: client 키워드 0건 → 규칙추출 보강(client+fallback) → 보강 후보가 상한 초과 시 cap 동시 적용."""
    result = asyncio.run(
        suggest_review_sources("간접비 특별평가", keywords=["절대로없는키워드zzz"])
    )
    assert result["keyword_source"] == "client+fallback"
    assert result["total"] > 15
    assert result["returned"] == 15
    assert result["truncated"] is True
    assert "note" in result


# === list_rule_sets contract_version (보강) ===
def test_list_rule_sets_includes_contract_version(mock_client):
    result = asyncio.run(list_rule_sets())
    assert "contract_version" in result
    assert result["contract_version"] == "0.7.0"


# === _build_article_content  ===
def test_build_article_content_concatenates_hangs_and_hos():
    """다항조문 본문이 조문내용 + 항(항내용 + 호) 형태로 reconstruct되는지 검증.

    P0: 직전 buggy 상태는 조문내용(title repeat)만 반환하여 본문 누락.
    """
    import xml.etree.ElementTree as ET

    from korean_rnd_regs_mcp.live_api import _build_article_content

    xml = """
    <조문단위>
      <조문번호>15</조문번호>
      <조문제목>특별평가</조문제목>
      <조문내용>제15조(특별평가)</조문내용>
      <항>
        <항번호>①</항번호>
        <항내용>① 중앙행정기관의 장은 다음 각 호의 사유</항내용>
        <호>
          <호번호>1.</호번호>
          <호내용>1.  부정행위가 발생한 경우</호내용>
        </호>
        <호>
          <호번호>2.</호번호>
          <호내용>2.  참여제한이 확정된 경우</호내용>
        </호>
      </항>
      <항>
        <항번호>②</항번호>
        <항내용>② 연구개발기관은 다음 경우 요청</항내용>
      </항>
    </조문단위>
    """
    elem = ET.fromstring(xml)
    content = _build_article_content(elem)

    # 조문내용 + 두 항 + 호 모두 포함
    assert "제15조(특별평가)" in content
    assert "① 중앙행정기관" in content
    assert "1.  부정행위" in content
    assert "2.  참여제한" in content
    assert "② 연구개발기관" in content
    # 길이 sanity: 조문내용만일 때보다 충분히 길어짐 (조문내용=14자, 항·호 합치면 ≥80자)
    assert len(content) > 80


def test_build_article_content_short_article_returns_intro_only():
    """짧은 조문(항 없음)은 조문내용만 반환."""
    import xml.etree.ElementTree as ET

    from korean_rnd_regs_mcp.live_api import _build_article_content

    xml = """
    <조문단위>
      <조문번호>1</조문번호>
      <조문제목>목적</조문제목>
      <조문내용>제1조(목적) 이 법은 ... 함을 목적으로 한다.</조문내용>
    </조문단위>
    """
    elem = ET.fromstring(xml)
    assert _build_article_content(elem) == "제1조(목적) 이 법은 ... 함을 목적으로 한다."


# === live_api 보안 회귀 (Fix A 검증의 mock 버전) ===
def test_live_api_error_message_no_url_no_key(monkeypatch):
    """_request_with_retry는 ConnectionError 시 URL/key를 message에 포함하지 않음."""
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import LawApiClient, LawApiError, _request_with_retry

    class FakeConnError(requests_mod.exceptions.ConnectionError):
        def __str__(self):
            # 일부러 키·URL 포함된 message로 시뮬레이션
            return f"Connection failed to url: /lawSearch.do?OC={_FAKE_KEY}"

    def mock_get(*args, **kwargs):
        raise FakeConnError()

    monkeypatch.setattr(requests_mod, "get", mock_get)

    try:
        _request_with_retry("https://test.invalid", {"OC": _FAKE_KEY}, max_retries=1)
    except LawApiError as e:
        msg = str(e)
        assert _FAKE_KEY not in msg, f"키 누설: {msg}"
        assert "OC=" not in msg, f"OC= 누설: {msg}"
        assert "url:" not in msg.lower(), f"URL 누설: {msg}"
        assert "ConnectionError" in msg or "FakeConnError" in msg  # type 정보는 유지
    else:
        pytest.fail("LawApiError가 발생해야 함")


# === 회귀 (requests 예외 포괄 catch) ===
def test_live_api_handles_sslerror_without_url_leak(monkeypatch):
    """RequestException subclass 전체(SSLError·ChunkedEncodingError·InvalidURL 등)도 catch + redact."""
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import LawApiError, _request_with_retry

    class FakeSSLError(requests_mod.exceptions.SSLError):
        def __str__(self):
            return f"SSL handshake failed at https://test.invalid/lawSearch.do?OC={_FAKE_KEY}"

    monkeypatch.setattr(requests_mod, "get", lambda *a, **kw: (_ for _ in ()).throw(FakeSSLError()))

    with pytest.raises(LawApiError) as exc_info:
        _request_with_retry("https://test.invalid", {"OC": _FAKE_KEY}, max_retries=1)
    msg = str(exc_info.value)
    assert _FAKE_KEY not in msg, f"SSL error에서 키 누설: {msg}"
    assert "OC=" not in msg
    # type 정보(SSLError)는 trace에 유지
    assert "SSLError" in msg or "FakeSSLError" in msg


def test_request_with_retry_log_no_key_prefix(monkeypatch, caplog):
    """회귀(작업1 gap d): _request_with_retry 로그에 키 값·앞자리·OC= 미포함, type 이름만 기록."""
    import logging
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import LawApiError, _request_with_retry

    class FakeConnError(requests_mod.exceptions.ConnectionError):
        def __str__(self):
            return f"Connection failed: /lawSearch.do?OC={_FAKE_KEY}"

    monkeypatch.setattr(
        requests_mod, "get",
        lambda *a, **kw: (_ for _ in ()).throw(FakeConnError()),
    )
    with caplog.at_level(logging.DEBUG, logger="rnd-regs-mcp.live_api"):
        with pytest.raises(LawApiError):
            _request_with_retry("https://test.invalid", {"OC": _FAKE_KEY}, max_retries=1)
    assert _FAKE_KEY not in caplog.text, f"로그 키 누설: {caplog.text[:200]}"
    assert _FAKE_KEY[:6] not in caplog.text
    assert "OC=" not in caplog.text
    # type 이름은 로그에 유지됨 (진단 가능성)
    assert "ConnectionError" in caplog.text or "FakeConnError" in caplog.text


# === LIVE 검증: 회귀 (wrapper filter) ===
def test_get_law_detail_excludes_wrapper_elements(monkeypatch):
    """장/절 wrapper(조문여부='전문')는 articles에서 제외 — 동일 조문번호 collision 방어.

    LIVE 검증 발견: 혁신법 MST 283849 + 시행령 285767의 각 7개 조문번호에서 wrapper("제1장 총칙" 등)와
    실제 조문이 동일 조문번호로 중복 등장. 직전 buggy 상태에서는 get_provision_detail("law:283849:JO0001")이
    wrapper만 반환하고 실제 제1조(목적)는 못 받았음. 본 test는 fix 후 wrapper exclude 검증.
    """
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import LawApiClient

    fake_xml = """<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보>
    <법령ID>013774</법령ID>
    <법령명_한글>국가연구개발혁신법</법령명_한글>
    <법종구분>법률</법종구분>
    <소관부처>과학기술정보통신부</소관부처>
    <시행일자>20250228</시행일자>
    <공포일자>20240227</공포일자>
  </기본정보>
  <조문>
    <조문단위>
      <조문번호>1</조문번호>
      <조문여부>전문</조문여부>
      <조문내용>제1장 총칙</조문내용>
    </조문단위>
    <조문단위>
      <조문번호>1</조문번호>
      <조문여부>조문</조문여부>
      <조문제목>목적</조문제목>
      <조문내용>제1조(목적) 이 법은 국가연구개발사업의 추진 체제를 ...</조문내용>
    </조문단위>
    <조문단위>
      <조문번호>2</조문번호>
      <조문여부>조문</조문여부>
      <조문제목>정의</조문제목>
      <조문내용>제2조(정의) 이 법에서 사용하는 용어의 뜻은 ...</조문내용>
    </조문단위>
  </조문>
</법령>"""

    class FakeResponse:
        status_code = 200
        text = fake_xml
        headers = {"Content-Type": "application/xml"}

    monkeypatch.setattr(requests_mod, "get", lambda *a, **kw: FakeResponse())

    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    result = client.get_law_detail("283849")
    # wrapper("제1장 총칙") 제외 → 실제 조문 2개만
    assert len(result["articles"]) == 2, f"wrapper filter 실패: {result['articles']}"
    titles = [a["조문제목"] for a in result["articles"]]
    assert titles == ["목적", "정의"], f"제목 순서·내용 불일치: {titles}"
    # 첫 조문이 wrapper가 아닌 실제 제1조인지 — JO0001 검색 시 wrapper만 반환되던 buggy 동작 회귀
    first = result["articles"][0]
    assert first["조문번호"] == "1"
    assert "제1조(목적)" in first["조문내용"]
    assert "제1장 총칙" not in first["조문내용"]


def test_get_admin_rule_detail_flat_schema_fallback(monkeypatch):
    """평면 schema (root 직속 <조문내용>) 행정규칙도 articles로 정상 파싱.

    LIVE 검증: 동시수행 과제 수 제한(ID 2100000196149) + 연구노트 지침(ID 2100000207982)이
    <조문단위> wrapper 없이 root 직속 <조문내용> 평면 배치 사용. v0.1.0 publish에 본 schema 지원 추가.
    """
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import LawApiClient

    fake_xml = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService>
  <행정규칙기본정보>
    <행정규칙ID>flat_test</행정규칙ID>
    <행정규칙명>국가연구개발사업 동시수행 연구개발과제 수 제한 기준</행정규칙명>
    <소관부처명>과학기술정보통신부</소관부처명>
    <시행일자>20210101</시행일자>
  </행정규칙기본정보>
  <조문내용>제1조(목적) 이 기준은 「국가연구개발혁신법 시행령」 제64조에 따라 ...</조문내용>
  <조문내용>제2조(동시수행제한제외과제 알림 등) ① 중앙행정기관의 장은 ...</조문내용>
  <조문내용>제3조(동시수행가능과제수 확인 등) ① 연구자는 ...</조문내용>
</AdmRulService>"""

    class FakeResponse:
        status_code = 200
        text = fake_xml
        headers = {"Content-Type": "application/xml"}

    monkeypatch.setattr(requests_mod, "get", lambda *a, **kw: FakeResponse())

    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    result = client.get_admin_rule_detail("2100000196149")
    # 평면 schema fallback 작동 — 3개 조문 모두 파싱
    assert len(result["articles"]) == 3, f"평면 schema fallback 실패: {result['articles']}"
    titles = [a["조문제목"] for a in result["articles"]]
    assert titles == ["목적", "동시수행제한제외과제 알림 등", "동시수행가능과제수 확인 등"]
    # 조문번호 추출 정확성
    nos = [a["조문번호"] for a in result["articles"]]
    assert nos == ["1", "2", "3"]
    # 조문내용 verbatim 보존
    assert result["articles"][0]["조문내용"].startswith("제1조(목적)")
    # structured는 평면이라 paragraphs 빈 list
    assert result["articles"][0]["structured"]["paragraphs"] == []


def test_get_admin_rule_detail_excludes_wrapper_elements(monkeypatch):
    """행정규칙도 동일 wrapper filter 적용 (일관성)."""
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import LawApiClient

    fake_xml = """<?xml version="1.0" encoding="UTF-8"?>
<행정규칙>
  <기본정보>
    <행정규칙ID>abc</행정규칙ID>
    <행정규칙명>연구개발비 사용 기준</행정규칙명>
    <소관부처명>과학기술정보통신부</소관부처명>
    <시행일자>20240613</시행일자>
  </기본정보>
  <조문>
    <조문단위>
      <조문번호>1</조문번호>
      <조문여부>전문</조문여부>
      <조문내용>제1장 wrapper</조문내용>
    </조문단위>
    <조문단위>
      <조문번호>1</조문번호>
      <조문여부>조문</조문여부>
      <조문제목>목적</조문제목>
      <조문내용>제1조(목적) 본문</조문내용>
    </조문단위>
  </조문>
  <별표>
    <별표단위>
      <별표번호>1</별표번호>
      <별표제목>기준</별표제목>
      <별표내용>별표 본문</별표내용>
    </별표단위>
  </별표>
</행정규칙>"""

    class FakeResponse:
        status_code = 200
        text = fake_xml
        headers = {"Content-Type": "application/xml"}

    monkeypatch.setattr(requests_mod, "get", lambda *a, **kw: FakeResponse())

    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    result = client.get_admin_rule_detail("2100000278740")
    assert len(result["articles"]) == 1, f"wrapper filter 실패: {result['articles']}"
    assert result["articles"][0]["조문제목"] == "목적"
    assert len(result["annexes"]) == 1


# === search-first (resolve_latest_doc_id) 패턴 테스트 ===


def test_resolve_latest_doc_id_no_change():
    """manifest ID와 동일하면 is_updated=False."""
    from korean_rnd_regs_mcp.live_api import LawApiClient, SearchResult, DocumentRef
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    sr = SearchResult(total=1, page=1, page_size=5, items=[
        DocumentRef(doc_type="law", doc_id="283849", title="국가연구개발혁신법",
                    extra={"시행일자": "20250228"}),
    ])
    client.search_laws = MagicMock(return_value=sr)
    result = client.resolve_latest_doc_id("국가연구개발혁신법", "law", "283849")
    assert result.doc_id == "283849"
    assert result.is_updated is False


def test_resolve_latest_doc_id_detects_update():
    """검색 결과 ID가 manifest ID와 다르면 is_updated=True."""
    from korean_rnd_regs_mcp.live_api import LawApiClient, SearchResult, DocumentRef
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    sr = SearchResult(total=1, page=1, page_size=5, items=[
        DocumentRef(doc_type="admrul", doc_id="2100000999999",
                    title="국가연구개발사업 연구개발비 사용 기준",
                    extra={"시행일자": "20260311"}),
    ])
    client.search_admin_rules = MagicMock(return_value=sr)
    result = client.resolve_latest_doc_id(
        "국가연구개발사업 연구개발비 사용 기준", "admrul", "2100000278740",
    )
    assert result.doc_id == "2100000999999"
    assert result.is_updated is True
    assert result.effective_date == "2026-03-11"
    assert result.manifest_doc_id == "2100000278740"


def test_resolve_latest_doc_id_fallback_on_error():
    """검색 실패 시 manifest ID fallback."""
    from korean_rnd_regs_mcp.live_api import LawApiClient
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    client.search_laws = MagicMock(side_effect=LawApiError("parse_failed", "test"))
    result = client.resolve_latest_doc_id("국가연구개발혁신법", "law", "283849")
    assert result.doc_id == "283849"
    assert result.is_updated is False


def test_resolve_latest_doc_id_cache_hit():
    """두 번째 호출은 캐시에서 반환."""
    from korean_rnd_regs_mcp.live_api import LawApiClient, SearchResult, DocumentRef
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    sr = SearchResult(total=1, page=1, page_size=5, items=[
        DocumentRef(doc_type="law", doc_id="999999", title="국가연구개발혁신법",
                    extra={"시행일자": "20260506"}),
    ])
    client.search_laws = MagicMock(return_value=sr)
    r1 = client.resolve_latest_doc_id("국가연구개발혁신법", "law", "283849")
    r2 = client.resolve_latest_doc_id("국가연구개발혁신법", "law", "283849")
    assert r1 == r2
    assert client.search_laws.call_count == 1


# === v0.2.6: 소관부처(ministry) resolve 필터 ===


def test_ministry_matches_static_helper():
    """_ministry_matches — 콤마 분리 정확일치, substring 매칭 금지, 빈 want는 통과."""
    m = LawApiClient._ministry_matches
    assert m("산업통상부", "산업통상부") is True
    # 콤마 다부처 행(보안대책 9부처형) — 정확일치 원소 포함
    assert m("과학기술정보통신부", "과학기술정보통신부,교육부,기후에너지환경부") is True
    # substring 오탐 차단: "환경부"는 "기후에너지환경부"의 부분문자열이나 별개 부처
    assert m("환경부", "기후에너지환경부") is False
    # 빈 want → 필터 미적용(기존 거동)
    assert m("", "아무부처") is True
    assert m(None, "아무부처") is True


def test_resolve_ministry_filter_rejects_homonym_other_ministry():
    """동명 2부처 행에서 ministry 지정 시 자부처 행만 채택(타부처가 더 최신이어도). 기술료 통합요령 LIVE 오집 재현."""
    from korean_rnd_regs_mcp.live_api import SearchResult, DocumentRef
    sr = SearchResult(total=2, page=1, page_size=5, items=[
        DocumentRef(doc_type="admrul", doc_id="2100000257278",
                    title="기술료 징수 및 관리에 관한 통합요령",
                    extra={"시행일자": "20250407", "소관부처명": "산업통상부"}),
        DocumentRef(doc_type="admrul", doc_id="2100000274950",
                    title="기술료 징수 및 관리에 관한 통합요령",
                    extra={"시행일자": "20260129", "소관부처명": "기후에너지환경부"}),
    ])
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    client.search_admin_rules = MagicMock(return_value=sr)
    result = client.resolve_latest_doc_id(
        "기술료 징수 및 관리에 관한 통합요령", "admrul", "2100000257278", "산업통상부",
    )
    assert result.doc_id == "2100000257278"  # 산업부 건 — 기후부가 시행일 최신이어도
    # 대조: ministry 미지정이면 최신(기후부)으로 오집되는 종전 거동
    client2 = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    client2.search_admin_rules = MagicMock(return_value=sr)
    result2 = client2.resolve_latest_doc_id(
        "기술료 징수 및 관리에 관한 통합요령", "admrul", "2100000257278",
    )
    assert result2.doc_id == "2100000274950"


def test_resolve_ministry_no_match_falls_back_to_manifest():
    """ministry 일치 행 0건 → manifest fallback(is_updated=False, 가용성 유지)."""
    from korean_rnd_regs_mcp.live_api import SearchResult, DocumentRef
    sr = SearchResult(total=1, page=1, page_size=5, items=[
        DocumentRef(doc_type="admrul", doc_id="2100000274950",
                    title="기술료 징수 및 관리에 관한 통합요령",
                    extra={"시행일자": "20260129", "소관부처명": "기후에너지환경부"}),
    ])
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    client.search_admin_rules = MagicMock(return_value=sr)
    result = client.resolve_latest_doc_id(
        "기술료 징수 및 관리에 관한 통합요령", "admrul", "2100000257278", "산업통상부",
    )
    assert result.doc_id == "2100000257278"  # manifest fallback
    assert result.is_updated is False


def test_resolve_ministry_cache_key_separation():
    """동일 title·상이 ministry는 캐시 키가 분리되어 각각 검색(오집 24h 고착 방지)."""
    from korean_rnd_regs_mcp.live_api import SearchResult, DocumentRef
    sr = SearchResult(total=2, page=1, page_size=5, items=[
        DocumentRef(doc_type="admrul", doc_id="A",
                    title="기술료 징수 및 관리에 관한 통합요령",
                    extra={"시행일자": "20250407", "소관부처명": "산업통상부"}),
        DocumentRef(doc_type="admrul", doc_id="B",
                    title="기술료 징수 및 관리에 관한 통합요령",
                    extra={"시행일자": "20260129", "소관부처명": "기후에너지환경부"}),
    ])
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    client.search_admin_rules = MagicMock(return_value=sr)
    r_ind = client.resolve_latest_doc_id("기술료 징수 및 관리에 관한 통합요령", "admrul", "A", "산업통상부")
    r_cli = client.resolve_latest_doc_id("기술료 징수 및 관리에 관한 통합요령", "admrul", "A", "기후에너지환경부")
    assert r_ind.doc_id == "A"
    assert r_cli.doc_id == "B"
    assert client.search_admin_rules.call_count == 2  # 캐시 키 분리 → 각각 검색


def test_resolve_ministry_none_preserves_behavior():
    """ministry=None(기존 다수 규정)은 종전 거동 불변 — 단일 일치 행 채택."""
    from korean_rnd_regs_mcp.live_api import SearchResult, DocumentRef
    sr = SearchResult(total=1, page=1, page_size=5, items=[
        DocumentRef(doc_type="law", doc_id="270435",
                    title="국가연구개발사업 등의 성과평가 및 성과관리에 관한 법률 시행령",
                    extra={"시행일자": "20250401", "소관부처명": "과학기술정보통신부"}),
    ])
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    client.search_laws = MagicMock(return_value=sr)
    result = client.resolve_latest_doc_id(
        "국가연구개발사업 등의 성과평가 및 성과관리에 관한 법률 시행령", "law", "270435",
    )
    assert result.doc_id == "270435"


def test_search_provision_uses_resolved_id(mock_client):
    """search_provision이 resolved doc_id로 detail API를 호출하는지 검증."""
    mock_client.resolve_latest_doc_id.side_effect = lambda title, target, mid, ministry=None: ResolvedDocId(
        doc_id="NEW_ID" if mid == "283849" else mid,
        effective_date="2026-05-06" if mid == "283849" else "",
        is_updated=(mid == "283849"),
        manifest_doc_id=mid,
    )
    result = asyncio.run(search_provision("특별평가"))
    assert result["total"] >= 1
    for m in result["results"]:
        if m["rule_set_id"] == "innovation_act":
            assert "NEW_ID" in m["provision_id"]
            assert "revision_notice" in m
            assert "개정 반영" in m["revision_notice"]


def test_search_provision_revision_notice_absent_when_same(mock_client):
    """ID 변경 없으면 revision_notice 없음."""
    result = asyncio.run(search_provision("특별평가"))
    for m in result["results"]:
        assert "revision_notice" not in m


def test_search_provision_truncates_large_results(mock_client, monkeypatch):
    """_RESULTS_MAX 초과 시 truncated=True, returned < total."""
    monkeypatch.setattr(main_module, "_RESULTS_MAX", 2)
    result = asyncio.run(search_provision("특별평가"))
    assert result["total"] > 2
    assert result["returned"] == 2
    assert result["truncated"] is True
    assert len(result["results"]) == 2


def test_search_provision_no_truncation_when_under_limit(mock_client):
    """결과가 _RESULTS_MAX 이하면 truncated=False."""
    result = asyncio.run(search_provision("특별평가"))
    assert result["truncated"] is False
    assert result["returned"] == result["total"]


def test_get_provision_detail_uses_resolved_id(mock_client):
    """get_provision_detail이 resolved ID로 상세 조회."""
    mock_client.resolve_latest_doc_id.side_effect = lambda title, target, mid, ministry=None: ResolvedDocId(
        doc_id="NEW_MST" if mid == "283849" else mid,
        effective_date="2026-05-06" if mid == "283849" else "",
        is_updated=(mid == "283849"),
        manifest_doc_id=mid,
    )
    result = asyncio.run(get_provision_detail("law:283849:JO0015"))
    assert result.get("revision_notice")
    assert "개정 반영" in result["revision_notice"]
    assert result["effective_date"] == "2026-05-06"
    mock_client.get_law_detail.assert_called_with("NEW_MST")


def test_get_provision_detail_with_resolved_doc_id_in_provision_id(mock_client):
    """회귀: search_provision이 반환한 resolved doc_id로 get_provision_detail 호출 시 정상 동작."""
    mock_client.resolve_latest_doc_id.side_effect = lambda title, target, mid, ministry=None: ResolvedDocId(
        doc_id="NEW_MST" if mid == "283849" else mid,
        effective_date="2026-05-06" if mid == "283849" else "",
        is_updated=(mid == "283849"),
        manifest_doc_id=mid,
    )
    # NEW_MST는 manifest에 없지만, resolve fallback으로 innovation_act에 매칭되어야 함
    result = asyncio.run(get_provision_detail("law:NEW_MST:JO0015"))
    assert "errors" not in result or not result.get("errors")
    assert result.get("unit_type") == "article"
    assert result.get("title") == "특별평가"


def test_resolve_latest_doc_id_picks_latest_by_date():
    """여러 검색 결과 중 시행일자가 가장 최신인 문서를 선택."""
    from korean_rnd_regs_mcp.live_api import LawApiClient, SearchResult, DocumentRef
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    sr = SearchResult(total=2, page=1, page_size=5, items=[
        DocumentRef(doc_type="admrul", doc_id="OLD_ID",
                    title="국가연구개발사업 연구개발비 사용 기준",
                    extra={"시행일자": "20240613"}),
        DocumentRef(doc_type="admrul", doc_id="NEW_ID",
                    title="국가연구개발사업 연구개발비 사용 기준",
                    extra={"시행일자": "20260311"}),
    ])
    client.search_admin_rules = MagicMock(return_value=sr)
    result = client.resolve_latest_doc_id(
        "국가연구개발사업 연구개발비 사용 기준", "admrul", "OLD_ID",
    )
    assert result.doc_id == "NEW_ID"
    assert result.effective_date == "2026-03-11"


def test_resolve_latest_doc_id_no_title_match_falls_back():
    """검색 결과에 title이 일치하는 항목이 없으면 manifest ID fallback."""
    from korean_rnd_regs_mcp.live_api import LawApiClient, SearchResult, DocumentRef
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    sr = SearchResult(total=1, page=1, page_size=5, items=[
        DocumentRef(doc_type="law", doc_id="999999", title="다른 법률",
                    extra={"시행일자": "20260101"}),
    ])
    client.search_laws = MagicMock(return_value=sr)
    result = client.resolve_latest_doc_id("국가연구개발혁신법", "law", "283849")
    assert result.doc_id == "283849"
    assert result.is_updated is False


def test_resolve_latest_doc_id_failure_uses_short_ttl_cache():
    """Codex P0: transient 실패는 5분 캐시에 저장되어 빠르게 복구 가능."""
    from korean_rnd_regs_mcp.live_api import LawApiClient, SearchResult, DocumentRef
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})

    client.search_laws = MagicMock(side_effect=LawApiError("parse_failed", "transient"))
    r1 = client.resolve_latest_doc_id("국가연구개발혁신법", "law", "283849")
    assert r1.doc_id == "283849"
    assert r1.is_updated is False

    # failure 캐시에 저장됨 — success 캐시에는 없어야 함 (v0.2.6: 캐시 키 4-tuple, ministry None→"")
    cache_key = ("resolve", "law", "국가연구개발혁신법", "")
    assert cache_key not in client._id_resolution_cache
    assert cache_key in client._id_resolution_failure_cache

    # failure 캐시 수동 만료 후 성공 시 복구
    del client._id_resolution_failure_cache[cache_key]
    sr = SearchResult(total=1, page=1, page_size=5, items=[
        DocumentRef(doc_type="law", doc_id="NEW_MST", title="국가연구개발혁신법",
                    extra={"시행일자": "20260506"}),
    ])
    client.search_laws = MagicMock(return_value=sr)
    r2 = client.resolve_latest_doc_id("국가연구개발혁신법", "law", "283849")
    assert r2.doc_id == "NEW_MST"
    assert r2.is_updated is True


def test_resolve_latest_doc_id_middle_dot_normalization():
    """중간점 문자 차이(U+00B7 vs U+318D)가 있어도 title matching 성공."""
    from korean_rnd_regs_mcp.live_api import LawApiClient, SearchResult, DocumentRef
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    sr = SearchResult(total=1, page=1, page_size=5, items=[
        DocumentRef(doc_type="admrul", doc_id="NEW_ID",
                    title="국가연구개발 시설ㆍ장비의 관리 등에 관한 표준지침",
                    extra={"시행일자": "20260423"}),
    ])
    client.search_admin_rules = MagicMock(return_value=sr)
    result = client.resolve_latest_doc_id(
        "국가연구개발 시설·장비의 관리 등에 관한 표준지침", "admrul", "OLD_ID",
    )
    assert result.doc_id == "NEW_ID"
    assert result.is_updated is True


def test_resolve_no_key_leak(mock_client):
    """resolve 응답에 API key 미포함."""
    mock_client.resolve_latest_doc_id.side_effect = lambda title, target, mid, ministry=None: ResolvedDocId(
        doc_id="UPDATED_ID", effective_date="2026-01-01",
        is_updated=True, manifest_doc_id=mid,
    )
    result = asyncio.run(search_provision("특별평가"))
    response_str = json.dumps(result, ensure_ascii=False)
    assert _FAKE_KEY not in response_str


def test_suggest_review_sources_works_with_resolved_ids(mock_client):
    """suggest_review_sources가 resolved ID로도 정상 동작 (rule_set_id 기반 lookup)."""
    mock_client.resolve_latest_doc_id.side_effect = lambda title, target, mid, ministry=None: ResolvedDocId(
        doc_id="CHANGED_ID" if mid == "283849" else mid,
        effective_date="2026-05-06" if mid == "283849" else "",
        is_updated=(mid == "283849"),
        manifest_doc_id=mid,
    )
    result = asyncio.run(suggest_review_sources("특별평가 절차는 어떻게 되나요?"))
    assert result["total"] >= 1
    assert len(result["recommended_review_order"]) >= 1


# === 현행 시행일 정합성 (안정적 일련번호 행정규칙 개정 감지) 회귀 테스트 ===

def test_effective_date_and_revision_notice_helpers():
    """helper 4분기 lock: LIVE 우선 표시 + 날짜 차이 기반 개정 감지 + 오탐 방지."""
    from types import SimpleNamespace
    rs = SimpleNamespace(effective_date="2024-06-13", api_doc_id="X")

    # (1) LIVE 비어있음(resolve 실패) → manifest 표시, 개정 안내 없음
    r = ResolvedDocId(doc_id="X", effective_date="", is_updated=False, manifest_doc_id="X")
    assert _resolve_effective_date(rs, r) == "2024-06-13"
    assert _revision_notice(rs, r) is None

    # (2) LIVE == manifest → manifest 표시, 개정 안내 없음 (오탐 방지)
    r = ResolvedDocId(doc_id="X", effective_date="2024-06-13", is_updated=False, manifest_doc_id="X")
    assert _resolve_effective_date(rs, r) == "2024-06-13"
    assert _revision_notice(rs, r) is None

    # (3) 일련번호 불변 + LIVE 시행일 다름 → 연구개발비 사용 기준 버그 시나리오: 개정 감지
    r = ResolvedDocId(doc_id="X", effective_date="2026-05-06", is_updated=False, manifest_doc_id="X")
    assert _resolve_effective_date(rs, r) == "2026-05-06"
    notice = _revision_notice(rs, r)
    assert notice and "개정 반영" in notice

    # (4) doc_id 변경 → 개정 감지 (신규 ID 포함)
    r = ResolvedDocId(doc_id="Y", effective_date="2026-05-06", is_updated=True, manifest_doc_id="X")
    notice = _revision_notice(rs, r)
    assert notice and "개정 반영" in notice and "Y" in notice


def test_search_provision_detects_amendment_on_stable_serial(mock_client):
    """회귀: 일련번호 불변(is_updated=False)이라도 LIVE 시행일이 manifest와 다르면
    개정 감지 → revision_notice + LIVE effective_date 노출 (연구개발비 사용 기준 버그)."""
    mock_client.resolve_latest_doc_id.side_effect = lambda title, target, mid, ministry=None: ResolvedDocId(
        doc_id=mid,                   # 일련번호 불변
        effective_date="2099-12-31",  # 어떤 manifest 시행일과도 다른 LIVE 값
        is_updated=False,             # doc_id 안 바뀜 → 기존 신호로는 개정 미감지
        manifest_doc_id=mid,
    )
    result = asyncio.run(search_provision("특별평가"))
    assert result["total"] >= 1
    for m in result["results"]:
        assert m["effective_date"] == "2099-12-31"
        assert "revision_notice" in m
        assert "개정 반영" in m["revision_notice"]


def test_get_provision_detail_detects_amendment_on_stable_serial(mock_client):
    """회귀: get_provision_detail도 일련번호 불변 + LIVE 시행일 차이를 개정으로 감지."""
    mock_client.resolve_latest_doc_id.side_effect = lambda title, target, mid, ministry=None: ResolvedDocId(
        doc_id=mid, effective_date="2099-12-31", is_updated=False, manifest_doc_id=mid,
    )
    result = asyncio.run(get_provision_detail("law:283849:JO0015"))
    assert result["effective_date"] == "2099-12-31"
    assert result.get("revision_notice")
    assert "개정 반영" in result["revision_notice"]


# === v0.1.6: 검색 recall·관련도 개선 ===

# --- Pillar D: 조사 strip(의)·불용어 보강 ---
def test_strip_particle_strips_genitive_eui_on_long_compound():
    """v0.1.6: 긴 복합어 끝 속격 '의'는 strip하되, 짧은 명사(정의/협의)는 len-guard로 보존."""
    assert _strip_particle("주관연구개발기관의") == "주관연구개발기관"
    assert _strip_particle("기관의") == "기관"
    assert _strip_particle("정의") == "정의"   # 2자 — 잔여 1자 < 2 → 보존
    assert _strip_particle("협의") == "협의"   # 2자 — 보존
    assert _strip_particle("특별평가") == "특별평가"  # 회귀: '가' 미strip 유지


def test_extract_keywords_filters_new_stopwords():
    """v0.1.6: '일부/다른/해당' 등 노이즈 토큰 제외."""
    result = _extract_keywords("연구개발비 일부를 다른 기관으로 이관하는 해당 절차")
    assert "일부" not in result
    assert "다른" not in result
    assert "해당" not in result
    assert "연구개발비" in result


# --- Pillar B: 동의어 확장 (_build_search_terms) ---
def test_build_search_terms_expands_synonyms():
    from korean_rnd_regs_mcp.main import _build_search_terms

    pairs = _build_search_terms(["정출금"])
    terms = [t for t, _ in pairs]
    origins = {o for _, o in pairs}
    assert "정출금" in terms
    assert "정부지원연구개발비" in terms
    assert "출연금" in terms
    assert origins == {"정출금"}  # origin은 항상 사용자 키워드 (변형 N개로 부풀지 않음)


def test_build_search_terms_no_synonym_passthrough():
    from korean_rnd_regs_mcp.main import _build_search_terms

    assert _build_search_terms(["특별평가"]) == [("특별평가", "특별평가")]


def test_build_search_terms_caps_total():
    from korean_rnd_regs_mcp.main import _SUGGEST_SEARCH_TERMS_MAX, _build_search_terms

    pairs = _build_search_terms([f"키워드{i}" for i in range(30)])
    assert len(pairs) <= _SUGGEST_SEARCH_TERMS_MAX


def test_suggest_synonym_origin_not_leaked(mock_client):
    """동의어 변형이 응답 extracted_keywords에 누설되지 않고 origin만 표시."""
    result = asyncio.run(suggest_review_sources("정출금 이관", keywords=["정출금"]))
    assert result["extracted_keywords"] == ["정출금"]


def test_suggest_synonym_variant_match_records_origin(mock_client):
    """동의어 변형(정부지원연구개발비)으로 매칭돼도 matched_keywords는 origin(정출금)만 기록."""
    art = mock_client.get_law_detail.return_value["articles"][0]
    art["조문제목"] = "비목"
    art["조문내용"] = "제12조(비목) 정부지원연구개발비의 사용 용도 ..."
    result = asyncio.run(suggest_review_sources("정출금", keywords=["정출금"]))
    assert result["candidates"], "동의어 변형으로 매칭되어야 함"
    for c in result["candidates"]:
        assert c["matched_keywords"] == ["정출금"]


# --- Pillar C: 토큰 AND 매칭 ---
def test_search_provision_token_and_matches_split_phrase(mock_client):
    """'협약 변경'(띄어쓰기)이 원문 '협약의 변경'을 토큰 AND로 포착."""
    art = mock_client.get_law_detail.return_value["articles"][0]
    art["조문제목"] = "협약"
    art["조문내용"] = "제11조(협약 등) 협약의 변경이 필요한 경우 협의하여야 한다 ..."
    result = asyncio.run(search_provision("협약 변경"))
    assert result["total"] >= 1
    assert all(r["unit_type"] in ("article", "annex") for r in result["results"])


def test_search_provision_token_and_requires_all_tokens(mock_client):
    """AND 의미: '협약'만 있고 '변경'이 없으면 매칭 안 됨 (OR 아님)."""
    arts = mock_client.get_law_detail.return_value["articles"]
    arts[0]["조문제목"] = "협약"
    arts[0]["조문내용"] = "제11조(협약) 협약을 체결한다 ..."   # '변경' 없음
    arts[1]["조문제목"] = "기타"
    arts[1]["조문내용"] = "제21조(기타) 기타 사항 ..."
    # 별표(annex)에도 두 토큰 동시 등장 없게
    mock_client.get_admin_rule_detail.return_value["annexes"][0]["별표내용"] = "별표 본문"
    result = asyncio.run(search_provision("협약 변경"))
    assert result["total"] == 0


def test_search_provision_single_token_unchanged(mock_client):
    """단일 토큰 query는 종전 부분문자열 매칭과 동일 (회귀)."""
    result = asyncio.run(search_provision("특별평가"))
    jo0015 = [r for r in result["results"] if r["unit_id"] == "JO0015"]
    assert len(jo0015) >= 1


# --- Pillar A: 관련도(매칭 키워드 수) 우선 cap 선별 ---
def test_select_capped_candidates_relevance_beats_position():
    """v0.1.6: 매칭 키워드 수가 많은 후보가 위계·pid가 불리해도 cap에서 생존."""
    used = ["k0", "k1", "k2"]
    # 단일 문서(rsA, rank1): 다중매칭 1건(pid 최댓값) + 단일매칭 15건
    cands = [{"provision_id": "zzz_high", "rule_set_id": "rsA",
              "matched_keywords": ["k0", "k1", "k2"]}]
    for i in range(15):
        cands.append({"provision_id": f"a{i:02d}", "rule_set_id": "rsA",
                      "matched_keywords": ["k0"]})
    out = _select_capped_candidates(cands, used, lambda c: 1)  # 16 > 15
    pids = {c["provision_id"] for c in out}
    assert len(out) == 15
    assert "zzz_high" in pids        # 3개 매칭 → 관련도 우선 생존
    assert "a14" not in pids         # 단일매칭 중 pid 최댓값 1건이 대신 탈락


def test_select_capped_candidates_relevance_tie_preserves_existing_order():
    """관련도 동률(모두 1매칭)이면 종전 (위계, pid) 선별과 동일 — 회귀."""
    cands = [{"provision_id": f"p{i:02d}", "rule_set_id": f"rs{i:02d}",
              "matched_keywords": ["k"]} for i in range(20)]
    out = _select_capped_candidates(cands, ["k"], lambda c: int(c["rule_set_id"][2:]) + 1)
    docs = {c["rule_set_id"] for c in out}
    assert docs == {f"rs{i:02d}" for i in range(15)}


# --- S1 회귀수정: '단어+한자리숫자' query는 리터럴 (토큰 과확장+truncation 유실 방지) ---
def test_search_provision_word_plus_digit_uses_literal(mock_client):
    """'별표 1'은 '별표' 1토큰으로 과확장하지 않고 리터럴 매칭 — '별표 5'만 있는 조문은 제외."""
    arts = mock_client.get_law_detail.return_value["articles"]
    arts[0]["조문제목"] = "별표 인용"
    arts[0]["조문내용"] = "제15조 별표 1에 따른 기준을 적용한다"   # '별표 1' 리터럴 포함
    arts[1]["조문제목"] = "다른 별표"
    arts[1]["조문내용"] = "제21조 별표 5에 따른다"                # '별표' 있으나 '별표 1' 아님
    mock_client.get_admin_rule_detail.return_value["annexes"][0]["별표내용"] = "별표 3 양식"
    result = asyncio.run(search_provision("별표 1"))
    ids = {r["unit_id"] for r in result["results"]}
    assert "JO0015" in ids, "리터럴 '별표 1' 포함 조문은 매칭돼야"
    assert "JO0021" not in ids, "'별표 5'만 있는 조문은 매칭 안 돼야 (과확장 방지)"


def test_search_provision_multitoken_still_and(mock_client):
    """'단어+단어'(둘 다 2자 이상)는 여전히 토큰 AND — S1 수정이 다중토큰을 안 깸."""
    arts = mock_client.get_law_detail.return_value["articles"]
    arts[0]["조문제목"] = "협약"
    arts[0]["조문내용"] = "제15조 협약의 변경 절차"
    result = asyncio.run(search_provision("협약 변경"))
    assert any(r["unit_id"] == "JO0015" for r in result["results"])


# === v0.2: 법령 별표 지원 (size-tiered + verbatim 정확성 가드) ===
def _fake_rs(title="국가연구개발혁신법 시행령",
             source_url="https://www.law.go.kr/법령/국가연구개발혁신법시행령",
             known=("기존 제약",)):
    return types.SimpleNamespace(title=title, source_url=source_url,
                                 known_limitations=list(known))


def test_build_annex_detail_small_returns_full_verbatim():
    """소형 별표 → 전문 verbatim(plain_text_verbatim), 인용 허용, 첨부 절대 URL."""
    ann = {"별표번호": "1", "별표제목": "정부지원 지원기준",
           "별표내용": "중소기업 75% 이하 / 중견기업 70% 이하 / 대기업 50% 이하",
           "별표서식파일링크": "/LSW/flDownload.do?flSeq=1"}
    resp = main_module._build_annex_detail("law:285767:BP0001", "BP0001", _fake_rs(), ann, "20260506")
    assert resp["unit_type"] == "annex"
    assert resp["content_format"] == "plain_text_verbatim"
    assert resp["content_available"] is True
    assert resp["verbatim_quote_allowed"] is True
    assert "75%" in resp["content"]
    assert resp["attached_file_url"].startswith("https://")


def test_build_annex_detail_oversized_returns_pointer_no_body():
    """대용량 별표 → 본문 미수록 oversized_pointer, 인용 금지, 원문 일부도 미포함."""
    big = "구분\t정부지원\t기관부담\n" * 3000
    ann = {"별표번호": "2", "별표제목": "연구개발비 사용용도", "별표내용": big,
           "별표서식파일링크": "https://www.law.go.kr/x.hwp"}
    resp = main_module._build_annex_detail("law:285767:BP0002", "BP0002", _fake_rs(), ann, "20260506")
    assert resp["content_format"] == "oversized_pointer"
    assert resp["content_available"] is False
    assert resp["verbatim_quote_allowed"] is False
    assert resp["is_complete"] is False
    assert resp["omitted_char_count"] == len(big.strip())   # content는 strip 후 길이
    assert big[:50] not in resp["content"]   # 본문(표)은 미수록
    assert "인용" in resp["content"]            # 안내 텍스트 + 인용 금지


def test_build_annex_detail_oversized_response_within_budget():
    """대용량 별표라도 최종 직렬화 응답이 예산(16k char)을 넘지 않음 (truncation 방지)."""
    big = "행 데이터 값 " * 6000
    ann = {"별표번호": "7", "별표제목": "제재부가금 처분기준", "별표내용": big, "별표서식파일링크": ""}
    resp = main_module._build_annex_detail("law:285767:BP0007", "BP0007", _fake_rs(), ann, "20260506")
    assert len(json.dumps(resp, ensure_ascii=False)) <= main_module._ANNEX_DETAIL_CHAR_BUDGET


def test_build_annex_detail_external_file_only():
    """본문 텍스트 없음 + 서식파일 → external_file_only, 인용 금지."""
    ann = {"별표번호": "9", "별표제목": "서식", "별표내용": "",
           "별표서식파일링크": "/LSW/flDownload.do?flSeq=9"}
    resp = main_module._build_annex_detail("law:285767:BP0009", "BP0009", _fake_rs(), ann, "20260506")
    assert resp["content_format"] == "external_file_only"
    assert resp["content_available"] is False
    assert resp["verbatim_quote_allowed"] is False
    assert resp["attached_file_url"].startswith("https://")


def test_build_annex_detail_deleted_stub():
    """삭제 stub → annex_status=deleted_stub + 경고(활성 규정 오인 방지)."""
    ann = {"별표번호": "3", "별표제목": "", "별표내용": "[별표 3] 삭제 <2022.2.28>",
           "별표서식파일링크": ""}
    resp = main_module._build_annex_detail("law:285767:BP0003", "BP0003", _fake_rs(), ann, "20260506")
    assert resp.get("annex_status") == "deleted_stub"
    assert resp["content_format"] == "plain_text_verbatim"
    assert any("삭제" in w for w in resp["warnings"])


def test_annex_snippet_has_marker_and_line_boundary():
    """별표 스니펫 — 발췌 마커 + 개행 경계 절단(공백표 행 중간 절단 방지)."""
    content = "\n".join(f"행{i}\t값{i}" for i in range(2000))
    snip = main_module._annex_snippet(content, ["행1000"])
    assert "발췌" in snip
    assert len(snip) <= main_module._SNIPPET_MAX
    body_lines = [ln for ln in snip.split("\n") if "\t" in ln]
    assert body_lines and all(ln.count("\t") == 1 for ln in body_lines)


def test_get_provision_detail_law_annex_returns_content(mock_client):
    """v0.2: 법령(시행령) 별표 BP 조회 — annexes 반환 시 size-tiered content_format 포함."""
    base = mock_client.get_law_detail.return_value
    mock_client.get_law_detail.return_value = {
        **base,
        "annexes": [{"별표번호": "1", "별표제목": "지원기준",
                     "별표내용": "중소기업 75% 이하", "별표서식파일링크": ""}],
        "annex_parse_error": None,
    }
    result = asyncio.run(get_provision_detail("law:285767:BP0001"))
    assert result["unit_type"] == "annex"
    assert result["content_format"] == "plain_text_verbatim"
    assert "75%" in result["content"]


def test_get_provision_detail_law_annex_parse_failure_surfaced(mock_client):
    """별표 파싱 실패 시 not_found가 아니라 annex_unavailable_parse_failed로 표면화."""
    base = mock_client.get_law_detail.return_value
    mock_client.get_law_detail.return_value = {
        **base, "annexes": [], "annex_parse_error": "ParseError",
    }
    result = asyncio.run(get_provision_detail("law:285767:BP0001"))
    assert "errors" in result
    assert result["errors"][0]["code"] == "annex_unavailable_parse_failed"


def test_search_provision_surfaces_annex_parse_error(mock_client):
    """search_provision: 법령 별표 파싱 실패를 errors에 annex_parse_failed로 노출."""
    base = mock_client.get_law_detail.return_value
    mock_client.get_law_detail.return_value = {
        **base, "annexes": [], "annex_parse_error": "ParseError",
    }
    result = asyncio.run(search_provision("특별평가"))
    codes = {e.get("code") for e in result.get("errors", [])}
    assert "annex_parse_failed" in codes


def test_annex_snippet_single_long_line_truncates_with_indicator():
    """리뷰 보강: 개행 없는 장문 별표내용 → 마커 + char 안전 절단 + 생략표시(…), max_len 준수."""
    content = "정부지원율 " + "9" * 5000  # 개행 없음(sparse)
    snip = main_module._annex_snippet(content, ["정부지원율"])
    assert "발췌" in snip
    assert snip.endswith("…")
    assert len(snip) <= main_module._SNIPPET_MAX


def test_build_annex_detail_both_empty_is_external_not_empty_verbatim():
    """리뷰 보강: 본문·서식파일 모두 빈 별표 → 빈 verbatim 오인이 아니라 external_file_only."""
    ann = {"별표번호": "5", "별표제목": "", "별표내용": "", "별표서식파일링크": ""}
    resp = main_module._build_annex_detail("law:285767:BP0005", "BP0005", _fake_rs(), ann, "20260506")
    assert resp["content_format"] == "external_file_only"
    assert resp["content_available"] is False
    assert resp["verbatim_quote_allowed"] is False


def test_build_annex_detail_active_annex_with_delete_verb_not_flagged():
    """리뷰 보강: 짧은 활성 별표가 '삭제' 동사를 포함해도(개정표기 '<' 없음) deleted_stub 오탐 안 함."""
    ann = {"별표번호": "4", "별표제목": "처분기준",
           "별표내용": "위반 시 등록을 삭제한다", "별표서식파일링크": ""}
    resp = main_module._build_annex_detail("law:285767:BP0004", "BP0004", _fake_rs(), ann, "20260506")
    assert resp.get("annex_status") != "deleted_stub"
    assert resp["content_format"] == "plain_text_verbatim"


# === v0.2.1: 별표 발견성·정확 선택 강화 (가지별표·별지 구분·doc-level 목록·hints·alias) ===


def test_annex_unit_id_and_kind_helpers():
    """가지 00·키 부재 → 기존 4자리 BP 불변(하위호환), 가지 != 0 → 6자리. 별지·서식 노출 제외."""
    assert main_module._annex_unit_id({"별표번호": "1", "별표가지번호": "00"}) == "BP0001"
    assert main_module._annex_unit_id({"별표번호": "1"}) == "BP0001"  # mock·키 부재 호환
    assert main_module._annex_unit_id({"별표번호": "1", "별표가지번호": "02"}) == "BP000102"
    assert main_module._annex_unit_id({"별표번호": "비고"}) is None
    assert main_module._is_annex_kind({"별표구분": "별표"}) is True
    assert main_module._is_annex_kind({}) is True  # 키 부재(mock)는 별표 간주
    assert main_module._is_annex_kind({"별표구분": "별지"}) is False
    assert main_module._is_annex_kind({"별표구분": "서식"}) is False


def test_dependent_article_hints_extraction():
    """B: 제목의 조문 참조 전건 추출 — 가지조문·항·다중 참조, 무참조는 빈 list."""
    f = main_module._dependent_article_hints
    assert f("정부지원연구개발비의 지원기준(제19조제3항 관련)") == ["제19조제3항"]
    assert f("이행강제금의 부과기준(제17조의3 관련)") == ["제17조의3"]
    assert f("기준(제59조제1항 및 제60조제2항 관련)") == ["제59조제1항", "제60조제2항"]
    assert f("삭제 <2016.1.22.>") == []


def test_is_deleted_annex_title():
    """deleted 제목 술어 — law형 '삭제 <날짜>'·admrul형 '삭제' 한정, '삭제○○' 활성 제목 오탐 방지(R2)."""
    f = main_module._is_deleted_annex_title
    assert f("삭제") is True
    assert f("삭제 <2016.1.22.>") is True
    assert f("삭제기준(제30조 관련)") is False
    assert f("과태료의 부과기준(제30조 관련)") is False


def test_get_provision_detail_branch_annex_strict_match(mock_client):
    """D: 동일 번호의 삭제 본별표(가지00)+활성 가지별표(가지02) 공존 —
    BP0001=deleted_stub, BP000102=활성 본문 (엄격 매칭, 첫-일치 오도달 제거)."""
    base = mock_client.get_law_detail.return_value
    mock_client.get_law_detail.return_value = {
        **base,
        "annexes": [
            {"별표번호": "1", "별표가지번호": "00", "별표구분": "별표",
             "별표제목": "삭제 <2016.1.22.>", "별표내용": "[별표 1] 삭제 <2016.1.22.>",
             "별표서식파일링크": ""},
            {"별표번호": "1", "별표가지번호": "02", "별표구분": "별표",
             "별표제목": "이행강제금의 부과기준(제17조의3 관련)",
             "별표내용": "이행강제금 부과기준 본문", "별표서식파일링크": ""},
        ],
        "annex_parse_error": None,
    }
    stub = asyncio.run(get_provision_detail("law:285767:BP0001"))
    assert stub.get("annex_status") == "deleted_stub"
    active = asyncio.run(get_provision_detail("law:285767:BP000102"))
    assert active.get("annex_status") != "deleted_stub"
    assert "이행강제금" in active["content"]
    assert active["dependent_article_hints"] == ["제17조의3"]
    assert "미검증" in active["dependent_article_hints_note"]


def test_get_provision_detail_bp_ignores_forms(mock_client):
    """D: 별지(구분=별지)는 BP 매칭 제외 — 동번호 별표가 반환됨(오도달 버그 수정)."""
    base = mock_client.get_law_detail.return_value
    mock_client.get_law_detail.return_value = {
        **base,
        "annexes": [
            {"별표번호": "1", "별표가지번호": "00", "별표구분": "별지",
             "별표제목": "신청서", "별표내용": "별지 서식 본문", "별표서식파일링크": ""},
            {"별표번호": "1", "별표가지번호": "00", "별표구분": "별표",
             "별표제목": "지원기준(제19조 관련)", "별표내용": "지원 비율 75",
             "별표서식파일링크": ""},
        ],
        "annex_parse_error": None,
    }
    result = asyncio.run(get_provision_detail("law:285767:BP0001"))
    assert "지원 비율" in result["content"]


def test_search_provision_emits_branch_annex_and_skips_forms(mock_client):
    """D: search — 가지별표는 6자리 BP id로 emit, 별지·서식은 미노출."""
    base = mock_client.get_law_detail.return_value
    mock_client.get_law_detail.return_value = {
        **base,
        "annexes": [
            {"별표번호": "1", "별표가지번호": "02", "별표구분": "별표",
             "별표제목": "특수기준", "별표내용": "특별평가 특수기준 본문",
             "별표서식파일링크": ""},
            {"별표번호": "3", "별표가지번호": "00", "별표구분": "별지",
             "별표제목": "특수신청서식", "별표내용": "특별평가 신청 서식 본문",
             "별표서식파일링크": ""},
        ],
        "annex_parse_error": None,
    }
    result = asyncio.run(search_provision("특별평가"))
    annex_results = [r for r in result["results"] if r.get("unit_type") == "annex"]
    annex_ids = [r["provision_id"] for r in annex_results]
    assert any(pid.endswith("BP000102") for pid in annex_ids)
    assert not any("신청서식" in r.get("title", "") for r in annex_results)


def test_doc_level_annexes_listing(mock_client):
    """A: document-level — annexes 목록(별표 한정·본문 미포함)·count_by_kind·deleted·가지 id·중복 0."""
    base = mock_client.get_law_detail.return_value
    mock_client.get_law_detail.return_value = {
        **base,
        "annexes": [
            {"별표번호": "1", "별표가지번호": "00", "별표구분": "별표",
             "별표제목": "삭제 <2016.1.22.>", "별표내용": "[별표 1] 삭제 <2016.1.22.>",
             "별표서식파일링크": ""},
            {"별표번호": "1", "별표가지번호": "02", "별표구분": "별표",
             "별표제목": "이행강제금의 부과기준(제17조의3 관련)", "별표내용": "본문",
             "별표서식파일링크": ""},
            {"별표번호": "1", "별표가지번호": "00", "별표구분": "별지",
             "별표제목": "신청서", "별표내용": "서식", "별표서식파일링크": ""},
        ],
        "annex_parse_error": None,
    }
    result = asyncio.run(get_provision_detail("law:285767"))
    assert result["annexes_count"] == 3  # 전건 집계 — 하위호환 유지
    assert result["annexes_count_by_kind"] == {"별표": 2, "별지": 1}
    listed = result["annexes"]
    assert [a["provision_id"] for a in listed] == ["law:285767:BP0001", "law:285767:BP000102"]
    assert listed[0]["deleted"] is True
    assert listed[1]["label"] == "별표 1의2"
    assert listed[1]["dependent_article_hints"] == ["제17조의3"]
    assert all("content" not in a and "별표내용" not in a for a in listed)  # 본문 미포함


def test_doc_level_annex_parse_error_honesty(mock_client):
    """G: law 별표 파싱 실패 시 doc-level이 annexes_count=0으로 '별표 없음' 위장하지 않음."""
    base = mock_client.get_law_detail.return_value
    mock_client.get_law_detail.return_value = {
        **base, "annexes": [], "annex_parse_error": "ParseError",
    }
    result = asyncio.run(get_provision_detail("law:285767"))
    assert result["annexes_unavailable"] is True
    assert result["annex_parse_error"] == "ParseError"
    assert any("별표 파싱 실패" in w for w in result["warnings"])


def test_build_annex_detail_admrul_deleted_title_flagged():
    """admrul형 삭제 별표(content '<삭 제>' 공백형·제목 '삭제') → 제목 보조 판정으로 deleted_stub
    (doc-level deleted 표시와 상세 분류 정합 — content 술어 단독으로는 전건 미탐)."""
    ann = {"별표번호": "4", "별표제목": "삭제",
           "별표내용": "■ 국가연구개발사업 연구개발비 사용 기준 [별표 4]  \n\n\n\n<삭 제>",
           "별표서식파일링크": ""}
    resp = main_module._build_annex_detail(
        "admrul:2100000278740:BP0004", "BP0004", _fake_rs(), ann, "20260506")
    assert resp.get("annex_status") == "deleted_stub"


def test_build_search_terms_alias_one_way():
    """F: 현장어 alias 입력 → 정식어 확장 / 정식어 입력 → alias 미확장(역방향 차단, cap 보호)."""
    pairs = main_module._build_search_terms(["정부출연연구비"])
    terms = [t for t, _ in pairs]
    assert "정부지원연구개발비" in terms
    assert "출연금" in terms
    assert "정부출연금" in terms
    assert {o for _, o in pairs} == {"정부출연연구비"}
    reverse_terms = [t for t, _ in main_module._build_search_terms(["정부지원연구개발비"])]
    for alias in ("정부출연연구비", "정출연연구비", "출연연구비"):
        assert alias not in reverse_terms


def test_law_detail_annex_title_unescaped_and_branch_captured(monkeypatch):
    """E+D(live_api): CDATA 사전 이스케이프 제목 unescape(단일 관문) + 가지번호·구분 캡처 +
    bare '&'(R&D) 과해소 없음. 네트워크 없이 로컬 XML."""
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import LawApiClient

    fake_xml = """<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <기본정보>
    <법령ID>9999</법령ID>
    <법령명_한글>테스트 시행령</법령명_한글>
    <시행일자>20260101</시행일자>
  </기본정보>
  <조문>
    <조문단위>
      <조문번호>1</조문번호>
      <조문여부>조문</조문여부>
      <조문제목>목적</조문제목>
      <조문내용>제1조(목적) 본문</조문내용>
    </조문단위>
  </조문>
  <별표>
    <별표단위>
      <별표번호>0001</별표번호>
      <별표가지번호>02</별표가지번호>
      <별표구분>별표</별표구분>
      <별표제목><![CDATA[삭제 &lt;2021. 1. 19.&gt;]]></별표제목>
      <별표내용><![CDATA[[별표 1의2] 삭제 <2021. 1. 19.>]]></별표내용>
    </별표단위>
    <별표단위>
      <별표번호>0002</별표번호>
      <별표가지번호>00</별표가지번호>
      <별표구분>별표</별표구분>
      <별표제목><![CDATA[R&D 수당 기준(제25조 관련)]]></별표제목>
      <별표내용>본문</별표내용>
    </별표단위>
  </별표>
</법령>"""

    class FakeResponse:
        status_code = 200
        text = fake_xml
        headers = {"Content-Type": "application/xml"}

    monkeypatch.setattr(requests_mod, "get", lambda *a, **kw: FakeResponse())
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    result = client.get_law_detail("9999")
    ann1, ann2 = result["annexes"]
    assert ann1["별표제목"] == "삭제 <2021. 1. 19.>"  # 이중 이스케이프 해소
    assert ann1["별표가지번호"] == "02"
    assert ann1["별표구분"] == "별표"
    assert ann2["별표제목"] == "R&D 수당 기준(제25조 관련)"  # bare '&' 불변


def test_admrul_detail_annex_fields_captured_and_title_unescaped(monkeypatch):
    """v0.2.2(④ 회귀): get_admin_rule_detail도 v0.2.1 필드(별표가지번호·별표구분) 캡처 +
    제목 html.unescape 단일 관문 + bare '&' 과해소 없음 + 별지도 파서 층에서는 캡처(필터는 main.py 책임).
    law 전례(test_law_detail_annex_title_unescaped_and_branch_captured)의 admrul 대응 —
    조문 0개 + 별표만 구조(사용기준형)에서 not_found 미발화도 함께 고정. 네트워크 없이 로컬 XML."""
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import LawApiClient

    fake_xml = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService>
  <행정규칙ID>5555</행정규칙ID>
  <행정규칙명>테스트 사용 기준</행정규칙명>
  <소관부처명>과학기술정보통신부</소관부처명>
  <시행일자>20260506</시행일자>
  <별표>
    <별표단위>
      <별표번호>0004</별표번호>
      <별표가지번호>00</별표가지번호>
      <별표구분>별표</별표구분>
      <별표제목><![CDATA[삭제 &lt;2021. 1. 19.&gt;]]></별표제목>
      <별표내용><![CDATA[■ 테스트 사용 기준 [별표 4]  <삭 제>]]></별표내용>
      <별표서식파일링크>/LSW/flDownload.do?flSeq=1</별표서식파일링크>
    </별표단위>
    <별표단위>
      <별표번호>0001</별표번호>
      <별표가지번호>02</별표가지번호>
      <별표구분>별표</별표구분>
      <별표제목><![CDATA[R&D 수당 계상기준(제74조 관련)]]></별표제목>
      <별표내용>수당 본문</별표내용>
      <별표서식파일링크></별표서식파일링크>
    </별표단위>
    <별표단위>
      <별표번호>0001</별표번호>
      <별표가지번호>00</별표가지번호>
      <별표구분>별지</별표구분>
      <별표제목>신청서 서식</별표제목>
      <별표내용>별지 본문</별표내용>
      <별표서식파일링크>/LSW/flDownload.do?flSeq=2</별표서식파일링크>
    </별표단위>
  </별표>
</AdmRulService>"""

    class FakeResponse:
        status_code = 200
        text = fake_xml
        headers = {"Content-Type": "application/xml"}

    monkeypatch.setattr(requests_mod, "get", lambda *a, **kw: FakeResponse())
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    result = client.get_admin_rule_detail("5555")
    assert result["articles"] == []                        # 조문 0 + 별표만 → not_found 아님
    deleted, branch, form = result["annexes"]
    assert deleted["별표제목"] == "삭제 <2021. 1. 19.>"    # CDATA 사전 이스케이프 해소(1회)
    assert deleted["별표가지번호"] == "00"
    assert deleted["별표구분"] == "별표"
    assert "<삭 제>" in deleted["별표내용"]                # 본문은 unescape 미적용(실문자 보존)
    assert branch["별표제목"] == "R&D 수당 계상기준(제74조 관련)"  # bare '&' 불변(과해소 없음)
    assert branch["별표가지번호"] == "02"
    assert form["별표구분"] == "별지"                      # 파서 층은 별지도 캡처 — 필터는 main.py
    assert form["별표번호"] == "0001"                      # 별표1과 동번호(독립 채번) 그대로 표면화


def test_doc_level_annexes_listing_admrul(mock_client):
    """v0.2.2(④): admrul doc-level(unit_id 없음) — annexes 목록·count_by_kind가 admrul 경로에서도
    반환(기존 doc-level 테스트는 law 한정). 별지 제외·가지 6자리 id·annexes_unavailable 미발화."""
    mock_client.get_admin_rule_detail.return_value = {
        **mock_client.get_admin_rule_detail.return_value,
        "annexes": [
            {"별표번호": "1", "별표가지번호": "00", "별표구분": "별표",
             "별표제목": "계상기준(제74조 관련)", "별표내용": "본문", "별표서식파일링크": ""},
            {"별표번호": "1", "별표가지번호": "02", "별표구분": "별표",
             "별표제목": "특례기준", "별표내용": "본문2", "별표서식파일링크": ""},
            {"별표번호": "1", "별표가지번호": "00", "별표구분": "별지",
             "별표제목": "신청서", "별표내용": "서식", "별표서식파일링크": ""},
        ],
    }
    result = asyncio.run(get_provision_detail("admrul:2100000278740"))
    assert result["unit_type"] == "document"
    assert result["annexes_count"] == 3                    # 전건 집계(별지 포함) — 하위호환
    assert result["annexes_count_by_kind"] == {"별표": 2, "별지": 1}
    listed = result["annexes"]
    assert [a["provision_id"] for a in listed] == [
        "admrul:2100000278740:BP0001", "admrul:2100000278740:BP000102"]
    assert listed[0]["dependent_article_hints"] == ["제74조"]
    assert listed[1]["label"] == "별표 1의2"
    assert all("content" not in a and "별표내용" not in a for a in listed)  # 본문 미포함
    assert "annexes_unavailable" not in result             # admrul은 annex_parse_error 미발화


# === v0.2.3: 대용량 별표 핀포인트 도달성 (멀티윈도우 스니펫 + 포인터 문구) ===
def _far_rows_annex_content(first_row, second_row):
    """두 매칭 행이 스니펫 예산(_SNIPPET_MAX=2000자) 밖으로 떨어진 표 본문 생성.

    중간 필러 80행(약 2,800자 > 2000)이 두 행을 갈라놓아 단일 연속 윈도우로는
    동시 포함 불가 — 멀티윈도우 합집합 수집이어야만 둘 다 스니펫에 들어간다.
    필러에는 검증 토큰(서울대학교·간접비·27.01)이 등장하지 않는다.
    """
    front = [f"│앞쪽기관{i:03d}│10.00│" for i in range(5)]
    gap = [f"│중간기관{i:03d}│15.00│연구기관 비율 자료 행 필러 데이터│" for i in range(80)]
    back = [f"│뒤쪽기관{i:03d}│12.00│" for i in range(5)]
    return "\n".join(front + [first_row] + gap + [second_row] + back)


def test_annex_snippet_multiwindow_includes_all_matching_rows_case0():
    """사례0 회귀: 한 토큰('서울대학교')의 매칭 행 2개(남서울대학교/본교 27.01)가
    예산 밖으로 떨어져 있어도 두 행 모두 스니펫에 포함 — 단일 윈도우 매몰 금지."""
    content = _far_rows_annex_content(
        "│남서울대학교│20.00│",
        "││서울대학교│27.01│서울미디어대학원대학교│20.00││",
    )
    snip = main_module._annex_snippet(content, ["서울대학교"])
    assert "남서울대학교" in snip                       # 앞 매칭 행
    assert "27.01" in snip, "본교 행(사례0 핵심 수치) 도달 실패"  # 뒤 매칭 행
    assert snip.index("남서울대학교") < snip.index("27.01")     # 문서 순서 유지


def test_annex_snippet_multiwindow_separator_and_budget():
    """비연속 윈도우 사이 '…' 단독 구분 줄 존재 + 전체 ≤ _SNIPPET_MAX + 행 원문 무절단."""
    content = _far_rows_annex_content(
        "│남서울대학교│20.00│",
        "││서울대학교│27.01│서울미디어대학원대학교│20.00││",
    )
    snip = main_module._annex_snippet(content, ["서울대학교"])
    assert len(snip) <= main_module._SNIPPET_MAX
    lines = snip.split("\n")
    i_first = next(i for i, ln in enumerate(lines) if "남서울대학교" in ln)
    i_second = next(i for i, ln in enumerate(lines) if "27.01" in ln)
    assert any(ln.strip() == "…" for ln in lines[i_first + 1:i_second]), \
        "비연속 윈도우 사이 '…' 구분 줄 누락"
    # 본문 행은 원문 줄 그대로(중간 절단 없음) — 마커는 '│' 미포함 전제
    orig = set(content.split("\n"))
    assert all(ln in orig for ln in lines if "│" in ln)


def test_annex_snippet_full_inclusion_marker_when_content_fits():
    """소형 별표(예산 내 전체 수록) → '발췌' 오표기 금지 + 전체 수록 표기 + 본문 무손실."""
    content = "기관명\t간접비율\n한국대학교\t15.00"
    snip = main_module._annex_snippet(content, ["간접비율"])
    assert content in snip                  # 본문 전체 수록
    assert "발췌" not in snip               # 전체 수록인데 누락 가능 신호를 주지 않음
    assert "전체" in snip                   # 전체 수록 마커
    assert len(snip) <= main_module._SNIPPET_MAX


def test_annex_snippet_partial_marker_signals_excerpt_path():
    """대형 별표(부분) → 발췌 마커 + 전문 확인 경로(get_provision_detail) 안내 보존."""
    content = "\n".join(f"행{i}\t값{i}" for i in range(2000))
    snip = main_module._annex_snippet(content, ["행1000"])
    assert "발췌" in snip
    assert "get_provision_detail" in snip


def test_annex_snippet_adjacent_matches_merge_without_duplicates():
    """인접한 매칭 줄(±1 윈도우 중첩)은 병합 — 줄 중복·불필요한 '…' 구분 없음."""
    rows = [f"│기관{i:03d}│10.00│" for i in range(40)]
    rows[20] = "│남서울대학교│20.00│"
    rows[21] = "││서울대학교│27.01│"          # 바로 다음 줄 — 윈도우 중첩
    content = "\n".join(rows + [f"│하단{i:03d}│필러 데이터 행│" for i in range(120)])
    snip = main_module._annex_snippet(content, ["서울대학교"])
    assert snip.count("│남서울대학교│20.00│") == 1
    lines = snip.split("\n")
    i1 = next(i for i, ln in enumerate(lines) if "남서울대학교" in ln)
    i2 = next(i for i, ln in enumerate(lines) if "27.01" in ln)
    assert i2 == i1 + 1, "인접 매칭 줄 사이에 구분/중복 줄이 끼면 안 됨"


def test_annex_snippet_multi_token_union_collects_rows_per_token():
    """토큰별 매칭 행 합집합: [간접비, 서울대학교] 각각의 매칭 행이 멀리 떨어져도 모두 포함."""
    content = _far_rows_annex_content("│간접비 계상 기준 행│", "││서울대학교│27.01│")
    snip = main_module._annex_snippet(content, ["간접비", "서울대학교"])
    assert "간접비 계상 기준 행" in snip
    assert "27.01" in snip


def test_search_provision_annex_snippet_covers_all_query_tokens(mock_client):
    """통합(호출부 회귀 가드): search_provision이 첫 anchor만이 아니라 본문 존재
    토큰 전부를 _annex_snippet에 전달 — 다중 토큰 질의의 양쪽 매칭 행이 snippet에 포함."""
    content = _far_rows_annex_content("│간접비 계상 기준 행│", "││서울대학교│27.01│")
    mock_client.get_admin_rule_detail.return_value["annexes"][0]["별표내용"] = content
    result = asyncio.run(search_provision("간접비 서울대학교"))
    annex_hits = [r for r in result["results"] if r["unit_type"] == "annex"]
    assert annex_hits, "별표가 토큰 AND로 매칭돼야 (간접비·서울대학교 모두 본문에 존재)"
    snip = annex_hits[0]["snippet"]
    assert "간접비" in snip and "27.01" in snip, "호출부가 단일 anchor만 넘기면 27.01 누락"


def test_suggest_candidates_strip_annex_snippet_marker(mock_client):
    """v0.2.3: suggest 후보 snippet은 300자 절단을 거치므로 별표 마커(전체 수록/발췌)를
    제거 — 절단본에 '전체 수록·줄 생략 없음' 주장이 잔존하는 오신호 방지."""
    content = "\n".join(f"│기관{i:03d}│10.00│ 간접비 비율 자료" for i in range(60))
    mock_client.get_admin_rule_detail.return_value["annexes"][0]["별표내용"] = content
    # 키워드는 mock 조문에 없는 "비율"만 — 별표 후보가 cap(15) 안에 들도록 (v0.2.5 25규정 확대 대응)
    result = asyncio.run(suggest_review_sources("간접비 비율 확인", keywords=["비율"]))
    annex_cands = [c for c in result["candidates"] if ":BP" in c.get("provision_id", "")]
    assert annex_cands, "별표 후보가 생성돼야"
    for c in annex_cands:
        assert not c["snippet"].startswith("[별표")
        assert "전체 수록" not in c["snippet"]


def test_search_provision_response_char_budget(mock_client):
    """v0.2.5: 광역 질의로 결과가 비대해도 전체 응답 직렬화가 예산(16k) 이내 —
    뒤쪽 결과 절단(최소 1건 보장) + 기존 returned/truncated 필드로 신호."""
    fat = "예산검증용 " * 400                      # ~2,400자 — snippet은 2000자로 cap
    arts = mock_client.get_law_detail.return_value["articles"]
    for a in arts:
        a["조문내용"] = a["조문내용"] + " " + fat
    mock_client.get_admin_rule_detail.return_value["annexes"][0]["별표내용"] = fat * 3
    result = asyncio.run(search_provision("예산검증용"))
    assert result["results"], "최소 1건 보장"
    assert len(json.dumps(result, ensure_ascii=False)) <= main_module._SEARCH_RESPONSE_CHAR_BUDGET
    assert result["returned"] == len(result["results"]) < result["total"]
    assert result["truncated"] is True


def test_annex_snippet_multi_token_frequent_token_does_not_starve_rare():
    """v0.2.4: 빈출 토큰(반복 표 머리글)이 매칭 줄 cap을 선점해도 희소 토큰의 매칭 행이
    수집됨 — 라이브 실증 회귀(간접비 머리글이 cap 6 소진 → 서울대 본교 행 27.01 탈락)."""
    header = "││구 분│기 관 명│간접비고시비율(%)│필러 칸 자리│"
    body = []
    for k in range(8):                      # 빈출 토큰 매칭 머리글 8줄 (cap 6 초과)
        body.append(header)
        body += [f"│기관{k:02d}{i:02d}│10.00│자료 행 필러 데이터 칸│" for i in range(12)]
    body.append("││서울대학교│27.01│서울미디어대학원대학교│20.00││")  # 희소 토큰의 유일 매칭 행(문서 끝)
    content = "\n".join(body)
    assert len(content) > main_module._SNIPPET_MAX            # 발췌 경로 강제
    snip = main_module._annex_snippet(content, ["간접비", "서울대학교"])
    assert "27.01" in snip, "토큰별 quota 미보장 시 빈출 토큰이 cap을 선점해 희소 행 누락"


def test_build_annex_detail_oversized_pointer_prefers_official_source_and_warns_hwp():
    """v0.2.3 C2: oversized_pointer 안내 — ① document_source_url(공식 원문) 1순위
    ② 첨부는 HWP·HWPX 등 기계 열람 불가 가능 보수 문구 ③ 기존 '인용 금지' 신호 보존."""
    big = "구분\t정부지원\t기관부담\n" * 3000     # 기존 oversized fixture 구성 재사용
    ann = {"별표번호": "6", "별표제목": "간접비율표", "별표내용": big,
           "별표서식파일링크": "https://www.law.go.kr/x.hwp"}
    resp = main_module._build_annex_detail(
        "admrul:2100000278740:BP0006", "BP0006", _fake_rs(), ann, "20260506")
    assert resp["content_format"] == "oversized_pointer"
    c = resp["content"]
    assert "document_source_url" in c and "attached_file_url" in c
    assert c.index("document_source_url") < c.index("attached_file_url"), \
        "공식 원문(document_source_url)이 1순위로 와야"
    assert "HWP" in c and "열람" in c          # 첨부 형식 보수 문구
    assert "인용하지 마십시오" in c             # 기존 인용 금지 신호 보존
    ra = resp["required_action"]
    assert ra.index("document_source_url") < ra.index("attached_file_url")


# === v0.2.6: search_provision fan-out 응답 예산 가드 (graceful skip) ===


def test_search_provision_fanout_budget_graceful_skip(mock_client, monkeypatch):
    """fan-out 응답 예산 초과 시 느린 규정을 graceful skip(errors code=timeout)하고 완료분으로 응답 — 전체 타임아웃 차단."""
    import time as _time
    monkeypatch.setattr(main_module, "_FANOUT_BUDGET_S", 0.05)

    def _slow_detail(doc_id):
        _time.sleep(0.4)
        return {"articles": [], "annexes": [], "annex_parse_error": None}

    mock_client.get_law_detail.side_effect = _slow_detail
    mock_client.get_admin_rule_detail.side_effect = _slow_detail

    # 예산(0.05s) << 지연(0.4s) → 전건 skip되지만 전체 타임아웃 없이 정상 반환
    result = asyncio.run(main_module.search_provision("기술료"))
    assert "results" in result and "errors" in result
    timeout_errs = [e for e in result["errors"] if e["code"] == "timeout"]
    assert timeout_errs, "예산 초과 규정이 timeout 코드로 errors에 표면화돼야 함"
    # graceful skip 메시지: '부분 결과 + 재검색' 신호 (v0.2.7 ⑨ — '끊김/생략' 뉘앙스 제거)
    _msg = timeout_errs[0]["message"]
    assert "제외" in _msg and "부분 결과" in _msg and "다시 검색" in _msg
    assert "중단" in _msg  # 서비스 중단이 아님을 명시


def test_search_provision_fanout_budget_no_skip_when_fast(mock_client):
    """정상(빠른) fetch는 예산 내 전건 완료 — timeout skip 미발생."""
    result = asyncio.run(main_module.search_provision("간접비"))
    timeout_errs = [e for e in result.get("errors", []) if e["code"] == "timeout"]
    assert not timeout_errs, "정상 fetch에서는 timeout skip이 없어야 함"


# === v0.2.7: 외부 API 대기 상한 보수화 (구동 안정성 강화) 회귀 ===


def test_request_defaults_conservative_timeout_and_retries():
    """v0.2.7 핵심 회귀: _request_with_retry 기본값이 보수화된 신 상수(timeout (8,12)·max_retries 2)와 일치 — 우발적 원복 방지. 네트워크 미발생(inspect만)."""
    import inspect
    from korean_rnd_regs_mcp import live_api
    sig = inspect.signature(live_api._request_with_retry)
    assert sig.parameters["max_retries"].default == 2
    assert sig.parameters["timeout"].default == (8.0, 12.0)
    assert live_api._MAX_RETRIES == 2
    assert live_api._CONNECT_TIMEOUT_S == 8.0
    assert live_api._READ_TIMEOUT_S == 12.0
    assert live_api._REQUEST_TIMEOUT == (8.0, 12.0)


def test_read_timeout_below_fanout_budget_invariant():
    """v0.2.7 부등식 회귀: read timeout(12) < fan-out 예산(20) — read가 끊겨도 예산 안에서 graceful skip으로 흡수됨을 코드로 강제."""
    from korean_rnd_regs_mcp import live_api
    from korean_rnd_regs_mcp import main as _m
    assert live_api._READ_TIMEOUT_S < _m._FANOUT_BUDGET_S, "read timeout이 fan-out 예산보다 작아야 함"
    assert live_api._CONNECT_TIMEOUT_S <= live_api._READ_TIMEOUT_S
    assert _m._FANOUT_BUDGET_S == 20.0  # ④ 예산값 유지


def test_request_passes_tuple_timeout_to_requests_get(monkeypatch):
    """v0.2.7: override 없이 호출 시 requests.get에 (8.0, 12.0) 튜플 timeout이 실제 전달됨 — 단일 locus가 신 default를 사용함을 검증(네트워크 미발생)."""
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import _request_with_retry

    captured = {}

    class _FakeResp:
        status_code = 200

    def mock_get(url, params=None, timeout=None, **kwargs):
        captured["timeout"] = timeout
        return _FakeResp()

    monkeypatch.setattr(requests_mod, "get", mock_get)
    _request_with_retry("https://test.invalid", {"OC": "x"})
    assert captured["timeout"] == (8.0, 12.0)


# === v0.2.8: search_provision 관련도 정렬 (광역 질의 매몰 방지) ===
def _fake_rank_rs(title, rank):
    """_relevance_sort_key 단위 테스트용 최소 rule set stub."""
    return types.SimpleNamespace(title=title, hierarchy_rank=types.SimpleNamespace(value=rank))


def test_relevance_sort_key_doc_title_hit_outranks_content_only():
    """문서 제목 적중이 본문만 적중보다 상위 정렬(키가 더 작다 = 앞)."""
    tokens = ["연구개발비"]
    key_doc = _relevance_sort_key(_fake_rank_rs("국가연구개발사업 연구개발비 사용 기준", 4), tokens,
                                  "기본사업계상기준", "별표 본문", "annex", 5)
    key_content = _relevance_sort_key(_fake_rank_rs("국가연구개발혁신법", 1), tokens,
                                      "특별평가", "연구개발비 관련 본문", "article", 0)
    assert key_doc < key_content, "문서 제목 적중이 위계·ordinal보다 우선해 상위 정렬돼야"


def test_relevance_sort_key_hierarchy_is_lower_priority_than_title():
    """위계(hierarchy_rank)는 하위 tie-break — 상위에 두면 eval 매몰 버그 재현.
    rank=4지만 제목 적중 규정이, rank=1이지만 제목 미적중 규정보다 앞서야 한다."""
    tokens = ["연구개발비"]
    key_rank4_titlehit = _relevance_sort_key(_fake_rank_rs("국가연구개발사업 연구개발비 사용 기준", 4),
                                             tokens, "계상기준", "별표 본문", "annex", 99)
    key_rank1_notitle = _relevance_sort_key(_fake_rank_rs("국가연구개발혁신법", 1),
                                            tokens, "총칙", "연구개발비 본문", "article", 0)
    assert key_rank4_titlehit < key_rank1_notitle


def test_relevance_sort_key_deterministic_tie_uses_ordinal():
    """전 신호 동률 → ordinal(기존 append 순서)로 결정, 낮은 ordinal이 앞. 정렬 결정성."""
    tokens = ["특별평가"]
    rs = _fake_rank_rs("국가연구개발혁신법", 1)
    k0 = _relevance_sort_key(rs, tokens, "특별평가", "본문", "article", 0)
    k1 = _relevance_sort_key(rs, tokens, "특별평가", "본문", "article", 1)
    assert k0 < k1
    assert k0[:-1] == k1[:-1]  # ordinal 외 전부 동일


def test_search_provision_relevance_doc_title_match_first(mock_client):
    """(eval 회귀) 광역 '연구개발비' — 문서 제목이 직접 일치하는 rnd_funding_standard가
    manifest 후순위(rank4)임에도 결과 최상위에 옴(매몰 해소). 제목 적중 유일 규정."""
    result = asyncio.run(search_provision("연구개발비"))
    assert result["results"], "매칭 결과가 있어야"
    assert result["results"][0]["rule_set_id"] == "rnd_funding_standard"


def test_search_provision_relevance_survives_truncation(mock_client, monkeypatch):
    """문서 제목 적중 규정이 강한 절단(예산 최소)에서도 생존 — 최상위라 1건만 남아도 포함.
    v0.2.7 eval에서 매몰됐던 규정이 정렬 후 절단 생존함을 직접 증명."""
    monkeypatch.setattr(main_module, "_SEARCH_RESPONSE_CHAR_BUDGET", 1)
    result = asyncio.run(search_provision("연구개발비"))
    assert result["returned"] >= 1  # 예산 최소여도 최소 1건 보장
    assert result["results"][0]["rule_set_id"] == "rnd_funding_standard"


def test_search_provision_no_relevance_score_leak(mock_client):
    """정렬키·score가 응답 결과에 누출되지 않음 — 알려진 키만 보유(schema 무변·contract 0.6.0 유지)."""
    result = asyncio.run(search_provision("특별평가"))
    allowed = {"provision_id", "rule_set_id", "document_title", "unit_id", "unit_type",
               "title", "snippet", "warnings", "effective_date", "revision_notice"}
    for r in result["results"]:
        assert set(r.keys()) <= allowed, f"예상치 못한 키: {set(r.keys()) - allowed}"


# === v0.2.10 관측성(B1): fan-out 지연 로그 가드 (요약 INFO + per-rule DEBUG + 시크릿 미포함) ===
def test_search_fanout_observability_logs_present_and_secret_free(mock_client, monkeypatch, caplog):
    """search fan-out 요약(INFO)+per-rule(DEBUG) 로그가 출력되고, OC 키·URL이 미포함됨을 단정."""
    import logging
    monkeypatch.setenv("LAW_API_KEY", _FAKE_KEY)  # 부재 단정에 의미 부여
    with caplog.at_level(logging.DEBUG, logger="rnd-regs-mcp"):
        asyncio.run(search_provision("특별평가"))
    recs = [r for r in caplog.records if r.name.startswith("rnd-regs-mcp")]
    summary = [r for r in recs if "event=search_fanout_summary" in r.getMessage()]
    assert summary, "search_fanout_summary 요약 로그 누락"
    assert summary[0].levelno == logging.INFO, "요약은 INFO여야 함"
    msg = summary[0].getMessage()
    for field in ("live_rules=", "done=", "skipped=", "wall_ms=",
                  "max_rule_ms=", "slow_rule_count=", "errors_count="):
        assert field in msg, f"요약 필드 누락: {field}"
    per_rule = [r for r in recs if "event=fanout_rule" in r.getMessage()]
    assert per_rule, "per-rule fanout_rule DEBUG 로그 누락"
    assert all(r.levelno == logging.DEBUG for r in per_rule), "per-rule은 DEBUG여야 함(INFO 폭주 방지)"
    blob = " ".join(r.getMessage() for r in recs)
    assert _FAKE_KEY not in blob, "로그에 OC 키 누설"
    assert _FAKE_KEY[:6] not in blob, "로그에 OC 키 앞자리 누설"
    assert "?oc=" not in blob, "로그에 oc= URL 파라미터 누설"
    assert "OC=" not in blob, "로그에 OC= 파라미터 누설"
    assert "law.go.kr" not in blob, "로그에 요청 URL 누설"


def test_suggest_search_summary_log_present(mock_client, caplog):
    """suggest_review_sources가 1회 유발한 내부 search 호출 수를 요약 INFO로 기록."""
    import logging
    import re as _re
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        asyncio.run(suggest_review_sources(
            "연구개발비 협약 변경 절차", keywords=["협약 변경", "연구개발비"]))
    recs = [r for r in caplog.records if r.name.startswith("rnd-regs-mcp")]
    summary = [r for r in recs if "event=suggest_search_summary" in r.getMessage()]
    assert summary, "suggest_search_summary 요약 로그 누락"
    assert summary[0].levelno == logging.INFO
    msg = summary[0].getMessage()
    for field in ("keyword_source=", "search_calls=", "wall_ms=",
                  "errors_count=", "candidates_count="):
        assert field in msg, f"suggest 요약 필드 누락: {field}"
    m = _re.search(r"search_calls=(\d+)", msg)
    assert m and int(m.group(1)) >= 1, "search_calls가 1 이상으로 기록되지 않음(fan-out 미발생)"


# === v0.2.11: HTTP 멀티테넌트 키 보호 (no-oc 가드) ===
def test_http_no_key_helper_states():
    """가드 헬퍼: stdio·http+oc → None / http+no-oc → auth_failed envelope."""
    from korean_rnd_regs_mcp.main import (
        _http_no_key_error, _is_http_request, _request_api_key,
    )
    # stdio (http 플래그 없음·기본 False) → 가드 미발화
    assert _http_no_key_error() is None
    # http + oc 있음 → 미발화(per-key 클라이언트 정상 경로)
    t1 = _is_http_request.set(True); t2 = _request_api_key.set("OC_FAKE")
    try:
        assert _http_no_key_error() is None
    finally:
        _request_api_key.reset(t2); _is_http_request.reset(t1)
    # http + oc 없음 → auth_failed
    t1 = _is_http_request.set(True); t2 = _request_api_key.set("")
    try:
        err = _http_no_key_error()
        assert err is not None
        assert err["errors"][0]["code"] == "auth_failed"
        assert "contract_version" in err and "disclaimer" in err
    finally:
        _request_api_key.reset(t2); _is_http_request.reset(t1)


def test_http_no_key_message_secret_free():
    """가드 메시지: 키 미포함 + 소문자 ?oc=만(대문자 OC= 신규 금지)."""
    from korean_rnd_regs_mcp.main import _HTTP_NO_KEY_MESSAGE
    assert "?oc=" in _HTTP_NO_KEY_MESSAGE
    assert "OC=" not in _HTTP_NO_KEY_MESSAGE
    assert _FAKE_KEY not in _HTTP_NO_KEY_MESSAGE


def test_http_no_oc_blocks_all_three_tools_without_api_call(mock_client):
    """HTTP no-oc 시 3개 도구가 auth_failed early-return + API/resolve 미호출(env 키 미과금)."""
    from korean_rnd_regs_mcp.main import _is_http_request, _request_api_key
    t1 = _is_http_request.set(True); t2 = _request_api_key.set("")
    try:
        r_s = asyncio.run(search_provision("간접비 기준"))
        r_d = asyncio.run(get_provision_detail("law:283849:JO0015"))
        r_g = asyncio.run(suggest_review_sources("간접비 검토", None))
    finally:
        _request_api_key.reset(t2); _is_http_request.reset(t1)
    for r in (r_s, r_d, r_g):
        assert r["errors"][0]["code"] == "auth_failed"
    # search_provision 가드 envelope shape 일관성(엄격 클라이언트 대비)
    assert r_s["results"] == []
    # 가드가 API 경로를 차단 — mock 클라이언트 미호출(조회/과금 0)
    mock_client.resolve_latest_doc_id.assert_not_called()
    mock_client.get_law_detail.assert_not_called()
    mock_client.get_admin_rule_detail.assert_not_called()


def test_stdio_no_oc_is_regression_free(mock_client):
    """stdio(=_is_http_request 기본 False)는 env 키 정상 경로 — 가드 미발화·검색 정상 수행(무회귀)."""
    from korean_rnd_regs_mcp.main import _is_http_request
    assert _is_http_request.get() is False
    res = asyncio.run(search_provision("간접비"))
    codes = [e.get("code") for e in res.get("errors", [])]
    assert "auth_failed" not in codes          # 가드에 막히지 않음(정상 경로)
    assert mock_client.resolve_latest_doc_id.called   # fan-out이 mock 클라이언트로 진행됨


def test_oc_key_middleware_sets_and_resets_http_flag():
    """미들웨어가 http scope에서 앱 실행 중 _is_http_request=True·요청 후 reset(누수 0)."""
    from korean_rnd_regs_mcp.main import _OCKeyMiddleware, _is_http_request
    seen = []
    async def _app(scope, receive, send):
        seen.append(_is_http_request.get())
    mw = _OCKeyMiddleware(_app)
    asyncio.run(mw({"type": "http", "query_string": b""}, None, None))
    assert seen == [True]
    assert _is_http_request.get() is False


def test_oc_key_middleware_resets_flag_on_exception():
    """미들웨어: 앱이 예외를 던져도 finally에서 _is_http_request reset(누수 0)."""
    from korean_rnd_regs_mcp.main import _OCKeyMiddleware, _is_http_request
    async def _boom(scope, receive, send):
        raise RuntimeError("boom")
    mw = _OCKeyMiddleware(_boom)
    with pytest.raises(RuntimeError):
        asyncio.run(mw({"type": "http", "query_string": b""}, None, None))
    assert _is_http_request.get() is False


def test_run_http_disables_uvicorn_access_log(monkeypatch):
    """_run_http가 run_http_async에 uvicorn_config={'access_log': False} 전달(?oc= 키 로그 차단)."""
    captured = {}
    async def _fake_run_http_async(**kwargs):
        captured.update(kwargs)
    monkeypatch.setattr(main_module.mcp, "run_http_async", _fake_run_http_async)
    asyncio.run(main_module._run_http("0.0.0.0", 18080))
    assert captured.get("uvicorn_config") == {"access_log": False}


# === v0.5.0: 행정규칙(admrul) version 메타데이터 내재화 ===
def test_get_admin_rule_detail_parses_issuance_and_kind_v050(monkeypatch):
    """v0.5.0: admrul 상세 파싱이 <행정규칙기본정보>의 발령번호·행정규칙종류를 result에 담는다."""
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import LawApiClient

    fake_xml = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService>
  <행정규칙기본정보>
    <행정규칙ID>v050_test</행정규칙ID>
    <행정규칙명>질병관리청 연구개발 관리 규정</행정규칙명>
    <소관부처명>질병관리청</소관부처명>
    <시행일자>20260518</시행일자>
    <발령번호>179</발령번호>
    <행정규칙종류>예규</행정규칙종류>
  </행정규칙기본정보>
  <조문내용>제1조(목적) 이 규정은 ...</조문내용>
</AdmRulService>"""

    class FakeResponse:
        status_code = 200
        text = fake_xml
        headers = {"Content-Type": "application/xml"}

    monkeypatch.setattr(requests_mod, "get", lambda *a, **kw: FakeResponse())
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    result = client.get_admin_rule_detail("2100000279440")
    assert result["발령번호"] == "179"
    assert result["행정규칙종류"] == "예규"


def test_get_admin_rule_detail_missing_meta_omits_safely_v050(monkeypatch):
    """v0.5.0: 발령번호·종류 element 누락 시 빈 문자열(예외 없음 — 검색 fan-out 공유 파서 안전)."""
    import requests as requests_mod
    from korean_rnd_regs_mcp.live_api import LawApiClient

    fake_xml = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulService>
  <행정규칙기본정보>
    <행정규칙ID>no_meta</행정규칙ID>
    <행정규칙명>테스트 규정</행정규칙명>
    <시행일자>20210101</시행일자>
  </행정규칙기본정보>
  <조문내용>제1조(목적) ...</조문내용>
</AdmRulService>"""

    class FakeResponse:
        status_code = 200
        text = fake_xml
        headers = {"Content-Type": "application/xml"}

    monkeypatch.setattr(requests_mod, "get", lambda *a, **kw: FakeResponse())
    client = LawApiClient(env_override={"LAW_API_KEY": "fake"})
    result = client.get_admin_rule_detail("123")
    assert result["발령번호"] == ""
    assert result["행정규칙종류"] == ""


def test_admrul_version_meta_synthesizes_label_all_kinds_v050():
    """v0.5.0: 종류+번호 정상이면 version_label 합성 — 예규/훈령 순번형·고시 연도형 모두 '{종류} 제{번호}호'."""
    from korean_rnd_regs_mcp.provision_id import parse
    pid = parse("admrul:2100000279440")
    m = _admrul_version_meta(pid, {"발령번호": "179", "행정규칙종류": "예규"})
    assert m == {"issuance_number": "179", "regulation_kind": "예규", "version_label": "예규 제179호"}
    assert _admrul_version_meta(pid, {"발령번호": "2026-25", "행정규칙종류": "고시"})["version_label"] == "고시 제2026-25호"
    assert _admrul_version_meta(pid, {"발령번호": "242", "행정규칙종류": "훈령"})["version_label"] == "훈령 제242호"


def test_admrul_version_meta_law_returns_empty_v050():
    """v0.5.0: law는 발령번호 의미 다름(공포번호)+C12 함정 → version_meta 미주입(빈 dict)."""
    from korean_rnd_regs_mcp.provision_id import parse
    assert _admrul_version_meta(parse("law:283849"), {"발령번호": "179", "행정규칙종류": "예규"}) == {}


def test_admrul_version_meta_omits_label_on_bad_kind_or_number_v050():
    """v0.5.0: 종류가 허용값 아니거나 번호가 검증 패턴 아니면 version_label omit(raw 필드는 노출)."""
    from korean_rnd_regs_mcp.provision_id import parse
    pid = parse("admrul:123")
    m = _admrul_version_meta(pid, {"발령번호": "179", "행정규칙종류": "기타"})
    assert "version_label" not in m and m["issuance_number"] == "179" and m["regulation_kind"] == "기타"
    m = _admrul_version_meta(pid, {"발령번호": "제179호", "행정규칙종류": "예규"})
    assert "version_label" not in m and m["issuance_number"] == "제179호"  # '제179호'는 \d+(-\d+)? 미매칭
    assert _admrul_version_meta(pid, {"발령번호": "", "행정규칙종류": "예규"}) == {"regulation_kind": "예규"}


def test_doc_level_admrul_includes_version_meta_v050(mock_client):
    """v0.5.0: admrul document-level 응답에 issuance_number·regulation_kind·version_label 포함."""
    mock_client.get_admin_rule_detail.return_value["발령번호"] = "2026-38"
    mock_client.get_admin_rule_detail.return_value["행정규칙종류"] = "고시"
    result = asyncio.run(get_provision_detail("admrul:2100000278740"))
    assert result["issuance_number"] == "2026-38"
    assert result["regulation_kind"] == "고시"
    assert result["version_label"] == "고시 제2026-38호"


def test_article_admrul_includes_version_meta_v050(mock_client):
    """v0.5.0: admrul 조문 응답에도 version 메타(조문+번호 동반 질의 시 외부행 차단)."""
    mock_client.get_admin_rule_detail.return_value["발령번호"] = "179"
    mock_client.get_admin_rule_detail.return_value["행정규칙종류"] = "예규"
    mock_client.get_admin_rule_detail.return_value["articles"] = [
        {"조문번호": "7", "조문제목": "목적", "조문내용": "제7조 본문", "structured": {"title": "제7조(목적)", "paragraphs": []}},
    ]
    result = asyncio.run(get_provision_detail("admrul:2100000278740:JO0007"))
    assert result["unit_type"] == "article"
    assert result["version_label"] == "예규 제179호"


def test_annex_admrul_includes_version_meta_v050(mock_client):
    """v0.5.0: admrul 별표 응답(전 tier 공통)에도 version 메타 — oversized여도 version은 도구에서(프롬프트4)."""
    mock_client.get_admin_rule_detail.return_value["발령번호"] = "2026-25"
    mock_client.get_admin_rule_detail.return_value["행정규칙종류"] = "고시"
    result = asyncio.run(get_provision_detail("admrul:2100000278740:BP0001"))
    assert result["unit_type"] == "annex"
    assert result["version_label"] == "고시 제2026-25호"


def test_law_doc_level_has_no_version_meta_v050(mock_client):
    """v0.5.0: law 응답에는 admrul 전용 version 필드 미주입(공포번호 의미 다름·C12 함정)."""
    result = asyncio.run(get_provision_detail("law:283849"))
    assert "issuance_number" not in result
    assert "regulation_kind" not in result
    assert "version_label" not in result


def test_version_meta_omits_abnormal_long_issuance_v050():
    """v0.5.0 B2: 비정상 장문 발령번호·종류(파싱 오염·악성)는 상한(_ISSUANCE_MAX_LEN/_KIND_MAX_LEN)으로 omit."""
    from korean_rnd_regs_mcp.provision_id import parse
    pid = parse("admrul:123")
    m = _admrul_version_meta(pid, {"발령번호": "9" * 160, "행정규칙종류": "예" * 40})
    assert "issuance_number" not in m and "version_label" not in m and "regulation_kind" not in m


def test_version_meta_bounded_within_annex_headroom_v050():
    """v0.5.0 B2(상한 증명): helper가 낼 수 있는 최대 version_meta + 정상 템플릿 revision_notice 사후주입이
    _ANNEX_DETAIL_HEADROOM 이내임을 입력 상한 기반으로 증명(임의 표본 아님) → 전문 tier 경계 불변.
    (응답 총량의 예산 초과는 OpenAPI 무한 공급 필드[title·effective_date] 의존·pre-existing — 별도 backlog.)"""
    from korean_rnd_regs_mcp.main import _ANNEX_DETAIL_HEADROOM, _ISSUANCE_MAX_LEN
    from korean_rnd_regs_mcp.provision_id import parse
    pid = parse("admrul:123")
    # 허용 경계 입력(이 이상은 omit) — helper가 낼 수 있는 최대 version_meta
    m_max = _admrul_version_meta(pid, {"발령번호": "9" * _ISSUANCE_MAX_LEN, "행정규칙종류": "훈령"})
    assert m_max["version_label"] == "훈령 제" + "9" * _ISSUANCE_MAX_LEN + "호"
    # _revision_notice 실제 최대(고정 템플릿 + 8자리 날짜 2개 + 13자리 ID)보다 보수적으로 긴 안내문
    worst_notice = "개정 반영: 시행일 20240101 → 20260506 (LIVE 검색 기준 현행 시행일과 manifest 시행일이 달라 자동으로 현행본을 조회했으며 별도 조치는 불필요합니다 추가 여유분)"
    injected = {**m_max, "revision_notice": worst_notice}
    assert len(json.dumps(injected, ensure_ascii=False)) <= _ANNEX_DETAIL_HEADROOM


def test_build_annex_detail_force_oversized_v050():
    """v0.5.0 B2 백스톱: force_oversized=True면 소형 전문 별표도 oversized_pointer로 강등(재호출용)."""
    ann = {"별표번호": "1", "별표제목": "소형", "별표내용": "짧은 별표 본문입니다", "별표서식파일링크": ""}
    resp = main_module._build_annex_detail(
        "admrul:2100000278740:BP0001", "BP0001", _fake_rs(), ann, "20260506", force_oversized=True)
    assert resp["content_format"] == "oversized_pointer"


def test_annex_demotes_to_oversized_when_injection_exceeds_budget_v050(mock_client):
    """v0.5.0 B2 백스톱(airtight): 전문 별표에 비정상 장문 사후주입(거대 revision_notice) 후 최종이 예산 초과면
    oversized로 강등 → 최종 직렬화 ≤ _ANNEX_DETAIL_CHAR_BUDGET. version 메타는 강등 후에도 유지."""
    from korean_rnd_regs_mcp.main import _ANNEX_DETAIL_CHAR_BUDGET
    # 경계 직전 전문 별표(사후주입 전엔 verbatim) + version 메타
    mock_client.get_admin_rule_detail.return_value["발령번호"] = "179"
    mock_client.get_admin_rule_detail.return_value["행정규칙종류"] = "예규"
    mock_client.get_admin_rule_detail.return_value["annexes"] = [
        {"별표번호": "1", "별표제목": "대형 별표", "별표내용": "가" * 14000, "별표서식파일링크": ""},
    ]
    # 비정상 장문 revision_notice 유발 — resolve가 거대 doc_id로 is_updated revision 생성
    def _huge_resolve(title, api_target, manifest_doc_id, ministry=None):
        return ResolvedDocId(doc_id="9" * 2000, effective_date="20260506", is_updated=True, manifest_doc_id=manifest_doc_id)
    mock_client.resolve_latest_doc_id.side_effect = _huge_resolve
    result = asyncio.run(get_provision_detail("admrul:2100000278740:BP0001"))
    assert result["content_format"] == "oversized_pointer"                       # 강등됨
    assert len(json.dumps(result, ensure_ascii=False)) <= _ANNEX_DETAIL_CHAR_BUDGET  # airtight
    assert result["version_label"] == "예규 제179호"                              # version 유지
