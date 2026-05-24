"""Unit tests for health and list_rule_sets — no network, no live API."""
import asyncio
import json

from korean_rnd_regs_mcp import __version__
from korean_rnd_regs_mcp.main import health, list_rule_sets


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


def test_list_rule_sets_returns_live_api_items():
    """Step 20 입력 후: 혁신법 본법·시행령·시행규칙 + 연구개발비 사용 기준 = 4건."""
    result = asyncio.run(list_rule_sets())
    assert "rule_sets" in result
    assert isinstance(result["rule_sets"], list)
    assert result["total"] == 4
    assert len(result["rule_sets"]) == 4
    ids = {rs["id"] for rs in result["rule_sets"]}
    assert ids == {"innovation_act", "innovation_decree", "innovation_rule", "rnd_funding_standard"}
    # 모든 항목이 필수 field
    for rs in result["rule_sets"]:
        assert rs["api_target"] in ("law", "admrul")
        assert rs["hierarchy_rank"] in (1, 2, 3, 4)
        assert rs["unit_types"] in ("article", "annex", "both")
