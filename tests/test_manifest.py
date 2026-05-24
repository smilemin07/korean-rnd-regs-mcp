"""Tests for rule_sets manifest loading + schema validation (Step 24)."""
from korean_rnd_regs_mcp.manifest import (
    ApiTarget,
    HierarchyRank,
    Retrieval,
    UnitTypes,
    load_manifest,
)


def test_load_manifest_returns_at_least_mvp_items():
    """v0.1.0 publish 범위: 최소 13건 (혁신법 family 4 + Tier 2 신규 3 + Supplementary 6)."""
    items = load_manifest()
    assert len(items) >= 13


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


def test_all_ids_are_unique():
    items = load_manifest()
    ids = [rs.id for rs in items]
    assert len(ids) == len(set(ids)), f"duplicate id: {ids}"


def test_api_doc_id_unique_per_target():
    """동일 (api_target, api_doc_id) 쌍 중복 없어야 함 (Step 22a/22b dispatch 충돌 방지)."""
    items = load_manifest()
    seen = set()
    for rs in items:
        key = (rs.api_target.value, rs.api_doc_id)
        assert key not in seen, f"duplicate (api_target, api_doc_id): {key}"
        seen.add(key)


def test_hierarchy_rank_matches_api_target():
    """law api_target은 rank 1/2/3/5/6, admrul은 rank 4.

    rank 5/6은 Supplementary 법률·시행령 (부패방지법 등) — 혁신법 family(1-3)와 분리하여
    추천 순서에서 후순위로 처리. 9차 AI review 합의 P1 반영.
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
    """v0.1.0 publish 범위 13개 rule set id 모두 존재."""
    ids = {rs.id for rs in load_manifest()}
    expected = {
        "innovation_act", "innovation_decree", "innovation_rule", "rnd_funding_standard",
        "simultaneous_research_limit", "facility_equipment_standard", "research_note_guideline",
        "anti_corruption_act", "anti_corruption_decree",
        "improper_solicitation_act", "improper_solicitation_decree",
        "public_interest_whistleblower_act", "public_interest_whistleblower_decree",
    }
    assert expected.issubset(ids), f"누락 entries: {expected - ids}"
