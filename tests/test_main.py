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


def test_list_rule_sets_returns_stub():
    result = asyncio.run(list_rule_sets())
    assert "rule_sets" in result
    assert isinstance(result["rule_sets"], list)
    assert result["rule_sets"] == []
    assert "note" in result
