"""scripts/audit_upcoming_enforcement.py의 판정 로직 단위 잠금 (네트워크 0).

"다가오는 시행 예정 판본" 검출 스크립트의 3분류(UPCOMING/NONE/UNKNOWN)가 fail-closed
규약을 지키는지 고정한다. 확인 실패(조회 실패·매칭 0건·날짜 이상)를 NONE으로 격하하면
경보 도구가 거짓 안심을 만들므로, 그 경계를 전수 잠근다. 당일 시행 = 현행(미래 아님)은
live_api._is_future_date와 동일 규약.
"""
import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "audit_upcoming_enforcement.py"
# 감사 스크립트는 저장소(GitHub) 수록물이며 PyPI sdist에는 포함되지 않는다(pyproject sdist include에 scripts/ 없음).
# sdist를 받아 pytest를 돌리는 downstream에서 collection이 깨지지 않도록 부재 시 skip한다(구현 diff 적대검토 Codex).
pytest.importorskip("pydantic")  # 스크립트가 manifest 모듈을 import
if not _SCRIPT.exists():  # pragma: no cover - sdist 배포본 경로
    pytest.skip("scripts/audit_upcoming_enforcement.py 미포함 배포본 — 감사 도구 가드는 저장소에서만 실행", allow_module_level=True)

_SPEC = importlib.util.spec_from_file_location("audit_upcoming_enforcement", _SCRIPT)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
classify_rows = _MOD.classify_rows
exit_code = _MOD.exit_code

TODAY = "20260827"


def _law_row(eff, serial="100001", pub="20260101"):
    return {"법령일련번호": serial, "시행일자": eff, "공포일자": pub, "공포번호": "제1호"}


def test_upcoming_future_row():
    """★골든 패턴: 2026-09-11 도래(283849)와 동형의 미래 행은 UPCOMING."""
    v, future, anomalies = classify_rows(
        [_law_row("20260701"), _law_row("20260911", serial="283849")], TODAY)
    assert v == "UPCOMING"
    assert [r["법령일련번호"] for r in future] == ["283849"]
    assert anomalies == 0


def test_today_is_current_not_upcoming():
    """당일 시행 = 현행 — _is_future_date 규약(> 비교)과 동일."""
    v, future, _ = classify_rows([_law_row(TODAY)], TODAY)
    assert v == "NONE" and future == []


def test_none_only_past_rows():
    v, future, _ = classify_rows([_law_row("20250101"), _law_row("2026-07-01")], TODAY)
    assert v == "NONE" and future == []


def test_hyphen_normalization_future():
    v, future, _ = classify_rows([_law_row("2026-09-11")], TODAY)
    assert v == "UPCOMING" and len(future) == 1


def test_unknown_on_fetch_error():
    """조회 실패는 미래 행이 보여도 UNKNOWN — 실패를 판정에 쓰지 않는다."""
    v, future, _ = classify_rows([_law_row("20260911")], TODAY, fetch_error=True)
    assert v == "UNKNOWN" and future == []


def test_unknown_on_zero_matched_rows():
    """매칭 행 0건 = 규정 자체를 못 찾음(제목·부처 변경 가능성) — NONE 격하 금지."""
    assert classify_rows([], TODAY)[0] == "UNKNOWN"


def test_unknown_on_anomalous_date_without_future():
    """날짜 형식·달력 무효 행이 있으면 '예정 없음'을 보증할 수 없다 — UNKNOWN."""
    for bad in ("", "2026", "미상", "20261340", "20260231", None):
        v, _, anomalies = classify_rows([_law_row("20250101"), _law_row(bad)], TODAY)
        assert v == "UNKNOWN", bad
        assert anomalies == 1


def test_upcoming_wins_over_anomaly():
    """유효 미래 행이 있으면 이상 행이 있어도 경보(UPCOMING)가 우선 — 이상 행 수는 보고."""
    v, future, anomalies = classify_rows(
        [_law_row("20260911"), _law_row("미상")], TODAY)
    assert v == "UPCOMING" and len(future) == 1 and anomalies == 1


def test_future_rows_deduped_and_sorted():
    v, future, _ = classify_rows(
        [_law_row("20261001", serial="B"), _law_row("20260911", serial="A"),
         _law_row("20260911", serial="A")], TODAY)
    assert v == "UPCOMING"
    assert [(r["법령일련번호"], r["시행일자"]) for r in future] == [("A", "20260911"), ("B", "20261001")]


def test_admrul_serial_key():
    """admrul 행(행정규칙일련번호)도 중복 제거 키로 인식."""
    rows = [{"행정규칙일련번호": "2100000000001", "시행일자": "20261001"},
            {"행정규칙일련번호": "2100000000001", "시행일자": "20261001"}]
    v, future, _ = classify_rows(rows, TODAY)
    assert v == "UPCOMING" and len(future) == 1


def test_exit_code_priority():
    assert exit_code({"UPCOMING": 1, "NONE": 60, "UNKNOWN": 5}) == 3   # 경보 우선
    assert exit_code({"UPCOMING": 0, "NONE": 60, "UNKNOWN": 1}) == 2
    assert exit_code({"UPCOMING": 0, "NONE": 66, "UNKNOWN": 0}) == 0


def test_main_unknown_id_fail_closed(monkeypatch):
    """미인식 rule_set_id 지정 시 '전건 NONE' 헛통과 대신 exit 2 (fail-closed).

    미인식 검증은 네트워크 호출 전에 수행되므로 본 테스트는 오프라인(단위 테스트 규약 준수).
    """
    monkeypatch.setenv("LAW_API_KEY", "unit-test-fake-key")
    assert _MOD.main(["no_such_rule_set"]) == 2
    assert _MOD.main(["innovation_act", "typo_id"]) == 2


def test_main_missing_key_returns_2(monkeypatch):
    monkeypatch.delenv("LAW_API_KEY", raising=False)
    monkeypatch.setattr(_MOD, "load_dotenv", lambda *a, **k: None)
    assert _MOD.main([]) == 2


def test_hyphenated_today_normalized():
    """★diff 적대검토 조건 1(Gemini): today가 하이픈 포맷이어도 문자 비교가 오염되지 않는다.

    미정규화 시 "20260101" > "2026-08-27"이 참이 되어 과거 행이 UPCOMING으로 오판된다.
    """
    v, future, _ = classify_rows([_law_row("20260101")], "2026-08-27")
    assert v == "NONE" and future == []
    v2, future2, _ = classify_rows([_law_row("20260911")], "2026-08-27")
    assert v2 == "UPCOMING" and len(future2) == 1


def test_fetch_rows_truncation_fail_closed(monkeypatch):
    """★diff 적대검토 조건 3(Gemini): 페이지 상한 도달 + 미탐색 행 잔존 시 침묵 NONE이 아니라
    RuntimeError(search_truncated) → 호출부에서 UNKNOWN 귀결 (네트워크 0 — 헬퍼 스텁)."""
    import types
    import xml.etree.ElementTree as ET

    import korean_rnd_regs_mcp.live_api as live_api

    def fake_request(url, params, **kw):
        return None  # _parse_xml을 함께 스텁하므로 미사용

    def fake_parse(_resp):
        root = ET.Element("root")
        ET.SubElement(root, "totalCnt").text = "2000"  # _PAGE_CAP(10)×100보다 큼 = 절단 상황
        for _ in range(100):
            e = ET.SubElement(root, "law")
            ET.SubElement(e, "법령명한글").text = "무관한 다른 법령"
        return root

    monkeypatch.setattr(live_api, "_request_with_retry", fake_request)
    monkeypatch.setattr(live_api, "_parse_xml", fake_parse)
    client = types.SimpleNamespace(
        base_url="https://unit.test", api_key="unit-test-fake-key",
        _normalize_title=staticmethod(lambda t: t.replace(" ", "")),
        _ministry_matches=staticmethod(lambda w, g: True),
    )
    rs = types.SimpleNamespace(
        api_target=types.SimpleNamespace(value="law"), title="표적 법령", ministry=None)
    import pytest
    with pytest.raises(RuntimeError, match="search_truncated"):
        _MOD._fetch_rows(client, rs)


def test_page_gap_fail_closed(monkeypatch):
    """★diff 적대검토 Codex MAJOR 1: 중간 빈 페이지(seen < total)를 부분 성공으로 돌려주면
    과거 행만 남아 거짓 NONE이 된다 — RuntimeError(search_page_gap)로 승격돼야 한다."""
    import types
    import xml.etree.ElementTree as ET

    import korean_rnd_regs_mcp.live_api as live_api

    pages = []

    def make_page(n_items):
        root = ET.Element("root")
        ET.SubElement(root, "totalCnt").text = "200"
        for _ in range(n_items):
            e = ET.SubElement(root, "law")
            ET.SubElement(e, "법령명한글").text = "표적 법령"
            ET.SubElement(e, "시행일자").text = "20250101"  # 과거 행만
        return root

    pages.extend([make_page(100), make_page(0)])  # 2페이지가 빈 페이지 (seen 100 < total 200)
    monkeypatch.setattr(live_api, "_request_with_retry", lambda *a, **k: None)
    monkeypatch.setattr(live_api, "_parse_xml", lambda _r: pages.pop(0))
    client = types.SimpleNamespace(
        base_url="https://unit.test", api_key="unit-test-fake-key",
        _normalize_title=staticmethod(lambda t: t.replace(" ", "")),
        _ministry_matches=staticmethod(lambda w, g: True),
    )
    rs = types.SimpleNamespace(
        api_target=types.SimpleNamespace(value="law"), title="표적 법령", ministry=None)
    with pytest.raises(RuntimeError, match="search_page_gap"):
        _MOD._fetch_rows(client, rs)


def test_exit_code_empty_counts_not_zero():
    """집계 0건은 '전건 NONE'이 아니다(Codex MINOR) — 2(확인 불가)로."""
    assert exit_code({}) == 2
    assert exit_code({"UPCOMING": 0, "NONE": 0, "UNKNOWN": 0}) == 2


def test_same_serial_two_stage_both_kept():
    """★골든 패턴 보강: 288335처럼 한 일련번호가 2단계 시행(9-11·2027-01-01)이면 둘 다 보존."""
    v, future, _ = classify_rows(
        [_law_row("20260911", serial="288335"), _law_row("20270101", serial="288335")], TODAY)
    assert v == "UPCOMING"
    assert [(r["법령일련번호"], r["시행일자"]) for r in future] == [
        ("288335", "20260911"), ("288335", "20270101")]


def test_missing_serial_rows_not_merged():
    """일련번호 누락 행은 식별 불가이므로 서로 합치지 않는다(Codex MINOR)."""
    rows = [{"시행일자": "20261001"}, {"시행일자": "20261001"}]
    v, future, _ = classify_rows(rows, TODAY)
    assert v == "UPCOMING" and len(future) == 2


def test_whitelist_excludes_link_fields():
    """키 누설 잠금: 화이트리스트에 '링크' 계열 필드(API가 OC 키 원문 삽입)가 절대 없어야 한다."""
    for f in _MOD.LAW_ROW_FIELDS + _MOD.ADMRUL_ROW_FIELDS:
        assert "링크" not in f, f
