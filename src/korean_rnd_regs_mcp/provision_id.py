"""provision_id parsing/formatting — see docs/api_contract.md (contract_version 0.1.0).

Format: {doc_type}:{doc_id}[:{unit_id}]
- doc_type: "law" or "admrul"
- doc_id: MST for law, 행정규칙일련번호(ID) for admrul
- unit_id (optional):
  - "JO" + 4 digits (본조문), e.g. "JO0003" = 제3조
  - "JO" + 6 digits (가지조문, 번호 4 + 가지 2 — v0.14.0), e.g. "JO000702" = 제7조의2
    (가지 2자리는 01~99만 유효 — '00'(가지 없음)은 4자리 본조문 JO0007과 의미가 겹쳐 reject.
     가지별표 BP 6자리와 동형: 자릿수 고정으로 'JO0702'=제702조와 'JO000702'=제7조의2가 길이로 구분됨.)
  - "BP" + 4 digits (본별표), e.g. "BP0001" = 별표 1
  - "BP" + 6 digits (가지별표, 번호 4 + 가지 2 — v0.2.1), e.g. "BP000102" = 별표 1의2
    (자릿수 고정으로 'BP0102'=별표 102와 'BP000102'=별표 1의2가 길이로 구분됨.
     5자리 등 그 외 길이는 의미가 정의되지 않아 reject — contract 0.6.0)

Examples:
- "law:189938"                    -> 법령 document-level
- "law:189938:JO0003"             -> 법령 제3조
- "law:189938:JO000702"           -> 법령 제7조의2 (가지조문, v0.14.0)
- "admrul:2100000278740"          -> 행정규칙 document-level
- "admrul:2100000278740:JO0007"   -> 행정규칙 제7조
- "admrul:2100000278740:BP0001"   -> 행정규칙 별표 1 (LIVE 검증으로 추가)
- "law:189938:BP000102"           -> 법령 별표 1의2 (가지별표, v0.2.1)
"""
import re
from dataclasses import dataclass
from typing import Optional

CONTRACT_VERSION = "0.27.0"
VALID_DOC_TYPES = frozenset({"law", "admrul"})
# JO = 조문(article): 4자리(본조문) 또는 6자리(가지조문, 번호4+가지2 — v0.14.0). 가지 2자리는 01~99만.
#   ★가지 '00'(=(?:00))은 4자리 본조문(JO0007)과 의미가 겹쳐(오도달·aliasing) reject → (?:0[1-9]|[1-9]\d).
#   종전 `JO\d{4,}`(4자리 이상 무제한)는 6자리 JO000602를 이미 통과시켜 '제602조'로 오해석(JO0602와 aliasing)했다.
#   서버 emit 이력은 전건 정확 4자리라 실 blast 0 — 협소화가 6자리 가지조문 emit의 전제(collision-safety).
# BP = 별표(annex): 4자리(본별표) 또는 6자리(가지별표, 번호4+가지2). BP는 v0.2.1 선례 보존(가지 00 허용은 별건).
_UNIT_PATTERN = re.compile(r"^(JO\d{4}(?:0[1-9]|[1-9]\d)?|BP\d{4}(?:\d{2})?)$")


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


def unit_label(unit_id: Optional[str]) -> str:
    """unit_id를 사람이 읽는 한국어 라벨로: JO0074->'제74조', JO000702->'제7조의2' (가지조문, v0.14.0),
    BP0001->'별표 1', BP000102->'별표 1의2' (가지별표, v0.2.1),
    None/document-level/판별 불가 -> '' (비-raising — 응답 빌드에서 안전하게 사용).
    """
    if not unit_id:
        return ""
    if unit_id.startswith("JO") and unit_id[2:].isdigit():
        digits = unit_id[2:]
        if len(digits) == 6:
            return f"제{int(digits[:4])}조의{int(digits[4:])}"
        return f"제{int(digits)}조"
    if unit_id.startswith("BP") and unit_id[2:].isdigit():
        digits = unit_id[2:]
        if len(digits) == 6:
            return f"별표 {int(digits[:4])}의{int(digits[4:])}"
        return f"별표 {int(digits)}"
    return ""


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
            f"unit_id는 'JO'(조문)+4자리(본조문)/6자리(가지조문, 번호4+가지2, 가지 01~99) 숫자, 또는 "
            f"'BP'(별표)+4자리(본별표)/6자리(가지별표, 번호4+가지2) 숫자여야 합니다 "
            f"(예: 'JO0003', 'JO000702', 'BP0001', 'BP000102'). 받은 값: {unit_id!r}"
        )
    return ProvisionId(doc_type=doc_type, doc_id=doc_id, unit_id=unit_id)


def build(doc_type: str, doc_id: str, unit_id: Optional[str] = None) -> str:
    pid = ProvisionId(doc_type=doc_type, doc_id=doc_id, unit_id=unit_id)
    parse(str(pid))  # validate
    return str(pid)
