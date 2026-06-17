"""Unit tests for health and list_rule_sets — no network, no live API."""
import asyncio
import json

from korean_rnd_regs_mcp import __version__
from korean_rnd_regs_mcp.main import health, list_rule_sets, mcp, review_regulation_prompt


def test_health_returns_required_fields():
    result = asyncio.run(health())
    assert result["status"] == "ok"
    assert result["service"] == "korean-rnd-regs-mcp"
    assert result["version"] == __version__
    assert isinstance(result["api_key_configured"], bool)


def test_health_no_key_leak(monkeypatch):
    test_key = "fake_secret_test_key_12345abc"
    monkeypatch.setenv("LAW_API_KEY", test_key)
    result = asyncio.run(health())
    response_str = json.dumps(result, ensure_ascii=False)
    assert test_key not in response_str
    assert test_key[:6] not in response_str
    assert result["api_key_configured"] is True


def test_health_reports_unset_key(monkeypatch):
    monkeypatch.delenv("LAW_API_KEY", raising=False)
    result = asyncio.run(health())
    assert result["api_key_configured"] is False


def test_health_no_per_user_oc_key_leak():
    """회귀(작업1 gap a·b): per-user OC key(contextvar)가 health 응답에 미포함."""
    from korean_rnd_regs_mcp.main import _request_api_key
    per_user_oc = "PER_USER_OC_FAKE_7788"
    token = _request_api_key.set(per_user_oc)
    try:
        result = asyncio.run(health())
        response_str = json.dumps(result, ensure_ascii=False)
        assert per_user_oc not in response_str
        assert per_user_oc[:6] not in response_str
        assert result["api_key_configured"] is True
    finally:
        _request_api_key.reset(token)


# === MCP prompt: review_regulation (v0.1.0 보강 — 다층적 검토 워크플로 자동 적용) ===
def test_review_regulation_prompt_substitutes_situation():
    """prompt template이 situation argument를 정확히 substitute."""
    situation = "연구기관이 공동연구기관 추가를 요청했으나 무응답 방치된 사례"
    body = review_regulation_prompt(situation)
    assert isinstance(body, str)
    assert situation in body, "situation argument substitution 실패"
    # 본 server의 핵심 도구 명시
    assert "suggest_review_sources" in body
    assert "get_provision_detail" in body
    # 위계 순서 안내
    assert "법률 → 시행령 → 시행규칙" in body
    # verbatim 정책 명시 — 의도: 원문 인용 충실성 보장. 표현은 시간에 따라 변할 수 있음
    assert "verbatim" in body
    assert "paraphrase" in body  # 핵심 키워드 (요약/paraphrase 금지)
    assert "원문" in body and ("그대로 사용" in body or "verbatim 인용" in body)


def test_review_regulation_prompt_handles_quotes_in_situation():
    """회귀(작업2): situation에 큰따옴표가 있어도 도구 호출 안내가 깨지지 않음."""
    situation = '연구자가 "특별평가" 대상인지 문의'
    body = review_regulation_prompt(situation)
    assert isinstance(body, str)
    assert situation in body  # 큰따옴표 포함 situation이 검토 상황 블록에 그대로 포함
    # question="{situation}" 리터럴 삽입 제거 → 중첩 따옴표로 깨지는 패턴 부재
    assert 'suggest_review_sources(question="' not in body


def test_review_regulation_prompt_includes_tier2_routing():
    """Tier 2 키워드 routing + v0.2.6 공통/사업 행정규칙 cross-check 안내 포함, 제거된 보조 법령 부재."""
    body = review_regulation_prompt("X")
    # Tier 2 routing
    assert "rnd_funding_standard" in body
    assert "simultaneous_research_limit" in body
    assert "facility_equipment_standard" in body
    assert "research_note_guideline" in body
    # v0.2.6 공통/사업 행정규칙 cross-check (보조 법령 routing 대체)
    assert "rnd_info_processing" in body
    assert "rnd_security_measures" in body
    assert "performance_eval_act" in body
    assert "tech_fee_integrated" in body
    # 제거된 보조 법령 routing은 더 이상 프롬프트에 없어야 함
    assert "anti_corruption_act" not in body
    assert "improper_solicitation_act" not in body
    assert "public_interest_whistleblower_act" not in body


def test_review_regulation_prompt_includes_limitation_notice():
    """본 server cover 범위 밖 자료 + 가지조문/별표 한계 명시 (false negative 방지)."""
    body = review_regulation_prompt("X")
    assert "매뉴얼" in body  # 매뉴얼·운영규정·관리지침
    assert "가지조문" in body  # v0.2 deferred
    assert "별표" in body  # v0.3 deferred
    assert "변호사 자문" in body  # 법률 판단 disclaimer


def test_review_regulation_prompt_includes_procedure_flow_section():
    """v0.1.10: 절차형 답변 시각화 — 조건부 8절 '절차 흐름' + fabrication 가드 + literal 백틱3개 부재."""
    body = review_regulation_prompt("X")
    assert "### 8. 절차 흐름" in body  # 조건부 절 신설
    assert "코드블록" in body  # 텍스트 흐름(모든 클라이언트 렌더)
    assert "임의로 추가하지 말 것" in body  # 규정에 없는 단계 fabrication 가드
    assert "mermaid" not in body.lower()  # mermaid 미언급(미렌더 커넥터 raw 노출 방지)
    assert "```" not in body  # README 단일 펜스·동기화 회귀 보호(literal triple-backtick 금지)


def test_readme_embedded_prompt_matches_template():
    """회귀: README에 임베드된 review_regulation 프롬프트가 main.py _REVIEW_PROMPT_TEMPLATE와
    정확히 일치하는지 검증 (문서-코드 drift 방지 — 단일 출처 가드)."""
    import re
    from pathlib import Path
    from korean_rnd_regs_mcp.main import _REVIEW_PROMPT_TEMPLATE
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    m = re.search(r"규정 검토용 프롬프트</summary>\s*\n+```\n(.*?)\n```", readme, re.DOTALL)
    assert m, "README에서 '규정 검토용 프롬프트' 코드블록을 찾지 못함"
    assert m.group(1).strip() == _REVIEW_PROMPT_TEMPLATE.strip(), (
        "README 임베드 프롬프트가 main.py _REVIEW_PROMPT_TEMPLATE와 불일치 — 동기화 필요"
    )


def test_suggest_review_sources_keywords_param_is_optional():
    """회귀(additive): suggest_review_sources에 keywords 선택 파라미터가 default None으로 존재 — 기존 question-only 호출 무영향."""
    import inspect
    from korean_rnd_regs_mcp.main import suggest_review_sources
    sig = inspect.signature(suggest_review_sources)
    assert "question" in sig.parameters
    assert "keywords" in sig.parameters
    assert sig.parameters["keywords"].default is None


def test_review_prompt_instructs_keyword_array_to_suggest():
    """프롬프트가 LLM에게 검색 키워드 배열을 suggest_review_sources의 keywords로 전달하도록 지시."""
    prompt = review_regulation_prompt("테스트 상황")
    assert "keywords" in prompt
    assert "검색 키워드 배열" in prompt


def test_list_rule_sets_returns_live_api_items():
    """v0.2.6 재편: 보조 법령 6건 제거 + 과기정통부 family 9건 추가 = 28건."""
    result = asyncio.run(list_rule_sets())
    assert "rule_sets" in result
    assert isinstance(result["rule_sets"], list)
    assert result["total"] == 28
    assert len(result["rule_sets"]) == 28
    ids = {rs["id"] for rs in result["rule_sets"]}
    expected = {
        # Tier 1 + 기존 Tier 2 (혁신법 family + 연구개발비 사용 기준)
        "innovation_act", "innovation_decree", "innovation_rule", "rnd_funding_standard",
        # Tier 2 신규 (review-regulations SKILL.md Tier 2 완성)
        "simultaneous_research_limit", "facility_equipment_standard", "research_note_guideline",
        # v0.1.3 — 국토교통 R&D family (혁신법과 함께 적용)
        "sector_kt_act", "sector_kt_decree", "sector_kt_rule", "kt_rnd_operations",
        # v0.2.5 — 산업기술 R&D family (산업통상부)
        "industry_tech_act", "industry_tech_decree", "industry_tech_rule", "industry_tech_operating",
        # v0.2.5 — 중소기업 R&D family (중소벤처기업부)
        "sme_tech_act", "sme_tech_decree", "sme_tech_rule", "sme_rnd_operating",
        # v0.2.6 — 성과평가 family
        "performance_eval_act", "performance_eval_decree",
        # v0.2.6 — 공통 행정규칙 (과기정통부)
        "rnd_info_processing", "rnd_security_measures", "msit_rnd_processing",
        "ict_rnd_management", "ict_research_ethics",
        # v0.2.6 — 기술료 family (산업부·중기부, 소관부처 필터)
        "tech_fee_integrated", "sme_tech_fee",
    }
    assert ids == expected, f"id 불일치: 누락={expected - ids}, 추가={ids - expected}"
    # 모든 항목이 필수 field + v0.2.6 ministry 필드(additive) 노출
    by_id = {rs["id"]: rs for rs in result["rule_sets"]}
    for rs in result["rule_sets"]:
        assert rs["api_target"] in ("law", "admrul")
        assert rs["hierarchy_rank"] in (1, 2, 3, 4, 5, 6)
        assert rs["unit_types"] in ("article", "annex", "both")
        assert "ministry" in rs  # additive 필드 — None 또는 부처명
    assert by_id["tech_fee_integrated"]["ministry"] == "산업통상부"
    assert by_id["innovation_act"]["ministry"] is None


def test_review_regulation_prompt_includes_annex_discovery_guides():
    """v0.2.1: 별표 의존조문 동반조회(dependent_article_hints·1단계 한정) +
    문서레벨 annexes 목록으로 BP 선택(추측 금지) 지시가 프롬프트에 포함."""
    body = review_regulation_prompt("테스트 상황")
    assert "dependent_article_hints" in body
    assert "annexes 목록" in body
    assert "1단계까지만" in body
    assert "추측해 호출하지 말 것" in body


# === v0.2.9: 도구 호출 유도 메타데이터 가드 (Level A — '문구 탑재'만 결정적 검증) ===
# 주의: 아래는 짧고 안정적인 핵심 구절만 단언한다(긴 문장 verbatim 단언은 사소한 리워딩에도
# 깨져 비프로그래머 유지보수에 churn). 실제 '호스트가 도구를 부르는가'(behavior)는 비결정·
# 호스트 의존(Level B)이라 여기서 검증하지 않으며 배포 후 수동 eval(acceptance LEVEL_B_PROMPTS)의 몫.

def test_server_instructions_nudges_tool_call():
    """v0.2.9 #1: FastMCP 서버 instructions가 탑재되고 호출 유도/금지 핵심 구절을 포함."""
    instr = mcp.instructions
    assert instr, "서버 instructions가 비어 있음 — initialize payload 호출 유도 신호 누락"
    assert "일반 학습지식으로 답하지 말고" in instr  # WHEN TO USE (호출 유도)
    assert "호출하지 마십시오" in instr               # WHEN NOT (과호출 차단)


def test_tool_docstrings_include_usage_timing_stanza():
    """v0.2.9 #2: 3개 도구 docstring 첫 문단에 '사용 시점/호출 금지' 스탠자 탑재(도구별 핵심 구절)."""
    import inspect
    from korean_rnd_regs_mcp.main import (
        search_provision,
        suggest_review_sources,
        get_provision_detail,
    )
    sp = inspect.getdoc(search_provision) or ""
    assert "사용 시점" in sp
    assert "일반 학습지식" in sp

    srs = inspect.getdoc(suggest_review_sources) or ""
    assert "사용 시점" in srs
    assert "알려줘" in srs  # 광역 '알려줘' 표현도 호출 대상임을 명시

    gpd = inspect.getdoc(get_provision_detail) or ""
    assert "사용 시점" in gpd
    assert "추측하지 마십시오" in gpd  # provision_id 없이 추측 금지(삭제 여부·현행 내용은 호출로 확인)


def test_contract_version_unchanged_at_0_6_0():
    """v0.2.9는 메타데이터 텍스트만 변경 — 응답 schema 무변이므로 contract 0.6.0 유지."""
    from korean_rnd_regs_mcp.provision_id import CONTRACT_VERSION
    assert CONTRACT_VERSION == "0.6.0"
