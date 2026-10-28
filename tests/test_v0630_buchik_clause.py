"""v0.63.0 분리 시행 조문의 부칙 시행일 조항 동봉 — 로더 격리·안내 문장·생성기 순수 함수·저장 게이트·실제 스냅샷.

네트워크 0. 스냅샷은 임시 파일로 바꿔 끼운다(article_history._reset_for_tests). 생성기는 순수 함수만 부르거나
네트워크 함수를 mock으로 바꿔 main()을 돌린다.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

import korean_rnd_regs_mcp.article_history as ah

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import extract_article_history as ext  # noqa: E402

_REAL = ROOT / "src" / "korean_rnd_regs_mcp" / "article_history.json"
_REPORT = ROOT / "scripts" / "article_history_extract_report.md"

# 혁신법 법률 제21421호(2026-03-10 공포) 부칙 제1조 — 2026-10-26 라이브 추출 원문
_CLAUSE_21421 = ("제1조(시행일) 이 법은 공포 후 6개월이 경과한 날부터 시행한다. 다만, 제2조ㆍ제17조제1항ㆍ제18조ㆍ"
                 "제32조의 개정규정 및 부칙 제3조는 공포 후 3개월이 경과한 날부터 시행한다.")
_REC = {"law_kind": "법률", "promulgation_no": "21704", "promulgation_date": "2026-05-26",
        "version_effective_date": "2026-05-26", "amendment_kind": "일부개정", "change_reason": "조문변경"}
_STAGED = dict(_REC, promulgation_no="21421", promulgation_date="2026-03-10", version_effective_date="2026-09-11",
               staged_dates=["2026-06-11", "2026-09-11"])
_ARGS_STAGED = ("innovation_act", "JO0002", "290757", "20261002", "eflaw", "2026-10-02")
_HEAD = ("국가법령정보 조문별 변경 이력(2026-10-29 확인)상 조회된 판본까지 이 조문의 최근 변경 기록은 법률 "
         "제21421호(2026-03-10 공포)")
_TAIL = " effective_date(2026-10-02)는 조회된 법령 판본 전체의 시행일입니다."
_OLD_STAGED = (f"{_HEAD}입니다. 그 판본의 시행일이 2026-06-11·2026-09-11로 나뉘어 있어, 이 조문의 시행일은 이 응답으로 "
               f"정할 수 없으니 그 부칙에서 확인하십시오.{_TAIL}")


def _law(clauses=None, articles=None):
    law = {"mst": "290757", "efyd": "2026-10-02", "law_id": "014818",
           "articles": articles if articles is not None else {"JO0002": _STAGED, "JO0001": _REC}}
    if clauses is not None:
        law["clauses"] = clauses
    return {"innovation_act": law}


def _snap(tmp_path, laws, schema=1):
    p = tmp_path / "ah.json"
    p.write_text(json.dumps({"schema": schema, "generated_at": "2026-10-29 00:10 KST", "laws": laws},
                            ensure_ascii=False), encoding="utf-8")
    ah._reset_for_tests(p)
    return p


@pytest.fixture(autouse=True)
def _restore_snapshot():
    yield
    ah._reset_for_tests(_REAL)


# === 1. 안내 문장 ===

def test_staged_sentence_with_clause(tmp_path):
    _snap(tmp_path, _law({"21421|2026-03-10": {"text": _CLAUSE_21421}}))
    s = ah.article_effective_notice(*_ARGS_STAGED)
    assert s == (
        f"{_HEAD}입니다. 그 판본의 시행일은 2026-06-11·2026-09-11로 나뉘어 있습니다. 그 개정의 부칙 시행일 조항 "
        f"원문은 다음과 같습니다.\n{_CLAUSE_21421}\n이 원문은 위 최근 개정으로 바뀐 부분의 시행일을 정합니다. "
        "단서가 항·호나 '…에 관한 부분'처럼 조문 일부에만 걸리면 부분별로 나누어 답하십시오. 단서가 이 조문이 아닌 "
        "다른 조문만 들면 이 조문에는 본문의 시행일이 적용됩니다. 조문 번호는 가지 번호(예: 제17조의2)까지 같을 때만 "
        "해당합니다. '공포 후 N개월' 같은 기간은 위 시행일 목록에서 대응하는 날짜를 고르고, 목록에 없는 날짜를 계산해 "
        "만들지 마십시오. 목록 중 아직 오지 않은 날짜는 시행 예정일입니다. 위 원문만으로 정할 수 없으면 한 날짜로 "
        f"단정하지 마십시오.{_TAIL}"
    )


def test_frame_has_no_article1_label(tmp_path):
    """라벨(틀 문장)에 '부칙 제1조'를 쓰지 않는다 — 원문 안의 '제1조(시행일)'은 원문이므로 검사 대상이 아니다."""
    _snap(tmp_path, _law({"21421|2026-03-10": {"text": _CLAUSE_21421}}))
    frame = ah.article_effective_notice(*_ARGS_STAGED).replace(_CLAUSE_21421, "")
    assert "제1조" not in frame and "「" not in frame


@pytest.mark.parametrize("clauses", [None, {}, {"21421|2026-03-11": {"text": _CLAUSE_21421}}])
def test_no_clause_keeps_v060_staged_sentence(tmp_path, clauses):
    _snap(tmp_path, _law(clauses))
    assert ah.article_effective_notice(*_ARGS_STAGED) == _OLD_STAGED


def test_clause_assembly_failure_keeps_v060_staged_sentence(tmp_path, monkeypatch):
    _snap(tmp_path, _law({"21421|2026-03-10": {"text": _CLAUSE_21421}}))

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(ah, "_staged_clause_sentence", boom)
    assert ah.article_effective_notice(*_ARGS_STAGED) == _OLD_STAGED


def test_clause_lookup_failure_keeps_v060_staged_sentence(tmp_path, monkeypatch):
    _snap(tmp_path, _law({"21421|2026-03-10": {"text": _CLAUSE_21421}}))
    snap = ah.load_snapshot()
    snap["laws"]["innovation_act"]["clauses"] = object()  # .get 없음
    assert ah.article_effective_notice(*_ARGS_STAGED) == _OLD_STAGED


def test_single_stage_and_general_sentences_unchanged(tmp_path):
    _snap(tmp_path, _law({"21421|2026-03-10": {"text": _CLAUSE_21421}, "21704|2026-05-26": {"text": "이 법은 공포한 날부터 시행한다."}}))
    a = ah.article_effective_notice("innovation_act", "JO0001", "290757", "20261002", "eflaw", "2026-10-02")
    assert a.endswith("그 부칙에서 조문별 시행일을 따로 정했다면 그에 따릅니다." + _TAIL)
    assert "원문은 다음과 같습니다" not in a  # (a)에는 조항을 싣지 않는다
    mismatch = ah.article_effective_notice("innovation_act", "JO0002", "999999", "20261002", "eflaw", "2026-10-02")
    assert mismatch == ah.general_notice("2026-10-02")  # 판본 불일치 = 일반 문장 전문


def test_clause_with_leading_zero_number(tmp_path):
    rec = dict(_STAGED, promulgation_no="00221", promulgation_date="2013-03-23")
    _snap(tmp_path, _law({"00221|2013-03-23": {"text": "이 규칙은 공포한 날부터 시행한다. 다만, 제5조의 개정규정은 2014년 1월 1일부터 시행한다."}},
                         {"JO0002": rec}))
    assert "원문은 다음과 같습니다.\n이 규칙은" in ah.article_effective_notice(*_ARGS_STAGED)


# === 2. 로더 격리 ===

@pytest.mark.parametrize("bad", [
    {"21421|2026-99-99": {"text": _CLAUSE_21421}},
    {"21421|2026-03-10": {"text": None}},
    {"21421|2026-03-10": "문자열"},
    {"21421|2026-03-10": {"text": "   \n  "}},
    {"21421|2026-03-10": {"text": "가" * 601}},
    {"21421|2026-03-10": {"text": "제1조(시행일) 이 법은\t공포한 날부터 시행한다."}},
    {"21421|2026-03-10": {"text": "제1조(시행일) OC=abc 이 법은 공포한 날부터 시행한다."}},
    {"21421|2026-03-10": {"text": "제1조(시행일) https://x 이 법은 공포한 날부터 시행한다."}},
    {"21421-2026-03-10": {"text": _CLAUSE_21421}},
    "목록",
])
def test_bad_clause_dropped_history_kept(tmp_path, bad):
    _snap(tmp_path, _law(bad))
    snap = ah.load_snapshot()
    assert snap["laws"]["innovation_act"]["clauses"] == {}
    assert set(snap["laws"]["innovation_act"]["articles"]) == {"JO0002", "JO0001"}
    assert ah.article_effective_notice(*_ARGS_STAGED) == _OLD_STAGED


def test_clause_600_chars_accepted_and_newlines_kept(tmp_path):
    head = "제1조(시행일) 이 법은 공포한 날부터 시행한다.\n  1. "
    text = head + "가" * (600 - len(head) - 2) + "다."
    assert len(text) == 600
    _snap(tmp_path, _law({"21421|2026-03-10": {"text": text}}))
    got = ah.load_snapshot()["laws"]["innovation_act"]["clauses"]["21421|2026-03-10"]
    assert got == text.strip() and "\n" in got


def test_one_bad_clause_does_not_drop_good_one(tmp_path):
    _snap(tmp_path, _law({"21421|2026-03-10": {"text": _CLAUSE_21421}, "1|2020-01-01": {"text": None}}))
    assert list(ah.load_snapshot()["laws"]["innovation_act"]["clauses"]) == ["21421|2026-03-10"]


def test_schema_other_than_1_drops_snapshot(tmp_path):
    _snap(tmp_path, _law({"21421|2026-03-10": {"text": _CLAUSE_21421}}), schema=2)
    assert ah.load_snapshot()["laws"] == {}


# === 3. 생성기 순수 함수 ===

_H = "부칙 <제21421호,2026.3.10>"


@pytest.mark.parametrize("text,stages,expect", [
    (f"{_H}\n{_CLAUSE_21421}\n제2조(경과조치) 생략 없음 규정이다.", 2, _CLAUSE_21421),  # 다음 조 앞에서 자름
    (f"{_H}\r\n{_CLAUSE_21421}\r\n제2조(적용례) 이 법은 적용한다.", 2, _CLAUSE_21421),    # CRLF 정규화
    (f"부칙(국가연구개발혁신법) <제21421호, 2026. 3. 10.>\n{_CLAUSE_21421}", 2, _CLAUSE_21421),  # 괄호 머리말
    (f"{_H}\n이 법은 2026년 3월 10일부터 시행한다. 다만, 제40조제1항의 개정규정은 2026년 9월 11일부터 시행한다.", 2,
     "이 법은 2026년 3월 10일부터 시행한다. 다만, 제40조제1항의 개정규정은 2026년 9월 11일부터 시행한다."),  # 한 문장 부칙·본문 중 조번호는 자르지 않음
    (f"{_H}\n제1조(시행일) 이 영은 공포한 날부터 시행한다. 다만, 다음 각 호의 개정규정은 해당 호에서 정하는 날부터 시행한다.\n\n"
     "  1. 제16조제2항의 개정규정: 2027년 1월 1일\n\n  2. 제36조의 개정규정: 2026년 9월 11일\n제2조(적용례) 이 영은 적용한다.", 3,
     "제1조(시행일) 이 영은 공포한 날부터 시행한다. 다만, 다음 각 호의 개정규정은 해당 호에서 정하는 날부터 시행한다.\n\n"
     "  1. 제16조제2항의 개정규정: 2027년 1월 1일\n\n  2. 제36조의 개정규정: 2026년 9월 11일"),  # 호 목록·날짜로 끝남
])
def test_extract_clause_ok(text, stages, expect):
    assert ext.extract_clause(text, "21421", "2026-03-10", stages) == (expect, "ok")


@pytest.mark.parametrize("text,no,date,stages,why", [
    ("제1조(시행일) 이 법은 공포한 날부터 시행한다.", "21421", "2026-03-10", 1, "머리말 형식 이상"),
    (f"{_H}\n{_CLAUSE_21421}", "21422", "2026-03-10", 2, "머리말 번호·날짜 불일치"),
    (f"{_H}\n{_CLAUSE_21421}", "21421", "2026-03-11", 2, "머리말 번호·날짜 불일치"),
    (f"{_H}\n제2조(다른 법률의 개정) 생략한다.", "21421", "2026-03-10", 1, "시행일 조항 형태 아님"),
    (f"{_H}\n이 법은 지금부터 쓴다.", "21421", "2026-03-10", 1, "시행일 조항 형태 아님"),
    (f"{_H}\n제1조(시행일) 이 법은 공포한 날부터 시행한다. <단서 생략>", "21421", "2026-03-10", 1, "생략 표시"),
    (f"{_H}\n제1조(시행일) ① 이 법은 공포한 날부터 시행한다.", "21421", "2026-03-10", 1, "①·② 짝 없음"),
    (f"{_H}\n제1조(시행일) ② 이 법은 공포한 날부터 시행한다.", "21421", "2026-03-10", 1, "①·② 짝 없음"),
    (f"{_H}\n제1조(시행일) 이 법은 공포한 날부터 시행한다. 다만, 공포 후 3개월 이내에 정한다.", "21421", "2026-03-10", 2,
     "날짜 표현 부족"),  # 시행일이 아닌 기간 표현은 세지 않는다
    (f"{_H}\n제1조(시행일) 이 법은 공포한 날부터 시행하며", "21421", "2026-03-10", 1, "끝맺음 이상"),
    (f"{_H}\n제1조(시행일) 이 법은 공포한 날부터 시행한다.", "21421", "2026-03-10", 2, "날짜 표현 부족"),
    (f"{_H}\n제1조(시행일) 이 법은 공포한 날부터 시행한다. " + "가" * 600 + "다.", "21421", "2026-03-10", 1, "600자 초과"),
    (f"{_H}\n제1조(시행일) 이 법은 공포한 날부터\x0b시행한다.", "21421", "2026-03-10", 1, "제어문자"),
    (f"{_H}\n제1조(시행일) 이 법은 공포한 날부터 시행한다. OC=x 다.", "21421", "2026-03-10", 1, "키·링크 문자열"),
])
def test_extract_clause_rejects(text, no, date, stages, why):
    assert ext.extract_clause(text, no, date, stages) == (None, why)


def test_extract_clause_rejects_api_key_text():
    assert ext.extract_clause(f"{_H}\n제1조(시행일) 이 법은 공포한 날 SECRETKEY부터 시행한다.", "21421", "2026-03-10", 1,
                              api_key="SECRETKEY") == (None, "키·링크 문자열")


def test_date_expression_definition():
    t = "공포한 날 · 공포 후 6개월이 경과한 날 · 공포 후 1년이 경과한 날 · 2027년 1월 1일 · 공포 후 3개월 · 공포 후 3개월 이내"
    assert len(ext._DATE_EXPR.findall(t)) == 4  # 계획서 5-3 정의: "공포 후 N…이 경과한 날"만 센다


def test_untitled_article_reference_line_is_not_a_cut_point():
    """호 표시 없이 "제N조…"로 시작하는 줄은 다음 조가 아니다 — 거기서 자르면 단계 하나의 날짜가 빠진다(Fable 재현)."""
    body = ("제1조(시행일) 이 영은 공포한 날부터 시행한다. 다만, 다음 각 호의 개정규정은 해당 호에서 정하는 날부터 시행한다.\n"
            "제16조제2항의 개정규정: 2027년 1월 1일\n제36조의 개정규정: 2026년 9월 11일")
    assert ext.extract_clause(f"{_H}\n{body}\n제2조(적용례) 이 영은 적용한다.", "21421", "2026-03-10", 3) == (body, "ok")


def test_leading_zero_header_matches_record():
    text = "부칙 <제221호,2013.3.23>\n이 규칙은 공포한 날부터 시행한다. 다만, 제5조는 2014년 1월 1일부터 시행한다."
    assert ext.extract_clause(text, "00221", "2013-03-23", 2)[1] == "ok"


def test_build_clauses_keys_and_targets():
    arts = {
        "JO0002": dict(_STAGED, promulgation_no="00221", promulgation_date="2013-03-23"),
        "JO0003": dict(_STAGED, promulgation_no="00221", promulgation_date="2013-03-23"),
        "JO0004": dict(_STAGED, amendment_kind="타법개정"),        # 대상 아님
        "JO0005": dict(_STAGED, amendment_kind=""),               # 허용 목록 밖
        "JO0006": _REC,                                           # 단일 시행
        "JO0007": dict(_STAGED, promulgation_no="99999"),         # 부칙 없음
    }
    units = [{"no": "221", "date": "20130323",
              "text": "부칙 <제221호,2013.3.23>\n이 규칙은 공포한 날부터 시행한다. 다만, 제5조는 2014년 1월 1일부터 시행한다."}]
    clauses, missing = ext.build_clauses(arts, units)
    assert list(clauses) == ["00221|2013-03-23"]  # 레코드 번호 문자열 그대로(앞 0 유지)
    assert missing == {"JO0007": "부칙 0건"}


def test_build_clauses_stage_list_mismatch():
    arts = {"JO0002": _STAGED, "JO0003": dict(_STAGED, staged_dates=["2026-06-11", "2026-09-11", "2027-01-01"])}
    u = {"no": "21421", "date": "20260310", "text": f"{_H}\n{_CLAUSE_21421}"}
    assert ext.build_clauses(arts, [u]) == ({}, {"JO0002": "단계 목록 불일치", "JO0003": "단계 목록 불일치"})


def test_build_clauses_duplicate_buchik():
    arts = {"JO0002": _STAGED}
    u = {"no": "21421", "date": "20260310", "text": f"{_H}\n{_CLAUSE_21421}"}
    assert ext.build_clauses(arts, [u, dict(u)]) == ({}, {"JO0002": "부칙 복수"})


def test_diff_against_existing():
    a = {"mst": "1", "efyd": "2026-01-01", "articles": {"JO0001": _REC}, "clauses": {"21704|2026-05-26": {"text": "x"}}}
    assert ext.diff_against_existing({"x": a}, {"x": dict(a)}) == {}
    assert ext.diff_against_existing({"x": a}, {"x": dict(a, mst="2")})["x"].startswith("판본 변경")
    assert ext.diff_against_existing({"x": a}, {"x": dict(a, articles={})})["x"].startswith("같은 판본에서 조문 레코드")
    assert ext.diff_against_existing({"x": a}, {"x": dict(a, clauses={})})["x"] == "조항 1건 감소"
    assert ext.diff_against_existing({}, {"x": a}) == {"x": "새 법령"}
    assert ext.diff_against_existing({"x": a}, {}) == {"x": "법령 빠짐"}
    assert ext.diff_against_existing({"x": a}, {"x": dict(a, clauses={"21704|2026-05-26": {"text": "x2"}})})["x"] == "조항 1건 원문 변경"
    more = dict(a, clauses={"21704|2026-05-26": {"text": "x"}, "1|2020-01-01": {"text": "y"}})
    assert ext.diff_against_existing({"x": a}, {"x": more}) == {}  # 조항 증가는 허용


def test_write_atomic_keeps_old_file_on_failure(tmp_path, monkeypatch):
    p = tmp_path / "a.json"
    p.write_text("old", encoding="utf-8")

    def fail(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(ext.os, "replace", fail)
    with pytest.raises(OSError):
        ext._write_atomic(p, "new")
    assert p.read_text(encoding="utf-8") == "old"
    assert [x.name for x in tmp_path.iterdir()] == ["a.json"]  # 임시 파일 남지 않음


def test_write_pair_restores_json_when_report_fails(tmp_path, monkeypatch):
    j, r = tmp_path / "a.json", tmp_path / "r.md"
    j.write_text("old-json", encoding="utf-8")
    r.write_text("old-report", encoding="utf-8")
    real = ext._write_atomic

    def flaky(path, text):
        if path == r:
            raise OSError("disk")
        real(path, text)
    monkeypatch.setattr(ext, "_write_atomic", flaky)
    with pytest.raises(OSError):
        ext._write_pair(j, "new-json", r, "new-report")
    assert j.read_text(encoding="utf-8") == "old-json" and r.read_text(encoding="utf-8") == "old-report"


# === fetch_buchik_units — 가짜 XML(네트워크 0) ===

from xml.sax.saxutils import escape  # noqa: E402


def _xml(efyd="20261002", law_id="014818", units=True, basic=True):
    b = f"<기본정보><법령ID>{law_id}</법령ID><시행일자>{efyd}</시행일자></기본정보>" if basic else ""
    u = ("<부칙><부칙단위><부칙공포일자>20260310</부칙공포일자><부칙공포번호>21421</부칙공포번호>"
         f"<부칙내용>{escape(_H)}\n{_CLAUSE_21421}</부칙내용></부칙단위></부칙>") if units else "<부칙/>"
    return f"<법령>{b}{u}</법령>"


@pytest.mark.parametrize("xml,expect", [
    (_xml(), "ok"),
    (_xml(efyd="2026-10-02"), "ok"),                 # 날짜 표기 정규화
    (_xml(efyd="20261001"), "buchik_version_mismatch"),
    (_xml(law_id="999999"), "buchik_version_mismatch"),
    (_xml(units=False), "buchik_absent"),
    (_xml(basic=False), "buchik_version_mismatch"),
], ids=["ok", "dash_date", "efyd_mismatch", "law_id_mismatch", "no_units", "no_basic_info"])
def test_fetch_buchik_units(monkeypatch, xml, expect):
    import xml.etree.ElementTree as ET
    import korean_rnd_regs_mcp.live_api as la
    monkeypatch.setattr(la, "_request_with_retry", lambda *a, **k: xml)
    monkeypatch.setattr(la, "_parse_xml", lambda resp: ET.fromstring(resp))
    if expect == "ok":
        units = ext.fetch_buchik_units(_FakeClient(), "290757", "20261002", "014818")
        assert units == [{"no": "21421", "date": "20260310", "text": f"{_H}\n{_CLAUSE_21421}"}]
    else:
        with pytest.raises(la.LawApiError) as ei:
            ext.fetch_buchik_units(_FakeClient(), "290757", "20261002", "014818")
        assert expect in str(ei.value) or ei.value.code == "not_found"


# === 4. 생성기 main() 저장 게이트(네트워크 mock) ===

class _FakeClient:
    api_key = "FAKEKEY123"
    base_url = "https://example.invalid/DRF"

    def resolve_latest_doc_id(self, title, target, doc_id, ministry):
        from korean_rnd_regs_mcp.live_api import ResolvedDocId
        return ResolvedDocId(doc_id="290757", effective_date="20261002", is_updated=False, manifest_doc_id="290757")

    def get_law_detail_staged(self, mst, efyd, title):
        return {"시행일자": "20261002", "법령ID": "014818", "articles": [
            {"조문번호": "2", "조문가지번호": "", "조문내용": "제2조(정의) 본문", "조문참고자료": "[전문개정 2026.3.10]"}]}, "eflaw"


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)  # 테스트가 실제 키를 환경에 올리지 않게


def _run_main(tmp_path, monkeypatch, argv, buchik_text=f"{_H}\n{_CLAUSE_21421}", out_old=None):
    import korean_rnd_regs_mcp.live_api as la
    from korean_rnd_regs_mcp.manifest import load_manifest
    out = tmp_path / "ah.json"
    rpt = tmp_path / "rpt.md"
    if out_old is not None:
        out.write_text(out_old, encoding="utf-8")
    monkeypatch.setattr(ext, "OUT_PATH", out)
    monkeypatch.setattr(ext, "REPORT_PATH", rpt)
    monkeypatch.setattr(la, "LawApiClient", _FakeClient)
    rs = next(r for r in load_manifest() if r.id == "innovation_act")
    import korean_rnd_regs_mcp.manifest as mf
    monkeypatch.setattr(mf, "load_manifest", lambda *a, **k: [rs])

    class _Col:
        def __init__(self, *a):
            pass

        def stage_rows(self, *a):
            return [{"법령일련번호": "999", "시행일자": "2026-06-11"}, {"법령일련번호": "999", "시행일자": "2026-09-11"}]
    import audit_law_stage_diff as asd
    monkeypatch.setattr(asd, "Collector", _Col)
    monkeypatch.setattr(ext, "fetch_article_history", lambda c, lid, jo6: [
        {"시행일자": "20260911", "공포일자": "20260310", "공포번호": "21421", "제개정구분명": "일부개정",
         "법령구분명": "법률", "법령일련번호": "999", "변경사유": "조문변경", "조문번호": jo6}])
    monkeypatch.setattr(ext, "fetch_buchik_units", lambda c, m, e, lid: [
        {"no": "21421", "date": "20260310", "text": buchik_text}])
    import korean_rnd_regs_mcp.main as mm
    monkeypatch.setattr(mm, "_article_amendment_history", lambda art: "개정 2026.3.10(공포)")
    code = ext.main(argv)
    return code, out, rpt


def test_main_saves_with_clause_and_hash(tmp_path, monkeypatch):
    code, out, rpt = _run_main(tmp_path, monkeypatch, ["--require-all-clauses"])
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["rules_version"] == 4 and data["schema"] == 1
    assert data["laws"]["innovation_act"]["clauses"] == {"21421|2026-03-10": {"text": _CLAUSE_21421}}
    r = rpt.read_text(encoding="utf-8")
    assert hashlib.sha256(out.read_bytes()).hexdigest() in r
    assert "FAKEKEY123" not in out.read_text(encoding="utf-8") + r


def test_main_require_all_clauses_blocks_save(tmp_path, monkeypatch):
    code, out, rpt = _run_main(tmp_path, monkeypatch, ["--require-all-clauses"],
                               buchik_text=f"{_H}\n제1조(시행일) 이 법은 공포한 날부터 시행한다. <단서 생략>")
    assert code == 2 and not out.exists() and not rpt.exists()


def test_main_without_flag_saves_and_reports_missing(tmp_path, monkeypatch):
    code, out, rpt = _run_main(tmp_path, monkeypatch, [],
                               buchik_text=f"{_H}\n제1조(시행일) 이 법은 공포한 날부터 시행한다. <단서 생략>")
    assert code == 0 and "clauses" not in json.loads(out.read_text(encoding="utf-8"))["laws"]["innovation_act"]
    assert "innovation_act|JO0002: 생략 표시" in rpt.read_text(encoding="utf-8")


def test_main_diff_needs_accept(tmp_path, monkeypatch):
    old = json.dumps({"schema": 1, "laws": {"innovation_act": {"mst": "1", "efyd": "2026-01-01", "articles": {}}}})
    code, out, _ = _run_main(tmp_path, monkeypatch, [], out_old=old)
    assert code == 2 and out.read_text(encoding="utf-8") == old  # 기존 파일 그대로
    code, out, _ = _run_main(tmp_path, monkeypatch, ["--accept-diff", "innovation_act"], out_old=old)
    assert code == 0 and json.loads(out.read_text(encoding="utf-8"))["laws"]["innovation_act"]["mst"] == "290757"


def test_main_unreadable_existing_snapshot_blocks(tmp_path, monkeypatch):
    code, out, _ = _run_main(tmp_path, monkeypatch, [], out_old="{망가진 JSON")
    assert code == 2 and out.read_text(encoding="utf-8") == "{망가진 JSON"


def test_main_partial_ids_never_saves(tmp_path, monkeypatch):
    code, out, rpt = _run_main(tmp_path, monkeypatch, ["innovation_act"])
    assert code == 0 and not out.exists() and not rpt.exists()


def test_main_buchik_fetch_failure_is_law_failure(tmp_path, monkeypatch):
    from korean_rnd_regs_mcp.live_api import LawApiError

    def fail(*a):
        raise LawApiError("not_found", "buchik_version_mismatch")
    code, out, rpt = None, None, None
    monkeypatch.setattr(ext, "fetch_buchik_units", fail)
    # _run_main이 fetch_buchik_units를 다시 덮으므로 직접 구성
    import korean_rnd_regs_mcp.live_api as la
    from korean_rnd_regs_mcp.manifest import load_manifest
    import korean_rnd_regs_mcp.manifest as mf
    import audit_law_stage_diff as asd
    import korean_rnd_regs_mcp.main as mm
    out, rpt = tmp_path / "ah.json", tmp_path / "rpt.md"
    monkeypatch.setattr(ext, "OUT_PATH", out)
    monkeypatch.setattr(ext, "REPORT_PATH", rpt)
    monkeypatch.setattr(la, "LawApiClient", _FakeClient)
    rs = next(r for r in load_manifest() if r.id == "innovation_act")
    monkeypatch.setattr(mf, "load_manifest", lambda *a, **k: [rs])

    class _Col:
        def __init__(self, *a):
            pass

        def stage_rows(self, *a):
            return [{"법령일련번호": "999", "시행일자": "2026-06-11"}, {"법령일련번호": "999", "시행일자": "2026-09-11"}]
    monkeypatch.setattr(asd, "Collector", _Col)
    monkeypatch.setattr(ext, "fetch_article_history", lambda c, lid, jo6: [
        {"시행일자": "20260911", "공포일자": "20260310", "공포번호": "21421", "제개정구분명": "일부개정",
         "법령구분명": "법률", "법령일련번호": "999", "변경사유": "조문변경", "조문번호": jo6}])
    monkeypatch.setattr(mm, "_article_amendment_history", lambda art: "개정 2026.3.10(공포)")
    assert ext.main([]) == 2 and not out.exists()


# === 5. 실제 스냅샷·보고서 ===

# 조항을 붙이지 않기로 사람이 확인한 대상(사유와 함께 추가한다). v0.63.0 생성 시점에는 없다.
_KNOWN_CLAUSE_EXCLUSIONS: dict[str, str] = {}


def test_real_snapshot_rules_and_schema():
    raw = json.loads(_REAL.read_text(encoding="utf-8"))
    assert raw["schema"] == 1 and raw["rules_version"] == ext.RULES_VERSION == 4


def test_real_snapshot_clause_keys_match_targets():
    raw = json.loads(_REAL.read_text(encoding="utf-8"))
    ah._reset_for_tests(_REAL)
    loaded = ah.load_snapshot()
    missing = {}
    for rid, law in raw["laws"].items():
        targets = ext.clause_targets(law["articles"])
        expected = {f"{r['promulgation_no']}|{r['promulgation_date']}" for r in targets.values()}
        keys = set(law.get("clauses") or {})
        assert keys <= expected, f"{rid}: 대상이 아닌 조항 {keys - expected}"  # 타법개정·단일 시행에 조항 없음
        assert set(loaded["laws"][rid]["clauses"]) == keys, f"{rid}: 로더가 버린 조항"
        for uid, r in targets.items():
            if f"{r['promulgation_no']}|{r['promulgation_date']}" not in keys:
                missing[f"{rid}|{uid}"] = True
    assert set(missing) <= set(_KNOWN_CLAUSE_EXCLUSIONS), f"조항 없는 대상: {sorted(set(missing) - set(_KNOWN_CLAUSE_EXCLUSIONS))}"


def test_real_report_pairs_with_snapshot():
    rpt = _REPORT.read_text(encoding="utf-8")
    m = re.search(r"JSON sha256: ([0-9a-f]{64})", rpt)
    assert m and m.group(1) == hashlib.sha256(_REAL.read_bytes()).hexdigest()
    raw = json.loads(_REAL.read_text(encoding="utf-8"))
    n = sum(len(v.get("clauses") or {}) for v in raw["laws"].values())
    assert f"수록 조항 {n}개" in rpt
