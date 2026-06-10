"""Tests for provision_id parsing per contract_version 0.2.0 (0.1.0 publish 시점 reset; pre-publish 이력 별도 보존)."""
import pytest

from korean_rnd_regs_mcp.provision_id import (
    CONTRACT_VERSION,
    InvalidProvisionId,
    ProvisionId,
    build,
    parse,
    unit_label,
    unit_type,
)


def test_contract_version_pinned():
    # pre-publish 내부 이력: 1.0.0 → 1.0.1 BP → 1.0.2 본문 reconstruct → 1.0.3 article_structure additive
    #                        → 1.0.3 revision (wrapper element filter + requests 예외 포괄)
    # publish 시점에 0.x.x 대역으로 reset (외부 사용자 0명). 0.2.0 = suggest_review_sources
    # 선택 keywords 입력·응답 additive 필드(keyword_source/returned/truncated/note)·candidates cap(거동 변경).
    # 0.3.0 = suggest_review_sources 응답에 overflow_candidates·overflow_truncated 필드 추가(v0.1.8) → minor bump.
    # 0.4.0 = 법령 별표 지원 — get_provision_detail(annex) size-tiered 필드(content_format 등) 추가(v0.2.0) → minor bump.
    # 0.5.0 = 별표 발견성·정확 선택 강화(v0.2.1) — document-level annexes 목록·annexes_count_by_kind·
    #         dependent_article_hints additive + BP 6자리 가지별표 인코딩(4/6자리 한정으로 협소화)·
    #         별지/서식 BP 노출 제외(오도달 버그 수정)·(번호,가지) 엄격 매칭 → minor bump.
    assert CONTRACT_VERSION == "0.5.0"


# === unit_label (v0.1.8 — overflow_candidates label용) ===
def test_unit_label_article_and_annex():
    assert unit_label("JO0074") == "제74조"
    assert unit_label("JO0001") == "제1조"
    assert unit_label("JO0108") == "제108조"
    assert unit_label("BP0001") == "별표 1"
    assert unit_label("BP0013") == "별표 13"


def test_unit_label_document_and_invalid_return_empty():
    assert unit_label(None) == ""        # document-level
    assert unit_label("") == ""
    assert unit_label("XX0001") == ""    # 알 수 없는 prefix → 비-raising, "" 반환
    assert unit_label("JOabcd") == ""    # 숫자부 아님 → ""


# === 정상 케이스: 조문(JO) 3개 ===
def test_parse_law_with_article():
    pid = parse("law:189938:JO0003")
    assert pid.doc_type == "law"
    assert pid.doc_id == "189938"
    assert pid.unit_id == "JO0003"


def test_parse_admrul_with_article():
    pid = parse("admrul:2100000023234:JO0007")
    assert pid.doc_type == "admrul"
    assert pid.doc_id == "2100000023234"
    assert pid.unit_id == "JO0007"


def test_parse_law_document_level():
    pid = parse("law:189938")
    assert pid.doc_type == "law"
    assert pid.doc_id == "189938"
    assert pid.unit_id is None


# === 별표(BP) 케이스 ===
def test_parse_admrul_with_annex_first():
    pid = parse("admrul:2100000278740:BP0001")
    assert pid.doc_type == "admrul"
    assert pid.doc_id == "2100000278740"
    assert pid.unit_id == "BP0001"


def test_parse_admrul_with_annex_high_number():
    pid = parse("admrul:2100000278740:BP0030")
    assert pid.unit_id == "BP0030"


# === malformed 케이스 5개 ===
def test_parse_empty_string_fails():
    with pytest.raises(InvalidProvisionId):
        parse("")


def test_parse_missing_doc_type_fails():
    with pytest.raises(InvalidProvisionId):
        parse(":189938:JO0003")


def test_parse_invalid_doc_type_fails():
    # 판례(prec)는 MVP 제외
    with pytest.raises(InvalidProvisionId):
        parse("prec:189938:JO0003")


def test_parse_too_many_parts_fails():
    with pytest.raises(InvalidProvisionId):
        parse("law:189938:JO0003:extra")


def test_parse_invalid_unit_prefix_fails():
    # Article3은 JO·BP 어느 것도 아님
    with pytest.raises(InvalidProvisionId):
        parse("law:189938:Article3")


def test_parse_invalid_unit_too_few_digits_fails():
    # JO 뒤 3자리만 — 4자리 이상 필요
    with pytest.raises(InvalidProvisionId):
        parse("law:189938:JO003")


# === unit_type helper ===
def test_unit_type_article():
    assert unit_type("JO0003") == "article"


def test_unit_type_annex():
    assert unit_type("BP0001") == "annex"


def test_unit_type_document_when_none():
    assert unit_type(None) == "document"
    assert unit_type("") == "document"


def test_unit_type_unknown_prefix_raises():
    with pytest.raises(InvalidProvisionId):
        unit_type("XY0001")


# === build + round-trip ===
def test_build_then_parse_roundtrip_article():
    s = build("law", "189938", "JO0003")
    assert s == "law:189938:JO0003"
    pid = parse(s)
    assert (pid.doc_type, pid.doc_id, pid.unit_id) == ("law", "189938", "JO0003")


def test_build_then_parse_roundtrip_annex():
    s = build("admrul", "2100000278740", "BP0001")
    assert s == "admrul:2100000278740:BP0001"
    pid = parse(s)
    assert pid.unit_id == "BP0001"


def test_str_representation():
    assert str(ProvisionId("law", "189938", "JO0003")) == "law:189938:JO0003"
    assert str(ProvisionId("law", "189938")) == "law:189938"
    assert str(ProvisionId("admrul", "2100000278740", "BP0001")) == "admrul:2100000278740:BP0001"


# === v0.2.1: BP 가지별표 (6자리 = 번호4 + 가지2) ===
def test_parse_branch_annex_six_digit_bp():
    pid = parse("law:264451:BP000102")
    assert pid.unit_id == "BP000102"
    assert build("law", "264451", "BP000102") == "law:264451:BP000102"
    assert unit_type("BP000102") == "annex"


def test_unit_label_branch_annex():
    assert unit_label("BP000102") == "별표 1의2"
    assert unit_label("BP001203") == "별표 12의3"
    assert unit_label("BP0001") == "별표 1"    # 본별표 4자리 불변
    assert unit_label("BP0102") == "별표 102"  # 4자리 = 번호 102 (가지 아님 — 길이로 구분)


def test_parse_rejects_undefined_bp_lengths():
    # v0.2.1 협소화: BP는 4자리(본별표)/6자리(가지별표)만 — 5·7자리는 디코드 의미 미정의라 reject.
    # (서버 emit 이력은 4자리뿐 — 실영향 0. contract 0.5.0 이력 명시.)
    with pytest.raises(InvalidProvisionId):
        parse("law:264451:BP00012")
    with pytest.raises(InvalidProvisionId):
        parse("law:264451:BP0001023")
    # JO(조문)는 종전대로 4자리 이상 허용 (불변)
    assert parse("law:264451:JO00012").unit_id == "JO00012"
