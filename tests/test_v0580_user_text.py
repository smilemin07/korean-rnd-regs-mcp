"""v0.58.0 사용자 안내문 정비 가드 — known_limitations·revision_notice 문면.

이 문면은 검색 매치(search_provision·suggest_review_sources)와 상세(get_provision_detail)의
`warnings`로 그대로 실린다. 아래 가드가 지키는 것:
  1) 규정별 길이 비증가: 검색 응답은 정렬된 매치를 앞에서부터 16,000자까지 쌓고 넘치는 지점에서 자른다
     (main.py search_provision). 어떤 규정의 문면이 길어지면 그 규정 매치가 앞쪽에 오는 질의에서
     returned가 줄 수 있다(배포 게이트 자동 BLOCK 신호). _V0570_LEN은 v0.57.0 실측 기준선으로 고정한다 —
     표본 질의 A/B로는 모든 질의의 비감소를 보장할 수 없으므로, 늘려야 하면 별도 릴리스에서 판단한다.
  2) 개발용 표기·변동값 금지: 낡는 값(조문·별표 수, 검증일, 현재 발령번호)과 내부 용어를 응답에 싣지 않는다.
  3) 원소 개수 스냅샷: YAML 주석·따옴표 실수로 문장이 조용히 빠지는 것을 잡는다.
"""
import json
import re
from pathlib import Path

import yaml
from types import SimpleNamespace

from korean_rnd_regs_mcp.live_api import ResolvedDocId
from korean_rnd_regs_mcp.main import _revision_notice
from korean_rnd_regs_mcp.manifest import load_manifest

# v0.57.0 규정별 json.dumps(known_limitations, ensure_ascii=False) 길이(상한)
_V0570_LEN = {
    "innovation_act": 2, "innovation_decree": 190, "innovation_rule": 2, "rnd_funding_standard": 171,
    "simultaneous_research_limit": 76, "facility_equipment_standard": 95, "research_note_guideline": 130, "innovation_challenge_criteria": 232,
    "sector_kt_act": 58, "sector_kt_decree": 36, "sector_kt_rule": 2, "kt_rnd_operations": 129,
    "kt_autonomous_driving": 360, "industry_tech_act": 37, "industry_tech_decree": 49, "industry_tech_rule": 106,
    "industry_tech_operating": 194, "industry_tech_security": 196, "industry_tech_evaluation": 259, "sme_tech_act": 133,
    "sme_tech_decree": 56, "sme_tech_rule": 55, "sme_rnd_operating": 163, "performance_eval_act": 81,
    "performance_eval_decree": 36, "rnd_info_processing": 138, "rnd_security_measures": 103, "msit_rnd_processing": 238,
    "large_rnd_plan_review": 146, "build_type_rnd_screening": 269, "ict_rnd_management": 151, "ict_research_ethics": 86,
    "tech_fee_integrated": 164, "sme_tech_fee": 124, "health_tech_act": 48, "health_tech_decree": 33,
    "health_tech_rule": 93, "health_rnd_operating": 174, "kdca_rnd_management": 169, "kdca_agency_designation": 80,
    "kdca_facility_equipment": 142, "kdca_relay_operating": 274, "hakjin_act": 54, "hakjin_decree": 84,
    "hakjin_rule": 62, "sanhak_act": 61, "sanhak_decree": 65, "sanhak_rule": 63,
    "research_ethics_guideline": 91, "corp_lab_act": 46, "corp_lab_decree": 45, "corp_lab_rule": 113,
    "research_industry_act": 48, "research_industry_decree": 44, "research_industry_rule": 65, "lab_safety_act": 54,
    "lab_safety_decree": 61, "lab_safety_rule": 55, "defense_tech_act": 221, "defense_tech_decree": 64,
    "defense_tech_rule": 131, "defense_rnd_guideline": 201, "defense_tech_fee_notice": 218, "defense_future_challenge_guideline": 243,
    "defense_facility_equipment": 244, "defense_standard_agreement": 157,
}

# v0.58.0 규정별 known_limitations 원소 수
_V0580_COUNT = {
    "innovation_act": 0, "innovation_decree": 1, "innovation_rule": 0, "rnd_funding_standard": 2,
    "simultaneous_research_limit": 0, "facility_equipment_standard": 1, "research_note_guideline": 1, "innovation_challenge_criteria": 2,
    "sector_kt_act": 1, "sector_kt_decree": 0, "sector_kt_rule": 0, "kt_rnd_operations": 2,
    "kt_autonomous_driving": 2, "industry_tech_act": 0, "industry_tech_decree": 0, "industry_tech_rule": 1,
    "industry_tech_operating": 3, "industry_tech_security": 2, "industry_tech_evaluation": 3, "sme_tech_act": 1,
    "sme_tech_decree": 0, "sme_tech_rule": 1, "sme_rnd_operating": 2, "performance_eval_act": 1,
    "performance_eval_decree": 0, "rnd_info_processing": 1, "rnd_security_measures": 1, "msit_rnd_processing": 3,
    "large_rnd_plan_review": 1, "build_type_rnd_screening": 2, "ict_rnd_management": 2, "ict_research_ethics": 1,
    "tech_fee_integrated": 2, "sme_tech_fee": 2, "health_tech_act": 1, "health_tech_decree": 0,
    "health_tech_rule": 1, "health_rnd_operating": 1, "kdca_rnd_management": 1, "kdca_agency_designation": 1,
    "kdca_facility_equipment": 1, "kdca_relay_operating": 1, "hakjin_act": 1, "hakjin_decree": 1,
    "hakjin_rule": 0, "sanhak_act": 1, "sanhak_decree": 1, "sanhak_rule": 1,
    "research_ethics_guideline": 1, "corp_lab_act": 1, "corp_lab_decree": 1, "corp_lab_rule": 1,
    "research_industry_act": 1, "research_industry_decree": 1, "research_industry_rule": 1, "lab_safety_act": 1,
    "lab_safety_decree": 1, "lab_safety_rule": 1, "defense_tech_act": 1, "defense_tech_decree": 1,
    "defense_tech_rule": 1, "defense_rnd_guideline": 1, "defense_tech_fee_notice": 1, "defense_future_challenge_guideline": 1,
    "defense_facility_equipment": 1, "defense_standard_agreement": 1,
}

_BANNED = ("schema", "fallback", "manifest", "resolve", "tier", "BP", "live", "★", "死", "admrul",
           "get_admin_rule_detail", "unit_types", "deleted_stub", "머신뷰", "정확일치", "ministry",
           "split", "skip", "정상 거동", "(v0.2)", "source_url", "별표구분", "amendment_text", "openapi")
_VOLATILE = (r"조문 ?\d+", r"별표 ?\d+ ?(건|개|종)", r"(서식|별지|별첨) ?\d+ ?(건|개|종)", r"\d{1,3},\d{3}자",
             r"\d+ ?만 ?자", r"별표 ?(0(?!000)|없음)", r"\d+개 부처", r"일부개정\(", r"(고시|예규|훈령) ?(제)?\d")
# 과거 사건으로 의미가 고정된 번호(낡지 않음) — 해당 규정에서만 허용
_ALLOWED_HISTORICAL = {"msit_rnd_processing": ("훈령 제325호",)}


def _items():
    return {rs.id: list(rs.known_limitations) for rs in load_manifest()}


def test_v0580_known_limitations_length_not_above_v0570():
    items = _items()
    assert set(items) == set(_V0570_LEN)
    for rid, kl in items.items():
        assert len(json.dumps(kl, ensure_ascii=False)) <= _V0570_LEN[rid], rid


def test_v0580_known_limitations_count_snapshot():
    assert {rid: len(kl) for rid, kl in _items().items()} == _V0580_COUNT


def test_v0580_known_limitations_no_dev_terms_or_volatile_values():
    for rid, kl in _items().items():
        for s in kl:
            assert isinstance(s, str) and s.strip(), rid
            for t in _BANNED:
                assert t.lower() not in s.lower(), (rid, t)
            probe = s
            for ok in _ALLOWED_HISTORICAL.get(rid, ()):
                probe = probe.replace(ok, "")
            for pat in _VOLATILE:
                assert not re.search(pat, probe), (rid, pat, s)


def test_v0580_yaml_values_double_quoted():
    """따옴표 없는 스칼라는 ' #' 뒤가 주석으로 잘리거나 날짜·숫자로 읽혀 부팅이 실패할 수 있다."""
    src = (Path(__file__).parent.parent / "src/korean_rnd_regs_mcp/rule_sets.yaml").read_text(encoding="utf-8")
    root = yaml.compose(src)
    rule_sets = next(v for k, v in root.value if k.value == "rule_sets")
    seen = 0
    for rs_node in rule_sets.value:
        for k, v in rs_node.value:
            if k.value == "known_limitations":
                assert isinstance(v, yaml.SequenceNode), k.start_mark
                for item in v.value:
                    assert isinstance(item, yaml.ScalarNode) and item.style == '"', item.start_mark
                    seen += 1
    assert seen == sum(_V0580_COUNT.values())


def test_v0580_sme_tech_act_article_effective_date_sentence():
    """v0.57.0 eval 재현 게이트 D: 제27조의3 자체의 시행일을 부칙 근거로 명시(문서 시행일 값은 넣지 않음)."""
    s = " ".join(_items()["sme_tech_act"])
    for tok in ("제27조의3(사업화 금융지원)", "법률 제21704호", "부칙 제1조", "2026-05-26", "effective_date", "제27조의4"):
        assert tok in s, tok
    assert "2026-07-01" not in s


def test_v0580_revision_notice_user_wording():
    rs = SimpleNamespace(effective_date="2024-06-13", api_doc_id="X")
    a = _revision_notice(rs, ResolvedDocId(doc_id="288335", effective_date="2026-09-11", is_updated=True, manifest_doc_id="288773"))
    assert a == "개정 반영: 시행일 2026-09-11 (등록 기준 ID 288773 → 최신 ID 288335)"
    b = _revision_notice(rs, ResolvedDocId(doc_id="X", effective_date="2026-05-06", is_updated=False, manifest_doc_id="X"))
    assert b == "개정 반영: 시행일 2024-06-13 → 2026-05-06 (문서 ID 동일)"
    for n in (a, b):
        assert "manifest" not in n and "갱신 권장" not in n
    # 최대 입력(10자리 날짜 2개·13자리 ID)에서도 v0.57.0 템플릿 최대 길이 이하(검색 예산 비증가)
    ids = "9" * 13
    worst_new = max(
        len(_revision_notice(rs, ResolvedDocId(doc_id=ids, effective_date="2026-12-31", is_updated=True, manifest_doc_id=ids))),
        len(_revision_notice(SimpleNamespace(effective_date="2026-01-01", api_doc_id=ids),
                             ResolvedDocId(doc_id=ids, effective_date="2026-12-31", is_updated=False, manifest_doc_id=ids))),
    )
    worst_old = max(len(f"개정 반영: 시행일 2026-12-31 (manifest 기준 ID {ids} → 최신 ID {ids})"),
                    len("개정 반영: 시행일 2026-01-01 → 2026-12-31 (문서 ID 동일, manifest 시행일 갱신 권장)"))
    assert worst_new <= worst_old
