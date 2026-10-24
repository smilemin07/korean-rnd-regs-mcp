"""v0.59.0 법령명·조문 번호 질의 도달성 개선 — 법령명+번호 고정·search_note·도구 설명·검증 로그.

네트워크 0(mock 클라이언트). 규정별로 다른 본문과 조회 경로(eflaw·law_fallback·law)를 줄 수 있게
전용 mock을 쓴다(test_tools의 mock_client는 모든 법령에 같은 본문을 돌려줘 고정 검증에 맞지 않음).
"""
import asyncio
import copy
import json
import logging
from unittest.mock import MagicMock

import pytest

import korean_rnd_regs_mcp.main as main_module
from korean_rnd_regs_mcp.live_api import LawApiClient, LawApiError, ResolvedDocId
from korean_rnd_regs_mcp.main import (
    _COLLOQUIAL_LAW_NAMES,
    _OFFICIAL_LAW_ABBREVIATIONS,
    _SEARCH_NOTE_ZERO,
    _STAGE_FALLBACK_NOTICE,
    _detect_law_unit_refs,
    _pin_names,
    list_rule_sets,
    search_provision,
    suggest_review_sources,
)
from korean_rnd_regs_mcp.manifest import load_manifest

_ALL = load_manifest()
_FAKE_KEY = "fake_secret_key_v0590_xyz"


def _refs(q, items=None):
    return [(r["rule_set_id"], r["unit_id"]) for r in _detect_law_unit_refs(q, items or _ALL)]


# === 1. 이름 집합 ===

def test_official_and_colloquial_targets_exist():
    ids = {rs.id for rs in _ALL}
    assert set(_OFFICIAL_LAW_ABBREVIATIONS) <= ids
    assert set(_COLLOQUIAL_LAW_NAMES.values()) <= ids
    assert len(_OFFICIAL_LAW_ABBREVIATIONS) == 20  # law 35건 중 법령약칭명이 있는 20건(2026-10-24 LIVE)


def test_name_set_unique_across_rule_sets():
    """정규화형 이름이 두 규정에 동시에 속하지 않는다(오고정의 1차 방어)."""
    owner: dict[str, str] = {}
    for name, rid, _c in _pin_names(_ALL):
        assert owner.setdefault(name, rid) == rid, f"이름 {name}이 {owner[name]}·{rid} 두 규정에 속함"


def test_every_containing_pair_resolves_to_the_longer_name():
    """한 이름이 다른 규정 이름에 들어 있으면(24쌍+약칭), 긴 이름 + 번호는 긴 이름의 규정으로 잡힌다."""
    names = _pin_names(_ALL)
    pairs = [(n2, r2) for n1, r1, _ in names for n2, r2, _ in names if r1 != r2 and n1 in n2 and n1 != n2]
    assert pairs  # 포함 관계가 실재한다
    for longer, rid in pairs:
        assert _refs(f"{longer} 제1조") == [(rid, "JO0001")], longer


# === 2. 탐지 표 ===

@pytest.mark.parametrize("q, expected", [
    ("중소기업 기술혁신 촉진법 제27조의3", [("sme_tech_act", "JO002703")]),
    ("중소기업기술혁신법 제27조의3", [("sme_tech_act", "JO002703")]),
    ("중소기업 기술 혁신법 제27조의3", [("sme_tech_act", "JO002703")]),  # 공식 약칭 최장 일치
    ("혁신법 제32조와 산업기술혁신법 제11조의2", [("innovation_act", "JO0032"), ("industry_tech_act", "JO001102")]),
    ("현행 혁신법 제32조", [("innovation_act", "JO0032")]),
    ("연구개발 혁신법 제32조", [("innovation_act", "JO0032")]),
    ("제재처분 기준은 혁신법 제32조", [("innovation_act", "JO0032")]),
    ("「국가연구개발혁신법」 제32조", [("innovation_act", "JO0032")]),
    ("국가연구개발혁신법 시행령 제26조", [("innovation_decree", "JO0026")]),
    ("혁신법 시행령 제26조에 따른 별표", [("innovation_decree", "JO0026")]),
    ("연구개발비 사용 기준 별표 2", [("rnd_funding_standard", "BP0002")]),
    ("연구개발비 사용기준 [별표 2의2]", [("rnd_funding_standard", "BP000202")]),
    ("자율주행기술개발혁신사업 운영관리규정 제5조", [("kt_autonomous_driving", "JO0005")]),  # 앞 괄호 없이
    ("국방과학 기술료 산정·징수방법 및 징수절차 등에 관한 고시 제3조", [("defense_tech_fee_notice", "JO0003")]),  # ㆍ/·
    ("국방과학기술혁신법 시행령 제10조", [("defense_tech_decree", "JO0010")]),
    ("혁신법 제27조 의3", [("innovation_act", "JO002703")]),
    ("혁신법 제27조의3제1항", [("innovation_act", "JO002703")]),
    ("혁신법 제32조 1항", [("innovation_act", "JO0032")]),
    ("혁신법 제32조에 따라", [("innovation_act", "JO0032")]),
    ("혁신법 제３２조", [("innovation_act", "JO0032")]),  # 전각 숫자
    ("혁신법 제1조 제2조 제3조와 학술진흥법 제4조", [("innovation_act", "JO0001"), ("hakjin_act", "JO0004")]),
    ("제재처분(혁신법 제32조)", [("innovation_act", "JO0032")]),
    ("부정행위(국가연구개발혁신법 제31조)", [("innovation_act", "JO0031")]),
    ("혁신법 제32조①", [("innovation_act", "JO0032")]),
])
def test_detect_pins(q, expected):
    assert _refs(q) == expected


@pytest.mark.parametrize("q", [
    "산업 혁신법 제5조", "기술 혁신법 제5조", "중소기업 혁신법 제5조", "국방 혁신법 제5조",
    "산업기술 혁신법 시행령 제5조", "산업 혁신법 시행령 제5조", "중소기업 혁신법 시행규칙 제2조",
    "옛 혁신법 제32조", "舊 혁신법 제32조", "개정 전 혁신법 제32조", "개정전 혁신법 제32조", "폐지된 혁신법 제32조",
    "혁신법 제32조∼제34조", "혁신법 제32조～제34조", "혁신법 제32조〜제34조", "혁신법 제32조, 부터",
    "산업ㆍ기술 혁신법 제5조", "산업·기술 혁신법 제5조", "구(舊) 혁신법 제32조", "혁신법 제32조–제34조", "혁신법 제32조—제34조", "혁신법 제32조 내지 제34조",
    "혁신법 제10000조", "혁신법 제27조의100", "혁신법 제27조의03", "혁신법 제27조의3 항", "혁신법 제27조의٣",
    "혁신법 제27조의3의٢",
    "구 혁신법 제32조", "구 「혁신법」 제32조", "구 국가연구개발혁신법 제32조", "종전 혁신법 제32조",
    "제27조의3", "혁신법 32조", "혁신법 제032조", "혁신법 제32조의0", "혁신법 제27조의3항",
    "혁신법 제27조의3의2", "혁신법 제32조부터 제34조까지", "혁신법 제32조~제34조", "혁신법 제32-2조",
    "혁신법 제27조3", "연구개발비 사용 기준 1조원", "혁신법의 제32조", "혁신법 별지 1",
    "중소기업기술혁신촉진법제27조의3a중소기업", "",
])
def test_detect_no_pin(q):
    if q == "중소기업기술혁신촉진법제27조의3a중소기업":
        # 붙여 쓴 정식 제목은 인정(앞 글자 없음), 번호 뒤 영문은 무시 — 대조용 양성 사례
        assert _refs(q) == [("sme_tech_act", "JO002703")]
        return
    assert _refs(q) == []


def test_every_official_abbreviation_pins_its_rule_set():
    for rid, abbr in _OFFICIAL_LAW_ABBREVIATIONS.items():
        assert _refs(f"{abbr} 제1조") == [(rid, "JO0001")], abbr


def test_detect_caps_at_three_and_dedupes():
    q = "혁신법 제1조, 혁신법 제1조, 학술진흥법 제2조, 산학협력법 제3조, 연구실안전법 제4조"
    assert _refs(q) == [("innovation_act", "JO0001"), ("hakjin_act", "JO0002"), ("sanhak_act", "JO0003")]


# === 3. search_provision 동작 (mock) ===

_SUBSET = ("sme_tech_act", "innovation_act", "rnd_funding_standard", "hakjin_act", "defense_standard_agreement")


def _law(mst, title, articles, annexes=None, annex_parse_error=None):
    return {"법령일련번호": mst, "법령명한글": title, "시행일자": "20260526",
            "articles": articles, "annexes": annexes or [], "annex_parse_error": annex_parse_error}


@pytest.fixture
def pin_env(monkeypatch):
    """규정별 본문·basis를 고를 수 있는 mock. env['law'][mst] = detail, env['basis'][mst] = basis."""
    subset = [rs for rs in _ALL if rs.id in _SUBSET]
    assert len(subset) == len(_SUBSET)
    monkeypatch.setattr("korean_rnd_regs_mcp.main.load_manifest", lambda: subset)
    by_id = {rs.id: rs for rs in subset}
    env = {"law": {}, "basis": {}, "admrul": {}, "raise": {}, "rs": by_id}
    sme = by_id["sme_tech_act"]
    env["law"][sme.api_doc_id] = _law(sme.api_doc_id, sme.title, [
        {"조문번호": "27", "조문가지번호": "03", "조문제목": "사업화 금융지원",
         "조문내용": "제27조의3(사업화 금융지원) 정부는 중소기업의 기술 사업화를 위하여 금융지원을 할 수 있다."},
        {"조문번호": "27", "조문가지번호": "04", "조문제목": "기술혁신 촉진",
         "조문내용": "제27조의4(기술혁신 촉진) 종전 제27조의3에서 이동한 조문."},
    ])
    inn = by_id["innovation_act"]
    env["law"][inn.api_doc_id] = _law(inn.api_doc_id, inn.title, [
        {"조문번호": "32", "조문제목": "제재처분",
         "조문내용": "제32조(부정행위 등에 대한 제재처분) ① 중앙행정기관의 장은 혁신법 위반에 제재부가금을 "
                     "부과할 수 있다. <개정 2025. 12. 30.>"},
        {"조문번호": "33", "조문제목": "재검토 요청",
         "조문내용": "제33조(재검토 요청) 혁신법 제32조에 따른 제재처분에 대하여 재검토를 요청할 수 있다."},
        {"조문번호": "34", "조문제목": "", "조문내용": "제34조 삭제 <2024. 1. 2.>"},
    ])
    hak = by_id["hakjin_act"]
    env["law"][hak.api_doc_id] = _law(hak.api_doc_id, hak.title, [
        {"조문번호": "20", "조문제목": "학술지원", "조문내용": "제20조(학술지원) 학술 연구를 지원한다."},
    ], annexes=[{"별표번호": "1", "별표가지번호": "", "별표구분": "별표", "별표제목": "학술지원 기준",
                  "별표내용": "학술지원 기준 표"}])
    dsa = by_id["defense_standard_agreement"]
    env["admrul"][dsa.api_doc_id] = {"articles": [{"조문번호": "1", "조문제목": "목적", "조문내용": "제1조(목적) 협약."}],
                                    "annexes": [{"별표번호": "1", "별표구분": "별지", "별표제목": "협약서 서식",
                                                 "별표내용": "서식"}]}
    rnd = by_id["rnd_funding_standard"]
    env["admrul"][rnd.api_doc_id] = {"articles": [], "annexes": [
        {"별표번호": "2", "별표가지번호": "00", "별표구분": "별표", "별표제목": "연구개발비 사용용도",
         "별표내용": "인건비 학생인건비 연구활동비 " * 900},
    ]}
    client = MagicMock(spec=LawApiClient)
    client.base_url = "https://test.invalid"
    client.api_key = _FAKE_KEY

    def _resolve(title, api_target, manifest_doc_id, ministry=None):
        return ResolvedDocId(doc_id=manifest_doc_id, effective_date="", is_updated=False,
                             manifest_doc_id=manifest_doc_id)

    def _staged(mst, efyd="", expected_title=""):
        if mst in env["raise"]:
            raise env["raise"][mst]
        return env["law"][mst], env["basis"].get(mst, "eflaw")

    def _admrul(doc_id):
        if doc_id in env["raise"]:
            raise env["raise"][doc_id]
        return env["admrul"][doc_id]

    client.resolve_latest_doc_id.side_effect = _resolve
    client.get_law_detail_staged.side_effect = _staged
    client.get_admin_rule_detail.side_effect = _admrul
    monkeypatch.setattr(main_module, "_client_instance", client)
    return env


def _run(q):
    return asyncio.run(search_provision(q))


def test_gate_d_query_pins_new_article(pin_env):
    r = _run("중소기업 기술혁신 촉진법 제27조의3")
    assert r["results"][0]["unit_id"] == "JO002703"
    assert r["results"][0]["rule_set_id"] == "sme_tech_act"
    assert "사업화 금융지원" in r["results"][0]["title"]
    assert any("제21704호" in w and "2026-05-26" in w for w in r["results"][0]["warnings"])
    assert r["total"] == 1 and r["returned"] == 1 and r["truncated"] is False
    assert r["search_note"] == "질의의 「중소기업 기술혁신 촉진법」 제27조의3에 해당하는 단위를 앞쪽 결과에 두었습니다."


def test_pinned_warnings_follow_detail_composition(pin_env):
    sme = pin_env["rs"]["sme_tech_act"]
    # eflaw 성공: 감사 고지 억제·폴백 고지 없음 = known_limitations만
    r = _run("중소기업기술혁신법 제27조의3")
    assert r["results"][0]["warnings"] == list(sme.known_limitations)
    # law_fallback: 감사 고지(감사 판본 일치) + 폴백 고지가 선두
    pin_env["basis"][sme.api_doc_id] = "law_fallback"
    r = _run("중소기업기술혁신법 제27조의3")
    w = r["results"][0]["warnings"]
    assert w[0] == sme.stage_notice.text and w[1] == _STAGE_FALLBACK_NOTICE
    assert w[2:] == list(sme.known_limitations)
    # law(스냅샷): 감사 고지만
    pin_env["basis"][sme.api_doc_id] = "law"
    r = _run("중소기업기술혁신법 제27조의3")
    assert r["results"][0]["warnings"][0] == sme.stage_notice.text
    assert _STAGE_FALLBACK_NOTICE not in r["results"][0]["warnings"]


def test_pin_dedupes_normal_match_and_keeps_order(pin_env, monkeypatch):
    # "혁신법 제32조": 제32조·제33조 본문 모두 '혁신법'·'제32조'를 담아 정규 매치가 된다.
    q = "혁신법 제32조"
    with monkeypatch.context() as m:
        m.setattr(main_module, "_detect_law_unit_refs", lambda *a, **k: [])
        plain = _run(q)
    plain_ids = [x["provision_id"] for x in plain["results"]]
    assert len(plain_ids) == 2 and any(p.endswith(":JO0032") for p in plain_ids)
    r = _run(q)
    pids = [x["provision_id"] for x in r["results"]]
    assert pids[0].endswith(":JO0032")
    assert len(pids) == len(set(pids)) == 2                       # 고정과 같은 정규 매치는 한 번만
    assert pids[1:] == [p for p in plain_ids if p != pids[0]]     # 나머지는 종전 순서 그대로
    assert r["total"] == 2 and r["returned"] == 2 and r["truncated"] is False


def test_pinned_law_article_keeps_latest_history(pin_env):
    r = _run("혁신법 제32조")
    assert r["results"][0]["latest_history"].startswith("개정 2025.12.30")


def test_deleted_article_is_pinned_as_is(pin_env):
    r = _run("혁신법 제34조")
    assert r["results"][0]["unit_id"] == "JO0034"
    assert "삭제" in r["results"][0]["snippet"]


def test_pinned_warnings_use_resolved_doc_id(pin_env):
    """resolve가 감사 판본과 다른 ID를 주면 상세 경로와 같이 '정합 미확인' 일반 경고가 선두."""
    sme = pin_env["rs"]["sme_tech_act"]
    new_id = "999999"
    pin_env["law"][new_id] = pin_env["law"][sme.api_doc_id]
    pin_env["basis"][new_id] = "law"
    client = main_module._client_instance
    orig = client.resolve_latest_doc_id.side_effect

    def _resolve(title, api_target, manifest_doc_id, ministry=None):
        if manifest_doc_id == sme.api_doc_id:
            return ResolvedDocId(doc_id=new_id, effective_date="", is_updated=True, manifest_doc_id=manifest_doc_id)
        return orig(title, api_target, manifest_doc_id, ministry)
    client.resolve_latest_doc_id.side_effect = _resolve
    r = _run("중소기업기술혁신법 제27조의3")
    assert r["results"][0]["provision_id"] == f"law:{new_id}:JO002703"
    w0 = r["results"][0]["warnings"][0]
    assert w0.startswith("주의(시행 단계 정합 미확인)") and f"(문서 ID {new_id})" in w0


def test_normal_query_without_name_has_no_note(pin_env):
    r = _run("제재부가금")
    assert r["results"] and "search_note" not in r


def test_zero_results_without_name_gets_zero_note(pin_env):
    r = _run("존재하지않는낱말 조합")
    assert r["results"] == []
    assert r["search_note"] == _SEARCH_NOTE_ZERO


def test_absent_number_sentence(pin_env):
    r = _run("학술진흥법 제99조")
    assert r["results"] == []
    assert r["search_note"].startswith("「학술진흥법」에서 제99조에 해당하는 단위를 찾지 못했습니다.")
    assert r["search_note"].endswith(_SEARCH_NOTE_ZERO)


def test_annex_pin_regardless_of_unit_types(pin_env):
    assert pin_env["rs"]["hakjin_act"].unit_types.value == "article"
    r = _run("학술진흥법 별표 1")
    assert r["results"][0]["unit_id"] == "BP0001"
    assert "search_note" in r and "별표 1" in r["search_note"]


def test_annex_absent_mentions_byeolji(pin_env):
    r = _run("무기체계 연구개발 표준협약서 별표 1")
    assert "(별지·서식은 조회 대상이 아닙니다.)" in r["search_note"]


def test_unreceived_rule_set_sentence(pin_env):
    hak = pin_env["rs"]["hakjin_act"]
    pin_env["raise"][hak.api_doc_id] = LawApiError("parse_failed", "x")
    r = _run("학술진흥법 제20조")
    assert r["search_note"].startswith("「학술진흥법」 자료를 이번 검색에서 받지 못해 제20조에 해당하는 단위를 확인하지 못했습니다.")
    assert "찾지 못했습니다" not in r["search_note"]


def test_annex_parse_error_sentence(pin_env):
    hak = pin_env["rs"]["hakjin_act"]
    pin_env["law"][hak.api_doc_id]["annex_parse_error"] = "XML 오류"
    pin_env["law"][hak.api_doc_id]["annexes"] = []
    r = _run("학술진흥법 별표 1")
    assert "별표 자료를 이번 검색에서 읽지 못해 별표 1에 해당하는 단위를 확인하지 못했습니다" in r["search_note"]
    assert "찾지 못했습니다" not in r["search_note"]


def test_auth_failure_suppresses_annex_parse_note(pin_env):
    """일부 규정만 인증 실패(합쳐진 auth 항목) + 대상 별표 파싱 실패 → 미수신 계열 문장 없음."""
    hak = pin_env["rs"]["hakjin_act"]
    pin_env["raise"][pin_env["rs"]["sme_tech_act"].api_doc_id] = LawApiError("auth_failed", "사용자 정보 검증에 실패")
    pin_env["law"][hak.api_doc_id]["annex_parse_error"] = "XML 오류"
    pin_env["law"][hak.api_doc_id]["annexes"] = []
    r = _run("학술진흥법 별표 1")
    assert "search_note" not in r


def test_auth_failure_suppresses_unreceived_and_zero_notes(pin_env):
    for rs in pin_env["rs"].values():
        pin_env["raise"][rs.api_doc_id] = LawApiError("auth_failed", "사용자 정보 검증에 실패")
    r = _run("학술진흥법 제20조")
    assert r["results"] == [] and "search_note" not in r
    assert r["errors"][0]["code"] == "auth_failed"


def test_large_annex_pin_within_budget(pin_env):
    r = _run("연구개발비 사용 기준 별표 2")
    assert r["results"][0]["unit_id"] == "BP0002"
    assert len(r["results"][0]["snippet"]) <= 2000
    assert len(json.dumps(r, ensure_ascii=False)) <= 16000


def test_budget_worst_case_three_fallback_pins(pin_env):
    """고정 3건(폴백 고지 포함) + 질의 토큰을 모두 담은 긴 정규 매치 40건 → 예산이 실제로 차고 절단된다."""
    q = "중소기업 기술혁신 촉진법 제27조의3 혁신법 제32조 학술진흥법 제20조"
    for mst in list(pin_env["law"]):
        pin_env["basis"][mst] = "law_fallback"
    big = (q + " 본문 ") * 120
    sme = pin_env["rs"]["sme_tech_act"]
    pin_env["law"][sme.api_doc_id]["articles"] += [
        {"조문번호": str(n), "조문제목": "중소기업 지원", "조문내용": big} for n in range(100, 140)]
    r = _run(q)
    assert [m["unit_id"] for m in r["results"][:3]] == ["JO002703", "JO0032", "JO0020"]
    assert r["total"] == 43 and r["returned"] < 30 and r["truncated"] is True
    assert len(json.dumps(r, ensure_ascii=False)) <= 16000
    assert r["search_note"].count("앞쪽 결과에 두었습니다") == 3
    assert all(_STAGE_FALLBACK_NOTICE in m["warnings"] for m in r["results"][:3])


def test_cached_detail_not_mutated(pin_env, monkeypatch):
    snap = copy.deepcopy((pin_env["law"], pin_env["admrul"]))
    _run("중소기업 기술혁신 촉진법 제27조의3")
    _run("혁신법 제32조와 학술진흥법 별표 1")
    _run("연구개발비 사용 기준 별표 2")
    monkeypatch.setattr(main_module, "_search_note_pinned", lambda *a, **k: 1 / 0)  # 예외 경로
    _run("혁신법 제32조와 학술진흥법 별표 1")
    assert (pin_env["law"], pin_env["admrul"]) == snap


def test_atomic_fallback_on_second_pin_failure(pin_env, monkeypatch):
    """첫 고정을 만든 뒤 두 번째에서 실패해도 고정·안내가 전부 사라지고 정규 결과·순서는 종전 그대로."""
    q = "혁신법 제32조 학술진흥법 제20조"
    pin_env["law"][pin_env["rs"]["innovation_act"].api_doc_id]["articles"].append(
        {"조문번호": "40", "조문제목": "인용", "조문내용": "제40조 혁신법 제32조 학술진흥법 제20조를 함께 본다."})
    with monkeypatch.context() as m:
        m.setattr(main_module, "_detect_law_unit_refs", lambda *a, **k: [])
        baseline = _run(q)
    assert baseline["results"] and "search_note" not in baseline
    calls = {"n": 0}
    real = main_module._detail_warnings

    def _second_fails(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return real(*a, **k)
    monkeypatch.setattr(main_module, "_detail_warnings", _second_fails)
    got = _run(q)
    assert calls["n"] == 2 and got == baseline


@pytest.mark.parametrize("target", ["_detect_law_unit_refs", "_search_note_pinned", "_detail_warnings", "unit_label"])
def test_atomic_fallback_on_exception(pin_env, monkeypatch, target):
    """고정 경로 어디서 예외가 나도 고정·안내 조각이 전부 사라지고 고정 없는 응답과 같다."""
    q = "혁신법 제32조 제재부가금"
    with monkeypatch.context() as m:
        m.setattr(main_module, "_detect_law_unit_refs", lambda *a, **k: [])
        baseline = _run(q)
    assert _run(q)["results"][0]["unit_id"] == "JO0032"  # 정상 경로에서는 실제로 고정된다

    def _boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(main_module, target, _boom)
    got = _run(q)
    assert got == baseline
    # 정규 매치가 있는 질의라 안내 필드가 아예 없어야 한다(고정 안내 조각이 새지 않음)
    assert got["results"] and "search_note" not in got


def test_result_summary_log_integers_only(pin_env, caplog):
    with caplog.at_level(logging.INFO, logger="rnd-regs-mcp"):
        _run("중소기업 기술혁신 촉진법 제27조의3")
    lines = [r.getMessage() for r in caplog.records if "event=search_result_summary" in r.getMessage()]
    assert lines == ["event=search_result_summary total=1 returned=1 pinned=1 note_parts=1"]
    assert all(r.levelno == logging.INFO for r in caplog.records if "search_result_summary" in r.getMessage())


def test_suggest_gets_pinned_candidate_without_note(pin_env):
    r = asyncio.run(suggest_review_sources("제27조의3 시행일", keywords=["중소기업 기술혁신 촉진법 제27조의3"]))
    assert any(c["unit_id"] == "JO002703" for c in r["candidates"])
    assert "search_note" not in r


# === 4. 도구 설명 ===

def test_tool_descriptions_v0590():
    from korean_rnd_regs_mcp.main import mcp
    tools = {t.name: t for t in asyncio.run(mcp.list_tools(run_middleware=False))}
    sp = tools["search_provision"].description
    assert len(sp) <= 2000
    for tok in ("list_rule_sets", "별지·서식은 검색하지 않습니다", "제N조(의M) 또는 별표N(의M)",
                "검색 0건은 수록 범위 밖이라는 뜻이 아닙니다", "warnings", "search_note"):
        assert tok in sp
    for dev in ("manifest", "v0.2.1", "live_api", "혁신법·시행령·시행규칙)"):
        assert dev not in sp
    lr = tools["list_rule_sets"].description
    assert lr == ("본 서버가 수록한 법령·행정규칙 목록입니다. 검색이 0건이거나 질문의 법령이 수록 대상인지 "
                  "불확실할 때 호출하십시오. effective_date는 등록 시점 값이며, 현행 여부는 unit 없이 "
                  "get_provision_detail로 확인하십시오.")
    assert asyncio.run(list_rule_sets())["contract_version"] == "0.37.0"
