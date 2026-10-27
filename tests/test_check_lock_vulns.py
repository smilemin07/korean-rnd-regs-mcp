"""scripts/check_lock_vulns.py 가드 (네트워크 0) — 2026-10-28 주간 취약점 확인."""
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_lock_vulns.py"
if not _SCRIPT.exists():  # pragma: no cover - sdist 배포본 경로
    pytest.skip("scripts/check_lock_vulns.py 미포함 배포본", allow_module_level=True)

_SPEC = importlib.util.spec_from_file_location("check_lock_vulns", _SCRIPT)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)


def test_parse_lock_reads_pins_and_skips_comments():
    text = "# 머리말\n\nmcp==1.29.0\ncertifi==2026.7.22\n"
    assert _MOD.parse_lock(text) == [("mcp", "1.29.0"), ("certifi", "2026.7.22")]


def test_parse_lock_rejects_unpinned_line():
    with pytest.raises(ValueError):
        _MOD.parse_lock("mcp>=1.29\n")


def test_parse_lock_rejects_empty():
    with pytest.raises(ValueError):
        _MOD.parse_lock("# 주석만\n")


def test_real_lock_parses():
    """저장소의 실제 lock이 해석된다(형식 결박)."""
    pins = _MOD.parse_lock(_MOD.LOCK.read_text(encoding="utf-8"))
    assert len(pins) >= 1


def test_query_osv_maps_results():
    pins = [("a", "1"), ("b", "2")]
    fake = lambda url, q: {"results": [{"vulns": [{"id": "GHSA-x"}]}, {}]}
    assert _MOD.query_osv(pins, post=fake) == {"a==1": ["GHSA-x"]}


def test_query_osv_fails_closed_on_count_mismatch():
    with pytest.raises(ValueError):
        _MOD.query_osv([("a", "1"), ("b", "2")], post=lambda url, q: {"results": [{}]})


def test_query_osv_fails_closed_on_paging():
    fake = lambda url, q: {"results": [{"vulns": [{"id": "X"}], "next_page_token": "t"}]}
    with pytest.raises(ValueError):
        _MOD.query_osv([("a", "1")], post=fake)


def test_new_findings_excludes_reviewed():
    found = {"a==1": ["R1", "N1"], "b==2": ["R2"]}
    assert _MOD.new_findings(found, {"R1": {}, "R2": {}}) == {"a==1": ["N1"]}


def test_reviewed_file_is_valid():
    reviewed = _MOD.load_reviewed()
    assert reviewed and all(isinstance(v, dict) and v.get("decision") for v in reviewed.values())


def test_main_returns_2_on_query_error(monkeypatch, capsys):
    def boom(pins):
        raise OSError("네트워크 없음")

    monkeypatch.setattr(_MOD, "query_osv", boom)
    assert _MOD.main([]) == 2
    assert "오류" in capsys.readouterr().out


def test_load_reviewed_rejects_bad_shape(tmp_path):
    bad = tmp_path / "r.json"
    bad.write_text(json.dumps({"reviewed": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        _MOD.load_reviewed(bad)


def test_describe_survives_malformed_detail():
    """상세 응답 형식이 어긋나도 예외 없이 ID를 남긴다(알림 누락 방지)."""
    bad = {"summary": None, "affected": [{"ranges": [{"events": None}]}]}
    assert _MOD.describe("GHSA-x", get=lambda url: bad).startswith("GHSA-x")
    assert _MOD.describe("GHSA-y", get=lambda url: ["x"]) == "GHSA-y (상세 조회 실패)"


def test_main_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(_MOD, "load_reviewed", lambda: {"OLD": {"decision": "x"}})
    monkeypatch.setattr(_MOD, "describe", lambda vid: vid)
    monkeypatch.setattr(_MOD, "query_osv", lambda pins: {"a==1": ["OLD"]})
    assert _MOD.main([]) == 0
    monkeypatch.setattr(_MOD, "query_osv", lambda pins: {"a==1": ["OLD", "NEW"]})
    assert _MOD.main([]) == 1
    assert "NEW" in capsys.readouterr().out
