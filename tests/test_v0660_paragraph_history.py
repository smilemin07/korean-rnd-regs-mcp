"""v0.66.0 항별 개정 표지 기반 조문 시행일 안내 — 생성기 순수 함수·저장 게이트·로더·안내 문장·폴백 경로.

네트워크 0. 스냅샷은 임시 파일로 바꿔 끼우고(article_history._reset_for_tests), 생성기 main()은 네트워크 함수를
mock으로 바꿔 돌린다(tests/test_v0630_buchik_clause.py와 같은 방식).
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import korean_rnd_regs_mcp.article_history as ah
import korean_rnd_regs_mcp.main as main_module
from korean_rnd_regs_mcp.live_api import LawApiClient, ResolvedDocId

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import extract_article_history as ext  # noqa: E402

_REAL = ROOT / "src" / "korean_rnd_regs_mcp" / "article_history.json"

_GENERAL = (
    "effective_date(2026-07-01)는 조회된 법령 판본 전체의 시행일이며, 이 조문의 시행일과 같다는 뜻은 아닙니다. "
    "개정 판본의 시행일은 이 조문이 처음 시행된 날과 다를 수 있으므로, 이 응답의 근거만으로 이 조문이 처음 "
    "시행된 날을 단정하지 마십시오. 필요하면 사용자가 국가법령정보센터의 조문 연혁과 부칙에서 확인하도록 "
    "안내하십시오."
)
_OLD_GENERAL_TAIL = "조문별 시행일은 국가법령정보센터의 조문 연혁과 부칙에서 확인하십시오."
_HEAD = (
    "항별 개정 표지 기준(각 항 끝 표지에 적힌 날짜 중 가장 최근 날짜, 공포일): 아래 날짜는 각 표지와 대응하는 "
    "개정 판본의 시행일이며 이 조문이 처음 시행된 날이 아닙니다. 표지가 없는 항·호의 개정 여부는 말하지 않습니다."
)
_SINGLE_TAIL = " 그 부칙에서 조문별 시행일을 따로 정했다면 그에 따릅니다."


def _g(no, pd, ved, items, kind="법률", ak="일부개정", staged=None):
    g = {"law_kind": kind, "promulgation_no": no, "promulgation_date": pd, "amendment_kind": ak,
         "version_effective_date": ved, "items": items}
    if staged:
        g["staged_dates"] = staged
    return g


# 중소기업 기술혁신 촉진법 제27조의2(계획서 4-1 실측 네 쌍) — 조문 단위 레코드 없음(스냅샷 밖)
_G27_2 = [
    _g("21065", "2025-10-01", "2025-10-01", [["1", "개정"]]),
    _g("21289", "2025-12-30", "2026-07-01", [["2", "개정"]]),
    _g("21704", "2026-05-26", "2026-05-26", [["3", "삭제"], ["4", "개정"]]),
]
_REC = {"law_kind": "법률", "promulgation_no": "21704", "promulgation_date": "2026-05-26",
        "version_effective_date": "2026-05-26", "amendment_kind": "일부개정", "change_reason": "조문변경"}
_ARGS = ("sme_tech_act", "JO002702", "281987", "20260701", "eflaw", "2026-07-01")
_CLAUSE = ("제1조(시행일) 이 법은 공포 후 6개월이 경과한 날부터 시행한다. 다만, 제2조의 개정규정은 공포 후 3개월이 "
           "경과한 날부터 시행한다.")
_GUIDANCE = ah._CLAUSE_GUIDANCE


def _law(articles, clauses=None):
    law = {"mst": "281987", "efyd": "2026-07-01", "law_id": "009145", "articles": articles}
    if clauses is not None:
        law["clauses"] = clauses
    return {"sme_tech_act": law}


def _snap(tmp_path, laws, schema=1):
    p = tmp_path / "ah.json"
    p.write_text(json.dumps({"schema": schema, "generated_at": "2026-11-12 10:00 KST", "laws": laws},
                            ensure_ascii=False), encoding="utf-8")
    ah._reset_for_tests(p)
    return p


@pytest.fixture(autouse=True)
def _restore_snapshot():
    yield
    ah._reset_for_tests(_REAL)


# === 1. 생성기: 항 표지 해석(순수 함수) ===

def _art(paras, title="제27조의2(기술혁신 지원)", sub=None):
    """paras: [(항번호, 항내용)] · sub: {항 index: [호·목 줄]} → live_api 형식의 조문 dict."""
    sub = sub or {}
    parts = [title]
    structured = []
    for i, (no, text) in enumerate(paras):
        parts.append(text)
        subs = sub.get(i, [])
        parts.extend("  " + s for s in subs)
        structured.append({"number": no, "text": text, "source_text": text,
                           "subparagraphs": [{"number": "", "text": s, "source_text": s} for s in subs]})
    return {"조문번호": "27", "조문가지번호": "2", "조문내용": "\n".join(parts), "조문참고자료": "",
            "structured": {"title": title, "paragraphs": structured}}


def test_latest_date_is_calendar_max_in_reversed_and_one_digit_markers():
    art = _art([("①", "① 본문. <개정 2025.12.30, 2017.7.26>"),
                ("②", "② 본문. <개정 2025.10.1, 2025.9.30>"),
                ("③", "③ 본문. <신설 2021.4.20>")])
    out, why, st = ext.paragraph_markers(art)
    assert why == "ok"
    assert [(m["no"], m["label"], m["date8"]) for m in out] == [
        (1, "개정", "20251230"), (2, "개정", "20251001"), (3, "신설", "20210420")]
    assert st["self_markers"] == 3 and st["multi_date"] == 2
    assert out[1]["first8"] == "20251001"


def test_deleted_paragraph_label_and_empty_label_fails():
    ok = _art([("①", "① 본문. <개정 2026.5.26>"), ("②", "② 삭제  <2026.5.26>")])
    out, why, _ = ext.paragraph_markers(ok)
    assert why == "ok" and [m["label"] for m in out] == ["개정", "삭제"]
    bad = _art([("①", "① 본문. <2026.5.26>")])  # 무접두·비삭제 = 빈 라벨
    assert ext.paragraph_markers(bad)[:2] == (None, "빈 라벨")


def test_subtree_later_date_fails_and_sub_only_paragraph_ignored():
    later = _art([("①", "① 다음 각 호. <개정 2020.1.1>")], sub={0: ["1. 가 <개정 2025.12.30>"]})
    out, why, st = ext.paragraph_markers(later)
    assert (out, why) == (None, "호·목 표지가 항 표지보다 늦음") and st["sub_later_paras"] == 1
    sub_only = _art([("①", "① 다음 각 호."), ("②", "② 본문. <개정 2024.1.1>")], sub={0: ["1. 가 <개정 2025.12.30>"]})
    out, why, st = ext.paragraph_markers(sub_only)
    assert why == "ok" and [m["no"] for m in out] == [2] and st["sub_only_paras"] == 1
    earlier_sub = _art([("①", "① 각 호. <개정 2025.12.30>")], sub={0: ["1. 가 <개정 2020.1.1>"]})
    assert ext.paragraph_markers(earlier_sub)[1] == "ok"


def test_multiple_self_markers_in_one_paragraph():
    same = _art([("①", "① 앞 <개정 2020.1.1> 뒤 <개정 2024.3.5>")])
    out, why, st = ext.paragraph_markers(same)
    assert why == "ok" and out[0]["date8"] == "20240305" and st["multi_marker_paras"] == 1
    diff = _art([("①", "① 앞 <신설 2020.1.1> 뒤 <개정 2024.3.5>")])
    assert ext.paragraph_markers(diff)[:2] == (None, "한 항 다중 표지 유형 다름")


@pytest.mark.parametrize("text,label,date8", [
    ("① 본문. <신설 2021.1.19, 2026.5.19>", "개정", "20260519"),             # 가장 늦은 날짜 = 신설 뒤 개정
    ("① 본문. <신설 2026.5.19, 2021.1.19>", "개정", "20260519"),             # 역순 표기도 같음
    ("① 본문. <신설 2019.3.1, 2021.1.19, 2026.5.19>", "개정", "20260519"),   # 3개
    ("① 본문. <신설 2021.1.19>", "신설", "20210119"),                        # 날짜 1개 신설은 그대로
    ("① 본문. <개정 2021.1.19, 2026.5.19>", "개정", "20260519"),
])
def test_multi_date_new_marker_relabelled_as_amendment(text, label, date8):
    out, why, st = ext.paragraph_markers(_art([("①", text)]))
    assert why == "ok" and (out[0]["label"], out[0]["date8"]) == (label, date8)
    assert st["relabel_new_to_amend"] == (1 if text.startswith("① 본문. <신설") and "," in text else 0)


def test_server_latest_history_label_unchanged_for_multi_date_new_marker():
    """latest_history는 별도 계약 — 다중 날짜 신설 표지도 종전처럼 '신설'이다(재라벨은 생성기 항별 데이터에만)."""
    art = {"조문내용": "제5조(목적)\n① 본문. <신설 2021.1.19, 2026.5.19>", "조문참고자료": ""}
    assert main_module._article_amendment_history(art) == "신설 2026.5.19(공포)"


def test_title_line_marker_and_unnumbered_paragraph_not_used():
    art = _art([("", "본문만 있는 항 <개정 2024.1.1>")], title="제5조(목적) <개정 2025.1.1>")
    assert ext.paragraph_markers(art)[1] == "항 번호 해석 불가"
    no_para = {"조문내용": "제5조(목적) 본문 <개정 2025.1.1>", "structured": {"title": "", "paragraphs": []}}
    assert ext.paragraph_markers(no_para)[:2] == ([], "ok")
    assert ext.paragraph_markers({"조문내용": "x"})[:2] == ([], "ok")  # structured 없음(가짜 클라이언트 등)


@pytest.mark.parametrize("raw,expect", [("①", 1), ("⑳", 20), ("㉑", 21), ("㉟", 35), ("㊱", 36), ("㊿", 50),
                                        ("3", 3), ("3.", 3), ("", None), ("가", None), ("0", None), ("100", None)])
def test_para_number(raw, expect):
    assert ext.para_number(raw) == expect


def test_generator_reuses_server_marker_regex():
    src = (ROOT / "scripts" / "extract_article_history.py").read_text(encoding="utf-8")
    assert "_CONTENT_HISTORY_MARKER" in src and "_content_marker_label" in src
    assert "re.compile(r\"(삭제)?" not in src  # 측정용 별도 정규식 금지(계획서 5-3)
    assert main_module._content_marker_label("삭제", "2020.1.1") == "삭제"
    assert main_module._content_marker_label(None, "신설 2020.1.1") == "신설"
    assert main_module._content_marker_label(None, "2020.1.1") == ""


# === 2. 생성기: 이력 대응·그룹화 ===

def _e(pd, no, ef, mst, kind="법률", ak="일부개정", jo="002702"):
    return {"시행일자": ef, "공포일자": pd, "공포번호": no, "변경사유": "조문변경", "조문번호": jo,
            "법령일련번호": mst, "법령구분명": kind, "제개정구분명": ak}


_ENTRIES = [_e("20210420", "18108", "20211021", "100"), _e("20251001", "21065", "20251001", "200"),
            _e("20251230", "21289", "20260701", "300"), _e("20260526", "21704", "20260526", "400")]
_ROWS = [{"법령일련번호": m, "시행일자": d} for m, d in
         [("100", "20211021"), ("200", "20251001"), ("300", "20260701"), ("400", "20260526")]]
_MK = [{"no": 1, "label": "개정", "date8": "20251001"}, {"no": 2, "label": "개정", "date8": "20251230"},
       {"no": 3, "label": "삭제", "date8": "20260526"}, {"no": 4, "label": "개정", "date8": "20260526"}]


def test_match_groups_by_promulgation_number_with_per_paragraph_labels():
    groups, why = ext.match_paragraphs(_MK, _ENTRIES, "002702", _ROWS)
    assert why == "ok"
    assert [(g["promulgation_no"], g["version_effective_date"], g["items"]) for g in groups] == [
        ("21065", "2025-10-01", [["1", "개정"]]), ("21289", "2026-07-01", [["2", "개정"]]),
        ("21704", "2026-05-26", [["3", "삭제"], ["4", "개정"]])]
    assert all("staged_dates" not in g for g in groups)


def test_match_staged_group_gets_stage_list():
    rows = _ROWS + [{"법령일련번호": "300", "시행일자": "20260330"}]
    groups, _ = ext.match_paragraphs(_MK[1:2], _ENTRIES, "002702", rows)
    assert groups[0]["staged_dates"] == ["2026-03-30", "2026-07-01"]


@pytest.mark.parametrize("entries,rows,reason", [
    ([], _ROWS, "이력 없음"),
    ([_e("20251001", "21065", "20251001", "200", jo="002703")], _ROWS, "조문번호 왕복 불일치"),
    ([_e("2025101", "21065", "20251001", "200")], _ROWS, "날짜 형식 이상"),
    ([_e("20200101", "1", "20200101", "200")], _ROWS, "이력에 없음"),
    ([_e("20251001", "21065", "20251001", "200"), _e("20251001", "21066", "20251001", "201")], _ROWS, "공포번호 복수"),
    ([_e("20251001", "21065", "20251001", "999")], _ROWS, "단계 표 없음"),
    ([_e("20251001", "21065", "20251001", "200")], [{"법령일련번호": "200", "시행일자": "20251002"}], "단계 표 불일치"),
    ([_e("20251001", "21065", "20251001", "200", kind="법령")], _ROWS, "법령구분명 허용 밖"),
    ([_e("20251001", "21065", "20251001", "200", ak="일부개정(x)")], _ROWS, "제개정구분명 형식 밖"),
    ([_e("20251001", "21065", "20251001", "200", ak="가" * 11)], _ROWS, "제개정구분명 형식 밖"),
])
def test_match_failures(entries, rows, reason):
    assert ext.match_paragraphs(_MK[:1], entries, "002702", rows) == (None, reason)


def test_decision_attach_rules():
    one = [_g("21704", "2026-05-26", "2026-05-26", [["1", "개정"]])]
    two = one + [_g("21289", "2025-12-30", "2026-07-01", [["2", "개정"]])]
    assert ext.paragraph_decision([], _REC) == "none"
    assert ext.paragraph_decision(one, _REC) == "single_same"           # 중복이라 붙이지 않음
    assert ext.paragraph_decision(one, dict(_REC, promulgation_no="1")) == "single_differs"  # 붙이지 않음
    assert ext.paragraph_decision(one, None) == "attach"                # 스냅샷 밖 1그룹
    assert ext.paragraph_decision(two, _REC) == "attach"


def test_paragraph_clause_targets_and_build():
    staged = _g("21421", "2026-03-10", "2026-09-11", [["2", "개정"]], staged=["2026-06-11", "2026-09-11"])
    other = _g("100", "2026-01-01", "2026-09-11", [["3", "개정"]], ak="타법개정", staged=["2026-06-11", "2026-09-11"])
    arts = {"JO0002": {"paragraphs": [staged, other]}}
    assert list(ext.paragraph_clause_targets(arts)) == ["JO0002|21421"]  # 타법개정 제외(조문 단위와 같은 규칙)
    u = {"no": "21421", "date": "20260310", "text": f"부칙 <제21421호,2026.3.10>\n{_CLAUSE}"}
    added, missing = ext.build_paragraph_clauses(arts, [u], {})
    assert added == {"21421|2026-03-10": {"text": _CLAUSE}} and missing == {}
    added, missing = ext.build_paragraph_clauses(arts, [u], {"21421|2026-03-10": {"text": _CLAUSE}})
    assert added == {} and missing == {}  # 조문 단위가 실은 조항 재사용
    added, missing = ext.build_paragraph_clauses(arts, [], {})
    assert added == {} and missing == {"JO0002|21421": "부칙 0건"}


def test_legacy_view_ignores_paragraphs_only():
    old = {"JO0001": _REC}
    new = {"JO0001": dict(_REC, paragraphs=_G27_2), "JO0002": {"paragraphs": _G27_2}}
    assert ext.legacy_bytes_equal(old, new)
    assert not ext.legacy_bytes_equal(old, {"JO0001": dict(_REC, version_effective_date="2026-05-27")})
    a = {"mst": "1", "efyd": "2026-01-01", "articles": old}
    b = {"mst": "1", "efyd": "2026-01-01", "articles": new}
    assert ext.diff_against_existing({"x": a}, {"x": b}) == {}
    assert ext.paragraph_diff({"x": a}, {"x": b}) == {"x": "항별 데이터 2개 조문 차이"}
    assert ext.paragraph_diff({"x": b}, {"x": b}) == {}


# === 3. 생성기 main() 저장 게이트(네트워크 mock) ===

class _FakeClient:
    api_key = "FAKEKEY660"
    base_url = "https://example.invalid/DRF"

    def resolve_latest_doc_id(self, title, target, doc_id, ministry):
        return ResolvedDocId(doc_id="290757", effective_date="20261002", is_updated=False, manifest_doc_id="290757")

    def get_law_detail_staged(self, mst, efyd, title):
        a1 = _art([("①", "① 본문. <개정 2026.3.10>")], title="제1조(목적)")
        a1.update(조문번호="1", 조문가지번호="")
        a2 = _art([("①", "① 본문. <개정 2025.10.1>"), ("②", "② 본문. <개정 2026.3.10>")], title="제2조(정의)")
        a2.update(조문번호="2", 조문가지번호="")
        return {"시행일자": "20261002", "법령ID": "014818", "articles": [a1, a2]}, "eflaw"


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)


def _run_main(tmp_path, monkeypatch, argv, out_old=None):
    import audit_law_stage_diff as asd
    import korean_rnd_regs_mcp.live_api as la
    import korean_rnd_regs_mcp.manifest as mf
    from korean_rnd_regs_mcp.manifest import load_manifest
    out, rpt = tmp_path / "ah.json", tmp_path / "rpt.md"
    if out_old is not None:
        out.write_text(out_old, encoding="utf-8")
    monkeypatch.setattr(ext, "OUT_PATH", out)
    monkeypatch.setattr(ext, "REPORT_PATH", rpt)
    monkeypatch.setattr(la, "LawApiClient", _FakeClient)
    rs = next(r for r in load_manifest() if r.id == "innovation_act")
    monkeypatch.setattr(mf, "load_manifest", lambda *a, **k: [rs])

    class _Col:
        def __init__(self, *a):
            pass

        def stage_rows(self, *a):
            return [{"법령일련번호": "999", "시행일자": "2026-03-10"}, {"법령일련번호": "888", "시행일자": "2025-10-01"}]
    monkeypatch.setattr(asd, "Collector", _Col)
    monkeypatch.setattr(ext, "fetch_article_history", lambda c, lid, jo6: [
        {"시행일자": "20260310", "공포일자": "20260310", "공포번호": "21421", "제개정구분명": "일부개정",
         "법령구분명": "법률", "법령일련번호": "999", "변경사유": "조문변경", "조문번호": jo6},
        {"시행일자": "20251001", "공포일자": "20251001", "공포번호": "21065", "제개정구분명": "타법개정",
         "법령구분명": "법률", "법령일련번호": "888", "변경사유": "조문변경", "조문번호": jo6}])
    monkeypatch.setattr(ext, "fetch_buchik_units", lambda *a: [])
    return ext.main(argv), out, rpt


def _old_snapshot():
    rec = {"law_kind": "법률", "promulgation_no": "21421", "promulgation_date": "2026-03-10",
           "version_effective_date": "2026-03-10", "amendment_kind": "일부개정", "change_reason": "조문변경"}
    return json.dumps({"schema": 1, "rules_version": 4, "laws": {"innovation_act": {
        "mst": "290757", "efyd": "2026-10-02", "law_id": "014818", "articles": {"JO0001": rec, "JO0002": rec}}}},
        ensure_ascii=False)


def test_main_paragraphs_need_flag_and_keep_legacy_fields(tmp_path, monkeypatch):
    old = _old_snapshot()
    code, out, rpt = _run_main(tmp_path, monkeypatch, [], out_old=old)
    assert code == 2 and out.read_text(encoding="utf-8") == old  # 플래그 없으면 저장 안 함
    code, out, rpt = _run_main(tmp_path, monkeypatch, ["--accept-paragraphs"], out_old=old)
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["rules_version"] == 5 and data["schema"] == 1
    arts = data["laws"]["innovation_act"]["articles"]
    old_arts = json.loads(old)["laws"]["innovation_act"]["articles"]
    assert {k: {f: v for f, v in r.items() if f != "paragraphs"} for k, r in arts.items()} == old_arts
    assert "paragraphs" not in arts["JO0001"]  # 그룹 1개 = 레코드와 같음 → 붙이지 않음
    assert [g["promulgation_no"] for g in arts["JO0002"]["paragraphs"]] == ["21065", "21421"]
    assert arts["JO0002"]["paragraphs"][0]["amendment_kind"] == "타법개정"
    r = rpt.read_text(encoding="utf-8")
    assert "## 항별 개정 표지(v0.66.0 결박 수치)" in r and "대상 1 = 그룹 2개 이상 1 + 스냅샷 밖 1그룹 0" in r
    assert "대상 ∩ (대응 실패 ∪ 그룹 1개 다름) = 0건" in r
    assert "다중 날짜 신설 표지 → 개정 재라벨 0" in r
    assert "조항 없이 목록 문장으로 나가는 그룹" in r
    assert "FAKEKEY660" not in out.read_text(encoding="utf-8") + r


def test_main_legacy_field_change_still_needs_accept_diff(tmp_path, monkeypatch):
    raw = json.loads(_old_snapshot())
    raw["laws"]["innovation_act"]["articles"]["JO0001"]["version_effective_date"] = "2026-03-11"
    old = json.dumps(raw, ensure_ascii=False)
    code, out, _ = _run_main(tmp_path, monkeypatch, ["--accept-paragraphs"], out_old=old)
    assert code == 2 and out.read_text(encoding="utf-8") == old  # 기존 6필드 바이트 동일이 아니면 중단


def test_main_same_version_legacy_change_blocks_even_with_both_flags(tmp_path, monkeypatch):
    """--accept-diff는 판본이 바뀐 법령만 덮는다 — 같은 판본에서 기존 6필드가 다르면 두 플래그를 다 줘도 중단."""
    raw = json.loads(_old_snapshot())
    raw["laws"]["innovation_act"]["articles"]["JO0001"]["amendment_kind"] = "전부개정"
    old = json.dumps(raw, ensure_ascii=False)
    code, out, rpt = _run_main(tmp_path, monkeypatch, ["--accept-diff", "innovation_act", "--accept-paragraphs"],
                               out_old=old)
    assert code == 2 and out.read_text(encoding="utf-8") == old and not rpt.exists()


def test_main_version_change_still_accepted_with_accept_diff(tmp_path, monkeypatch):
    raw = json.loads(_old_snapshot())
    raw["laws"]["innovation_act"]["mst"] = "1"
    old = json.dumps(raw, ensure_ascii=False)
    code, out, _ = _run_main(tmp_path, monkeypatch, ["--accept-diff", "innovation_act", "--accept-paragraphs"],
                             out_old=old)
    assert code == 0 and json.loads(out.read_text(encoding="utf-8"))["laws"]["innovation_act"]["mst"] == "290757"


def test_main_blocks_when_runtime_loader_drops_paragraphs(tmp_path, monkeypatch):
    monkeypatch.setattr(ah, "_clean_paragraphs", lambda raw: None)  # 로더가 항별 데이터를 버리는 상황
    old = _old_snapshot()
    code, out, _ = _run_main(tmp_path, monkeypatch, ["--accept-paragraphs"], out_old=old)
    assert code == 2 and out.read_text(encoding="utf-8") == old


def test_main_dry_run_never_saves(tmp_path, monkeypatch):
    code, out, rpt = _run_main(tmp_path, monkeypatch, ["--dry-run", "--accept-paragraphs"], out_old=_old_snapshot())
    assert code == 0 and json.loads(out.read_text(encoding="utf-8"))["rules_version"] == 4 and not rpt.exists()


# === 4. 런타임 안내 문장 ===

def test_27_2_paragraph_only_record_four_pairs(tmp_path):
    _snap(tmp_path, _law({"JO002702": {"paragraphs": _G27_2}}))
    s = ah.article_effective_notice(*_ARGS)
    assert s == "\n".join([
        _GENERAL,
        _HEAD,
        "제1항의 개정 표지(2025-10-01 공포)는 법률 제21065호와 대응하고, 그 판본은 2025-10-01에 시행되었습니다." + _SINGLE_TAIL,
        "제2항의 개정 표지(2025-12-30 공포)는 법률 제21289호와 대응하고, 그 판본은 2026-07-01에 시행되었습니다." + _SINGLE_TAIL,
        "제4항의 개정 표지와 제3항의 삭제 표지(2026-05-26 공포)는 법률 제21704호와 대응하고, 그 판본은 2026-05-26에 "
        "시행되었습니다. 제3항은 이 개정으로 삭제되었습니다." + _SINGLE_TAIL,
    ])
    assert "가장 오래된 변경 기록" not in s


def test_block_follows_existing_sentence_with_newline_boundary(tmp_path):
    rec = dict(_REC, paragraphs=_G27_2)
    _snap(tmp_path, _law({"JO002702": rec, "JO002703": _REC}))
    base = ah.article_effective_notice("sme_tech_act", "JO002703", "281987", "20260701", "eflaw", "2026-07-01")
    s = ah.article_effective_notice(*_ARGS)
    assert s.startswith(base + "\n" + _HEAD + "\n")  # 기존 (a) 문장 접두 동등
    assert "이 조문의 최근 변경 기록(" not in s  # 레코드 공포번호가 그룹에 있음


def test_record_number_absent_sentence(tmp_path):
    rec = dict(_REC, promulgation_no="21999", paragraphs=_G27_2[:2])
    _snap(tmp_path, _law({"JO002702": rec}))
    lines = ah.article_effective_notice(*_ARGS).split("\n")
    assert lines[1] == _HEAD
    assert lines[2] == ("이 조문의 최근 변경 기록(법률 제21999호)의 표지는 항 본문에 없어 어느 항이 바뀌었는지 이 응답으로 "
                        "알 수 없습니다.")


def test_other_law_amendment_and_staged_group_with_clause(tmp_path):
    groups = [
        _g("21065", "2025-10-01", "2025-10-01", [["1", "개정"]], ak="타법개정"),
        _g("21421", "2026-03-10", "2026-09-11", [["2", "신설"], ["3", "개정"]], staged=["2026-06-11", "2026-09-11"]),
    ]
    _snap(tmp_path, _law({"JO002702": {"paragraphs": groups}}, {"21421|2026-03-10": {"text": _CLAUSE}}))
    lines = ah.article_effective_notice(*_ARGS).split("\n")
    assert lines[2] == ("제1항의 개정 표지(2025-10-01 공포)는 법률 제21065호(타법개정)와 대응하고, 그 판본은 2025-10-01에 "
                        "시행되었습니다." + _SINGLE_TAIL)
    assert lines[3] == ("제2항의 신설 표지와 제3항의 개정 표지(2026-03-10 공포)는 법률 제21421호와 대응합니다. 그 판본의 "
                        "시행일은 2026-06-11·2026-09-11로 나뉘어 있어 각 항에 어느 날짜가 해당하는지 이 응답으로 정하지 "
                        "않습니다. 그 개정의 부칙 시행일 조항 원문은 다음과 같습니다.")
    assert lines[4] == _CLAUSE
    assert lines[5] == "이 원문은 그 개정으로 바뀐 부분의 시행일을 정합니다. " + _GUIDANCE


def test_group_subject_order_keeps_paragraph_order_and_deleted_last():
    assert ah._group_subject([(2, "신설"), (3, "개정")]) == "제2항의 신설 표지와 제3항의 개정 표지"
    assert ah._group_subject([(1, "개정"), (2, "개정"), (3, "삭제")]) == "제1항·제2항의 개정 표지와 제3항의 삭제 표지"
    assert ah._group_subject([(1, "삭제"), (2, "신설"), (3, "개정")]) == "제2항의 신설 표지, 제3항의 개정 표지와 제1항의 삭제 표지"


def test_staged_group_without_clause_is_list_sentence(tmp_path):
    groups = [_g("1", "2020-01-01", "2020-01-01", [["1", "개정"]]),
              _g("21421", "2026-03-10", "2026-09-11", [["2", "개정"]], staged=["2026-06-11", "2026-09-11"])]
    _snap(tmp_path, _law({"JO002702": {"paragraphs": groups}}))
    last = ah.article_effective_notice(*_ARGS).split("\n")[-1]
    assert last == ("제2항의 개정 표지(2026-03-10 공포)는 법률 제21421호와 대응합니다. 그 판본의 시행일은 "
                    "2026-06-11·2026-09-11로 나뉘어 있어 이 항에 어느 날짜가 해당하는지 이 응답으로 정하지 않습니다.")


def test_same_clause_printed_once_in_whole_notice(tmp_path):
    staged_rec = dict(_REC, promulgation_no="21421", promulgation_date="2026-03-10", version_effective_date="2026-09-11",
                      staged_dates=["2026-06-11", "2026-09-11"])
    groups = [_g("1", "2020-01-01", "2020-01-01", [["1", "개정"]]),
              _g("21421", "2026-03-10", "2026-09-11", [["2", "개정"]], staged=["2026-06-11", "2026-09-11"])]
    _snap(tmp_path, _law({"JO002702": dict(staged_rec, paragraphs=groups)}, {"21421|2026-03-10": {"text": _CLAUSE}}))
    s = ah.article_effective_notice(*_ARGS)
    assert s.count(_CLAUSE) == 1 and s.count(_GUIDANCE) == 1
    assert s.endswith("그 개정의 부칙 시행일 조항 원문은 위에 실은 것과 같습니다. 판단 방법은 위 안내와 같습니다.")


def test_length_cap_drops_clause_then_oldest_groups(tmp_path):
    long_clause = "제1조(시행일) " + "가" * 560 + " 이 법은 공포한 날부터 시행한다."
    staged = [_g(str(21000 + i), f"2026-0{i}-01", "2026-09-11", [[str(i), "개정"]], staged=["2026-06-11", "2026-09-11"])
              for i in range(1, 6)]
    clauses = {f"{21000 + i}|2026-0{i}-01": {"text": long_clause} for i in range(1, 6)}
    _snap(tmp_path, _law({"JO002702": {"paragraphs": staged}}, clauses))
    s = ah.article_effective_notice(*_ARGS)
    block = s.split("\n", 1)[1]
    assert len(block) <= ah._PARA_BLOCK_MAX_CHARS and long_clause not in block  # 조항 원문부터 생략
    many = [_g(str(21000 + i), f"2026-{(i % 12) + 1:02d}-{(i // 12) + 1:02d}", "2026-09-11",
               [[str(i), "개정"]], staged=["2026-06-11", "2026-09-11"]) for i in range(1, 13)]
    _snap(tmp_path, _law({"JO002702": {"paragraphs": many}}))
    block = ah.article_effective_notice(*_ARGS).split("\n", 1)[1]
    assert len(block) <= ah._PARA_BLOCK_MAX_CHARS and block.endswith(ah._PARA_OMITTED)
    assert "제12항" in block or "제11항" in block  # 최근 공포일 그룹이 남는다
    assert "(2026-02-01 공포)" not in block  # 가장 오래된 그룹(i=1)부터 뺀다


def test_record_absent_sentence_uses_full_group_list_before_cap(tmp_path):
    """레코드 그룹이 길이 제한으로 빠져도 '표지가 항 본문에 없다'고 말하지 않는다(Redteam diff Codex MAJOR)."""
    many = [_g(str(21000 + i), f"2026-{(i % 12) + 1:02d}-{(i // 12) + 1:02d}", "2026-09-11",
               [[str(i), "개정"]], staged=["2026-06-11", "2026-09-11"]) for i in range(1, 13)]
    oldest = min(many, key=lambda g: g["promulgation_date"])
    rec = dict(_REC, promulgation_no=oldest["promulgation_no"], promulgation_date=oldest["promulgation_date"],
               paragraphs=many)
    _snap(tmp_path, _law({"JO002702": rec}))
    s = ah.article_effective_notice(*_ARGS)
    block = s.split("\n" + _HEAD, 1)[1]
    assert block.endswith(ah._PARA_OMITTED)  # 축약이 일어났고
    assert f"({oldest['promulgation_date']} 공포)" not in block  # 레코드 그룹이 빠졌지만
    assert "이 조문의 최근 변경 기록(" not in s  # 부재 문장은 없다
    other = dict(rec, promulgation_no="99999")
    _snap(tmp_path, _law({"JO002702": other}))
    assert "이 조문의 최근 변경 기록(법률 제99999호)" in ah.article_effective_notice(*_ARGS)  # 정말 없을 때는 있다


def test_block_failure_keeps_existing_sentence(tmp_path, monkeypatch):
    _snap(tmp_path, _law({"JO002702": dict(_REC, paragraphs=_G27_2)}))
    base = ah.notice_from_snapshot(ah.load_snapshot(), *_ARGS, with_paragraphs=False)

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(ah, "_paragraph_block", boom)
    assert ah.article_effective_notice(*_ARGS) == base and "\n" not in base


def test_version_mismatch_drops_block_with_general_sentence(tmp_path):
    _snap(tmp_path, _law({"JO002702": dict(_REC, paragraphs=_G27_2)}))
    assert ah.article_effective_notice("sme_tech_act", "JO002702", "999999", "20260701", "eflaw", "2026-07-01") == _GENERAL
    assert ah.article_effective_notice("sme_tech_act", "JO002702", "281987", "20270101", "eflaw", "2026-07-01") == _GENERAL
    assert ah.article_effective_notice("sme_tech_act", "JO002702", "281987", "20260701", "law_fallback",
                                       "2026-07-01") == _GENERAL


# === 5. 로더 ===

@pytest.mark.parametrize("bad", [
    "list-아님",
    [],
    [dict(_G27_2[0], promulgation_no="제21065")],
    [dict(_G27_2[0], law_kind="법율")],
    [dict(_G27_2[0], promulgation_date="2025-02-30")],
    [dict(_G27_2[0], items=[["01", "개정"]])],
    [dict(_G27_2[0], items=[["1", "본조신설"]])],
    [dict(_G27_2[0], items=[])],
    [dict(_G27_2[0], staged_dates=["2026-01-01"])],
    [dict(_G27_2[0], amendment_kind="<img>")],
    [dict(_G27_2[0], law_kind="법률\n")],
    [dict(_G27_2[0], amendment_kind="타법개정\n")],
    [dict(_G27_2[0], items=[["1\n", "개정"]])],
    [dict(_G27_2[0], promulgation_date="2025-10-01\n")],
    [_G27_2[0], dict(_G27_2[1], items=[["1", "개정"]])],  # 항 번호 중복
    [_G27_2[0], dict(_G27_2[1], promulgation_no="21065")],  # 공포번호 중복
])
def test_bad_paragraphs_dropped_only_and_counted(tmp_path, bad, caplog):
    _snap(tmp_path, _law({"JO002703": dict(_REC, paragraphs=bad), "JO002702": {"paragraphs": bad},
                          "JO0001": dict(_REC, paragraphs=_G27_2)}))
    caplog.set_level(logging.INFO, logger="rnd-regs-mcp.article_history")
    snap = ah.load_snapshot()
    arts = snap["laws"]["sme_tech_act"]["articles"]
    assert "paragraphs" not in arts["JO002703"] and arts["JO002703"]["promulgation_no"] == "21704"  # 조문 단위는 유지
    assert "JO002702" not in arts  # 항별 전용 레코드는 남을 것이 없다
    assert len(arts["JO0001"]["paragraphs"]) == 3
    recs = [r for r in caplog.records if r.getMessage().startswith("article_history: 조문")]
    assert [r.getMessage() for r in recs] == ["article_history: 조문 2, paragraphs 1, 형식 탈락 2"]
    assert recs[0].levelno == logging.WARNING
    assert ah.article_effective_notice(*_ARGS) == _GENERAL


def test_load_log_info_when_nothing_dropped_and_legacy_not_counted(tmp_path, caplog):
    _snap(tmp_path, _law({"JO002703": _REC, "JO002702": {"paragraphs": _G27_2}}))
    caplog.set_level(logging.INFO, logger="rnd-regs-mcp.article_history")
    ah.load_snapshot()
    recs = [r for r in caplog.records if r.getMessage().startswith("article_history: 조문")]
    assert [(r.getMessage(), r.levelno) for r in recs] == [("article_history: 조문 1, paragraphs 1, 형식 탈락 0", logging.INFO)]


def test_paragraph_only_record_with_extra_keys_is_rejected(tmp_path):
    _snap(tmp_path, _law({"JO002702": {"paragraphs": _G27_2, "x": 1}}))
    assert "JO002702" not in ah.load_snapshot()["laws"]["sme_tech_act"]["articles"]


# === 6. (c) 새 일반 문장 — 모든 폴백 경로 ===

def test_general_constant_text():
    assert ah.general_notice("2026-07-01") == _GENERAL


@pytest.mark.parametrize("args", [
    ("sme_tech_act", "JO002702", "281987", "20260701", "law_fallback", "2026-07-01"),
    ("sme_tech_act", "JO0099", "281987", "20260701", "eflaw", "2026-07-01"),
    ("innovation_act", "JO0001", "290757", "20261002", "eflaw", "2026-07-01"),
    ("sme_tech_act", "JO002702", "999999", "20260701", "eflaw", "2026-07-01"),
])
def test_every_fallback_path_uses_new_general_sentence(tmp_path, args):
    _snap(tmp_path, _law({"JO002702": dict(_REC, paragraphs=_G27_2)}))
    assert ah.article_effective_notice(*args) == _GENERAL


@pytest.mark.parametrize("content", ["{not json", json.dumps({"schema": 2, "laws": {}})])
def test_broken_snapshot_uses_new_general_sentence(tmp_path, content):
    p = tmp_path / "bad.json"
    p.write_text(content, encoding="utf-8")
    ah._reset_for_tests(p)
    assert ah.article_effective_notice(*_ARGS) == _GENERAL


def test_loader_exception_uses_new_general_sentence(monkeypatch):
    monkeypatch.setattr(ah, "load_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert ah.article_effective_notice(*_ARGS) == _GENERAL


def test_executor_failure_in_detail_uses_new_general_sentence(tmp_path, monkeypatch):
    _snap(tmp_path, _law({"JO002702": {"paragraphs": _G27_2}}))
    c = MagicMock(spec=LawApiClient)
    c.base_url, c.api_key = "https://test.invalid", "fake_v0660_key"
    c.resolve_latest_doc_id.side_effect = lambda title, target, mid, ministry=None: ResolvedDocId(
        doc_id=mid, effective_date="2026-07-01", is_updated=False, manifest_doc_id=mid)
    c.get_law_detail_staged.return_value = ({"법령ID": "009145", "시행일자": "20260701", "articles": [
        {"조문번호": "27", "조문가지번호": "2", "조문제목": "x", "조문내용": "제27조의2(x) 본문", "조문참고자료": "",
         "structured": None}], "annexes": []}, "eflaw")
    monkeypatch.setattr(main_module, "_client_instance", c)
    r = asyncio.run(main_module.get_provision_detail("law:281987:JO002702"))
    assert r["article_effective_notice"].startswith(_GENERAL + "\n" + _HEAD)  # 정상 경로: 일반 문장 + 블록
    real = main_module._run_offloaded

    async def boom(fn, *a):
        if fn is main_module._article_effective_notice:
            raise RuntimeError("executor down")
        return await real(fn, *a)
    monkeypatch.setattr(main_module, "_run_offloaded", boom)
    r = asyncio.run(main_module.get_provision_detail("law:281987:JO002702"))
    assert r["article_effective_notice"] == _GENERAL
    assert r["contract_version"] == "0.41.0"


def test_old_general_sentence_and_oldest_record_wording_absent_everywhere():
    for p in [ROOT / "src" / "korean_rnd_regs_mcp" / "article_history.py", ROOT / "src" / "korean_rnd_regs_mcp" / "main.py",
              ROOT / "src" / "korean_rnd_regs_mcp" / "article_history.json"]:
        text = p.read_text(encoding="utf-8")
        assert _OLD_GENERAL_TAIL not in text, p.name
        assert "가장 오래된 변경 기록" not in text, p.name
        assert '"oldest"' not in text, p.name  # 계획서 5-3: oldest 필드를 만들지 않는다


# === 7. 실제 스냅샷 ===

def test_real_snapshot_paragraphs_load_without_drops(caplog):
    caplog.set_level(logging.INFO, logger="rnd-regs-mcp.article_history")
    ah._reset_for_tests(_REAL)
    snap = ah.load_snapshot()
    msgs = [r.getMessage() for r in caplog.records if r.getMessage().startswith("article_history: 조문")]
    assert len(msgs) == 1 and msgs[0].endswith("형식 탈락 0")
    n_para = sum(1 for v in snap["laws"].values() for a in v["articles"].values() if a.get("paragraphs"))
    assert 101 <= n_para <= 137  # 계획 119 ± 15%
    raw = json.loads(_REAL.read_text(encoding="utf-8"))
    assert raw["schema"] == 1 and raw["rules_version"] == ext.RULES_VERSION == 5


def test_real_snapshot_27_2_four_pairs():
    ah._reset_for_tests(_REAL)
    law = ah.load_snapshot()["laws"]["sme_tech_act"]
    rec = law["articles"]["JO002702"]
    pairs = {(n, label, g["promulgation_no"], g.get("staged_dates") and tuple(g["staged_dates"]) or g["version_effective_date"])
             for g in rec["paragraphs"] for n, label in g["items"]}
    assert pairs == {(1, "개정", "21065", "2025-10-01"), (2, "개정", "21289", "2026-07-01"),
                     (3, "삭제", "21704", "2026-05-26"), (4, "개정", "21704", "2026-05-26")}


def test_real_snapshot_freshness_checker_still_parses():
    import check_article_history_freshness as chk
    gen, laws = chk.parse_snapshot(_REAL.read_text(encoding="utf-8"))
    assert gen and len(laws) == 35
