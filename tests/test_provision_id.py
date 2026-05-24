"""Tests for provision_id parsing per contract_version 0.1.0 (publish 시점 reset; pre-publish 이력 별도 보존)."""
import pytest

from korean_rnd_regs_mcp.provision_id import (
    CONTRACT_VERSION,
    InvalidProvisionId,
    ProvisionId,
    build,
    parse,
    unit_type,
)


def test_contract_version_pinned():
    # pre-publish 내부 이력: 1.0.0 → 1.0.1 BP → 1.0.2 본문 reconstruct → 1.0.3 article_structure additive
    #                        → 1.0.3 revision (wrapper element filter + requests 예외 포괄)
    # publish 시점에 0.x.x 대역으로 reset (외부 사용자 0명, v0.2 가지조문 확장 시 0.2.0 minor bump 자연스러움)
    assert CONTRACT_VERSION == "0.1.0"


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
