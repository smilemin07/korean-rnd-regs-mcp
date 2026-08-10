"""Tests for rule_sets manifest loading + schema validation ()."""
from korean_rnd_regs_mcp.manifest import (
    ApiTarget,
    HierarchyRank,
    Retrieval,
    UnitTypes,
    load_manifest,
)


def test_load_manifest_returns_at_least_mvp_items():
    """publish 범위 하한. v0.4.0: 질병관리청 R&D family 4건 추가 → 36건."""
    items = load_manifest()
    assert len(items) >= 36


def test_all_required_fields_populated():
    """Pydantic schema validation은 load_manifest 시 자동 — 본 test는 비즈니스 의미 보강."""
    items = load_manifest()
    for rs in items:
        assert rs.id, f"id missing"
        assert rs.title, f"title missing: {rs.id}"
        assert rs.tier, f"tier missing: {rs.id}"
        assert isinstance(rs.hierarchy_rank, HierarchyRank)
        assert isinstance(rs.retrieval, Retrieval)
        assert isinstance(rs.api_target, ApiTarget)
        assert rs.api_doc_id, f"api_doc_id missing: {rs.id}"
        assert isinstance(rs.unit_types, UnitTypes)
        assert rs.query and len(rs.query) >= 1, f"query missing: {rs.id}"
        assert rs.license_status, f"license_status missing: {rs.id}"
        assert rs.effective_date, f"effective_date missing: {rs.id}"
        assert rs.source_url, f"source_url missing: {rs.id}"


def test_rnd_funding_standard_effective_date_is_current():
    """회귀: 연구개발비 사용 기준 manifest 시행일이 현행(2026-05-06)으로 갱신됨.

    LIVE 검증(2026-05-30): 일련번호 2100000278740 불변이나 현행 시행일은 2026-05-06.
    이 단언이 2024-06-13으로의 회귀(stale 표시 버그 재발)를 차단한다.
    """
    rs = next(r for r in load_manifest() if r.id == "rnd_funding_standard")
    assert rs.effective_date == "2026-05-06"


def test_all_ids_are_unique():
    items = load_manifest()
    ids = [rs.id for rs in items]
    assert len(ids) == len(set(ids)), f"duplicate id: {ids}"


def test_api_doc_id_unique_per_target():
    """동일 (api_target, api_doc_id) 쌍 중복 없어야 함 (a/22b dispatch 충돌 방지)."""
    items = load_manifest()
    seen = set()
    for rs in items:
        key = (rs.api_target.value, rs.api_doc_id)
        assert key not in seen, f"duplicate (api_target, api_doc_id): {key}"
        seen.add(key)


def test_hierarchy_rank_matches_api_target():
    """law api_target은 rank 1/2/3/5/6, admrul은 rank 4.

    rank 5/6은 Supplementary 법률·시행령 (부패방지법 등) — 혁신법 family(1-3)와 분리하여
    추천 순서에서 후순위로 처리. 반영.
    """
    for rs in load_manifest():
        if rs.api_target == ApiTarget.LAW:
            assert rs.hierarchy_rank.value in (1, 2, 3, 5, 6), (
                f"{rs.id}: law는 rank 1/2/3/5/6이어야 함, 실제 {rs.hierarchy_rank.value}"
            )
        elif rs.api_target == ApiTarget.ADMRUL:
            assert rs.hierarchy_rank.value == 4, (
                f"{rs.id}: admrul은 rank 4여야 함, 실제 {rs.hierarchy_rank.value}"
            )


def test_mvp_entries_present():
    """핵심 rule set id 존재 (v0.2.6: 보조 법령 6건 제거 후 혁신법 family 4 + Tier 2 핵심 3)."""
    ids = {rs.id for rs in load_manifest()}
    expected = {
        "innovation_act", "innovation_decree", "innovation_rule", "rnd_funding_standard",
        "simultaneous_research_limit", "facility_equipment_standard", "research_note_guideline",
    }
    assert expected.issubset(ids), f"누락 entries: {expected - ids}"


def test_supplementary_entries_removed():
    """v0.2.6 회귀: 보조 법령 6건(부패방지·청탁금지·공익신고자보호)이 manifest에서 제거됨."""
    ids = {rs.id for rs in load_manifest()}
    removed = {
        "anti_corruption_act", "anti_corruption_decree",
        "improper_solicitation_act", "improper_solicitation_decree",
        "public_interest_whistleblower_act", "public_interest_whistleblower_decree",
    }
    assert not (removed & ids), f"제거됐어야 할 보조 법령 잔존: {removed & ids}"


def test_v026_msit_family_present_with_ministry():
    """v0.2.6 추가: 과기정통부 family 9건 등록 + 기술료 통합요령 소관부처='산업통상부'."""
    by_id = {rs.id: rs for rs in load_manifest()}
    expected = {
        "performance_eval_act", "performance_eval_decree",
        "rnd_info_processing", "rnd_security_measures", "msit_rnd_processing",
        "ict_rnd_management", "ict_research_ethics",
        "tech_fee_integrated", "sme_tech_fee",
    }
    assert expected.issubset(set(by_id)), f"v0.2.6 누락: {expected - set(by_id)}"
    # 소관부처 필터 핵심: 동명 2부처 규정은 산업통상부로 명시 (기후부 동명 오집 방지)
    assert by_id["tech_fee_integrated"].ministry == "산업통상부"
    assert by_id["sme_tech_fee"].ministry == "중소벤처기업부"
    assert by_id["performance_eval_act"].hierarchy_rank == HierarchyRank.LAW
    assert by_id["performance_eval_decree"].hierarchy_rank == HierarchyRank.DECREE


def test_ministry_field_optional_default_none():
    """v0.2.6 회귀: ministry는 Optional default None — 미기재 규정(기존 다수)은 None."""
    by_id = {rs.id: rs for rs in load_manifest()}
    assert by_id["innovation_act"].ministry is None
    assert by_id["rnd_funding_standard"].ministry is None


def test_v013_sector_kt_entries_present():
    """v0.1.3 추가: 국토교통 R&D family 4건 (법률·시행령·시행규칙 + 부처 운영규정)."""
    ids = {rs.id for rs in load_manifest()}
    expected = {
        "sector_kt_act", "sector_kt_decree", "sector_kt_rule", "kt_rnd_operations",
    }
    assert expected.issubset(ids), f"v0.1.3 누락 entries: {expected - ids}"


def test_v013_sector_kt_entries_rank_alignment():
    """v0.1.3 sector KT family의 hierarchy_rank가 법률·시행령·시행규칙·행정규칙(1·2·3·4)에 정렬."""
    by_id = {rs.id: rs for rs in load_manifest()}
    assert by_id["sector_kt_act"].hierarchy_rank == HierarchyRank.LAW
    assert by_id["sector_kt_decree"].hierarchy_rank == HierarchyRank.DECREE
    assert by_id["sector_kt_rule"].hierarchy_rank == HierarchyRank.RULE
    assert by_id["kt_rnd_operations"].hierarchy_rank == HierarchyRank.ADMIN_RULE


def test_v0470_msit_screening_notices_present():
    """v0.47.0 추가: 과기정통부 심사·검토 고시 2건 — 필드 전수 검증(LIVE 2026-08-10 프로브 값).

    query[0] == 정식 제목 잠금은 계획 /disc 조건 ③(정식 제목 최우선 배치)의 회귀 방지."""
    by_id = {rs.id: rs for rs in load_manifest()}
    a = by_id["large_rnd_plan_review"]
    assert a.title == "대형 연구개발 사업계획검토 운영에 관한 규정"
    assert a.api_target == ApiTarget.ADMRUL
    assert a.api_id_type.value == "admrul_id"
    assert a.api_doc_id == "2100000276390"
    assert a.effective_date == "2026-03-26"
    assert a.ministry == "과학기술정보통신부"
    assert a.unit_types == UnitTypes.ARTICLE
    assert a.hierarchy_rank == HierarchyRank.ADMIN_RULE
    assert a.retrieval == Retrieval.LIVE_API
    assert a.tier == "Tier 2"
    assert a.license_status == "public_data"
    assert a.query[0] == "대형 연구개발 사업계획검토 운영에 관한 규정"
    assert a.source_url and "law.go.kr" in a.source_url
    assert any("별지" in note and "미지원" in note for note in a.known_limitations)
    b = by_id["build_type_rnd_screening"]
    assert b.title == "구축형 연구개발사업 심사 운용지침"
    assert b.api_target == ApiTarget.ADMRUL
    assert b.api_id_type.value == "admrul_id"
    assert b.api_doc_id == "2100000278982"
    assert b.effective_date == "2026-05-11"
    assert b.ministry == "과학기술정보통신부"
    assert b.unit_types == UnitTypes.ARTICLE
    assert b.hierarchy_rank == HierarchyRank.ADMIN_RULE
    assert b.retrieval == Retrieval.LIVE_API
    assert b.tier == "Tier 2"
    assert b.license_status == "public_data"
    assert b.query[0] == "구축형 연구개발사업 심사 운용지침"
    assert b.source_url and "law.go.kr" in b.source_url
    assert any("서식" in note and "미지원" in note for note in b.known_limitations)


def test_v0470_manifest_count_66():
    """v0.47.0: 지원 규정 64 → 66 (과기정통부 심사·검토 고시 2건)."""
    assert len(load_manifest()) == 66


def test_v0470_build_type_screening_partial_application_note():
    """v0.47.0: 구축형 심사 운용지침의 부칙 제2조 적용례가 known_limitations에 명시 — 전체 미시행 오인 방지.

    핵심 적용 시점('각 목'·'2026년 11월')까지 잠가 문면 삭제·변경 회귀를 차단(diff 적대검토 Codex MINOR)."""
    by_id = {rs.id: rs for rs in load_manifest()}
    notes = " ".join(by_id["build_type_rnd_screening"].known_limitations)
    assert "부칙 제2조" in notes
    assert "제17조제2항제2호" in notes
    assert "각 목" in notes
    assert "2026년 11월" in notes
    assert "2026-05-11부터 시행 중" in notes
    assert "규정 전체의 시행일 변경이 아님" in notes
