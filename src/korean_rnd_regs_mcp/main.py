"""korean-rnd-regs-mcp main entry — stdio MCP server."""
import argparse
import asyncio
import logging
import os
import re
import sys
from urllib.parse import urljoin

from dotenv import load_dotenv
from fastmcp import FastMCP

from . import __version__
from .live_api import LawApiClient, LawApiError
from .manifest import ApiTarget, Retrieval, UnitTypes, load_manifest
from .provision_id import (
    CONTRACT_VERSION,
    InvalidProvisionId,
    build as build_provision_id,
    parse as parse_provision_id,
)

load_dotenv()

logger = logging.getLogger("rnd-regs-mcp")
_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logger.setLevel(_level)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(_handler)

mcp = FastMCP("korean-rnd-regs-mcp")

_DISCLAIMER = "본 결과는 검토 후보일 뿐 법률 판단이 아닙니다. 출처를 직접 확인하세요."
_SNIPPET_MAX = 2000
_LAW_GO_KR_BASE = "https://www.law.go.kr"
_RANK_NAMES = {1: "법률", 2: "시행령", 3: "시행규칙", 4: "행정규칙"}
_KEYWORD_STOPWORDS = frozenset({
    "대해", "관련", "관해", "관하여", "경우", "에서", "으로", "에게",
    "있는", "있을", "있나요", "있는지", "있습니까", "있습니다",
    "하는", "하면", "하려면", "해야", "한다", "합니다",
    "되는", "된다", "됩니까", "될까요", "필요한", "필요합니까",
    "어떻게", "무엇", "어떤", "어디서", "언제", "왜", "얼마", "몇",
    "받으려면", "받을", "받으면", "이라면", "인지", "인가요",
    "대한", "이번", "이전", "이후", "그러나", "그리고", "그래서",
})
# 흔한 한국어 조사 (긴 것부터 정렬 — endswith 매칭 우선순위)
_PARTICLES = (
    "에서는", "에서도", "으로는", "에게는",
    "에서", "으로", "에게", "한테", "까지", "부터", "조차", "마저",
    "와의", "과의",
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로", "와", "과",
)


def _strip_particle(word: str) -> str:
    """단어 끝의 조사 1-3글자 suffix 제거. 단어가 너무 짧아지면(<2자) 원본 유지."""
    for p in _PARTICLES:
        if word.endswith(p) and len(word) - len(p) >= 2:
            return word[: -len(p)]
    return word


def _extract_keywords(question: str, max_count: int = 5) -> list[str]:
    """질문에서 2자 이상 한글 단어 → 조사 strip → stopword 제외 → 최대 max_count개."""
    raw = re.findall(r"[가-힣]{2,}", question)
    stripped = [_strip_particle(w) for w in raw]
    # 조사 strip 후 길이 2 미만 제거
    valid = [w for w in stripped if len(w) >= 2]
    deduped = list(dict.fromkeys(valid))
    filtered = [w for w in deduped if w not in _KEYWORD_STOPWORDS]
    return filtered[:max_count]


def _sanitize_error_message(msg: str) -> str:
    """Defense-in-depth: 도구 응답으로 error message 출력 전 LAW_API_KEY 값이 우연히 포함됐는지 확인 + redact.

    Source(_request_with_retry)는 이미 type name만 사용하여 안전하나, 향후 코드 변경·외부 라이브러리 변경으로
    키가 섞일 가능성에 대비한 second layer.
    """
    if not msg:
        return msg
    key = os.environ.get("LAW_API_KEY", "")
    if key and key in msg:
        msg = msg.replace(key, "<KEY-REDACTED>")
    return msg


def _make_snippet(content: str, query: str, max_len: int = _SNIPPET_MAX) -> str:
    """match 위치를 중심으로 잘라 snippet 생성. 최종 길이가 max_len을 절대 초과하지 않음 (ellipsis 포함 계산)."""
    if len(content) <= max_len:
        return content
    idx = content.find(query)
    if idx < 0:
        return content[:max_len]
    # ellipsis 자리(앞 3 + 뒤 3 = 6자) 예약: content 슬라이스는 max_len-6 이내로 제한
    content_budget = max(1, max_len - 6)
    half = content_budget // 2
    start = max(0, idx - half)
    end = min(len(content), start + content_budget)
    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    # 최종 안전망 — 어떤 경우에도 max_len 초과 금지
    return snippet[:max_len]

# Lazy LawApiClient singleton — first call instantiates with current env
_client_instance: LawApiClient | None = None


def _get_client() -> LawApiClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = LawApiClient()
    return _client_instance


def _build_match(rs, unit_id: str, unit_type: str, title: str, snippet: str) -> dict:
    """단일 검색 결과 dict 생성. snippet은 호출자가 _make_snippet으로 미리 생성."""
    return {
        "provision_id": build_provision_id(rs.api_target.value, rs.api_doc_id, unit_id),
        "document_title": rs.title,
        "unit_id": unit_id,
        "unit_type": unit_type,
        "title": title or "(제목없음)",
        "snippet": snippet,
        "warnings": list(rs.known_limitations),
    }


@mcp.tool()
async def health() -> dict:
    """서비스 상태 확인 — status, service name, version, API 키 설정 여부."""
    return {
        "status": "ok",
        "service": "korean-rnd-regs-mcp",
        "version": __version__,
        "api_key_configured": bool(os.environ.get("LAW_API_KEY")),
    }


@mcp.tool()
async def search_provision(query: str) -> dict:
    """규정 조문·별표 본문에서 query 키워드를 찾아 후보 list 반환.

    manifest의 live_api 문서들을 대상으로:
      - law(혁신법·시행령·시행규칙): 조문(`조문내용`) 검색
      - admrul(연구개발비 사용 기준 등): 조문 + 별표(`별표내용`) 검색
        - 각 항목의 `unit_types` (article/annex/both)에 따라 검색 범위 결정

    응답 최상위에 짧은 `disclaimer` 1개만 두고, 각 결과에는 manifest 특유의 `warnings`만 첨부.
    snippet은 _SNIPPET_MAX (2000자)로 제한 — MCP output size limit 회피.
    """
    items = load_manifest()
    live_items = [rs for rs in items if rs.retrieval == Retrieval.LIVE_API]
    client = _get_client()

    matches: list[dict] = []
    errors: list[dict] = []

    for rs in live_items:
        try:
            if rs.api_target == ApiTarget.LAW:
                detail = await asyncio.to_thread(client.get_law_detail, rs.api_doc_id)
                articles = detail.get("articles", [])
                annexes: list = []  # law detail은 별표 미반환 (시행령 별표는 v0.3 이후)
            else:  # admrul
                detail = await asyncio.to_thread(client.get_admin_rule_detail, rs.api_doc_id)
                articles = detail.get("articles", [])
                annexes = detail.get("annexes", [])
        except LawApiError as e:
            logger.warning("search_provision: %s detail 실패: %s", rs.id, e)
            errors.append({"rule_set_id": rs.id, "code": e.code, "message": _sanitize_error_message(e.message)})
            continue

        # article 검색
        if rs.unit_types in (UnitTypes.ARTICLE, UnitTypes.BOTH):
            for art in articles:
                title = (art.get("조문제목") or "").strip()
                content = (art.get("조문내용") or "").strip()
                if query in title or query in content:
                    art_no = (art.get("조문번호") or "").strip()
                    if art_no.isdigit():
                        snippet = _make_snippet(content, query)
                        matches.append(_build_match(rs, f"JO{int(art_no):04d}", "article", title, snippet))

        # annex 검색
        if rs.unit_types in (UnitTypes.ANNEX, UnitTypes.BOTH):
            for ann in annexes:
                title = (ann.get("별표제목") or "").strip()
                content = (ann.get("별표내용") or "").strip()
                if query in title or query in content:
                    ann_no = (ann.get("별표번호") or "").strip()
                    if ann_no.isdigit():
                        snippet = _make_snippet(content, query)
                        matches.append(_build_match(rs, f"BP{int(ann_no):04d}", "annex", title, snippet))

    response = {
        "query": query,
        "total": len(matches),
        "contract_version": CONTRACT_VERSION,
        "disclaimer": _DISCLAIMER,
        "results": matches,
    }
    if errors:
        response["errors"] = errors
    return response


@mcp.tool()
async def suggest_review_sources(question: str) -> dict:
    """본 도구는 법률 판단을 하지 않습니다. 사용자 질문의 키워드로 검토해야 할 rule set·후보 조문·검토 순서만 반환합니다. 최종 판단은 사용자의 책임이며, 별표·매뉴얼·기관 운영규정 별도 확인이 필요합니다."""
    keywords = _extract_keywords(question)
    if not keywords:
        return {
            "question": question,
            "extracted_keywords": [],
            "recommended_review_order": [],
            "candidates": [],
            "total": 0,
            "disclaimer": _DISCLAIMER,
            "contract_version": CONTRACT_VERSION,
        }

    # 각 keyword로 search_provision 호출 후 통합 (provision_id로 dedupe)
    all_matches: dict[str, dict] = {}
    for kw in keywords:
        res = await search_provision(kw)
        for m in res.get("results", []):
            pid = m["provision_id"]
            if pid in all_matches:
                all_matches[pid]["matched_keywords"].append(kw)
            else:
                m_copy = dict(m)
                m_copy["matched_keywords"] = [kw]
                all_matches[pid] = m_copy

    # manifest 참조해 hierarchy_rank 정렬
    rs_by_doc = {
        (rs.api_target.value, rs.api_doc_id): rs
        for rs in load_manifest()
        if rs.retrieval == Retrieval.LIVE_API
    }

    def _rank_key(match: dict) -> tuple:
        pid = parse_provision_id(match["provision_id"])
        rs = rs_by_doc.get((pid.doc_type, pid.doc_id))
        return (rs.hierarchy_rank.value if rs else 99, match["provision_id"])

    candidates = sorted(all_matches.values(), key=_rank_key)

    # recommended_review_order — 후보가 속한 hierarchy 순서로 unique document list
    seen_titles: dict[int, list[str]] = {}
    for m in candidates:
        pid = parse_provision_id(m["provision_id"])
        rs = rs_by_doc.get((pid.doc_type, pid.doc_id))
        if rs:
            rank = rs.hierarchy_rank.value
            seen_titles.setdefault(rank, [])
            if rs.title not in seen_titles[rank]:
                seen_titles[rank].append(rs.title)

    review_order = [
        {"rank": rank, "rank_name": _RANK_NAMES.get(rank, "기타"), "document": title}
        for rank in sorted(seen_titles.keys())
        for title in seen_titles[rank]
    ]

    return {
        "question": question,
        "extracted_keywords": keywords,
        "recommended_review_order": review_order,
        "candidates": candidates,
        "total": len(candidates),
        "disclaimer": _DISCLAIMER,
        "contract_version": CONTRACT_VERSION,
    }


@mcp.tool()
async def get_provision_detail(provision_id: str) -> dict:
    """provision_id로 단일 조문/별표 본문 재조회 (Step 22a 법령 + Step 22b 행정규칙 통합).

    provision_id 포맷: {doc_type}:{doc_id}[:{unit_id}]
    - unit_id 생략 시 document-level 요약 반환
    - unit_id가 JO… 면 조문 본문, BP… 면 별표 본문 (행정규칙 한정)
    """
    try:
        pid = parse_provision_id(provision_id)
    except InvalidProvisionId as e:
        return {
            "errors": [{"code": "invalid_provision_id", "message": str(e)}],
            "contract_version": CONTRACT_VERSION,
            "disclaimer": _DISCLAIMER,
        }

    # manifest에서 매칭 rule_set 찾기
    rs = next(
        (
            r for r in load_manifest()
            if r.api_doc_id == pid.doc_id and r.api_target.value == pid.doc_type
        ),
        None,
    )
    if rs is None:
        return {
            "errors": [{
                "code": "not_found",
                "message": f"manifest에 {pid.doc_type}:{pid.doc_id} 항목 없음",
            }],
            "contract_version": CONTRACT_VERSION,
            "disclaimer": _DISCLAIMER,
        }

    client = _get_client()
    try:
        if pid.doc_type == "law":
            detail = await asyncio.to_thread(client.get_law_detail, pid.doc_id)
            articles = detail.get("articles", [])
            annexes: list = []
        else:  # admrul
            detail = await asyncio.to_thread(client.get_admin_rule_detail, pid.doc_id)
            articles = detail.get("articles", [])
            annexes = detail.get("annexes", [])
    except LawApiError as e:
        return {
            "errors": [{"code": e.code, "message": _sanitize_error_message(e.message)}],
            "contract_version": CONTRACT_VERSION,
            "disclaimer": _DISCLAIMER,
        }

    # document-level (unit_id 없음)
    if pid.unit_id is None:
        result = {
            "provision_id": provision_id,
            "document_title": rs.title,
            "document_source_url": rs.source_url,
            "unit_type": "document",
            "effective_date": rs.effective_date,
            "articles_count": len(articles),
            "contract_version": CONTRACT_VERSION,
            "disclaimer": _DISCLAIMER,
            "warnings": list(rs.known_limitations),
        }
        if pid.doc_type == "admrul":
            result["annexes_count"] = len(annexes)
        return result

    # article (JO)
    if pid.unit_id.startswith("JO"):
        target_no = int(pid.unit_id[2:])
        for art in articles:
            no = (art.get("조문번호") or "").strip()
            if no.isdigit() and int(no) == target_no:
                return {
                    "provision_id": provision_id,
                    "document_title": rs.title,
                    "document_source_url": rs.source_url,
                    "unit_type": "article",
                    "unit_id": pid.unit_id,
                    "title": (art.get("조문제목") or "").strip(),
                    "content": (art.get("조문내용") or "").strip(),
                    "effective_date": rs.effective_date,
                    "contract_version": CONTRACT_VERSION,
                    "disclaimer": _DISCLAIMER,
                    "warnings": list(rs.known_limitations),
                }

    # annex (BP)
    elif pid.unit_id.startswith("BP"):
        target_no = int(pid.unit_id[2:])
        for ann in annexes:
            no = (ann.get("별표번호") or "").strip()
            if no.isdigit() and int(no) == target_no:
                attached = (ann.get("별표서식파일링크") or "").strip()
                # 상대 path(/LSW/...) → 절대 URL 변환
                if attached and not attached.startswith(("http://", "https://")):
                    attached = urljoin(_LAW_GO_KR_BASE, attached)
                return {
                    "provision_id": provision_id,
                    "document_title": rs.title,
                    "document_source_url": rs.source_url,
                    "unit_type": "annex",
                    "unit_id": pid.unit_id,
                    "title": (ann.get("별표제목") or "").strip(),
                    "content": (ann.get("별표내용") or "").strip(),
                    "attached_file_url": attached or None,
                    "effective_date": rs.effective_date,
                    "contract_version": CONTRACT_VERSION,
                    "disclaimer": _DISCLAIMER,
                    "warnings": list(rs.known_limitations),
                }

    return {
        "errors": [{
            "code": "not_found",
            "message": f"{provision_id}의 unit을 detail 응답에서 찾지 못함",
        }],
        "contract_version": CONTRACT_VERSION,
        "disclaimer": _DISCLAIMER,
    }


@mcp.tool()
async def list_rule_sets() -> dict:
    """등록된 규정 문서(rule set) 목록 — MVP는 live_api retrieval 대상만 반환."""
    items = load_manifest()
    live_items = [rs for rs in items if rs.retrieval == Retrieval.LIVE_API]
    return {
        "total": len(live_items),
        "contract_version": CONTRACT_VERSION,
        "rule_sets": [
            {
                "id": rs.id,
                "title": rs.title,
                "tier": rs.tier,
                "hierarchy_rank": rs.hierarchy_rank.value,
                "api_target": rs.api_target.value,
                "api_doc_id": rs.api_doc_id,
                "unit_types": rs.unit_types.value,
                "effective_date": rs.effective_date,
                "source_url": rs.source_url,
            }
            for rs in live_items
        ],
    }


async def _run() -> None:
    logger.info("korean-rnd-regs-mcp stdio server starting")
    await mcp.run_stdio_async()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="korean-rnd-regs-mcp",
        description="국가연구개발 규정 검토용 MCP server (stdio mode). 인자 없이 실행하면 stdio MCP 서버가 시작됩니다.",
        epilog="Claude Desktop·Claude Code 등 MCP 클라이언트에서 자동 실행됨. 직접 실행 시 stdin EOF 발생 시 종료.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args()  # --version / --help는 여기서 exit. 다른 인자는 silent ignore (FastMCP가 stdin 처리)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
