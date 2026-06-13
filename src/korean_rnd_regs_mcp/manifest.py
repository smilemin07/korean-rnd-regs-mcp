"""rule_sets manifest schema + loader.

본 모듈은 `rule_sets.yaml`을 읽어 검증된 RuleSet 객체 list로 반환한다.
schema는 에 정의된 13개 필드 + `api_doc_id`(실제 ID 값) 1개 = 총 14개.

(`api_doc_id`는 plan에 명시되지 않았지만 LawApiClient 호출에 필수 — 누락 시 API call 불가.
plan은 type만 정의했고 value는 implicit으로 가정한 듯하여 본 schema에서 명시 추가.)

사용 예:
    from korean_rnd_regs_mcp.manifest import load_manifest
    rule_sets = load_manifest()   # default path: 같은 디렉터리의 rule_sets.yaml
    for rs in rule_sets:
        print(rs.id, rs.title, rs.api_target, rs.api_doc_id)
"""
from enum import Enum
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field


class HierarchyRank(int, Enum):
    LAW = 1            # 법률 (혁신법 family — Tier 1)
    DECREE = 2         # 시행령 (혁신법 family — Tier 1)
    RULE = 3           # 시행규칙 (혁신법 family — Tier 1)
    ADMIN_RULE = 4     # 행정규칙 (Tier 2)
    # Supplementary (부패방지법·청탁금지법·공익신고자보호법 등) — Tier 1 검토 후순위로 추천
    # rank=1로 두면 혁신법(rank 1)과 동순위가 되어
    # suggest_review_sources의 recommended_review_order에서 Supplementary 법률이 혁신법 시행령(rank 2)보다
    # 먼저 추천되는 정렬 오염 발생 → Supplementary는 rank 5/6으로 명확히 후순위.
    SUPP_LAW = 5       # Supplementary 법률
    SUPP_DECREE = 6    # Supplementary 시행령


class Retrieval(str, Enum):
    LIVE_API = "live_api"        # MVP
    PLANNED_PDF = "planned_pdf"  # v0.3 이후 deferred


class ApiTarget(str, Enum):
    LAW = "law"
    ADMRUL = "admrul"


class ApiIdType(str, Enum):
    MST = "MST"              # law의 법령일련번호 (canonical for law)
    LAW_ID = "law_id"        # law의 법령ID (fallback)
    ADMRUL_ID = "admrul_id"  # admrul의 행정규칙일련번호 (canonical for admrul)


class UnitTypes(str, Enum):
    ARTICLE = "article"  # 조문만 (대다수 법령)
    ANNEX = "annex"      # 별표만 (예: 연구개발비 사용 기준 — 조문 0개 + 별표 30개)
    BOTH = "both"        # 둘 다 (시행령 등에서 흔함)


class RuleSet(BaseModel):
    """rule_sets.yaml 한 항목의 schema (총 15 fields — v0.2.6 ministry 추가).

    docs/api_contract.md §2와 참조.
    """

    model_config = ConfigDict(extra="forbid")  # 정의되지 않은 field 사용 시 validation 실패 (오타 방어)

    id: str = Field(
        ...,
        description="고유 slug. 영문 snake_case 권장 (예: 'innovation_act', 'innovation_decree', 'rnd_funding_standard')",
        min_length=1,
    )
    title: str = Field(
        ...,
        description="정식 명칭 한국어 (예: '국가연구개발혁신법')",
        min_length=1,
    )
    tier: str = Field(
        ...,
        description="중요도 분류 (예: 'Tier 1' = 본법·핵심 시행령, 'Tier 2' = 핵심 행정규칙)",
    )
    hierarchy_rank: HierarchyRank = Field(
        ...,
        description="1=법률, 2=시행령, 3=시행규칙, 4=행정규칙. suggest_review_sources의 검토 순서에 사용",
    )
    retrieval: Retrieval = Field(
        ...,
        description="live_api (MVP) 또는 planned_pdf (v0.3 이후 deferred)",
    )
    api_target: ApiTarget = Field(
        ...,
        description="국가법령정보 OpenAPI target (law | admrul)",
    )
    api_id_type: ApiIdType = Field(
        ...,
        description="ID 유형 (MST | law_id | admrul_id)",
    )
    api_doc_id: str = Field(
        ...,
        description="실제 ID 값 — LawApiClient.get_law_detail / get_admin_rule_detail 호출 시 그대로 사용 (예: '260807')",
        min_length=1,
    )
    unit_types: UnitTypes = Field(
        ...,
        description="article|annex|both — search_provision이 어느 단위에서 검색할지 결정",
    )
    query: List[str] = Field(
        ...,
        description="검색 후보 query string list. 띄어쓰기·약칭 변형으로 2-3개 권장 (함정 회피)",
        min_length=1,
    )
    license_status: str = Field(
        ...,
        description="라이선스 상태 (예: 'public_data' = 공공 OpenAPI 조회 대상, 원문 대량 저장·배포 금지)",
    )
    effective_date: str = Field(
        ...,
        description="시행일자 (ISO 형식 YYYY-MM-DD 권장)",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    source_url: str = Field(
        ...,
        description="원본 URL (국가법령정보센터 등)",
    )
    known_limitations: List[str] = Field(
        default_factory=list,
        description="알려진 제약 사항. 예: '별표는 본문 텍스트로 반환되지만 일부 HWP/PDF 첨부 — source_url 별도 확인'",
    )
    ministry: Optional[str] = Field(
        default=None,
        description=(
            "소관부처명 (OpenAPI 검색 행의 개편 후 부처명, 예: '산업통상부'). "
            "동명 규정이 복수 부처에 존재할 때 resolve_latest_doc_id가 자부처 행만 채택하도록 하는 필터값. "
            "None이면 필터 미적용(기존 거동). v0.2.6 추가."
        ),
    )


def load_manifest(path: Optional[Path] = None) -> List[RuleSet]:
    """rule_sets.yaml을 읽어 검증된 RuleSet list 반환.

    Args:
        path: yaml 파일 경로. None이면 본 패키지 내 `rule_sets.yaml` 사용.

    Returns:
        RuleSet list. 파일이 없거나 비어있으면 [].

    Raises:
        pydantic.ValidationError: 항목이 schema 위반 시.
    """
    if path is None:
        path = Path(__file__).parent / "rule_sets.yaml"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = yaml.safe_load(text) or {}
    items = data.get("rule_sets", []) or []
    return [RuleSet.model_validate(item) for item in items]
