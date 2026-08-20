"""v0.51.0: scripts/audit_manifest_effective_dates.py의 classify() 단위 잠금 (네트워크 0).

배포 전 감사 검사("manifest api_doc_id의 lawService 상세 시행일자 > 오늘이면 실패")의 판정
로직이 _is_future_date와 동일 규약(하이픈 정규화·8자리·당일=현행)임을 잠근다. UNKNOWN을
PASS로 오분류하면 감사가 헛통과하므로 3분류 경계를 전수 고정.
"""
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "audit_manifest_effective_dates",
    Path(__file__).resolve().parent.parent / "scripts" / "audit_manifest_effective_dates.py",
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
classify = _MOD.classify


def test_classify_pass_current_and_today():
    assert classify("20260820", "20260821") == "PASS"   # 과거
    assert classify("20260821", "20260821") == "PASS"   # 당일 시행 = 현행
    assert classify("2026-08-20", "20260821") == "PASS"  # 하이픈 정규화


def test_classify_fail_future():
    assert classify("20260911", "20260821") == "FAIL"    # ★C12 실사례(283849 상세 시행일자)
    assert classify("2099-12-31", "20260821") == "FAIL"


def test_classify_unknown_not_pass():
    assert classify(None, "20260821") == "UNKNOWN"
    assert classify("", "20260821") == "UNKNOWN"
    assert classify("2026", "20260821") == "UNKNOWN"
    assert classify("미상", "20260821") == "UNKNOWN"
    assert classify("20260911", "20260821", fetch_error=True) == "UNKNOWN"  # 조회 실패가 우선


def test_classify_invalid_calendar_unknown():
    """8자리 숫자여도 달력 무효(월 13 등)면 UNKNOWN — FAIL(미래 단정) 금지(Codex 조건 5)."""
    assert classify("20261340", "20260821") == "UNKNOWN"
    assert classify("20260231", "20260821") == "UNKNOWN"  # 2월 31일


def test_main_unknown_id_fail_closed(monkeypatch):
    """미인식 rule_set_id 지정 시 '전건 PASS' 헛통과 대신 exit 2 (fail-closed·Codex 조건 2).

    미인식 검증은 네트워크 호출 전에 수행되므로 본 테스트는 오프라인(단위 테스트 규약 준수).
    """
    monkeypatch.setenv("LAW_API_KEY", "unit-test-fake-key")
    assert _MOD.main(["no_such_rule_set"]) == 2          # 전건 미인식
    assert _MOD.main(["innovation_act", "typo_id"]) == 2  # 유효+오타 혼합도 차단
