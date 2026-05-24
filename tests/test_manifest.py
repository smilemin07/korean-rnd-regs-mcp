"""Tests for rule_sets manifest loading + schema validation (Step 24)."""
from korean_rnd_regs_mcp.manifest import (
    ApiTarget,
    HierarchyRank,
    Retrieval,
    UnitTypes,
    load_manifest,
)


def test_load_manifest_returns_at_least_mvp_items():
    """Step 20 입력 후: 최소 4건 (혁신법 본법·시행령·시행규칙 + 연구개발비 사용 기준)."""
    items = load_manifest()
    assert len(items) >= 4


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
    """law api_target은 rank 1-3, admrul은 rank 4."""
    for rs in load_manifest():
        if rs.api_target == ApiTarget.LAW:
            assert rs.hierarchy_rank.value in (1, 2, 3), (
                f"{rs.id}: law는 rank 1-3이어야 함, 실제 {rs.hierarchy_rank.value}"
            )
        elif rs.api_target == ApiTarget.ADMRUL:
            assert rs.hierarchy_rank.value == 4, (
                f"{rs.id}: admrul은 rank 4여야 함, 실제 {rs.hierarchy_rank.value}"
            )


def test_mvp_entries_present():
    """MVP rule set 4개의 id가 모두 존재."""
    ids = {rs.id for rs in load_manifest()}
    expected = {"innovation_act", "innovation_decree", "innovation_rule", "rnd_funding_standard"}
    assert expected.issubset(ids), f"누락 entries: {expected - ids}"
