"""korean-rnd-regs-mcp main entry — stdio / HTTP MCP server."""
import argparse
import asyncio
import contextvars
import logging
import os
import re
import sys
from typing import Annotated
from urllib.parse import urljoin, parse_qs

from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import Field

from . import __version__
from .live_api import LawApiClient, LawApiError, ResolvedDocId
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

mcp = FastMCP("korean-rnd-regs-mcp", version=__version__)

_DISCLAIMER = "본 결과는 검토 후보일 뿐 법률 판단이 아닙니다. 출처를 직접 확인하세요."
_SNIPPET_MAX = 2000
_RESULTS_MAX = 30
_SUGGEST_KEYWORDS_MAX = 10  # suggest_review_sources: 클라이언트(LLM) 제공 키워드 사용 상한
_SUGGEST_CANDIDATES_MAX = 15  # suggest_review_sources: 반환 후보 개수 상한 (토큰 한도 회피)
_SUGGEST_SNIPPET_MAX = 300   # suggest_review_sources: 반환 후보 snippet 단축 길이 (포인터 도구)
_LAW_GO_KR_BASE = "https://www.law.go.kr"
_VERBATIM_INSTRUCTIONS = (
    "본 응답의 content / article_structure는 국가법령정보 OpenAPI에서 직접 받은 법령 원문을 "
    "재구성한 것입니다 (plain text verbatim). 사용자에게 표시할 때 다음 정책을 엄격히 준수: "
    "(1) 임의 부제·요약·paraphrase 추가 금지 — 원문에 없는 '(중앙행정기관 직권 변경·중단)' 같은 "
    "헤더 발명 금지. (2) 항(①②③) 번호와 호(1./2./3.) 번호 prefix를 stripping 금지. "
    "(3) 줄바꿈·들여쓰기를 유지. (4) 항·호 hierarchy는 article_structure 필드로 machine-readable "
    "제공되므로 LLM이 직접 reformat할 필요 없음. 법령 검토의 정확성 훼손 방지를 위해 verbatim 인용."
)
_RANK_NAMES = {
    1: "법률",
    2: "시행령",
    3: "시행규칙",
    4: "행정규칙",
    5: "Supplementary 법률",   # 부패방지법·청탁금지법·공익신고자보호법 등
    6: "Supplementary 시행령",
}
_KEYWORD_STOPWORDS = frozenset({
    "대해", "관련", "관해", "관하여", "경우", "에서", "으로", "에게",
    "있는", "있을", "있나요", "있는지", "있습니까", "있습니다",
    "하는", "하면", "하려면", "해야", "한다", "합니다",
    "되는", "된다", "됩니까", "될까요", "필요한", "필요합니까",
    "어떻게", "무엇", "어떤", "어디서", "언제", "왜", "얼마", "몇",
    "받으려면", "받을", "받으면", "이라면", "인지", "인가요",
    "대한", "이번", "이전", "이후", "그러나", "그리고", "그래서",
    # 흔한 동사형 어미·서술어 추가
    "필요한가요", "변경되었나요", "되었나요", "되었습니까", "있었나요",
    "있을까요", "없을까요", "되나요", "되었던가요",
    "있습니다", "없습니다", "됩니다",
    "주의사항은", "주의사항",
})
# 흔한 한국어 조사 (긴 것부터 정렬 — endswith 매칭 우선순위)
# 1글자 조사 중 "이/가/의/에/도/만/로"는 명사 끝 음절에 자주 등장(false positive risk)
# → "을/를/은/는/과/와"만 strip. 예: "특별평가" + "가" 조사 strip로 "특별평" 되는 버그 방지.
_PARTICLES = (
    "에서는", "에서도", "으로는", "에게는",
    "에서", "으로", "에게", "한테", "까지", "부터", "조차", "마저",
    "와의", "과의",
    "을", "를", "은", "는", "과", "와",
)


def _strip_particle(word: str) -> str:
    """단어 끝의 조사 suffix 제거. 단어가 너무 짧아지면(<2자) 원본 유지.

    "특별평가" → "특별평가" (1글자 "가"는 strip 안 함; 명사 끝 음절에 자주 등장)
    "특별평가를" → "특별평가"
    "혁신법은" → "혁신법"
    """
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


def _sanitize_keywords(keywords: list[str] | None) -> list[str]:
    """클라이언트(호스트 LLM)가 제공한 keywords를 검색용으로 정규화.

    - 문자열 항목만 채택(직접 호출 방어), 좌우 공백 strip
    - 공백 제외 2자 이상만 유지(search_provision의 invalid_query 회피)
    - 순서 보존 dedupe, 최대 _SUGGEST_KEYWORDS_MAX(10)개
    None이거나 유효 항목이 없으면 빈 list 반환 → 호출부가 fallback 여부 판단.
    """
    if not keywords:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        if not isinstance(kw, str):
            continue
        kw = kw.strip()
        if len(kw) < 2 or kw in seen:
            continue
        seen.add(kw)
        cleaned.append(kw)
        if len(cleaned) >= _SUGGEST_KEYWORDS_MAX:
            break
    return cleaned


def _select_capped_candidates(candidates, used, rank_of, max_n=_SUGGEST_CANDIDATES_MAX):
    """후보가 max_n 초과 시 선별: 매칭된 각 문서(rule_set_id) 최소 1건 보장 + 중요 키워드 우선.

    - used: 검색에 사용된 키워드(앞쪽일수록 중요). rank_of(candidate)->int(낮을수록 상위 위계).
    - phase1: 매칭된 문서마다 최우선 후보 1건씩 → 법률이 상한을 독식해 행정규칙 등 하위 문서가
      통째로 누락되는 것 방지(행정규칙은 같은 rank에 문서가 여럿이라 위계 단위로는 부족).
      매칭 문서 수가 max_n 초과면 (rank, priority) 상위 문서만.
    - phase2: 남은 슬롯을 가장 관련 높은(중요 키워드 매칭) 후보로 채움.
    - 출력은 (rank, provision_id) 순. max_n 이하면 입력을 그대로 반환(단축은 호출부 담당).
    """
    if len(candidates) <= max_n:
        return candidates

    used_index = {kw: i for i, kw in enumerate(used)}

    def _priority(c):
        idxs = [used_index[kw] for kw in c.get("matched_keywords", []) if kw in used_index]
        return min(idxs) if idxs else 999

    # phase1: 문서별 최우선 후보 1건 (문서 수가 max_n 초과면 위계·관련도 상위 문서만)
    by_doc: dict[str, list] = {}
    for c in candidates:
        by_doc.setdefault(c.get("rule_set_id", ""), []).append(c)
    reps = [min(group, key=lambda c: (_priority(c), c["provision_id"])) for group in by_doc.values()]
    reps.sort(key=lambda c: (rank_of(c), _priority(c), c["provision_id"]))
    selected: list = reps[:max_n]
    selected_ids: set = {c["provision_id"] for c in selected}

    # phase2: 남은 슬롯을 (priority, rank, provision_id)로 채움 (phase1 선택분 제외)
    if len(selected) < max_n:
        rest = [c for c in candidates if c["provision_id"] not in selected_ids]
        rest.sort(key=lambda c: (_priority(c), rank_of(c), c["provision_id"]))
        selected += rest[: max_n - len(selected)]

    selected.sort(key=lambda c: (rank_of(c), c["provision_id"]))
    return selected


def _shorten_snippet(text: str, max_len: int = _SUGGEST_SNIPPET_MAX) -> str:
    """suggest 반환 snippet을 max_len 이하로 단축 (초과 시 말줄임표 포함, 최종 길이 ≤ max_len). None·빈 값은 ""로 방어(F3)."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _sanitize_error_message(msg: str) -> str:
    """Defense-in-depth: 도구 응답으로 error message 출력 전 LAW_API_KEY 값이 우연히 포함됐는지 확인 + redact.

    Source(_request_with_retry)는 이미 type name만 사용하여 안전하나, 향후 코드 변경·외부 라이브러리 변경으로
    키가 섞일 가능성에 대비한 second layer. HTTP 모드의 per-user key도 검사.
    """
    if not msg:
        return msg
    key = os.environ.get("LAW_API_KEY", "")
    if key and key in msg:
        msg = msg.replace(key, "<KEY-REDACTED>")
    req_key = _request_api_key.get("")
    if req_key and req_key in msg:
        msg = msg.replace(req_key, "<KEY-REDACTED>")
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

_request_api_key: contextvars.ContextVar[str] = contextvars.ContextVar("_request_api_key", default="")

_client_instance: LawApiClient | None = None
_client_by_key: dict[str, LawApiClient] = {}
_CLIENT_BY_KEY_MAX = 100


def _get_client() -> LawApiClient:
    key = _request_api_key.get("")
    if key:
        if key not in _client_by_key:
            if len(_client_by_key) >= _CLIENT_BY_KEY_MAX:
                oldest = next(iter(_client_by_key))
                del _client_by_key[oldest]
            _client_by_key[key] = LawApiClient(env_override={"LAW_API_KEY": key})
        return _client_by_key[key]
    global _client_instance
    if _client_instance is None:
        _client_instance = LawApiClient()
    return _client_instance


async def _resolve_doc_id(rs, client: LawApiClient) -> ResolvedDocId:
    return await asyncio.to_thread(
        client.resolve_latest_doc_id,
        rs.title,
        rs.api_target.value,
        rs.api_doc_id,
    )


def _resolve_effective_date(rs, resolved: ResolvedDocId | None) -> str:
    """표시용 시행일자 — LIVE resolve 값을 우선, 없으면(=resolve 실패) manifest 값으로 폴백.

    search-first가 매번 현행 시행일자를 가져오므로 LIVE 값을 항상 신뢰한다. law.go.kr 행정규칙은
    개정돼도 일련번호가 유지되는 경우가 있어(연구개발비 사용 기준 사례), is_updated(doc_id 변경)
    여부와 무관하게 LIVE 시행일을 표시해야 manifest 박제 값으로 인한 stale 표시를 막는다.
    """
    if resolved and resolved.effective_date:
        return resolved.effective_date
    return rs.effective_date


def _revision_notice(rs, resolved: ResolvedDocId | None) -> str | None:
    """개정 반영 안내 — doc_id가 바뀌었거나, LIVE 시행일이 manifest와 다를 때 생성.

    doc_id 비교만으로는 일련번호가 안정적인 행정규칙의 개정을 놓치므로, LIVE 시행일자 ≠ manifest
    시행일자도 개정 신호로 삼는다. LIVE 값이 비어있으면(=resolve 실패) 개정 판단을 하지 않는다(오탐 방지).
    """
    if resolved is None:
        return None
    live = resolved.effective_date
    if resolved.is_updated:
        return (
            f"개정 반영: 시행일 {live or rs.effective_date} "
            f"(manifest 기준 ID {resolved.manifest_doc_id} → 최신 ID {resolved.doc_id})"
        )
    if live and live != rs.effective_date:
        return (
            f"개정 반영: 시행일 {rs.effective_date} → {live} "
            f"(문서 ID 동일, manifest 시행일 갱신 권장)"
        )
    return None


def _build_match(rs, unit_id: str, unit_type: str, title: str, snippet: str,
                 resolved: ResolvedDocId | None = None) -> dict:
    """단일 검색 결과 dict 생성. snippet은 호출자가 _make_snippet으로 미리 생성."""
    doc_id = resolved.doc_id if resolved else rs.api_doc_id
    result = {
        "provision_id": build_provision_id(rs.api_target.value, doc_id, unit_id),
        "rule_set_id": rs.id,
        "document_title": rs.title,
        "unit_id": unit_id,
        "unit_type": unit_type,
        "title": title or "(제목없음)",
        "snippet": snippet,
        "warnings": list(rs.known_limitations),
    }
    if resolved:
        result["effective_date"] = _resolve_effective_date(rs, resolved)
        notice = _revision_notice(rs, resolved)
        if notice:
            result["revision_notice"] = notice
    return result


@mcp.tool()
async def health() -> dict:
    """서비스 상태 확인 — status, service name, version, API 키 설정 여부."""
    return {
        "status": "ok",
        "service": "korean-rnd-regs-mcp",
        "version": __version__,
        "api_key_configured": bool(os.environ.get("LAW_API_KEY") or _request_api_key.get("")),
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
    # empty/공백/1글자 query 무차별 매칭 방어
    query = (query or "").strip()
    if len(query) < 2:
        return {
            "query": query,
            "total": 0,
            "results": [],
            "errors": [{
                "code": "invalid_query",
                "message": "query는 의미 있는 검색을 위해 공백 제외 2자 이상이어야 합니다.",
            }],
            "contract_version": CONTRACT_VERSION,
            "disclaimer": _DISCLAIMER,
        }

    items = load_manifest()
    live_items = [rs for rs in items if rs.retrieval == Retrieval.LIVE_API]
    client = _get_client()

    matches: list[dict] = []
    errors: list[dict] = []

    async def _fetch_rule_set(rs):
        resolved = await _resolve_doc_id(rs, client)
        doc_id = resolved.doc_id
        if rs.api_target == ApiTarget.LAW:
            detail = await asyncio.to_thread(client.get_law_detail, doc_id)
            return rs, resolved, detail.get("articles", []), []
        else:
            detail = await asyncio.to_thread(client.get_admin_rule_detail, doc_id)
            return rs, resolved, detail.get("articles", []), detail.get("annexes", [])

    fetch_results = await asyncio.gather(
        *[_fetch_rule_set(rs) for rs in live_items],
        return_exceptions=True,
    )

    for i, result in enumerate(fetch_results):
        if isinstance(result, LawApiError):
            rs = live_items[i]
            logger.warning("search_provision: rule_set=%s detail 실패, code=%s", rs.id, result.code)
            errors.append({"rule_set_id": rs.id, "code": result.code, "message": _sanitize_error_message(result.message)})
            continue
        if isinstance(result, Exception):
            rs = live_items[i]
            logger.warning("search_provision: rule_set=%s unexpected error: %s", rs.id, type(result).__name__)
            errors.append({"rule_set_id": rs.id, "code": "parse_failed", "message": type(result).__name__})
            continue
        rs, resolved, articles, annexes = result

        # article 검색
        if rs.unit_types in (UnitTypes.ARTICLE, UnitTypes.BOTH):
            for art in articles:
                title = (art.get("조문제목") or "").strip()
                content = (art.get("조문내용") or "").strip()
                if query in title or query in content:
                    art_no = (art.get("조문번호") or "").strip()
                    if art_no.isdigit():
                        snippet = _make_snippet(content, query)
                        matches.append(_build_match(rs, f"JO{int(art_no):04d}", "article", title, snippet, resolved))

        # annex 검색
        if rs.unit_types in (UnitTypes.ANNEX, UnitTypes.BOTH):
            for ann in annexes:
                title = (ann.get("별표제목") or "").strip()
                content = (ann.get("별표내용") or "").strip()
                if query in title or query in content:
                    ann_no = (ann.get("별표번호") or "").strip()
                    if ann_no.isdigit():
                        snippet = _make_snippet(content, query)
                        matches.append(_build_match(rs, f"BP{int(ann_no):04d}", "annex", title, snippet, resolved))

    truncated = len(matches) > _RESULTS_MAX
    limited = matches[:_RESULTS_MAX]
    response = {
        "query": query,
        "total": len(matches),
        "returned": len(limited),
        "truncated": truncated,
        "contract_version": CONTRACT_VERSION,
        "disclaimer": _DISCLAIMER,
        "results": limited,
    }
    if errors:
        response["errors"] = errors
    return response


@mcp.tool()
async def suggest_review_sources(
    question: str,
    keywords: Annotated[
        list[str] | None,
        Field(
            description=(
                "선택. 호스트 LLM이 question에서 직접 추출한 검색 키워드 배열(1~10개, 권장 3~8). "
                "질문에 담긴 서로 다른 쟁점·절차·대상을 모두 포괄하고 중요한 키워드를 앞쪽에 둘 것. "
                "국가·사업·연구개발 같은 지나치게 광범위한 단어는 제외하되 승인·통보·보고 같은 절차어(2자 이상)는 포함 가능. "
                "검색은 부분문자열 정확 매칭이므로 법령 본문 표기(주로 공백 없는 복합어, 예: 협약변경)를 우선하되, "
                "검색 실패에 대비해 분리된 핵심 단어도 함께 넣을 것(예: 협약변경, 협약, 변경). "
                "공백이 포함된 한 덩어리(예: 협약 변경)는 매칭되지 않으니 피할 것. "
                "생략하면 서버가 질문에서 단순 규칙으로 추출(품질 낮음)하여 대체함."
            )
        ),
    ] = None,
) -> dict:
    """본 도구는 법률 판단을 하지 않습니다. 사용자 질문과 핵심 검색 키워드로 검토할 rule set·후보 조문·검토 순서만 반환합니다.

    가능하면 keywords 인자에 호스트 LLM이 추출한 핵심 검색어 배열을 함께 전달하십시오(question에는 검토 상황 전체).
    keywords가 제공되면 서버의 단순 규칙 추출보다 우선 사용되며, 생략·무효 시에만 규칙 추출로 대체됩니다.
    최종 판단은 사용자의 책임이며, 별표·매뉴얼·기관 운영규정 별도 확인이 필요합니다.
    """
    provided = _sanitize_keywords(keywords)
    if provided:
        used = provided
        keyword_source = "client"
    else:
        used = _extract_keywords(question)
        keyword_source = "fallback"

    if not used:
        return {
            "question": question,
            "extracted_keywords": [],
            "keyword_source": keyword_source,
            "recommended_review_order": [],
            "candidates": [],
            "total": 0,
            "returned": 0,
            "truncated": False,
            "disclaimer": _DISCLAIMER,
            "contract_version": CONTRACT_VERSION,
        }

    async def _search_union(kw_list: list[str]) -> tuple[dict[str, dict], list[dict]]:
        """주어진 키워드들로 search_provision을 순차 호출해 provision_id로 union (dedupe)."""
        matches: dict[str, dict] = {}
        errors: list[dict] = []  # search 실패를 "후보 없음"으로 위장하지 말 것
        for kw in kw_list:
            res = await search_provision(kw)
            for err in res.get("errors", []):
                errors.append({**err, "keyword": kw})
            for m in res.get("results", []):
                pid = m["provision_id"]
                if pid in matches:
                    matches[pid]["matched_keywords"].append(kw)
                else:
                    m_copy = dict(m)
                    m_copy["matched_keywords"] = [kw]
                    matches[pid] = m_copy
        return matches, errors

    all_matches, all_errors = await _search_union(used)

    # post-search 안전망: 클라이언트 키워드가 결과 0건 + 오류 없음이면(과협소 복합어 등)
    # 규칙 추출 키워드로 보강 — question-only 대비 recall 저하 방지. 클라이언트 검색에 오류가 있으면 보강 생략(원인 은폐 방지).
    if keyword_source == "client" and not all_matches and not all_errors:
        fb = _extract_keywords(question)
        if fb and set(fb) != set(used):  # 규칙 추출이 client 키워드와 같은 집합이면 재검색은 무의미
            fb_matches, fb_errors = await _search_union(fb)
            if fb_matches or fb_errors:  # 보강 결과(후보 또는 오류)가 있으면 일괄 채택 — 응답 필드 일관성 유지
                all_matches, all_errors = fb_matches, fb_errors
                used, keyword_source = fb, "client+fallback"

    # manifest 참조해 hierarchy_rank 정렬 — rule_set_id 기반 (search-first로 doc_id가 변경될 수 있으므로)
    rs_by_id = {
        rs.id: rs
        for rs in load_manifest()
        if rs.retrieval == Retrieval.LIVE_API
    }

    def _rank_key(match: dict) -> tuple:
        rs = rs_by_id.get(match.get("rule_set_id", ""))
        return (rs.hierarchy_rank.value if rs else 99, match["provision_id"])

    candidates = sorted(all_matches.values(), key=_rank_key)

    # recommended_review_order — 후보가 속한 hierarchy 순서로 unique document list
    seen_titles: dict[int, list[str]] = {}
    for m in candidates:
        rs = rs_by_id.get(m.get("rule_set_id", ""))
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

    # B축: 응답 후보 개수 cap + snippet 단축 (review_order·total은 전체 candidates 기준 유지)
    def _rank_of(c: dict) -> int:
        rs = rs_by_id.get(c.get("rule_set_id", ""))
        return rs.hierarchy_rank.value if rs else 99

    capped = _select_capped_candidates(candidates, used, _rank_of)
    returned_candidates = []
    for c in capped:
        c2 = dict(c)  # shallow copy — snippet(str)만 교체, warnings 등 원본 미변경
        c2["snippet"] = _shorten_snippet(c2.get("snippet", ""))
        returned_candidates.append(c2)

    response = {
        "question": question,
        "extracted_keywords": used,
        "keyword_source": keyword_source,
        "recommended_review_order": review_order,
        "candidates": returned_candidates,
        "total": len(candidates),
        "returned": len(returned_candidates),
        "truncated": len(candidates) > len(returned_candidates),
        "disclaimer": _DISCLAIMER,
        "contract_version": CONTRACT_VERSION,
    }
    if len(candidates) > len(returned_candidates):
        response["note"] = (
            "검색 결과가 많아 위계·중요도 기준 상위 후보만 반환했습니다. "
            "recommended_review_order의 전체 문서 목록을 참고하고, 필요 시 search_provision으로 추가 검색하십시오."
        )
    if all_errors:
        response["errors"] = all_errors
    return response


@mcp.tool()
async def get_provision_detail(provision_id: str) -> dict:
    """provision_id로 단일 조문/별표 본문 재조회 — 응답은 법령 원문 verbatim.

    중요 (LLM 표시 정책): 응답의 `content`와 `article_structure` 는 국가법령정보 OpenAPI의
    법령 원문을 그대로 재구성한 것입니다. 사용자에게 표시할 때 임의 부제 추가·요약·paraphrase
    를 절대 추가하지 말고, 항(①②③)·호(1./2./3.) 번호와 줄바꿈을 모두 유지하여 원문을
    그대로 인용해야 합니다 (법령 검토의 정확성 훼손 방지). 자세한 정책은 응답의
    `format_instructions` 필드 참조.

    provision_id 포맷: {doc_type}:{doc_id}[:{unit_id}]
    - unit_id 생략 시 document-level 요약 반환
    - unit_id가 JO… 면 조문 본문 + article_structure, BP… 면 별표 본문 (행정규칙 한정)
    """
    try:
        pid = parse_provision_id(provision_id)
    except InvalidProvisionId as e:
        return {
            "errors": [{"code": "invalid_provision_id", "message": str(e)}],
            "contract_version": CONTRACT_VERSION,
            "disclaimer": _DISCLAIMER,
        }

    # manifest에서 매칭 rule_set 찾기 (manifest doc_id 직접 매칭)
    live_items = [r for r in load_manifest() if r.retrieval == Retrieval.LIVE_API]
    rs = next(
        (r for r in live_items if r.api_doc_id == pid.doc_id and r.api_target.value == pid.doc_type),
        None,
    )
    # Fallback: pid.doc_id가 resolved(최신) ID일 수 있음 — search-first로 확인
    client = _get_client()
    if rs is None:
        for r in live_items:
            if r.api_target.value != pid.doc_type:
                continue
            try:
                res = await _resolve_doc_id(r, client)
                if res.doc_id == pid.doc_id:
                    rs = r
                    break
            except Exception:
                continue
    if rs is None:
        return {
            "errors": [{
                "code": "not_found",
                "message": f"manifest에 {pid.doc_type}:{pid.doc_id} 항목 없음",
            }],
            "contract_version": CONTRACT_VERSION,
            "disclaimer": _DISCLAIMER,
        }
    try:
        resolved = await _resolve_doc_id(rs, client)
        doc_id = resolved.doc_id
        if pid.doc_type == "law":
            detail = await asyncio.to_thread(client.get_law_detail, doc_id)
            articles = detail.get("articles", [])
            annexes: list = []
        else:  # admrul
            detail = await asyncio.to_thread(client.get_admin_rule_detail, doc_id)
            articles = detail.get("articles", [])
            annexes = detail.get("annexes", [])
    except LawApiError as e:
        return {
            "errors": [{"code": e.code, "message": _sanitize_error_message(e.message)}],
            "contract_version": CONTRACT_VERSION,
            "disclaimer": _DISCLAIMER,
        }

    eff_date = _resolve_effective_date(rs, resolved)
    _revision = _revision_notice(rs, resolved)

    # document-level (unit_id 없음)
    if pid.unit_id is None:
        result = {
            "provision_id": provision_id,
            "document_title": rs.title,
            "document_source_url": rs.source_url,
            "unit_type": "document",
            "effective_date": eff_date,
            "articles_count": len(articles),
            "contract_version": CONTRACT_VERSION,
            "disclaimer": _DISCLAIMER,
            "warnings": list(rs.known_limitations),
        }
        if pid.doc_type == "admrul":
            result["annexes_count"] = len(annexes)
        if _revision:
            result["revision_notice"] = _revision
        return result

    # article (JO)
    if pid.unit_id.startswith("JO"):
        target_no = int(pid.unit_id[2:])
        for art in articles:
            no = (art.get("조문번호") or "").strip()
            if no.isdigit() and int(no) == target_no:
                resp = {
                    "provision_id": provision_id,
                    "document_title": rs.title,
                    "document_source_url": rs.source_url,
                    "unit_type": "article",
                    "unit_id": pid.unit_id,
                    "title": (art.get("조문제목") or "").strip(),
                    "content": (art.get("조문내용") or "").strip(),
                    "content_format": "plain_text_verbatim",
                    "article_structure": art.get("structured"),
                    "format_instructions": _VERBATIM_INSTRUCTIONS,
                    "effective_date": eff_date,
                    "contract_version": CONTRACT_VERSION,
                    "disclaimer": _DISCLAIMER,
                    "warnings": list(rs.known_limitations),
                }
                if _revision:
                    resp["revision_notice"] = _revision
                return resp

    # annex (BP)
    elif pid.unit_id.startswith("BP"):
        target_no = int(pid.unit_id[2:])
        for ann in annexes:
            no = (ann.get("별표번호") or "").strip()
            if no.isdigit() and int(no) == target_no:
                attached = (ann.get("별표서식파일링크") or "").strip()
                if attached and not attached.startswith(("http://", "https://")):
                    attached = urljoin(_LAW_GO_KR_BASE, attached)
                resp = {
                    "provision_id": provision_id,
                    "document_title": rs.title,
                    "document_source_url": rs.source_url,
                    "unit_type": "annex",
                    "unit_id": pid.unit_id,
                    "title": (ann.get("별표제목") or "").strip(),
                    "content": (ann.get("별표내용") or "").strip(),
                    "attached_file_url": attached or None,
                    "effective_date": eff_date,
                    "contract_version": CONTRACT_VERSION,
                    "disclaimer": _DISCLAIMER,
                    "warnings": list(rs.known_limitations),
                }
                if _revision:
                    resp["revision_notice"] = _revision
                return resp

    return {
        "errors": [{
            "code": "not_found",
            "message": f"{provision_id}의 unit을 detail 응답에서 찾지 못함",
        }],
        "contract_version": CONTRACT_VERSION,
        "disclaimer": _DISCLAIMER,
    }


_REVIEW_PROMPT_TEMPLATE = """당신은 연구행정 관련 규정 검토 전문가입니다. 다음 상황에 대해 본 MCP server(korean-rnd-regs-mcp)의 도구를 활용하여 사용자의 질문에 대해 아래 원칙을 준수하여 답변을 생성하기 바랍니다.

== Core Principles ==

- 절대 하지 말아야 할 것:
  - 규정에 명시되지 않은 해석을 추가하지 말 것.
  - 규정에 구체적으로 명시되지 않은 해결 방안을 제시하지 말 것.
  - 실체적 결론은 구체적인 조문번호·provision_id·원문 인용 없이 제시하지 말 것.
  - 규정이 해당 질문을 명확히 다루지 않는 경우, 추측해서 답변을 생성하지 말 것.
    - 추측해서 답변을 생성하지 말고 "규정에서 질문에 대한 답변을 다루지 않음"을 명시하는 쪽을 택할 것.

- 반드시 해야 할 것:
  - 규정을 체계적으로 검토할 것.
    - 규정 간 충돌 발생 시 상위 규정을 우선 적용하여 답변을 생성할 것(법률 > 시행령 > 행정규칙)
  - 모든 답변에는 근거가 되는 조항(조문 번호)을 인용할 것.
  - 규정 범위 안에서만 답변을 생성할 것.
  - 실제 규정에 기재된 바와 그 규정의 해석은 분리해서 기재할 것.
  - 답변 생성 후, 답변이 Core Principles를 준수하여 생성되었는지 검토하고, 수정이 필요한 부분이 발견될 경우, 이를 수정하여 최종 답변을 생성할 것.
  - 구동 중 도구에 오류가 발생한 경우, "도구 오류"로 표시할 것.
  - 조문 검색 결과, 얻게 된 정보가 없는 경우, "본 MCP 검색 범위에서 확인되지 않음"이라고 표시할 것.
  - 본 프롬프트로 생성된 규정 검토 결과에 대해 사용자가 추가 질문을 하는 경우, 아래 원칙을 준수하여 답변을 생성할 것.
    - 사용자 질문 검토 후, 질문에 담긴 사용자의 판단이 규정에 부합하지 않는다고 판단되는 경우, 답변 생성 시 해당 정보를 반드시 포함시킬 것.
  - 한국어 격식체로 답변을 생성할 것.

== 검토 상황 ==
{situation}

== MCP 적용 범위 (17개 규정) ==
- Tier 1 (혁신법 family): 혁신법(일반법)·시행령·시행규칙
- Tier 1 (Sector — 국토교통 R&D family): 국토교통과학기술 육성법(특별법)·시행령·시행규칙
- Tier 2 (행정규칙): 연구개발비 사용 기준·동시수행 제한·시설장비 표준지침·연구노트 지침, 국토교통부소관 연구개발사업 운영규정
- Supplementary (법률·시행령 6개): 부패방지·청탁금지·공익신고자보호
- 미커버: 국가연구개발혁신법 매뉴얼, 시행령 별표, 기관 내부 기준, 기타 부처별 매뉴얼·가이드
- 미커버 자료가 결론에 필요하면 단정하지 말고 "추가 확인 필요"로 표시할 것.
- 일반법 vs 특별법 적용 우선순위는 사안의 특성에 따라 판단할 것.

== 검토 절차 (반드시 본 순서 준수) ==

1. 핵심 쟁점 파악 및 검색 키워드 작성
   - 상황의 핵심 행위·주체·절차·금액·기간 등을 분해하여 검토할 것.
   - 권한 있는 기관(중앙행정기관·전문기관·연구개발기관 등)의 승인·보고·통보 대상인지 확인할 것.
   - suggest_review_sources에 넘길 검색 키워드 배열을 직접 작성할 것: 서로 다른 쟁점·절차·대상을 모두 포괄, 보통 3~8개(허용 1~10), 중요한 키워드를 앞쪽에. 국가·사업·연구개발 같은 지나치게 광범위한 단어는 제외하되 승인·통보·보고 같은 절차어는 포함할 것. 검색은 부분문자열 정확 매칭이므로 법령 본문 표기(주로 공백 없는 복합어, 예: 협약변경)를 우선하되, 검색 실패 대비 분리된 핵심 단어도 함께 넣을 것(예: 협약변경, 협약, 변경).

2. suggest_review_sources 호출 (question 인자에 위 '== 검토 상황 =='의 상황 전체를, keywords 인자에 1단계에서 작성한 검색 키워드 배열을 함께 전달)
   - extracted_keywords(실제 검색에 사용된 키워드), candidates, recommended_review_order, errors를 확인할 것.
   - recommended_review_order는 기본 검토 순서로 삼되, 후보가 적으면 3단계에서 보완할 것.
   - returned·truncated·note도 확인할 것: truncated가 true이면 후보가 위계·중요도 상위 일부만 반환된 것(전체 후보 수는 total)이므로, recommended_review_order의 전체 문서 목록을 기준으로 3단계에서 search_provision으로 누락 후보를 보완할 것.

3. search_provision(query=...)으로 추가 검색 및 주제별 cross-check
   - 핵심 키워드, 법령상 유사어, 절차어(승인, 통보, 보고, 협약변경, 정산, 제재 등)로 검색할 것.
   - suggest_review_sources 후보와 중복 제거 후 통합할 것.
   - 주제별 Tier 2 cross-check (해당 시):
     연구개발비/예산/비목/집행 → rnd_funding_standard | 동시수행/과제 수 → simultaneous_research_limit
     시설/장비/기자재 → facility_equipment_standard | 연구노트/실험노트 → research_note_guideline
   - Supplementary (해당 시):
     신고/포상금/부패행위 → anti_corruption_act + decree | 부정청탁/금품수수 → improper_solicitation_act + decree
     공익신고/신변보호 → public_interest_whistleblower_act + decree

4. 위계 순서에 따른 상세 조회
   - 법률 → 시행령 → 시행규칙 → 행정규칙 → Supplementary 순서로 검토할 것
   - 각 provision_id로 get_provision_detail을 호출할 것.
   - content는 OpenAPI 원문을 그대로 사용할 것.
     - OpenAPI로부터 입수한 조문의 원문을 임의로 수정(요약, paraphrase 등)하지 말 것.
     - OpenAPI로부터 입수한 조문의 항·호·목 번호를 유지할 것.

5. 참조 조항 추적
   - 조문이 "제X조에 따라", "시행령 제X조", "별표", "고시로 정하는" 등을 참조하면 해당 조항도 조회할 것.
   - 행정규칙 별표(BP)는 get_provision_detail로 조회 가능하나, 시행령 별표는 현재 버전의 MCP로 fetch 불가.
   - 참조 조항 확인 없이 결론을 확정하지 말 것.

6. 조문 요건 해석, 사실관계 분석, 상위 규정 우선 원칙
   - 조문 요건 해석
     - 재량·의무 구분: "할 수 있다"는 재량, "하여야 한다"는 의무로 판단할 것.
     - 선택·병렬 구분: "하거나"와 "하고"를 혼동하지 말 것.
     - 조회한 조문에서 의무·재량·금지·예외·선택·병렬 요건을 분리하여 정리할 것.
   - 사실관계 분석
     - 정리한 조문 요건과 사용자가 제시한 사실관계를 1:1로 대응시킬 것.
     - 대응 결과를 다음으로 구분할 것: 충족 확인 / 불충족 확인 / 사실 부족 / 규정 미확인 / MCP 범위 밖.
     - 규정상 근거가 불명확한 경우, 가능성·한계·추가 확인 필요를 분리하여 작성할 것.
   - 상위 규정 우선 원칙
     - 규정 간 충돌 시 상위 규정 우선 적용
     - 일반법·특별법 관계는 사안 특성에 따라 판단.

== 최종 출력 형식 ==
- 아래 제목과 순서를 그대로 사용할 것.
- 중요한 정보 위주로 답변을 구성할 것.
- 불필요한 정보가 답변에 포함되지 않도록 주의할 것.
  - 단, 근거 조항의 원문 인용은 생략·요약하지 말 것.

## 【규정 검토 결과】

### 1. 상황 요약
[1-2문장으로 핵심 사실과 쟁점을 요약할 것.]

### 2. 검토 규정
- Tier 1 법률·시행령·시행규칙: [규정명 목록]
- Tier 2 행정규칙: [규정명 목록, 없으면 "해당 없음"]
- Supplementary: [규정명 목록, 없으면 "해당 없음"]

### 3. 핵심 답변
- 결론: [허용/불가/승인 필요/보고 필요/추가 확인 필요 등으로 명확히 기재]
- 이유: [1-3문장으로 근거 조항과 연결]

### 4. 근거 조항
각 근거는 아래 형식을 반복할 것.
- [규정명] [조문번호] — provision_id: [provision_id]
  - 원문:
    > [get_provision_detail의 content를 verbatim 인용]
  - 적용: [이 조항이 어느 판단단위(행위·주체·절차·금액·기간)에 적용되며, 사실관계를 충족/불충족하는지]
  - 표현 판단: [의무/재량/금지/예외/선택·병렬 중 표시]

### 5. 위계 및 충돌 검토
- 상위법 우선: [상위법과 하위 규정 관계]
- 충돌 여부: [충돌 없음/충돌 가능/추가 확인 필요]

### 6. 쟁점·결손 분석
- 조문상 불명확한 부분: [없으면 "해당 없음"]
- 사용자가 제공하지 않은 필수 사실: [없으면 "해당 없음"]
- MCP 미커버 자료 확인 필요: [없으면 "해당 없음"]
- 위 각 항목이 결론에 미치는 영향: [예: "사실 부족으로 단정 불가" 등]
- 가지조문(예: 제15조의2) 검색·상세조회 누락 가능

### 7. 권고 조치
- 규정상 확인된 후속 절차·승인·보고·문서화 조치만 기재할 것.
- 법률 판단이 필요한 사안(징계·소송·제재 비례성·승소 가능성)은 변호사 자문 권고를 표시할 것.
"""


@mcp.prompt(
    name="review_regulation",
    title="규정 검토 (표준 워크플로 기반 1차 검토)",
    description=(
        "본 MCP 적용 범위 내 국가연구개발 및 국토교통 R&D 연구행정 규정 검토 — 혁신법·시행령·시행규칙·핵심 행정규칙 + "
        "Supplementary(부패방지·청탁금지·공익신고자보호)를 자동으로 cross-reference하여 근거 조항 "
        "verbatim 인용과 함께 답변. Tier 1 → Tier 2 → Supplementary 위계 순서 + provision_id 인용을 "
        "본 MCP server 도구(suggest_review_sources, get_provision_detail)로 자동 적용. "
        "매뉴얼·부처별 운영규정·관리지침은 본 server 미커버 — 별도 자료 확인 필요."
    ),
)
def review_regulation_prompt(situation: str) -> str:
    """다층적 규정 검토를 위한 prompt template.

    Args:
        situation: 검토 대상 상황·질문 (자연어. 예: "연구기관이 공동연구기관 추가를 요청했으나 ...")
    """
    return _REVIEW_PROMPT_TEMPLATE.format(situation=situation)


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


async def _run_stdio() -> None:
    logger.info("korean-rnd-regs-mcp stdio server starting")
    await mcp.run_stdio_async()


class _OCKeyMiddleware:
    """ASGI middleware: URL의 ?oc= 파라미터를 추출하여 요청별 LAW_API_KEY로 설정."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            qs = scope.get("query_string", b"").decode()
            params = parse_qs(qs)
            oc = params.get("oc", [""])[0]
            token = _request_api_key.set(oc)
            try:
                await self.app(scope, receive, send)
            finally:
                _request_api_key.reset(token)
        else:
            await self.app(scope, receive, send)


async def _run_http(host: str, port: int) -> None:
    logger.info("korean-rnd-regs-mcp HTTP server starting on %s:%d", host, port)
    from starlette.middleware import Middleware
    await mcp.run_http_async(
        transport="streamable-http",
        host=host,
        port=port,
        middleware=[Middleware(_OCKeyMiddleware)],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="korean-rnd-regs-mcp",
        description="국가연구개발 규정 검토용 MCP server. 기본은 stdio, --http로 원격 배포용 HTTP 모드.",
        epilog="Claude Desktop·Claude Code → stdio (기본). Claude.ai 웹 커넥터 → --http.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="HTTP (streamable-http) 모드로 실행. PORT 환경변수 또는 기본 8080 포트 사용.",
    )
    args = parser.parse_args()

    if args.http:
        port = int(os.environ.get("PORT", "8080"))
        asyncio.run(_run_http("0.0.0.0", port))
    else:
        asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
