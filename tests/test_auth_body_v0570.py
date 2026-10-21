"""v0.57.0 「틀린 API Key 판별과 조용한 구판 폴백 기록」 가드 — 네트워크 0.

잠그는 불변식:
  1) 본문 인증 오류 판별: 루트 Response + result 전문 일치일 때만 auth_failed. 정상 루트 6종·result 부재·
     다른 문구·유사 문구는 판별하지 않는다(오탐 = 전 이용자 장애이므로 경계 고정).
  2) auth_failed도 요청 단위 300초 기억(종전 not_found 300초 기억과 같은 재호출 억제).
  3) 검색 fan-out: 인증 오류는 1건으로 합치고(규정 수 표기), 응답 모양·footer는 그대로, 다른 오류는 규정별.
  4) suggest: 합쳐진 인증 오류는 1건만, keyword 없이.
  5) resolve 폴백 경고: 일치 0행 경로에 WARNING(제목·첫 행 제목) · auth_failed는 규정별 경고 생략 ·
     (target, 제목, 사유)당 1시간 1회 · 외부 제목은 제어문자 제거·80자.
  6) 요약 로그: errors_count는 합치기 전 수(종전 의미) + resolve_failed·auth_failed 계수.
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

import korean_rnd_regs_mcp.live_api as LA
from korean_rnd_regs_mcp import main as main_module
from korean_rnd_regs_mcp.live_api import (
    AUTH_FAILED_BODY_MESSAGE, ERROR_AUTH_FAILED, LawApiClient, LawApiError, ResolvedDocId,
    _MAX_RETRIES, _REQUEST_TIMEOUT,
)

# 2026-10-21 가짜 키 실측 본문(6개 엔드포인트 동일)
_AUTH_BODY = (
    '<?xml version="1.0" encoding="UTF-8"?>\n    <Response>\n'
    "        <result>사용자 정보 검증에 실패하였습니다.</result>\n"
    "        <msg>OPEN API 호출 시 사용자 검증을 위하여 정확한 서버장비의 IP주소 및 도메인주소를 등록해 주세요.</msg>\n"
    "    </Response>\n"
)


class _Resp:
    def __init__(self, text, ctype="application/xml;charset=UTF-8"):
        self.status_code, self.text, self.content = 200, text, text.encode()
        self.headers = {"Content-Type": ctype}


@pytest.fixture(autouse=True)
def _reset_warn_throttle():
    LA._resolve_warn_last.clear()
    yield
    LA._resolve_warn_last.clear()


@pytest.fixture
def client():
    return LawApiClient(env_override={"LAW_API_KEY": "fake_key_for_test",
                                      "LAW_API_URL": "https://test.invalid/DRF"})


def _spy(monkeypatch, handler):
    calls = []

    def fake(url, params, max_retries=_MAX_RETRIES, timeout=_REQUEST_TIMEOUT):
        calls.append(params.get("target"))
        return handler(params)
    monkeypatch.setattr(LA, "_request_with_retry", fake)
    return calls


# ── 1) 판별 경계
def test_auth_body_is_auth_failed():
    with pytest.raises(LawApiError) as ei:
        LA._parse_xml(_Resp(_AUTH_BODY))
    assert ei.value.code == ERROR_AUTH_FAILED
    assert ei.value.message == AUTH_FAILED_BODY_MESSAGE


@pytest.mark.parametrize("body", [
    '<LawSearch><target>law</target><totalCnt>0</totalCnt></LawSearch>',
    '<AdmRulSearch><totalCnt>0</totalCnt></AdmRulSearch>',
    '<법령><기본정보/></법령>',
    '<Law></Law>',
    '<Law/>',
    '<AdmRulService><행정규칙기본정보/></AdmRulService>',
    '<OldAndNewService/>',
])
def test_valid_roots_never_auth(body):
    """정상 응답 루트 6종(2026-10-21 실측)은 판별 분기에 들어오지 않는다."""
    root = LA._parse_xml(_Resp(body))
    assert isinstance(root, ET.Element)


@pytest.mark.parametrize("body", [
    "<Response/>",                                               # result 부재 → None 방어
    "<Response><result></result></Response>",                   # 빈 result
    "<Response><result>일치하는 법령이 없습니다.</result></Response>",  # 다른 문구 — 근거 없어 분기 없음
    "<Response><result>사용자 정보 검증에 실패하지 않았습니다.</result></Response>",  # 유사 문구(부분일치 금지)
    "<LawSearch><result>사용자 정보 검증에 실패하였습니다.</result></LawSearch>",    # 정상 루트 안의 같은 문구
])
def test_non_matching_shapes_keep_current_behaviour(body):
    root = LA._parse_xml(_Resp(body))
    assert isinstance(root, ET.Element)


def test_auth_message_has_no_key_and_no_delete_instruction():
    assert "fake_key_for_test" not in AUTH_FAILED_BODY_MESSAGE
    assert "비워" not in AUTH_FAILED_BODY_MESSAGE and "삭제" not in AUTH_FAILED_BODY_MESSAGE
    assert "oc=" in AUTH_FAILED_BODY_MESSAGE and "LAW_API_KEY" in AUTH_FAILED_BODY_MESSAGE


# ── 2) 300초 기억
def test_auth_failed_search_is_remembered(client, monkeypatch):
    calls = _spy(monkeypatch, lambda p: _Resp(_AUTH_BODY))
    for _ in range(3):
        with pytest.raises(LawApiError) as ei:
            client.search_laws("국가연구개발혁신법")
        assert ei.value.code == ERROR_AUTH_FAILED
    assert calls == ["law"], "두 번째부터는 실패 기억에서 반환(네트워크 0)"


def test_auth_failed_admin_detail_is_remembered(client, monkeypatch):
    calls = _spy(monkeypatch, lambda p: _Resp(_AUTH_BODY))
    for _ in range(2):
        with pytest.raises(LawApiError) as ei:
            client.get_admin_rule_detail("2100000285280")
        assert ei.value.code == ERROR_AUTH_FAILED
    assert calls == ["admrul"]


def test_auth_failure_cache_is_per_client(monkeypatch):
    """키를 고치면 새 클라이언트 — 틀린 키의 실패 기억이 따라오지 않는다."""
    bad = LawApiClient(env_override={"LAW_API_KEY": "bad", "LAW_API_URL": "https://test.invalid/DRF"})
    good = LawApiClient(env_override={"LAW_API_KEY": "good", "LAW_API_URL": "https://test.invalid/DRF"})
    monkeypatch.setattr(LA, "_request_with_retry",
                        lambda url, params, **kw: _Resp(_AUTH_BODY if params["OC"] == "bad"
                                                        else '<LawSearch><totalCnt>1</totalCnt>'
                                                             '<law><법령명한글>국가연구개발혁신법</법령명한글>'
                                                             '<법령일련번호>290757</법령일련번호></law></LawSearch>'))
    with pytest.raises(LawApiError):
        bad.search_laws("국가연구개발혁신법")
    assert good.search_laws("국가연구개발혁신법").items[0].doc_id == "290757"


# ── 5) resolve 폴백 경고
def test_resolve_auth_failure_falls_back_without_per_rule_warning(client, monkeypatch, caplog):
    _spy(monkeypatch, lambda p: _Resp(_AUTH_BODY))
    with caplog.at_level(logging.WARNING, logger="rnd-regs-mcp.live_api"):
        r = client.resolve_latest_doc_id("국가연구개발혁신법", "law", "290757")
    assert r.resolve_failed and r.doc_id == "290757", "목록 미신청 키의 manifest ID 서빙 보존"
    assert not [m for m in caplog.messages if "resolve_latest_doc_id" in m]


def _search_xml(title):
    return ('<AdmRulSearch><totalCnt>1</totalCnt><admrul>'
            f'<행정규칙일련번호>2100000285280</행정규칙일련번호><행정규칙명>{title}</행정규칙명>'
            '<소관부처명>과학기술정보통신부</소관부처명><시행일자>20260918</시행일자>'
            '</admrul></AdmRulSearch>')


def test_zero_row_fallback_warns_with_first_row_title(client, monkeypatch, caplog):
    """처리규정 제목 변경형: 구 제목 검색이 새 제목 1행을 돌려줘 일치 0행 → 경고에 두 제목."""
    _spy(monkeypatch, lambda p: _Resp(_search_xml("과학기술정보통신부 과학기술분야 연구개발사업처리규정")))
    with caplog.at_level(logging.WARNING, logger="rnd-regs-mcp.live_api"):
        r = client.resolve_latest_doc_id(
            "과학기술정보통신부 소관 과학기술분야 연구개발사업 처리규정", "admrul", "2100000228284",
            ministry="과학기술정보통신부")
    assert r.resolve_failed
    hits = [m for m in caplog.messages if "정확일치 0행" in m]
    assert len(hits) == 1
    assert "rows=1" in hits[0] and "first_row_title=과학기술정보통신부 과학기술분야 연구개발사업처리규정" in hits[0]


def test_zero_row_warning_throttled_across_clients(monkeypatch, caplog):
    """같은 (target, 제목, 사유)는 다른 키(클라이언트)여도 1시간에 1회."""
    _spy(monkeypatch, lambda p: _Resp(_search_xml("다른 제목")))
    with caplog.at_level(logging.WARNING, logger="rnd-regs-mcp.live_api"):
        for key in ("k1", "k2", "k3"):
            c = LawApiClient(env_override={"LAW_API_KEY": key, "LAW_API_URL": "https://test.invalid/DRF"})
            c.resolve_latest_doc_id("구 제목", "admrul", "1")
    assert len([m for m in caplog.messages if "정확일치 0행" in m]) == 1


def test_warn_throttle_expires_and_is_bounded(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(LA.time, "monotonic", lambda: t[0])
    assert LA._resolve_warn_due("admrul", "제목", "zero_rows") is True
    assert LA._resolve_warn_due("admrul", "제목", "zero_rows") is False
    assert LA._resolve_warn_due("admrul", "제목", "parse_failed") is True, "사유가 다르면 숨기지 않는다"
    t[0] += LA._RESOLVE_WARN_INTERVAL_S
    assert LA._resolve_warn_due("admrul", "제목", "zero_rows") is True
    for i in range(LA._RESOLVE_WARN_MAX_KEYS + 5):
        LA._resolve_warn_due("law", f"t{i}", "zero_rows")
    assert len(LA._resolve_warn_last) <= LA._RESOLVE_WARN_MAX_KEYS


def test_pending_only_is_not_warned(client, monkeypatch, caplog):
    """미래 시행 행만 있는 정상 폴백(resolve_failed False)은 경고하지 않는다."""
    xml = ('<AdmRulSearch><totalCnt>1</totalCnt><admrul><행정규칙일련번호>9</행정규칙일련번호>'
           '<행정규칙명>규정</행정규칙명><시행일자>20991231</시행일자></admrul></AdmRulSearch>')
    _spy(monkeypatch, lambda p: _Resp(xml))
    with caplog.at_level(logging.WARNING, logger="rnd-regs-mcp.live_api"):
        r = client.resolve_latest_doc_id("규정", "admrul", "1")
    assert not r.resolve_failed and r.pending_doc_id == "9"
    assert not [m for m in caplog.messages if "정확일치 0행" in m]


def test_log_safe_title_strips_control_chars():
    assert LA._log_safe_title("가\n나\r다\x00라" + "마" * 200) == ("가 나 다 라" + "마" * 200)[:80]
    assert LA._log_safe_title("") == ""


# ── 3·4·6) main fan-out 합치기
@pytest.fixture
def mock_client(monkeypatch):
    c = MagicMock(spec=LawApiClient)
    c.api_key = "fake_secret_key_xyz_2099"
    c.resolve_latest_doc_id.side_effect = lambda title, api_target, manifest_doc_id, ministry=None: (
        ResolvedDocId(doc_id=manifest_doc_id, effective_date="", is_updated=False,
                      manifest_doc_id=manifest_doc_id))
    c.get_law_detail_staged.side_effect = lambda mst, efyd="", expected_title="": (
        c.get_law_detail(mst), "law")
    monkeypatch.setattr(main_module, "_client_instance", c)
    return c


def _auth_err():
    return LawApiError(ERROR_AUTH_FAILED, AUTH_FAILED_BODY_MESSAGE)


def test_all_auth_failed_merges_to_one_entry(mock_client, caplog):
    mock_client.get_law_detail.side_effect = _auth_err()
    mock_client.get_admin_rule_detail.side_effect = _auth_err()
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        r = asyncio.run(main_module.search_provision("특별평가"))
    auth = [e for e in r["errors"] if e["code"] == "auth_failed"]
    assert len(r["errors"]) == 1 and len(auth) == 1
    assert "rule_set_id" not in auth[0]
    n_law = sum(1 for rs in main_module.load_manifest() if rs.api_target.value == "law")
    n_adm = len(main_module.load_manifest()) - n_law
    assert auth[0]["message"].startswith(AUTH_FAILED_BODY_MESSAGE)
    assert f"법령 {n_law}·행정규칙 {n_adm}개 규정" in auth[0]["message"]
    # 응답 모양·footer 유지(§5.31 — 전건 fan-out 오류 envelope에도 부착)
    for k in ("query", "total", "returned", "truncated", "results", "standard_footer"):
        assert k in r, k
    assert r["total"] == 0 and r["results"] == []
    summary = [m for m in caplog.messages if "event=search_fanout_summary" in m][-1]
    total = n_law + n_adm
    assert f"errors_count={total}" in summary, "합치기 전 수(종전 의미)"
    assert f"auth_failed={total}" in summary and "resolve_failed=0" in summary
    assert not [m for m in caplog.messages if "detail 실패" in m], "auth는 규정별 경고 생략"


def test_partial_auth_keeps_results_and_other_errors(mock_client):
    """부분 권한 키(행정규칙만 거부) + 다른 오류 혼합: 결과·다른 오류는 그대로, 인증 오류만 1건."""
    mock_client.get_law_detail.side_effect = None
    mock_client.get_law_detail.return_value = {
        "법령명한글": "국가연구개발혁신법", "시행일자": "20260611",
        "articles": [{"조문번호": "15", "조문제목": "특별평가", "조문내용": "제15조(특별평가) 특별평가 본문",
                      "structured": {"title": "제15조(특별평가)", "paragraphs": []}}],
    }

    def admrul(doc_id):
        if doc_id.endswith("0"):
            raise LawApiError("parse_failed", "synthetic")
        raise _auth_err()
    mock_client.get_admin_rule_detail.side_effect = admrul
    r = asyncio.run(main_module.search_provision("특별평가"))
    assert r["total"] >= 1 and r["results"]
    auth = [e for e in r["errors"] if e["code"] == "auth_failed"]
    others = [e for e in r["errors"] if e["code"] != "auth_failed"]
    assert len(auth) == 1 and r["errors"][0] is auth[0], "합친 항목은 맨 앞"
    assert "법령 0·행정규칙" in auth[0]["message"]
    assert others and all("rule_set_id" in e for e in others), "다른 오류는 규정별 유지"


def test_no_auth_errors_unchanged(mock_client):
    """인증 오류가 없으면 종전과 같다(합친 항목 없음)."""
    mock_client.get_law_detail.side_effect = LawApiError("parse_failed", "synthetic")
    mock_client.get_admin_rule_detail.side_effect = LawApiError("parse_failed", "synthetic")
    r = asyncio.run(main_module.search_provision("특별평가"))
    assert r["errors"] and all("rule_set_id" in e for e in r["errors"])
    assert not [e for e in r["errors"] if e["code"] == "auth_failed"]


def test_suggest_keeps_single_auth_entry_without_keyword(mock_client):
    mock_client.get_law_detail.side_effect = _auth_err()
    mock_client.get_admin_rule_detail.side_effect = _auth_err()
    r = asyncio.run(main_module.suggest_review_sources(
        "특별평가 사유는?", keywords=["특별평가", "제재처분", "연구개발비"]))
    auth = [e for e in r.get("errors", []) if e["code"] == "auth_failed"]
    assert len(auth) == 1 and "keyword" not in auth[0]
    assert len(r["errors"]) == 1


def test_resolve_failed_counted_in_summary(mock_client, caplog):
    mock_client.resolve_latest_doc_id.side_effect = lambda title, api_target, manifest_doc_id, ministry=None: (
        ResolvedDocId(doc_id=manifest_doc_id, effective_date="", is_updated=False,
                      manifest_doc_id=manifest_doc_id, resolve_failed=True))
    mock_client.get_law_detail.side_effect = LawApiError("parse_failed", "synthetic")
    mock_client.get_admin_rule_detail.side_effect = LawApiError("parse_failed", "synthetic")
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        asyncio.run(main_module.search_provision("특별평가"))
    summary = [m for m in caplog.messages if "event=search_fanout_summary" in m][-1]
    n = len(main_module.load_manifest())
    assert f"resolve_failed={n}" in summary and "auth_failed=0" in summary


def test_merged_auth_error_masks_key(monkeypatch):
    monkeypatch.setenv("LAW_API_KEY", "leakme123456")
    rs = MagicMock()
    rs.api_target = main_module.ApiTarget.LAW
    e = main_module._merged_auth_error([(rs, LawApiError(ERROR_AUTH_FAILED, "bad leakme123456"))])
    assert "leakme123456" not in e["message"] and "법령 1·행정규칙 0개 규정" in e["message"]


# ── 구현 diff 적대검토 반영(Codex·Gemini·Grok·Fable·change-verify)
def test_result_with_child_element_is_not_auth():
    """findtext는 자식 텍스트를 무시하므로 자식이 붙은 result는 전문 일치로 볼 수 없다(Codex)."""
    body = "<Response><result>사용자 정보 검증에 실패하였습니다.<detail>추가</detail></result></Response>"
    assert isinstance(LA._parse_xml(_Resp(body)), ET.Element)


def test_warn_throttle_overflow_evicts_oldest_not_all(monkeypatch):
    """상한 도달 시 전체 비움 금지 — 다른 키의 억제가 풀리지 않는다(Codex·Gemini)."""
    t = [0.0]
    monkeypatch.setattr(LA.time, "monotonic", lambda: t[0])
    for i in range(LA._RESOLVE_WARN_MAX_KEYS):
        t[0] += 0.001
        LA._resolve_warn_due("law", f"t{i}", "zero_rows")
    t[0] += 0.001
    assert LA._resolve_warn_due("law", "new", "zero_rows") is True
    assert ("law", "t0", "zero_rows") not in LA._resolve_warn_last, "가장 오래된 1건만 축출"
    assert LA._resolve_warn_due("law", "t5", "zero_rows") is False, "나머지는 계속 억제"
    assert len(LA._resolve_warn_last) == LA._RESOLVE_WARN_MAX_KEYS


def test_merged_message_uses_most_common_guidance():
    law, adm = MagicMock(), MagicMock()
    law.api_target, adm.api_target = main_module.ApiTarget.LAW, main_module.ApiTarget.ADMRUL
    errs = [(law, LawApiError(ERROR_AUTH_FAILED, "HTTP 401 문구"))] + \
           [(adm, LawApiError(ERROR_AUTH_FAILED, AUTH_FAILED_BODY_MESSAGE))] * 3
    e = main_module._merged_auth_error(errs)
    assert e["message"].startswith(AUTH_FAILED_BODY_MESSAGE)
    assert "법령 1·행정규칙 3개 규정" in e["message"]


def _summary(caplog):
    return [m for m in caplog.messages if "event=search_fanout_summary" in m][-1]


def test_list_only_rejected_key_counts_auth_not_resolve_failed(mock_client, caplog):
    """목록 API만 거부(resolve 인증 실패)·상세 성공: 응답 무오류(manifest ID 서빙) + 요약 auth_failed에 잡힘,
    resolve_failed(구판 서빙 신호)에는 안 잡힘(Gemini·Fable)."""
    mock_client.resolve_latest_doc_id.side_effect = lambda title, api_target, manifest_doc_id, ministry=None: (
        ResolvedDocId(doc_id=manifest_doc_id, effective_date="", is_updated=False,
                      manifest_doc_id=manifest_doc_id, resolve_failed=True,
                      resolve_error_code=ERROR_AUTH_FAILED))
    mock_client.get_law_detail.side_effect = None
    mock_client.get_law_detail.return_value = {"articles": [], "annexes": []}
    mock_client.get_admin_rule_detail.side_effect = None
    mock_client.get_admin_rule_detail.return_value = {"articles": [], "annexes": []}
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        r = asyncio.run(main_module.search_provision("특별평가"))
    assert not [e for e in (r.get("errors") or []) if e["code"] == "auth_failed"]
    n = len(main_module.load_manifest())
    s = _summary(caplog)
    assert "resolve_failed=0" in s and f"auth_failed={n}" in s


def test_zero_row_resolve_counts_as_resolve_failed(mock_client, caplog):
    mock_client.resolve_latest_doc_id.side_effect = lambda title, api_target, manifest_doc_id, ministry=None: (
        ResolvedDocId(doc_id=manifest_doc_id, effective_date="", is_updated=False,
                      manifest_doc_id=manifest_doc_id, resolve_failed=True, resolve_error_code="zero_rows"))
    mock_client.get_law_detail.side_effect = None
    mock_client.get_law_detail.return_value = {"articles": [], "annexes": []}
    mock_client.get_admin_rule_detail.side_effect = None
    mock_client.get_admin_rule_detail.return_value = {"articles": [], "annexes": []}
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        asyncio.run(main_module.search_provision("특별평가"))
    n = len(main_module.load_manifest())
    assert f"resolve_failed={n}" in _summary(caplog) and "auth_failed=0" in _summary(caplog)


def test_budget_skip_mixed_with_auth(mock_client, monkeypatch, caplog):
    """예산 초과 skip + 인증 오류 혼합: 합친 1건이 맨 앞, timeout은 규정별, 취소된 규정은 계수 제외(Grok·Fable)."""
    import time as _time
    monkeypatch.setattr(main_module, "_FANOUT_BUDGET_S", 0.3)
    mock_client.get_law_detail.side_effect = _auth_err()

    def slow_admrul(doc_id):
        _time.sleep(0.6)
        raise _auth_err()
    mock_client.get_admin_rule_detail.side_effect = slow_admrul
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        r = asyncio.run(main_module.search_provision("특별평가"))
    n_law = sum(1 for rs in main_module.load_manifest() if rs.api_target.value == "law")
    assert r["errors"][0]["code"] == "auth_failed" and "rule_set_id" not in r["errors"][0]
    assert f"법령 {n_law}·행정규칙 0개 규정" in r["errors"][0]["message"]
    timeouts = [e for e in r["errors"] if e["code"] == "timeout"]
    assert timeouts and all("rule_set_id" in e for e in timeouts)
    assert f"auth_failed={n_law}" in _summary(caplog)


def test_suggest_keywordless_fallback_keeps_single_auth(mock_client):
    """keywords 없이(서버 추출 경로) 호출해도 합친 인증 오류는 1건·keyword 없음(Gemini 확인 요청)."""
    mock_client.get_law_detail.side_effect = _auth_err()
    mock_client.get_admin_rule_detail.side_effect = _auth_err()
    r = asyncio.run(main_module.suggest_review_sources("연구개발비 정산과 제재처분 기준은?"))
    auth = [e for e in r.get("errors", []) if e["code"] == "auth_failed"]
    assert len(auth) == 1 and "keyword" not in auth[0]


def _runner():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "acc_run_v0570", Path(__file__).parent / "acceptance" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("resp,expected", [
    ({"results": [], "errors": [{"code": "auth_failed", "message": "m"}]}, True),
    ({"results": [], "errors": [{"code": "auth_failed", "message": "m"},
                                {"rule_set_id": "a", "code": "timeout", "message": "t"}]}, True),
    ({"results": [{"x": 1}], "errors": [{"code": "auth_failed", "message": "m"}]}, True),
    ({"results": [], "errors": [{"rule_set_id": "a", "code": "parse_failed", "message": "p"}]}, False),
    ({"results": [], "errors": [{"code": "auth_failed", "message": "m"}]
      + [{"rule_set_id": str(i), "code": "not_found", "message": "n"} for i in range(5)]}, False),
])
def test_runner_infra_rule_v0570(resp, expected):
    """합친 인증 항목 특례만 infra — 단일 parse_failed·비-infra 혼합은 종전 규칙(Codex·Gemini·Fable)."""
    assert _runner()._is_infra(resp, None) is expected


def test_runner_fetched_ok_fails_with_merged_auth():
    ok, _ = _runner()._eval_assert({"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
                                   {"results": [], "errors": [{"code": "auth_failed", "message": "m"}]}, 0)
    assert ok is False, "합친 인증 오류 = 전 규정 미도달(거짓 PASS 차단)"
