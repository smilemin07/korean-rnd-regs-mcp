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
    # verbatim 정책 명시
    assert "verbatim" in body
    assert "임의 부제" in body or "paraphrase 추가 금지" in body


def test_review_regulation_prompt_includes_tier2_and_supplementary_routing():
    """Tier 2 키워드 routing + Supplementary cross-check 안내 포함."""
    body = review_regulation_prompt("X")
    # Tier 2 routing
    assert "rnd_funding_standard" in body
    assert "simultaneous_research_limit" in body
    assert "facility_equipment_standard" in body
    assert "research_note_guideline" in body
    # Supplementary routing
    assert "anti_corruption_act" in body
    assert "improper_solicitation_act" in body
    assert "public_interest_whistleblower_act" in body


def test_review_regulation_prompt_includes_limitation_notice():
    """본 server cover 범위 밖 자료 + 가지조문/별표 한계 명시 (false negative 방지)."""
    body = review_regulation_prompt("X")
    assert "매뉴얼" in body  # 매뉴얼·운영규정·관리지침
    assert "가지조문" in body  # v0.2 deferred
    assert "별표" in body  # v0.3 deferred
    assert "변호사 자문" in body  # 법률 판단 disclaimer


def test_list_rule_sets_returns_live_api_items():
    """v0.1.3 범위: 13건(혁신법 family 4 + Tier 2 행정규칙 3 + Supplementary 6) + 국토교통 family 4 = 17건."""
    result = asyncio.run(list_rule_sets())
    assert "rule_sets" in result
    assert isinstance(result["rule_sets"], list)
    assert result["total"] == 17
    assert len(result["rule_sets"]) == 17
    ids = {rs["id"] for rs in result["rule_sets"]}
    expected = {
        # Tier 1 + 기존 Tier 2 (혁신법 family + 연구개발비 사용 기준)
        "innovation_act", "innovation_decree", "innovation_rule", "rnd_funding_standard",
        # Tier 2 신규 (review-regulations SKILL.md Tier 2 완성)
        "simultaneous_research_limit", "facility_equipment_standard", "research_note_guideline",
        # Supplementary (부패방지·청탁금지·공익신고자보호)
        "anti_corruption_act", "anti_corruption_decree",
        "improper_solicitation_act", "improper_solicitation_decree",
        "public_interest_whistleblower_act", "public_interest_whistleblower_decree",
        # v0.1.3 — 국토교통 R&D family (혁신법과 함께 적용)
        "sector_kt_act", "sector_kt_decree", "sector_kt_rule", "kt_rnd_operations",
    }
    assert ids == expected, f"id 불일치: 누락={expected - ids}, 추가={ids - expected}"
    # 모든 항목이 필수 field. rank 5/6 = Supplementary 법률/시행령 (추가)
    for rs in result["rule_sets"]:
        assert rs["api_target"] in ("law", "admrul")
        assert rs["hierarchy_rank"] in (1, 2, 3, 4, 5, 6)
        assert rs["unit_types"] in ("article", "annex", "both")
