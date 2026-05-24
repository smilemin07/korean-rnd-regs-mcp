"""Unit tests for search_provision / get_provision_detail / suggest_review_sources.

LawApiClient를 mock하여 네트워크 없이 도구 동작·키 누설 차단·응답 shape 검증.
Step 38.5 GitHub Actions에서 별도 통합 테스트 (@pytest.mark.network) 도입 예정.
"""
import asyncio
import json
from unittest.mock import MagicMock

import pytest

from korean_rnd_regs_mcp import main as main_module
from korean_rnd_regs_mcp.live_api import LawApiClient, LawApiError
from korean_rnd_regs_mcp.main import (
    _extract_keywords,
    _make_snippet,
    _strip_particle,
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
        "법령일련번호": "260807",
        "법령명한글": "국가연구개발혁신법",
        "법령구분명": "법률",
        "소관부처명": "과학기술정보통신부",
        "시행일자": "20250228",
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
    """6차 AI feedback 회귀: '특별평가'의 끝 '가'를 조사로 잘못 strip하지 않아야 함."""
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
    """6차 AI feedback 회귀: empty/공백/1글자 query는 invalid_query error 반환."""
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
    assert "contract_version" in result
    assert "disclaimer" in result
    assert "results" in result
    assert isinstance(result["results"], list)


def test_search_provision_finds_article(mock_client):
    result = asyncio.run(search_provision("특별평가"))
    # mock가 모든 law(3건)에 같은 articles 반환 → JO0015 매칭 3개
    assert result["total"] >= 1
    jo0015_matches = [r for r in result["results"] if r["unit_id"] == "JO0015"]
    assert len(jo0015_matches) >= 1
    assert jo0015_matches[0]["unit_type"] == "article"
    assert jo0015_matches[0]["title"] == "특별평가"


def test_search_provision_no_key_leak(mock_client):
    """ P0 회귀: 도구 응답에 API key 원문·prefix·OC= 미포함."""
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
    result = asyncio.run(get_provision_detail("law:260807:JO0015"))
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
    result = asyncio.run(get_provision_detail("law:260807"))
    assert result["unit_type"] == "document"
    assert "articles_count" in result
    assert "disclaimer" in result


def test_get_provision_detail_no_key_leak(mock_client):
    result = asyncio.run(get_provision_detail("law:260807:JO0015"))
    response_str = json.dumps(result, ensure_ascii=False)
    assert _FAKE_KEY not in response_str
    assert _FAKE_KEY[:6] not in response_str


# === 7차 AI feedback: LLM 환각 방어 (article_structure + format_instructions) ===
def test_get_provision_detail_article_includes_verbatim_metadata(mock_client):
    """7차 AI feedback 회귀: content가 verbatim임을 명시하는 metadata 포함."""
    result = asyncio.run(get_provision_detail("law:260807:JO0015"))
    assert result.get("content_format") == "plain_text_verbatim"
    assert "format_instructions" in result
    instructions = result["format_instructions"]
    # 핵심 지시 키워드 확인
    assert "verbatim" in instructions.lower() or "그대로" in instructions
    assert "임의" in instructions  # "임의 부제·요약·paraphrase 금지"
    assert "번호" in instructions  # 항·호 번호 stripping 금지


def test_get_provision_detail_article_includes_article_structure(mock_client):
    """7차 AI feedback 회귀: machine-readable nested hierarchy."""
    result = asyncio.run(get_provision_detail("law:260807:JO0015"))
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


def test_suggest_review_sources_propagates_search_errors(mock_client):
    """6차 AI feedback 회귀: 내부 search_provision 실패를 errors로 전파 (매칭 없음으로 위장 금지)."""
    mock_client.get_law_detail.side_effect = LawApiError("parse_failed", "synthetic error")
    mock_client.get_admin_rule_detail.side_effect = LawApiError("parse_failed", "synthetic error")
    result = asyncio.run(suggest_review_sources("특별평가"))
    assert "errors" in result, "search 실패가 suggest_review_sources errors로 전파되어야 함"
    assert len(result["errors"]) >= 1
    # error에 keyword 정보 포함
    assert any("keyword" in e for e in result["errors"])


# === list_rule_sets contract_version (Phase 3 보강) ===
def test_list_rule_sets_includes_contract_version(mock_client):
    result = asyncio.run(list_rule_sets())
    assert "contract_version" in result
    assert result["contract_version"] == "0.1.0"


# === _build_article_content (6차 AI P0 회귀) ===
def test_build_article_content_concatenates_hangs_and_hos():
    """다항조문 본문이 조문내용 + 항(항내용 + 호) 형태로 reconstruct되는지 검증.

    6차 AI feedback P0: 직전 buggy 상태는 조문내용(title repeat)만 반환하여 본문 누락.
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


# === 8차 AI review 회귀 ( P0: requests 예외 포괄 catch) ===
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


# === 8차 AI review LIVE 검증 P0 회귀 (wrapper filter) ===
def test_get_law_detail_excludes_wrapper_elements(monkeypatch):
    """장/절 wrapper(조문여부='전문')는 articles에서 제외 — 동일 조문번호 collision 방어.

    LIVE 검증 발견: 혁신법 MST 260807 + 시행령 285767의 각 7개 조문번호에서 wrapper("제1장 총칙" 등)와
    실제 조문이 동일 조문번호로 중복 등장. 직전 buggy 상태에서는 get_provision_detail("law:260807:JO0001")이
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
    result = client.get_law_detail("260807")
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
