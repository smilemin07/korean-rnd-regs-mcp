"""rule_sets manifest schema + loader.

본 모듈은 `rule_sets.yaml`을 읽어 검증된 RuleSet 객체 list로 반환한다.
schema는 plan v3.2 Step 19에 정의된 12개 필드 + `api_doc_id`(실제 ID 값) 1개 = 13개.

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
    LAW = 1            # 법률
    DECREE = 2         # 시행령
    RULE = 3           # 시행규칙
    ADMIN_RULE = 4     # 행정규칙


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
    """rule_sets.yaml 한 항목의 schema (13 fields).

    docs/api_contract.md §2와 plan v3.2 Step 19·20 참조.
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
        description="검색 후보 query string list. 띄어쓰기·약칭 변형으로 2-3개 권장 (Step 17 함정 회피)",
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
