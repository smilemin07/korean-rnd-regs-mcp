"""v0.60.0 조문별 변경 이력 안내 — 배포 전 스냅샷·article_effective_notice·도구 설명 1문장.

네트워크 0. 스냅샷은 임시 파일로 바꿔 끼우고(article_history._reset_for_tests), 상세 조회는 전용 mock을 쓴다.
추출 스크립트의 순수 함수(선택·게이트)도 여기서 잠근다.
"""
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import korean_rnd_regs_mcp.article_history as ah
import korean_rnd_regs_mcp.main as main_module
from korean_rnd_regs_mcp.live_api import LawApiClient, ResolvedDocId
from korean_rnd_regs_mcp.main import get_provision_detail

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import extract_article_history as ext  # noqa: E402

_REAL = ROOT / "src" / "korean_rnd_regs_mcp" / "article_history.json"
_MANUAL_27_3 = (
    "제27조의3(사업화 금융지원)은 법률 제21704호 부칙 제1조(공포한 날부터 시행)에 따라 2026-05-26부터 시행되었습니다."
)


def _snap(tmp_path, laws, generated="2026-10-25 00:34 KST", schema=1):
    p = tmp_path / "ah.json"
    p.write_text(json.dumps({"schema": schema, "generated_at": generated, "laws": laws}, ensure_ascii=False), encoding="utf-8")
    ah._reset_for_tests(p)
    return p


_REC = {"law_kind": "법률", "promulgation_no": "21704", "promulgation_date": "2026-05-26",
        "version_effective_date": "2026-05-26", "amendment_kind": "일부개정", "change_reason": "조문변경"}
_STAGED = dict(_REC, promulgation_no="21421", promulgation_date="2026-03-10", version_effective_date="2026-09-11",
               staged_dates=["2026-06-11", "2026-09-11"])
_LAW = {"sme_tech_act": {"mst": "281987", "efyd": "2026-07-01", "law_id": "009145",
                         "articles": {"JO002703": _REC, "JO0002": _STAGED}}}


@pytest.fixture(autouse=True)
def _restore_snapshot():
    yield
    ah._reset_for_tests(_REAL)


# === 1. 문장 조립 ===

def test_matched_single_stage_sentence(tmp_path):
    _snap(tmp_path, _LAW)
    s = ah.article_effective_notice("sme_tech_act", "JO002703", "281987", "20260701", "eflaw", "2026-07-01")
    assert s == (
        "국가법령정보 조문별 변경 이력(2026-10-25 확인)상 조회된 판본까지 이 조문의 최근 변경 기록은 법률 제21704호"
        "(2026-05-26 공포)이고, 그 판본은 2026-05-26에 시행되었습니다. 그 부칙에서 조문별 시행일을 "
        "따로 정했다면 그에 따릅니다. effective_date(2026-07-01)는 조회된 법령 판본 전체의 시행일입니다."
    )


def test_staged_sentence_gives_no_article_date(tmp_path):
    _snap(tmp_path, _LAW)
    s = ah.article_effective_notice("sme_tech_act", "JO0002", "281987", "20260701", "eflaw", "2026-07-01")
    assert "그 판본의 시행일이 2026-06-11·2026-09-11로 나뉘어 있어" in s
    assert "이 조문의 시행일은 이 응답으로 정할 수 없으니 그 부칙에서 확인하십시오" in s
    assert "에 시행되었습니다" not in s  # 분리 시행이면 판본 날짜를 조문 날짜처럼 쓰지 않는다


@pytest.mark.parametrize("args", [
    ("sme_tech_act", "JO002703", "281987", "20260701", "law_fallback", "2026-07-01"),  # 폴백 본문
    ("sme_tech_act", "JO002703", "281987", "20260701", "law", "2026-07-01"),           # efyd 부재
    ("sme_tech_act", "JO002703", "999999", "20260701", "eflaw", "2026-07-01"),         # 판본 교체(mst)
    ("sme_tech_act", "JO002703", "281987", "20270101", "eflaw", "2027-01-01"),         # 판본 교체(시행일)
    ("sme_tech_act", "JO0099", "281987", "20260701", "eflaw", "2026-07-01"),           # 스냅샷 제외 조문
    ("innovation_act", "JO0001", "290757", "20261002", "eflaw", "2026-10-02"),         # 스냅샷에 없는 법령
])
def test_general_sentence_paths(tmp_path, args):
    _snap(tmp_path, _LAW)
    s = ah.article_effective_notice(*args)
    assert s == (
        f"effective_date({args[5]})는 조회된 법령 판본 전체의 시행일이며, 이 조문의 시행일과 같다는 뜻은 "
        "아닙니다. 조문별 시행일은 국가법령정보센터의 조문 연혁과 부칙에서 확인하십시오."
    )


def test_mismatch_logged_once_per_rule_set(tmp_path, caplog):
    _snap(tmp_path, _LAW)
    caplog.set_level(logging.INFO, logger="rnd-regs-mcp.article_history")
    for _ in range(3):
        ah.article_effective_notice("sme_tech_act", "JO002703", "999999", "20260701", "eflaw", "2026-07-01")
    lines = [r.getMessage() for r in caplog.records if "article_history_snapshot_mismatch" in r.getMessage()]
    assert lines == ["event=article_history_snapshot_mismatch rule_set_id=sme_tech_act"]


# === 2. 로더 격리 ===

@pytest.mark.parametrize("content", ["{not json", json.dumps({"schema": 2, "laws": {}}), json.dumps([1, 2])])
def test_broken_snapshot_falls_back_to_general(tmp_path, content, caplog):
    p = tmp_path / "bad.json"
    p.write_text(content, encoding="utf-8")
    ah._reset_for_tests(p)
    caplog.set_level(logging.WARNING, logger="rnd-regs-mcp.article_history")
    s = ah.article_effective_notice("sme_tech_act", "JO002703", "281987", "20260701", "eflaw", "2026-07-01")
    assert s.startswith("effective_date(2026-07-01)는 조회된 법령 판본 전체의 시행일이며")
    assert any("article_history" in r.getMessage() for r in caplog.records)


def test_missing_snapshot_file(tmp_path):
    ah._reset_for_tests(tmp_path / "absent.json")
    assert ah.load_snapshot() == {"generated_date": "", "laws": {}}


@pytest.mark.parametrize("bad", [
    dict(_REC, law_kind="법율"), dict(_REC, law_kind="법률<img>"), dict(_REC, promulgation_no="제21704"),
    dict(_REC, change_reason="삭제"), dict(_REC, promulgation_date="2026-02-30"),
    dict(_REC, staged_dates=["2026-06-11"]), dict(_REC, staged_dates="2026-06-11"), "string-record",
    dict(_REC, change_reason=["조문변경"]), dict(_REC, change_reason={"a": 1}), dict(_REC, law_kind=["법률"]),
])
def test_bad_record_dropped_only(tmp_path, bad):
    laws = {"sme_tech_act": dict(_LAW["sme_tech_act"], articles={"JO002703": bad, "JO0002": _STAGED})}
    _snap(tmp_path, laws)
    snap = ah.load_snapshot()
    assert "JO002703" not in snap["laws"]["sme_tech_act"]["articles"]
    assert "JO0002" in snap["laws"]["sme_tech_act"]["articles"]


def test_department_ordinance_kind_accepted(tmp_path):
    rec = dict(_REC, law_kind="과학기술정보통신부령")
    _snap(tmp_path, {"sme_tech_act": dict(_LAW["sme_tech_act"], articles={"JO002703": rec})})
    s = ah.article_effective_notice("sme_tech_act", "JO002703", "281987", "20260701", "eflaw", "2026-07-01")
    assert "과학기술정보통신부령 제21704호" in s


def test_executor_failure_falls_back_to_general(tmp_path, monkeypatch):
    _snap(tmp_path, _LAW)
    monkeypatch.setattr(main_module, "_client_instance", _client(_DETAIL))
    real = main_module._run_offloaded

    async def boom(fn, *a):
        if fn is main_module._article_effective_notice:
            raise RuntimeError("executor down")
        return await real(fn, *a)
    monkeypatch.setattr(main_module, "_run_offloaded", boom)
    r = asyncio.run(get_provision_detail("law:281987:JO002703"))
    assert not r.get("errors") and r["content"].startswith("제27조의3")
    assert r["article_effective_notice"] == ah.general_notice("2026-07-01")


def test_notice_falls_back_when_loader_raises(monkeypatch):
    def boom():
        raise RuntimeError("loader")
    monkeypatch.setattr(ah, "load_snapshot", boom)
    s = ah.article_effective_notice("sme_tech_act", "JO002703", "281987", "20260701", "eflaw", "2026-07-01")
    assert s == ah.general_notice("2026-07-01")


def test_notice_never_raises_on_odd_inputs(tmp_path):
    _snap(tmp_path, _LAW)
    assert ah.article_effective_notice(None, None, None, None, "eflaw", "2026-07-01").startswith("effective_date(")


# === 3. 상세 응답 배선 ===

def _client(detail, stage="eflaw", effective="2026-07-01"):
    c = MagicMock(spec=LawApiClient)
    c.base_url = "https://test.invalid"
    c.api_key = "fake_v0600_key"
    c.resolve_latest_doc_id.side_effect = lambda title, target, mid, ministry=None: ResolvedDocId(
        doc_id=mid, effective_date=effective, is_updated=False, manifest_doc_id=mid)
    c.get_law_detail_staged.return_value = (detail, stage)
    c.get_admin_rule_detail.return_value = {"articles": [{"조문번호": "2", "조문제목": "정의", "조문내용": "제2조 본문"}],
                                            "annexes": []}
    return c


_DETAIL = {"법령ID": "009145", "법령명한글": "중소기업 기술혁신 촉진법", "시행일자": "20260701", "articles": [
    {"조문번호": "27", "조문가지번호": "3", "조문제목": "사업화 금융지원", "조문내용": "제27조의3(사업화 금융지원) 본문",
     "조문참고자료": "[본조신설 2026.5.26]", "structured": None},
], "annexes": []}


def test_detail_carries_notice_on_law_article(tmp_path, monkeypatch):
    _snap(tmp_path, _LAW)
    monkeypatch.setattr(main_module, "_client_instance", _client(_DETAIL))
    r = asyncio.run(get_provision_detail("law:281987:JO002703"))
    assert r["article_effective_notice"].startswith("국가법령정보 조문별 변경 이력(2026-10-25 확인)상 조회된 판본까지")
    assert r["content_format"] == "plain_text_verbatim"
    assert r["contract_version"] == "0.38.0"
    keys = list(r)
    assert keys.index("article_effective_notice") < keys.index("content")  # head 배치(3-tier 전건)


def test_detail_fallback_stage_gets_general_sentence(tmp_path, monkeypatch):
    _snap(tmp_path, _LAW)
    monkeypatch.setattr(main_module, "_client_instance", _client(_DETAIL, stage="law_fallback"))
    r = asyncio.run(get_provision_detail("law:281987:JO002703"))
    assert r["article_effective_notice"].startswith("effective_date(2026-07-01)는 조회된 법령 판본 전체의 시행일이며")


def test_oversized_article_keeps_notice(tmp_path, monkeypatch):
    _snap(tmp_path, _LAW)
    big = json.loads(json.dumps(_DETAIL))
    big["articles"][0]["조문내용"] = "가" * 20000
    monkeypatch.setattr(main_module, "_client_instance", _client(big))
    r = asyncio.run(get_provision_detail("law:281987:JO002703"))
    assert r["content_format"] == "oversized_pointer"
    assert "article_effective_notice" in r
    assert len(json.dumps(r, ensure_ascii=False)) <= main_module._ANNEX_DETAIL_CHAR_BUDGET


def test_admrul_article_has_no_notice(monkeypatch):
    monkeypatch.setattr(main_module, "_client_instance", _client(_DETAIL))
    rs = next(r for r in main_module.load_manifest() if r.api_target.value == "admrul")
    r = asyncio.run(get_provision_detail(f"admrul:{rs.api_doc_id}:JO0002"))
    assert not r.get("errors") and r["unit_type"] == "article" and r["content"] == "제2조 본문"
    assert "article_effective_notice" not in r


def test_document_level_has_no_notice(tmp_path, monkeypatch):
    _snap(tmp_path, _LAW)
    monkeypatch.setattr(main_module, "_client_instance", _client(_DETAIL))
    r = asyncio.run(get_provision_detail("law:281987"))
    assert not r.get("errors") and r["unit_type"] == "document" and r["articles_count"] == 1
    assert "article_effective_notice" not in r


def test_tool_description_sentence():
    src = (ROOT / "src" / "korean_rnd_regs_mcp" / "main.py").read_text(encoding="utf-8")
    sent = ("법령 조문 응답의 effective_date는 법령 판본 전체의 시행일이므로, 조문이 언제부터 시행됐는지 물으면 "
            "그 값을 조문 시행일로 답하지 말고 article_effective_notice 문장에 따라 답하십시오.")
    assert sent in src


# === 4. 실제 스냅샷 파일 ===

def test_real_snapshot_loads_and_is_clean():
    text = _REAL.read_text(encoding="utf-8")
    assert "OC=" not in text and "http" not in text.lower() and "링크" not in text
    ah._reset_for_tests(_REAL)
    snap = ah.load_snapshot()
    assert len(snap["laws"]) == 35
    rpt = (ROOT / "scripts" / "article_history_extract_report.md").read_text(encoding="utf-8")
    m = re.search(r"조문 (\d+)건", rpt)
    assert m and sum(len(v["articles"]) for v in snap["laws"].values()) == int(m.group(1))  # 보고서와 같은 건수
    assert int(m.group(1)) >= 900
    raw = json.loads(text)
    assert sum(len(v["articles"]) for v in raw["laws"].values()) == sum(len(v["articles"]) for v in snap["laws"].values())


def test_real_snapshot_matches_manual_27_3_sentence():
    """수기 고지(rule_sets.yaml)와 스냅샷이 같은 공포번호·날짜를 말한다 — 한 응답에 두 날짜가 나오지 않게."""
    snap = json.loads(_REAL.read_text(encoding="utf-8"))
    rec = snap["laws"]["sme_tech_act"]["articles"]["JO002703"]
    assert (rec["promulgation_no"], rec["version_effective_date"]) == ("21704", "2026-05-26")
    assert "staged_dates" not in rec
    yaml_text = (ROOT / "src" / "korean_rnd_regs_mcp" / "rule_sets.yaml").read_text(encoding="utf-8")
    assert _MANUAL_27_3 in yaml_text


def test_real_snapshot_built_with_current_rules():
    """스냅샷이 현재 추출 규칙으로 만들어졌는지 — 규칙을 바꾸고 재생성을 잊으면 실패(구현 diff Fable MAJOR)."""
    raw = json.loads(_REAL.read_text(encoding="utf-8"))
    assert raw.get("rules_version") == ext.RULES_VERSION


def test_snapshot_force_included_in_wheel():
    pp = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"src/korean_rnd_regs_mcp/article_history.json" = "korean_rnd_regs_mcp/article_history.json"' in pp


# === 5. 추출 규칙(순수 함수) ===

def _e(ef, pd, no, why="조문변경", jo="002703", mst="1", kind="법률"):
    return {"시행일자": ef, "공포일자": pd, "공포번호": no, "변경사유": why, "조문번호": jo,
            "법령일련번호": mst, "법령구분명": kind, "제개정구분명": "일부개정"}


def test_select_latest_not_after_served():
    es = [_e("20211021", "20210420", "18108"), _e("20260526", "20260526", "21704"), _e("20270316", "20260915", "21913")]
    chosen, why = ext.select_entry(es, "002703", "20260701")
    assert why == "ok" and chosen["공포번호"] == "21704"


@pytest.mark.parametrize("entries,reason", [
    ([], "이력 없음"),
    ([_e("20260526", "20260526", "21704", jo="002704")], "조문번호 왕복 불일치"),
    ([_e("2026526", "20260526", "21704")], "날짜 형식 이상"),
    ([_e("20270101", "20260526", "21704")], "서빙 시행일 이하 항목 없음"),
    ([_e("20260526", "20260526", "21704"), _e("20260526", "20260520", "21700")], "같은 시행일에 공포번호 복수"),
    ([_e("20260526", "20260526", "21704", why="삭제")], "변경사유 제외(삭제)"),
    ([_e("20260526", "20260526", "21704", kind="법령")], "법령구분명 허용 밖"),
    ([_e("20260526", "20260526", "21704"), _e("20250101", "20260526", "21705")], "같은 공포일에 공포번호 복수"),
    ([_e("20260526", "20260526", "21704"), _e("20260526", "20260526", "21704", why="본조신설")], "같은 시행일에 항목 불일치"),
    ([_e("20260526", "20260526", "123456789")], "공포번호 형식 이상"),
])
def test_select_exclusions(entries, reason):
    chosen, why = ext.select_entry(entries, "002703", "20260701")
    assert chosen is None and why == reason


_ROWS = [{"법령일련번호": "218729", "시행일자": "20210101"},
         {"법령일련번호": "283849", "시행일자": "20260611"}, {"법령일련번호": "283849", "시행일자": "20260911"}]


def test_stage_gate_excludes_mid_stage():
    """서빙 시행일이 분리 시행 판본의 두 단계 사이면 결정 불가(이력은 마지막 단계로만 남음)."""
    old = _e("20210101", "20200609", "17343", why="제정", mst="218729")
    new = _e("20260911", "20260310", "21421", mst="283849")
    assert ext.stage_gate(old, [old, new], _ROWS, "20260701") == "분리 시행 단계 귀속 불명"
    assert ext.stage_gate(new, [old, new], _ROWS, "20261002") == "ok"
    assert ext.stage_dates_for(_ROWS, "283849") == ["20260611", "20260911"]


def test_stage_gate_stage_cap():
    e = _e("20260526", "20260526", "21704", mst="9")
    rows = [{"법령일련번호": "9", "시행일자": f"2026{m:02d}01"} for m in range(1, 8)] + [{"법령일련번호": "9", "시행일자": "20260526"}]
    assert ext.stage_gate(e, [e], rows, "20261231") == "시행 단계 상한 초과"


def test_stage_gate_unknown_version_is_excluded():
    """판본이 단계 표에 없거나 날짜가 무효·불일치면 '단일 시행'으로 취급하지 않는다(구현 diff Codex MAJOR)."""
    e = _e("20260526", "20260526", "21704", mst="286263")
    assert ext.stage_gate(e, [e], _ROWS, "20260701") == "단계 표 미확인"
    bad = [{"법령일련번호": "286263", "시행일자": "2026-13-40"}]
    assert ext.stage_gate(e, [e], bad, "20260701") == "단계 표 미확인"
    other = [{"법령일련번호": "286263", "시행일자": "20260601"}]
    assert ext.stage_gate(e, [e], other, "20260701") == "단계 표 불일치"
    fut = _e("20270316", "20260915", "21913", mst="289563")
    ok_rows = [{"법령일련번호": "286263", "시행일자": "20260526"}]
    assert ext.stage_gate(e, [e, fut], ok_rows, "20260701") == "단계 표 미확인"  # 미래 판본 단계 미확인
    assert ext.stage_gate(e, [e, fut], ok_rows + [{"법령일련번호": "289563", "시행일자": "20270316"}], "20260701") == "ok"


@pytest.mark.parametrize("why,hist,content,expect", [
    ("조문변경", "개정 2026.5.26(공포)", "본문", "ok"),
    ("조문변경", "개정 2025.1.1(공포)", "본문", "표지 공포일 불일치"),
    ("조문변경", None, "본문", "표지 없음(조문변경·본조신설)"),
    ("제정", None, "본문", "ok"),
    ("전부개정", None, "본문", "ok"),
    ("조문변경", "삭제 2026.5.26(공포)", "본문", "삭제된 조문"),
    ("조문변경", None, "제5조 삭제 <2020.1.1>", "삭제된 조문"),
])
def test_marker_gate(why, hist, content, expect):
    assert ext.marker_gate({"변경사유": why, "공포일자": "20260526"}, hist, content) == expect


def test_extract_report_has_no_urls():
    rpt = (ROOT / "scripts" / "article_history_extract_report.md").read_text(encoding="utf-8")
    assert "OC=" not in rpt and not re.search(r"https?://", rpt)
