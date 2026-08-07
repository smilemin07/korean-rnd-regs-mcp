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
    # 0.6.0 = 소관부처(ministry) resolve 필터 + list_rule_sets ministry 필드(v0.2.6) → minor bump.
    # 0.7.0 = 행정규칙 version 메타(issuance_number·regulation_kind·version_label) get_provision_detail
    #         응답에 additive 노출(v0.5.0 — admrul 한정) → minor bump.
    # 0.8.0 = get_provision_detail 조문(JO) 응답 size-tiered(v0.6.0 — 대용량 조문 article_structure 생략
    #         또는 oversized_pointer, 별표 패턴 확장) → minor bump.
    # 0.9.0 = get_provision_detail document-level 응답에 articles(조문) 목록 additive(v0.7.0 — 별표
    #         annexes 목록 패턴 재현, JO 발견성 갭 해소) → minor bump.
    # 0.11.0 = 조문 개정 이력 발견성(v0.15.0)·직전 0.10.0 = 가지조문(제N조의M) 지원(v0.14.0) — JO 6자리 가지 인코딩(JO000702=제7조의2, 가지별표 BP 6자리
    #          동형)·_UNIT_PATTERN 협소화(JO 4/6자리·가지 01~99)·검색/doc-level articles/상세에 가지조문 유입
    #          (거동 변경·신규 provision_id 의미 추가) → minor bump.
    # 0.12.0 = 검색 경로 개정 이력 노출(v0.16.0) — search_provision/suggest 결과의 law 조문 매치에 latest_history additive(§5.13) → minor bump.
    # 0.14.0 = 형태 B redline(v0.18.0) — get_provision_detail optional include_old_and_new + law 문서레벨 old_and_new 블록 additive(§5.15) → minor bump.
    # 0.15.0 = admrul redline 확장(v0.19.0) — 행정규칙 문서레벨에도 amendment_text·amendment_kind additive(§5.16·<제개정구분명> 정규화) → minor bump.
    # 0.25.0 = 구조 안내 완성형 승격(v0.34.0) — get_manual_section 본문 응답에 structure_notice·
    #          structure_notice_note additive(§5.26·구조 손실 확인 절 한정·예산 백스톱) → minor bump.
    assert CONTRACT_VERSION == "0.32.0"


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
    # JO 뒤 3자리만 — 4자리(본조문)/6자리(가지조문)만 유효
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
    pid = parse("law:189938:BP000102")
    assert pid.unit_id == "BP000102"
    assert build("law", "189938", "BP000102") == "law:189938:BP000102"
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
        parse("law:189938:BP00012")
    with pytest.raises(InvalidProvisionId):
        parse("law:189938:BP0001023")
    # v0.14.0 협소화: JO도 BP와 동형으로 4자리(본조문)/6자리(가지조문)만 — 5자리는 reject
    # (종전 JO\d{4,} 무제한은 6자리 JO000602를 '제602조'로 aliasing시켰음; 서버 emit은 전건 4자리라 실영향 0).
    with pytest.raises(InvalidProvisionId):
        parse("law:189938:JO00012")


# === v0.14.0: JO 가지조문 (6자리 = 번호4 + 가지2) ===
def test_parse_branch_article_six_digit_jo():
    pid = parse("law:287505:JO000702")
    assert pid.unit_id == "JO000702"
    assert build("law", "287505", "JO000702") == "law:287505:JO000702"
    assert unit_type("JO000702") == "article"


def test_unit_label_branch_article():
    assert unit_label("JO000702") == "제7조의2"      # 제7조의2 (융자·보증 지원기관)
    assert unit_label("JO001503") == "제15조의3"
    assert unit_label("JO0007") == "제7조"           # 본조문 4자리 불변
    assert unit_label("JO0702") == "제702조"         # 4자리 = 번호 702 (가지 아님 — 길이로 구분)


def test_parse_rejects_branch_zero_jo():
    # 가지 '00'(=본조문 없음)은 4자리 본조문 JO0007과 의미 중복 → reject (collision-safety, Codex R1).
    with pytest.raises(InvalidProvisionId):
        parse("law:287505:JO000700")


def test_parse_rejects_five_and_seven_digit_jo():
    # 5자리·7자리 JO는 디코드 의미 미정의 → reject (BP 4/6자리 협소화와 동형).
    with pytest.raises(InvalidProvisionId):
        parse("law:287505:JO00070")     # 5자리
    with pytest.raises(InvalidProvisionId):
        parse("law:287505:JO0007021")   # 7자리
