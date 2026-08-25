"""v0.55.0 「시행일 기준 조회 전환」 가드 — 네트워크 0(_request_with_retry patch).

잠그는 불변식:
  1) 제로콜 버그 차단: eflaw 시도가 실제로 1회 요청을 낸다(_EFLAW_ATTEMPTS != 0).
  2) eflaw 전용 예산이 기본 예산을 상속하지 않는다.
  3) 4중 성공 판정(조문·법령명·법령 일치·시행일자 provenance).
  4) 실패 6종 전부 law 폴백 / auth_failed만 즉시 전파.
  5) 서킷 브레이커: 실패 후 재시도 생략, 실패 기억이 만료되면 재시도 재개.
  6) sticky fallback 금지: 폴백 본문이 24h _detail_cache를 오염시키지 않는다.
  7) 공유 dict 무오염: stage_basis를 본문에 쓰지 않는다.
  8) efYd 정규화(하이픈 제거 8자리) — resolved.effective_date 형식 그대로 수용.
  9) resolve 캐시 시행일 도래 재평가 — 항목을 실제로 제거한다.
"""
import pytest

import korean_rnd_regs_mcp.live_api as LA
from korean_rnd_regs_mcp.live_api import (
    LawApiClient, LawApiError, ResolvedDocId,
    _EFLAW_TIMEOUT, _EFLAW_ATTEMPTS, _REQUEST_TIMEOUT, _MAX_RETRIES,
    ERROR_AUTH_FAILED, ERROR_NOT_FOUND, ERROR_PARSE_FAILED, ERROR_RATE_LIMITED,
)

_LAW_XML = """<?xml version="1.0" encoding="UTF-8"?><법령>
 <기본정보><법령ID>013774</법령ID><법령명_한글>국가연구개발혁신법</법령명_한글>
 <법종구분>법률</법종구분><소관부처>과학기술정보통신부</소관부처>
 <시행일자>{eff}</시행일자><공포일자>20260219</공포일자></기본정보>
 <조문><조문단위><조문번호>1</조문번호><조문여부>조문</조문여부>
  <조문제목>목적</조문제목><조문내용>제1조(목적) {body}</조문내용></조문단위></조문>
</법령>"""
_EMPTY_XML = '<?xml version="1.0" encoding="UTF-8"?><Law></Law>'


class _Resp:
    def __init__(self, text):
        self.status_code, self.text, self.content = 200, text, text.encode()
        self.headers = {"Content-Type": "application/xml"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LAW_API_KEY", "fake_key_for_test")
    return LawApiClient(env_override={"LAW_API_KEY": "fake_key_for_test",
                                      "LAW_API_URL": "https://test.invalid/DRF"})


def _spy(monkeypatch, handler):
    """_request_with_retry를 가로채 (params, timeout, max_retries)를 기록."""
    calls = []

    def fake(url, params, max_retries=_MAX_RETRIES, timeout=_REQUEST_TIMEOUT):
        calls.append({"target": params.get("target"), "efYd": params.get("efYd"),
                      "timeout": timeout, "max_retries": max_retries})
        return handler(params)
    monkeypatch.setattr(LA, "_request_with_retry", fake)
    return calls


# ── 1·2) 제로콜 버그 차단 + 전용 예산
def test_eflaw_budget_exact_values():
    """★확정 계획의 수치를 정확히 잠근다(부등식만 잠그면 값이 바뀌어도 통과 — 적대검토 지적).

    _request_with_retry(max_retries=N)의 N은 range(N) = 실제 시도 횟수다. 0이면 요청이 0회(제로콜 버그).
    """
    assert _EFLAW_ATTEMPTS == 1, "'시도 1회' 확정값 — 0이면 요청 0회, 2 이상이면 폴백 시간을 잠식"
    assert _EFLAW_TIMEOUT == (2.0, 4.0), "결정론 시뮬레이션으로 확정된 (connect 2s, read 4s)"
    assert _REQUEST_TIMEOUT == (8.0, 12.0) and _MAX_RETRIES == 2, "기본 예산 불변(상속 금지의 전제)"
    c = LawApiClient(env_override={"LAW_API_KEY": "k", "LAW_API_URL": "https://test.invalid/DRF"})
    assert (c._eflaw_failure_cache.maxsize, c._eflaw_failure_cache.ttl) == (48, 300)
    assert (c._law_fallback_cache.maxsize, c._law_fallback_cache.ttl) == (40, 300)
    assert c._detail_cache.ttl == 86400, "eflaw 성공은 종전 24h 캐시를 공유한다"


def test_eflaw_uses_dedicated_budget_and_single_attempt(client, monkeypatch):
    calls = _spy(monkeypatch, lambda p: _Resp(_LAW_XML.format(eff="20260820", body="본문")))
    detail, basis = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert basis == "eflaw" and detail["시행일자"] == "20260820"
    assert calls[0] == {"target": "eflaw", "efYd": "20260820",
                        "timeout": _EFLAW_TIMEOUT, "max_retries": _EFLAW_ATTEMPTS}
    assert len(calls) == 1, "성공 시 law 추가 호출이 없어야 한다"


# ── 3) 4중 성공 판정
@pytest.mark.parametrize("eff,body,title,why", [
    ("20260820", "본문", "다른 법률",   "법령 불일치(같은 시행일로 위장한 다른 법령)"),
    ("20260101", "본문", "국가연구개발혁신법", "시행일자 provenance 불일치"),
])
def test_eflaw_verify_rejects_and_falls_back(client, monkeypatch, eff, body, title, why):
    def h(p):
        return _Resp(_LAW_XML.format(eff=eff, body=body) if p["target"] == "eflaw"
                     else _LAW_XML.format(eff="19990101", body="합본"))
    calls = _spy(monkeypatch, h)
    detail, basis = client.get_law_detail_staged("283413", "2026-08-20", title)
    assert basis == "law_fallback", why
    assert detail["articles"][0]["조문내용"].endswith("합본")
    assert [c["target"] for c in calls] == ["eflaw", "law"]


def test_eflaw_empty_response_falls_back(client, monkeypatch):
    """(MST, efYd) 불일치 시 API는 오류가 아니라 빈 <Law/>를 준다 — fail-closed로 잡아야 한다."""
    calls = _spy(monkeypatch, lambda p: _Resp(_EMPTY_XML if p["target"] == "eflaw"
                                              else _LAW_XML.format(eff="19990101", body="합본")))
    _, basis = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert basis == "law_fallback"
    assert [c["target"] for c in calls] == ["eflaw", "law"]


# ── 4) 실패 6종 폴백 / auth_failed 전파
@pytest.mark.parametrize("code", [ERROR_NOT_FOUND, ERROR_PARSE_FAILED, ERROR_RATE_LIMITED])
def test_all_failure_kinds_fall_back(client, monkeypatch, code):
    def h(p):
        if p["target"] == "eflaw":
            raise LawApiError(code, "synthetic")
        return _Resp(_LAW_XML.format(eff="19990101", body="합본"))
    _spy(monkeypatch, h)
    _, basis = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert basis == "law_fallback"


def test_auth_failed_propagates_without_fallback(client, monkeypatch):
    """같은 키로 law를 다시 불러도 동일하게 실패하므로 요청만 2배가 된다 → 즉시 전파."""
    def h(p):
        if p["target"] == "eflaw":
            raise LawApiError(ERROR_AUTH_FAILED, "synthetic")
        raise AssertionError("auth_failed에서 law 폴백을 시도하면 안 된다")
    calls = _spy(monkeypatch, h)
    with pytest.raises(LawApiError) as ei:
        client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert ei.value.code == ERROR_AUTH_FAILED
    assert [c["target"] for c in calls] == ["eflaw"]


# ── 5) 서킷 브레이커
def test_breaker_skips_retry_then_resumes_after_expiry(client, monkeypatch):
    def h(p):
        if p["target"] == "eflaw":
            raise LawApiError(ERROR_PARSE_FAILED, "synthetic")
        return _Resp(_LAW_XML.format(eff="19990101", body="합본"))
    calls = _spy(monkeypatch, h)
    for _ in range(3):
        _, basis = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
        assert basis == "law_fallback"
    assert [c["target"] for c in calls].count("eflaw") == 1, "실패 기억 동안 eflaw 재시도 생략"

    client._eflaw_failure_cache.clear()          # TTL 만료 등가
    client._law_fallback_cache.clear()
    _, basis = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert [c["target"] for c in calls].count("eflaw") == 2, "만료 후에는 재시도 재개(자가 회복)"


# ── 6) sticky fallback 금지
def test_fallback_body_never_pollutes_24h_detail_cache(client, monkeypatch):
    def h(p):
        if p["target"] == "eflaw":
            raise LawApiError(ERROR_PARSE_FAILED, "synthetic")
        return _Resp(_LAW_XML.format(eff="19990101", body="합본"))
    _spy(monkeypatch, h)
    client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert ("get_law_detail", "283413") not in client._detail_cache, \
        "폴백 본문이 24h 캐시에 들어가면 eflaw 복구 후에도 하루 동안 합본이 서빙된다"
    assert ("law_fallback", "283413") in client._law_fallback_cache


def test_eflaw_store_success_pops_breaker(client):
    """★저장 함수 자체를 직접 검증 — 종전 우회 방식(clear 후 재호출)은 pop 코드가 삭제돼도
    통과했다(최종 재검증 라운드 지적). 실패 기억이 있는 상태에서 성공 저장이 그것을 제거해야 한다."""
    key = ("get_law_detail", "eflaw", "283413", "20260820")
    client._eflaw_store_failure(key, LawApiError(ERROR_PARSE_FAILED, "synthetic"))
    assert client._eflaw_failure_cache.get(key) is not None
    good = {"법령명한글": "국가연구개발혁신법", "시행일자": "20260820",
            "articles": [{"조문번호": "1", "조문내용": "제1조"}], "annexes": []}
    client._eflaw_store_success(key, good)
    assert client._eflaw_failure_cache.get(key) is None, "성공 저장이 상충 실패 기억을 제거해야 한다"
    assert client._eflaw_success(key) is good


def test_eflaw_store_failure_yields_to_success(client):
    """실패 기록 직전 성공 재확인 — 성공이 이미 있으면 실패가 그것을 덮지 못한다."""
    key = ("get_law_detail", "eflaw", "283413", "20260820")
    good = {"법령명한글": "국가연구개발혁신법", "시행일자": "20260820",
            "articles": [{"조문번호": "1", "조문내용": "제1조"}], "annexes": []}
    client._eflaw_store_success(key, good)
    client._eflaw_store_failure(key, LawApiError(ERROR_PARSE_FAILED, "synthetic"))
    assert client._eflaw_failure_cache.get(key) is None, "성공 존재 시 실패 기록은 생략돼야 한다"


# ── 7) 공유 dict 무오염
def test_stage_basis_never_written_into_body(client, monkeypatch):
    _spy(monkeypatch, lambda p: _Resp(_LAW_XML.format(eff="20260820", body="본문")))
    detail, _ = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert "stage_basis" not in detail and "stage_efyd" not in detail, \
        "출처를 본문에 쓰면 같은 dict를 공유하는 다른 경로가 오염된다"


# ── 8) efYd 정규화
@pytest.mark.parametrize("raw,want", [
    ("2026-08-20", "20260820"), ("20260820", "20260820"),
    ("", ""), ("2026-08", ""), ("abcdefgh", ""), ("  2026-08-20 ", "20260820"),
])
def test_normalize_efyd(raw, want):
    assert LawApiClient.normalize_efyd(raw) == want


def test_missing_efyd_uses_legacy_law_path(client, monkeypatch):
    calls = _spy(monkeypatch, lambda p: _Resp(_LAW_XML.format(eff="19990101", body="합본")))
    _, basis = client.get_law_detail_staged("283413", "", "국가연구개발혁신법")
    assert basis == "law", "efyd 부재는 시도 실패가 아니라 종전 경로"
    assert [c["target"] for c in calls] == ["law"]


# ── 9) resolve 캐시 시행일 도래 재평가
def _rd(pending):
    return ResolvedDocId(doc_id="288773", effective_date="2026-08-20", is_updated=False,
                         manifest_doc_id="288773", pending_effective_date=pending)


@pytest.mark.parametrize("pending,today,due", [
    ("2026-09-11", "20260911", True),    # 당일 도래
    ("2026-09-11", "20260912", True),    # 지난 뒤
    ("2026-09-11", "20260910", False),   # 아직 미래
    ("", "20260911", False),             # 예정 없음
    ("bad-date", "20260911", False),     # 형식 이상 → 과잉 무효화 금지
])
def test_resolution_due(pending, today, due):
    assert LawApiClient._resolution_due(_rd(pending), today) is due


def test_due_entry_removed_via_product_path(client, monkeypatch):
    """★제품 함수 경유로 실제 제거를 검증 — 종전 방식은 제품의 pop 로직을 테스트 안에서 재수행해
    구현에서 제거 코드가 사라져도 통과했다(최종 재검증 라운드 지적).

    도래일에 재판정이 '실패'하는 최악 경로: due 항목이 실제로 제거되고, 실패는 300초 실패 캐시로
    가서 다음 호출이 폭풍 없이 즉시 같은 폴백을 받아야 한다.
    """
    key = ("resolve", "law", "국가연구개발혁신법 시행령", "과학기술정보통신부")
    client._id_resolution_cache[key] = _rd("2000-01-01")   # 이미 도래한 예정일을 가진 warm 엔트리
    calls = {"n": 0}

    def failing_search(title, page=1, page_size=5):
        calls["n"] += 1
        raise LawApiError(ERROR_PARSE_FAILED, "synthetic")
    monkeypatch.setattr(client, "search_laws", failing_search)

    r1 = client.resolve_latest_doc_id("국가연구개발혁신법 시행령", "law", "288773", "과학기술정보통신부")
    assert r1.resolve_failed and calls["n"] == 1, "due 항목을 제거하고 재판정을 실행해야 한다"
    assert key not in client._id_resolution_cache, "재판정 실패 후 due 성공 항목이 남으면 매 호출 재평가"
    r2 = client.resolve_latest_doc_id("국가연구개발혁신법 시행령", "law", "288773", "과학기술정보통신부")
    assert r2.resolve_failed and calls["n"] == 1, "실패는 300초 캐시로 — 네트워크 재실행 없어야 한다"


# ── 10) 도구 응답 층: 고지 억제·폴백 가시화·내부 필드 미노출
import asyncio
import json as _json
import korean_rnd_regs_mcp.main as M
from korean_rnd_regs_mcp.manifest import load_manifest
from test_tools import mock_client  # noqa: F401 — 공용 mock 계약을 그대로 재사용(중복 정의 금지)


def _rs(rule_id):
    return next(r for r in load_manifest() if r.id == rule_id)


def test_stage_notice_suppressed_only_on_eflaw():
    """eflaw 본문에는 '반영되어 있지 않습니다'가 거짓이 되므로 억제. 그 외에는 fail-closed 유지."""
    rs = _rs("innovation_act")
    served = rs.stage_notice.audited_doc_id
    assert M._stage_notice_line(rs, served, "eflaw") is None
    for basis in ("law_fallback", "law"):
        line = M._stage_notice_line(rs, served, basis)
        assert line and line == rs.stage_notice.text, f"{basis}에서는 감사 고지를 유지해야 한다"


def test_fallback_line_fires_only_on_attempted_failure():
    """efyd 부재(law)는 '조회 실패'가 아니다 — resolve_fallback_notice가 전담하는 별개 상태."""
    assert M._stage_fallback_line("law_fallback") == M._STAGE_FALLBACK_NOTICE
    assert M._stage_fallback_line("eflaw") is None
    assert M._stage_fallback_line("law") is None


def test_detail_warnings_order_and_isolation():
    rs = _rs("innovation_act")
    before = list(rs.known_limitations)
    w = M._detail_warnings(rs, "감사고지", "폴백고지")
    assert w[:2] == ["감사고지", "폴백고지"] and w[2:] == before
    # 고지가 없는 규정에서는 폴백 고지가 자연히 선두
    assert M._detail_warnings(rs, None, "폴백고지")[0] == "폴백고지"
    assert M._detail_warnings(rs, None, None) == before
    assert list(rs.known_limitations) == before, "원본 known_limitations 불변"


def test_internal_stage_fields_never_serialized(mock_client, monkeypatch):
    """stage_basis·stage_efyd가 응답에 새면 계약 additive가 되어 규격 번호를 올려야 한다."""
    monkeypatch.setenv("LAW_API_KEY", "fake_key_for_test")
    for pid in ("law:283413", "law:283413:JO0015"):
        out = asyncio.run(M.get_provision_detail(pid))
        blob = _json.dumps(out, ensure_ascii=False)
        assert "stage_basis" not in blob and "stage_efyd" not in blob, pid


def test_detail_carries_fallback_notice_when_eflaw_fails(mock_client, monkeypatch):
    """폴백 시 상세 warnings에 폴백 고지가 실린다(감사 고지가 없는 규정에서도 열화가 보인다)."""
    monkeypatch.setenv("LAW_API_KEY", "fake_key_for_test")
    mock_client.get_law_detail_staged.side_effect = (
        lambda mst, efyd="", expected_title="": (mock_client.get_law_detail(mst), "law_fallback")
    )
    out = asyncio.run(M.get_provision_detail("law:283413:JO0015"))
    assert M._STAGE_FALLBACK_NOTICE in out["warnings"]


def test_fanout_logs_stage_counts(mock_client, monkeypatch, caplog):
    """(v0.55.0) 배포 게이트 ⑤·⑦이 쓰는 경로별 집계가 요약 로그에 실린다.

    stage_basis는 응답에 노출하지 않으므로 이 로그가 운영에서 폴백 잔존을 보는 유일한 직접 증거다.
    """
    import logging
    monkeypatch.setenv("LAW_API_KEY", "fake_key_for_test")
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        asyncio.run(M.search_provision("연구개발"))
    summary = [r.getMessage() for r in caplog.records if "search_fanout_summary" in r.getMessage()]
    assert summary, "fan-out 요약 로그 부재"
    for token in ("stage_eflaw=", "stage_fallback=", "stage_law="):
        assert token in summary[-1], f"{token} 미기록 — 배포 게이트 ⑤·⑦ 판정 불가"
    assert "oc=" not in summary[-1] and "fake_key" not in summary[-1], "요약 로그에 비밀값 금지"


def test_fallback_failure_is_remembered(client, monkeypatch):
    """★eflaw·law 동시 장애에서 실패 기억이 없으면 매 호출이 재시도 전량을 다시 태운다(outage 증폭).

    종전 get_law_detail과 같은 실패 캐시를 공유해 2번째 호출부터는 네트워크 0으로 즉시 실패해야 한다.
    """
    def h(p):
        raise LawApiError(ERROR_PARSE_FAILED, "synthetic outage")
    calls = _spy(monkeypatch, h)
    for _ in range(3):
        with pytest.raises(LawApiError):
            client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    # 1회차: eflaw 1 + law 1 = 2회. 2·3회차: 브레이커 + 실패 기억으로 네트워크 0.
    assert len(calls) == 2, f"장애 지속 중 재요청이 반복됨({len(calls)}회) — 실패 기억 미공유"


def test_resolve_reevaluates_on_due_date(client, monkeypatch):
    """★2026-09-11 전환 — 전날 캐시를 들고 있어도 당일 즉시 새 판본을 선택한다(이번 릴리스의 표적)."""
    rows = [
        {"doc_id": "288773", "eff": "20260820"},
        {"doc_id": "288335", "eff": "20260911"},
    ]

    def fake_search(title, page=1, page_size=5):
        from korean_rnd_regs_mcp.live_api import SearchResult, DocumentRef
        return SearchResult(total=len(rows), page=1, page_size=page_size, items=[
            DocumentRef(doc_type="law", doc_id=r["doc_id"], title="국가연구개발혁신법 시행령",
                        extra={"소관부처명": "과학기술정보통신부", "시행일자": r["eff"]})
            for r in rows])
    monkeypatch.setattr(client, "search_laws", fake_search)

    monkeypatch.setattr(LawApiClient, "_today_kst", staticmethod(lambda: "20260910"))
    before = client.resolve_latest_doc_id("국가연구개발혁신법 시행령", "law", "288773", "과학기술정보통신부")
    assert before.doc_id == "288773" and before.pending_effective_date == "2026-09-11"

    monkeypatch.setattr(LawApiClient, "_today_kst", staticmethod(lambda: "20260911"))
    after = client.resolve_latest_doc_id("국가연구개발혁신법 시행령", "law", "288773", "과학기술정보통신부")
    assert after.doc_id == "288335", "도래일에 옛 캐시가 24h 동안 남으면 전환이 하루 늦는다"
    assert after.effective_date == "2026-09-11"


# ── 11) 적대검토(구현 diff) 유래 보강 가드
def test_verify_conditions_fire_independently(client, monkeypatch):
    """조문 없음 / 법령명 없음이 각각 독립적으로 폴백을 유발하는지 분리 확인."""
    NO_ART = ('<?xml version="1.0" encoding="UTF-8"?><법령><기본정보>'
              '<법령명_한글>국가연구개발혁신법</법령명_한글><시행일자>20260820</시행일자>'
              '</기본정보><조문></조문></법령>')
    NO_TITLE = ('<?xml version="1.0" encoding="UTF-8"?><법령><기본정보>'
                '<법령명_한글></법령명_한글><시행일자>20260820</시행일자></기본정보>'
                '<조문><조문단위><조문번호>1</조문번호><조문여부>조문</조문여부>'
                '<조문내용>제1조 본문</조문내용></조문단위></조문></법령>')
    for xml, why in ((NO_ART, "조문 0건"), (NO_TITLE, "법령명 공백")):
        c = LawApiClient(env_override={"LAW_API_KEY": "k", "LAW_API_URL": "https://test.invalid/DRF"})
        _spy(monkeypatch, lambda p, x=xml: _Resp(x if p["target"] == "eflaw"
                                                 else _LAW_XML.format(eff="19990101", body="합본")))
        _, basis = c.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
        assert basis == "law_fallback", why


def test_cache_hit_revalidates_title(client, monkeypatch):
    """★캐시 적중에도 제목 검증이 다시 돌아야 한다(적대검토가 결정론 프로브로 재현한 우회 경로)."""
    _spy(monkeypatch, lambda p: _Resp(_LAW_XML.format(eff="20260820", body="본문")
                                      if p["target"] == "eflaw"
                                      else _LAW_XML.format(eff="19990101", body="합본")))
    _, b1 = client.get_law_detail_staged("283413", "2026-08-20", "")      # 제목 미지정으로 캐시 적재
    assert b1 == "eflaw"
    _, b2 = client.get_law_detail_staged("283413", "2026-08-20", "다른 법률")
    assert b2 == "law_fallback", "캐시된 본문이 요청 규정과 다르면 폴백해야 한다"
    _, b3 = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert b3 == "eflaw", "올바른 제목 호출은 계속 캐시를 사용해야 한다"


def test_concurrent_race_prefers_success(client, monkeypatch):
    """★경합: 실패한 호출도 그 사이 성립한 성공을 재확인해야 사용자별 본문이 갈리지 않는다."""
    key = ("get_law_detail", "eflaw", "283413", "20260820")
    good = {"법령명한글": "국가연구개발혁신법", "시행일자": "20260820",
            "articles": [{"조문번호": "1", "조문내용": "제1조 본문"}], "annexes": []}

    def h(p):
        if p["target"] == "eflaw":
            client._eflaw_store_success(key, good)   # 동시 호출이 먼저 성공한 상황 재현
            raise LawApiError(ERROR_PARSE_FAILED, "synthetic race")
        return _Resp(_LAW_XML.format(eff="19990101", body="합본"))
    _spy(monkeypatch, h)
    detail, basis = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert basis == "eflaw" and detail is good, "경합 시 성공 본문을 우선해야 한다"


def test_main_passes_exact_staged_arguments(mock_client, monkeypatch):
    """★main 호출부가 (문서번호, 시행일자, 제목)을 정확한 순서로 넘기는지 직접 잠근다.

    적대검토 지적: 공용 mock은 두 번째 인자가 비어 있지 않기만 하면 통과하므로,
    시행일자와 제목의 순서가 뒤바뀌어도 종전 테스트는 전부 통과한다.
    """
    monkeypatch.setenv("LAW_API_KEY", "fake_key_for_test")
    # 공용 mock의 resolve는 effective_date=""를 돌려주므로(=종전 경로 폴백 검증용),
    # 배선 검증에는 실제 형태의 판정 결과를 명시 주입한다.
    mock_client.resolve_latest_doc_id.side_effect = lambda title, target, mid, ministry: ResolvedDocId(
        doc_id=mid, effective_date="2026-08-20", is_updated=False, manifest_doc_id=mid)
    asyncio.run(M.get_provision_detail("law:283413:JO0015"))
    assert mock_client.get_law_detail_staged.call_args is not None, "staged 경로 미사용"
    args, kwargs = mock_client.get_law_detail_staged.call_args
    doc_id, efyd, title = (list(args) + [kwargs.get("efyd"), kwargs.get("expected_title")])[:3]
    assert doc_id == "283413"
    assert efyd == "2026-08-20", f"2번째 인자는 시행일자여야 한다(받은 값 {efyd!r})"
    assert title == "국가연구개발혁신법", f"3번째 인자는 규정 제목이어야 한다(받은 값 {title!r})"


def test_stage_counts_sum_matches_law_rule_count(mock_client, monkeypatch, caplog):
    """경로 집계 합계가 완료된 law 규정 수와 일치해야 한다(알 수 없는 basis 누락 검출)."""
    import logging, re
    from korean_rnd_regs_mcp.manifest import load_manifest as _lm
    from korean_rnd_regs_mcp.manifest import Retrieval
    monkeypatch.setenv("LAW_API_KEY", "fake_key_for_test")
    n_law = sum(1 for r in _lm() if r.retrieval == Retrieval.LIVE_API and r.api_target.value == "law")
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        asyncio.run(M.search_provision("연구개발"))
    msg = [r.getMessage() for r in caplog.records if "search_fanout_summary" in r.getMessage()][-1]
    got = {k: int(v) for k, v in re.findall(r"stage_(\w+)=(\d+)", msg)}
    assert sum(got.values()) == n_law, f"집계 합계 {sum(got.values())} != law 규정 {n_law} — 미분류 basis 존재"


# ── 12) 최종 재검증(3라운드) 유래 가드 — Codex 결정론 프로브 재현 3건
def test_fallback_reads_but_never_writes_law_success_cache(client, monkeypatch):
    """★F1 회귀 차단 — 유효한 24h law 성공 본문이 있으면 staged 폴백이 그것을 반환하고,
    실패 기억을 기록하지 않아야 한다. 종전 구현은 성공 캐시를 무시하고 네트워크를 타다 실패를
    공유 키에 기록해, efyd-부재 경로(get_law_detail — 실패를 성공보다 먼저 검사)까지 5분간
    오류가 됐다(최종 재검증 라운드 Codex 프로브 재현).
    """
    calls = _spy(monkeypatch, lambda p: _Resp(_LAW_XML.format(eff="19990101", body="합본")))
    warm = client.get_law_detail("283413")                 # 24h 성공 캐시 선적재
    assert ("get_law_detail", "283413") in client._detail_cache

    def h(p):
        raise LawApiError(ERROR_PARSE_FAILED, "synthetic outage")   # 이후 전 네트워크 실패
    calls2 = _spy(monkeypatch, h)
    detail, basis = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert basis == "law_fallback" and detail is warm, "살아 있는 law 성공 본문을 반환해야 한다"
    assert [c["target"] for c in calls2] == ["eflaw"], "law 성공이 있으면 law 네트워크를 타지 않는다"
    assert client._failure_cache.get(("get_law_detail", "283413")) is None, \
        "성공이 있는데 실패가 기록되면 efyd-부재 경로가 5분간 오류가 된다"
    assert client.get_law_detail("283413") is warm, "efyd-부재 경로도 계속 성공해야 한다"


def test_late_success_beats_fallback_body(client, monkeypatch):
    """★F4 후행 경합 — 폴백이 진행되는 동안 eflaw 성공이 성립하면 폴백 본문 대신 성공을 반환."""
    key = ("get_law_detail", "eflaw", "283413", "20260820")
    good = {"법령명한글": "국가연구개발혁신법", "시행일자": "20260820",
            "articles": [{"조문번호": "1", "조문내용": "제1조 본문"}], "annexes": []}

    def h(p):
        if p["target"] == "eflaw":
            raise LawApiError(ERROR_PARSE_FAILED, "synthetic")
        client._eflaw_store_success(key, good)   # 폴백 네트워크 도중 다른 호출이 성공한 상황
        return _Resp(_LAW_XML.format(eff="19990101", body="합본"))
    _spy(monkeypatch, h)
    detail, basis = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert basis == "eflaw" and detail is good, "성공이 성립했으면 폴백 본문이 아니라 성공을 반환"


def test_late_success_beats_fallback_error(client, monkeypatch):
    """★F4 후행 경합(오류 변형) — 폴백까지 실패해도 그 사이 성립한 성공이 있으면 오류가 아니라
    성공을 반환해야 한다(성공이 캐시에 있는데 오류가 나가는 것은 수용 불가 — Codex 프로브 재현)."""
    key = ("get_law_detail", "eflaw", "283413", "20260820")
    good = {"법령명한글": "국가연구개발혁신법", "시행일자": "20260820",
            "articles": [{"조문번호": "1", "조문내용": "제1조 본문"}], "annexes": []}

    def h(p):
        if p["target"] == "eflaw":
            raise LawApiError(ERROR_PARSE_FAILED, "synthetic")
        client._eflaw_store_success(key, good)
        raise LawApiError(ERROR_PARSE_FAILED, "synthetic outage")   # 폴백도 실패
    _spy(monkeypatch, h)
    detail, basis = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert basis == "eflaw" and detail is good


def test_race_recheck_still_verifies_title(client, monkeypatch):
    """★경합 재조회로 얻은 본문도 4중 판정을 거친다 — 검증 경로 단일화(자가 발견 반영)."""
    key = ("get_law_detail", "eflaw", "283413", "20260820")
    wrong = {"법령명한글": "전혀 다른 법률", "시행일자": "20260820",
             "articles": [{"조문번호": "1", "조문내용": "제1조"}], "annexes": []}

    def h(p):
        if p["target"] == "eflaw":
            client._eflaw_store_success(key, wrong)
            raise LawApiError(ERROR_PARSE_FAILED, "synthetic")
        return _Resp(_LAW_XML.format(eff="19990101", body="합본"))
    _spy(monkeypatch, h)
    detail, basis = client.get_law_detail_staged("283413", "2026-08-20", "국가연구개발혁신법")
    assert basis == "law_fallback", "재조회 본문이 요청 규정과 다르면 그대로 반환하면 안 된다"
    assert detail["articles"][0]["조문내용"].endswith("합본")
