"""provision_id parsing/formatting — see docs/api_contract.md (contract_version 1.0.1).

Format: {doc_type}:{doc_id}[:{unit_id}]
- doc_type: "law" or "admrul"
- doc_id: MST for law, 행정규칙일련번호(ID) for admrul
- unit_id (optional): "JO" + 4+ digits (조문) or "BP" + 4+ digits (별표), e.g. "JO0003", "BP0001"

Examples:
- "law:189938"                    -> 법령 document-level
- "law:189938:JO0003"             -> 법령 제3조
- "admrul:2100000278740"          -> 행정규칙 document-level
- "admrul:2100000278740:JO0007"   -> 행정규칙 제7조
- "admrul:2100000278740:BP0001"   -> 행정규칙 별표 1 (Step 16-17 LIVE 검증으로 추가)
"""
import re
from dataclasses import dataclass
from typing import Optional

CONTRACT_VERSION = "1.0.1"
VALID_DOC_TYPES = frozenset({"law", "admrul"})
# JO = 조문(article), BP = 별표(annex). 둘 다 4자리 이상 숫자.
_UNIT_PATTERN = re.compile(r"^(JO|BP)\d{4,}$")


class InvalidProvisionId(ValueError):
    """Raised when provision_id does not match the contract format."""


def unit_type(unit_id: Optional[str]) -> str:
    """Return 'article' (JO prefix), 'annex' (BP prefix), or 'document' (None/empty)."""
    if not unit_id:
        return "document"
    if unit_id.startswith("JO"):
        return "article"
    if unit_id.startswith("BP"):
        return "annex"
    raise InvalidProvisionId(f"Unknown unit prefix in {unit_id!r}; allowed: JO/BP")


@dataclass(frozen=True)
class ProvisionId:
    doc_type: str
    doc_id: str
    unit_id: Optional[str] = None  # JO0003 or BP0001 etc., None for document-level

    def __str__(self) -> str:
        if self.unit_id:
            return f"{self.doc_type}:{self.doc_id}:{self.unit_id}"
        return f"{self.doc_type}:{self.doc_id}"


def parse(provision_id: str) -> ProvisionId:
    if not isinstance(provision_id, str) or not provision_id:
        raise InvalidProvisionId(
            "provision_id는 비어있지 않은 문자열이어야 합니다"
        )
    parts = provision_id.split(":")
    if len(parts) not in (2, 3):
        raise InvalidProvisionId(
            f"provision_id는 2개 또는 3개 part로 구성되어야 합니다 "
            f"(예: 'law:189938' 또는 'law:189938:JO0003'). 받은 값: {provision_id!r}"
        )
    doc_type, doc_id = parts[0], parts[1]
    if doc_type not in VALID_DOC_TYPES:
        raise InvalidProvisionId(
            f"doc_type은 {sorted(VALID_DOC_TYPES)} 중 하나여야 합니다. "
            f"받은 값: {doc_type!r}"
        )
    if not doc_id:
        raise InvalidProvisionId("doc_id는 비어있을 수 없습니다")
    unit_id = parts[2] if len(parts) == 3 else None
    if unit_id is not None and not _UNIT_PATTERN.match(unit_id):
        raise InvalidProvisionId(
            f"unit_id는 'JO'(조문) 또는 'BP'(별표) + 4자리 이상 숫자여야 합니다 "
            f"(예: 'JO0003', 'BP0001'). 받은 값: {unit_id!r}"
        )
    return ProvisionId(doc_type=doc_type, doc_id=doc_id, unit_id=unit_id)


def build(doc_type: str, doc_id: str, unit_id: Optional[str] = None) -> str:
    pid = ProvisionId(doc_type=doc_type, doc_id=doc_id, unit_id=unit_id)
    parse(str(pid))  # validate
    return str(pid)
