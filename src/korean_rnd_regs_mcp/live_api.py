"""국가법령정보 OpenAPI client — generalized from korean-law-mcp/src/tools.py.

See docs/api_contract.md for endpoint mapping, ID conventions, and error codes.
Sync API; wrap with asyncio.to_thread when called from FastMCP tools.
"""
import logging
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from cachetools import TTLCache

from .provision_id import CONTRACT_VERSION

logger = logging.getLogger("rnd-regs-mcp.live_api")

DEFAULT_LAW_API_URL = "https://www.law.go.kr/DRF"

# Standard error codes (docs/api_contract.md §4)
ERROR_AUTH_FAILED = "auth_failed"
ERROR_RATE_LIMITED = "rate_limited"
ERROR_PARSE_FAILED = "parse_failed"
ERROR_NOT_FOUND = "not_found"
ERROR_INVALID_PROVISION_ID = "invalid_provision_id"


class LawApiError(Exception):
    """Standard error for live API calls (carries `code` per contract §4)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DocumentRef:
    """법령/행정규칙 문서 메타 (검색 응답 item)."""
    doc_type: str           # "law" | "admrul"
    doc_id: str             # MST for law, 행정규칙일련번호 for admrul
    title: str
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProvisionRef:
    """조문 또는 별표 단위 reference (search_provision 응답 item, Step 21에서 사용)."""
    provision_id: str       # see provision_id.py
    unit_id: Optional[str]  # JO0003 (조문) or BP0001 (별표) or None (document-level)
    snippet: str            # <= 2000 chars (contract §5)
    document_title: str
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    """검색 응답 wrapper."""
    total: int
    page: int
    page_size: int
    items: list             # list[DocumentRef]
    contract_version: str = CONTRACT_VERSION


# === Credentials ===

def get_credentials(env_override: Optional[dict] = None) -> dict:
    """Load LAW_API_KEY/LAW_API_URL with priority: env_override > process env."""
    api_key = ""
    api_url = DEFAULT_LAW_API_URL
    if isinstance(env_override, dict):
        if env_override.get("LAW_API_KEY"):
            api_key = env_override["LAW_API_KEY"]
        if env_override.get("LAW_API_URL"):
            api_url = env_override["LAW_API_URL"]
    if not api_key:
        api_key = os.environ.get("LAW_API_KEY", "")
    if api_url == DEFAULT_LAW_API_URL:
        api_url = os.environ.get("LAW_API_URL", DEFAULT_LAW_API_URL)
    return {"LAW_API_KEY": api_key, "LAW_API_URL": api_url}


# === HTTP request with retry + content-type defense ===

def _request_with_retry(
    url: str,
    params: dict,
    max_retries: int = 3,
    timeout: int = 30,
) -> requests.Response:
    last_err: Optional[Exception] = None
    backoff = 1.0
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            # 429 / 5xx → backoff retry
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt < max_retries - 1:
                    logger.warning(
                        "HTTP %d (attempt %d/%d), backoff %.1fs",
                        response.status_code, attempt + 1, max_retries, backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                code = ERROR_RATE_LIMITED if response.status_code == 429 else ERROR_PARSE_FAILED
                raise LawApiError(
                    code,
                    f"HTTP {response.status_code} after {max_retries} retries",
                )
            # 4xx (excl. 429) → no retry
            if 400 <= response.status_code < 500:
                if response.status_code in (401, 403):
                    raise LawApiError(
                        ERROR_AUTH_FAILED,
                        f"HTTP {response.status_code} — LAW_API_KEY 확인 필요",
                    )
                raise LawApiError(
                    ERROR_PARSE_FAILED,
                    f"HTTP {response.status_code} (4xx)",
                )
            return response
        except requests.exceptions.Timeout as e:
            last_err = e
            if attempt < max_retries - 1:
                logger.warning("Timeout (attempt %d/%d), backoff %.1fs", attempt + 1, max_retries, backoff)
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error("Timeout after %d attempts", max_retries)
        except requests.exceptions.ConnectionError as e:
            last_err = e
            if attempt < max_retries - 1:
                logger.warning("ConnectionError (attempt %d/%d), backoff %.1fs", attempt + 1, max_retries, backoff)
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error("ConnectionError after %d attempts", max_retries)
    # SECURITY: last_err를 str()화하면 requests 라이브러리가 URL(OC=<key>)을 포함시킴 → key 누설.
    # type 이름만 사용하여 호출 URL과 query params가 절대 message·log·tool response에 노출되지 않게 함.
    err_type = type(last_err).__name__ if last_err else "Unknown"
    raise LawApiError(ERROR_PARSE_FAILED, f"네트워크 오류 (재시도 {max_retries}회 실패, 종류={err_type})")


def _build_article_content(article_elem: ET.Element) -> str:
    """조문 element의 전체 본문 reconstruct: 조문내용 + 항(항내용 + 호) 합침.

    국가법령정보 OpenAPI 응답 구조:
    - <조문내용>: 짧은 조문(항 없음)은 본문 전체. 다항조문(예: 혁신법 제15조)은 title repeat만 ("제15조(...)").
    - <항>: 각 항이 <항내용>(예: "① ...본문...")과 <호>들(<호내용>="1. ...")을 포함.

    본 헬퍼는 둘을 합쳐 사용자가 read 가능한 단일 본문으로 반환.
    """
    parts: list[str] = []
    intro = (article_elem.findtext("조문내용") or "").strip()
    if intro:
        parts.append(intro)
    for hang in article_elem.findall("항"):
        hang_text = (hang.findtext("항내용") or "").strip()
        if hang_text:
            parts.append(hang_text)
        for ho in hang.findall("호"):
            ho_text = (ho.findtext("호내용") or "").strip()
            if ho_text:
                parts.append("  " + ho_text)  # 2-space indent for visual hierarchy
    return "\n".join(parts)


def _parse_xml(response: requests.Response) -> ET.Element:
    """Parse response as XML. Defend against HTML error pages."""
    content_type = response.headers.get("Content-Type", "").lower()
    body_head = response.text[:200].lstrip().lower()
    if "text/html" in content_type or body_head.startswith("<!doctype html") or body_head.startswith("<html"):
        raise LawApiError(
            ERROR_PARSE_FAILED,
            "응답이 HTML 형식 (에러 페이지로 추정) — endpoint 또는 API 키 확인 필요",
        )
    try:
        return ET.fromstring(response.text)
    except ET.ParseError as e:
        raise LawApiError(ERROR_PARSE_FAILED, f"XML 파싱 실패: {e}") from e


# === LawApiClient ===

class LawApiClient:
    """Stateless-ish client (caches per instance). One per server is enough."""

    def __init__(self, env_override: Optional[dict] = None) -> None:
        creds = get_credentials(env_override)
        self.api_key = creds["LAW_API_KEY"]
        self.base_url = creds["LAW_API_URL"]
        if not self.api_key:
            logger.warning("LAW_API_KEY empty — calls will raise auth_failed")
        # caches: 24h for success, 5min for failure (avoid hammering)
        self._search_cache: TTLCache = TTLCache(maxsize=100, ttl=86400)
        self._detail_cache: TTLCache = TTLCache(maxsize=50, ttl=86400)
        self._failure_cache: TTLCache = TTLCache(maxsize=200, ttl=300)

    def _require_key(self) -> None:
        if not self.api_key:
            raise LawApiError(ERROR_AUTH_FAILED, "LAW_API_KEY가 설정되지 않음")

    def _check_caches(self, cache_key: tuple, success_cache: TTLCache) -> Any:
        if cache_key in self._failure_cache:
            raise self._failure_cache[cache_key]
        if cache_key in success_cache:
            return success_cache[cache_key]
        return None

    def _record_failure(self, cache_key: tuple, err: LawApiError) -> None:
        # do not cache auth_failed (user might fix key) or parse on first attempt
        if err.code not in (ERROR_AUTH_FAILED,):
            self._failure_cache[cache_key] = err

    # --- 법령 검색 ---
    def search_laws(self, query: str, page: int = 1, page_size: int = 10) -> SearchResult:
        self._require_key()
        cache_key = ("search_laws", query, page, page_size)
        cached = self._check_caches(cache_key, self._search_cache)
        if cached is not None:
            return cached
        url = f"{self.base_url}/lawSearch.do"
        params = {
            "OC": self.api_key,
            "target": "law",
            "type": "XML",
            "query": query,
            "display": min(page_size, 50),
            "page": page,
        }
        try:
            response = _request_with_retry(url, params)
            root = _parse_xml(response)
            items = []
            for elem in root.findall(".//law"):
                mst = elem.findtext("법령일련번호", "") or elem.findtext("법령ID", "")
                items.append(DocumentRef(
                    doc_type="law",
                    doc_id=mst,
                    title=elem.findtext("법령명한글", ""),
                    extra={
                        "법령ID": elem.findtext("법령ID", ""),
                        "법령일련번호": elem.findtext("법령일련번호", ""),
                        "법령구분명": elem.findtext("법령구분명", ""),
                        "소관부처명": elem.findtext("소관부처명", ""),
                        "시행일자": elem.findtext("시행일자", ""),
                        "공포일자": elem.findtext("공포일자", ""),
                    },
                ))
            total = int(root.findtext(".//totalCnt", "0") or "0")
            if total == 0 and not items:
                raise LawApiError(ERROR_NOT_FOUND, f"법령 검색 결과 0건: query={query!r}")
            result = SearchResult(total=total, page=page, page_size=page_size, items=items)
            self._search_cache[cache_key] = result
            return result
        except LawApiError as e:
            self._record_failure(cache_key, e)
            raise

    # --- 법령 상세 ---
    def get_law_detail(self, mst: str) -> dict:
        self._require_key()
        cache_key = ("get_law_detail", mst)
        cached = self._check_caches(cache_key, self._detail_cache)
        if cached is not None:
            return cached
        url = f"{self.base_url}/lawService.do"
        params = {"OC": self.api_key, "target": "law", "type": "XML", "MST": mst}
        try:
            response = _request_with_retry(url, params)
            root = _parse_xml(response)
            # lawService.do?target=law 의 응답 schema는 search와 다름:
            #   - 법령명_한글 (underscore!), 법종구분 (구분명 아님), 소관부처 (명 없음)
            #   - 조문 list는 .//조문 wrapper 아래 .//조문단위 49개 형태
            #   - 법령일련번호는 response에 없음 — 호출 param mst를 그대로 사용
            articles = [
                {
                    "조문번호": a.findtext("조문번호", ""),
                    "조문제목": a.findtext("조문제목", ""),
                    # 6차 AI feedback P0: 다항조문은 본문이 <항>·<호>에 있음.
                    # _build_article_content가 조문내용 + 항(항내용 + 호) 모두 합침.
                    "조문내용": _build_article_content(a),
                }
                for a in root.findall(".//조문단위")
            ]
            result = {
                "법령ID": root.findtext(".//법령ID", ""),
                "법령일련번호": mst,
                "법령명한글": root.findtext(".//법령명_한글", ""),
                "법령구분명": root.findtext(".//법종구분", ""),
                "소관부처명": root.findtext(".//소관부처", ""),
                "시행일자": root.findtext(".//시행일자", ""),
                "공포일자": root.findtext(".//공포일자", ""),
                "articles": articles,
            }
            if not articles and not result["법령명한글"]:
                raise LawApiError(ERROR_NOT_FOUND, f"법령 상세 결과 없음: MST={mst}")
            self._detail_cache[cache_key] = result
            return result
        except LawApiError as e:
            self._record_failure(cache_key, e)
            raise

    # --- 행정규칙 상세 ---
    def get_admin_rule_detail(self, admrul_id: str) -> dict:
        """행정규칙 상세 (lawService.do?target=admrul&ID=...).

        조문 + 별표(`별표단위` 안의 별표번호·별표제목·별표내용·별표서식파일링크) 반환.
        Step 17 LIVE 검증: 일부 행정규칙은 조문 0개 + 별표만 30개 구성.
        """
        self._require_key()
        cache_key = ("get_admin_rule_detail", admrul_id)
        cached = self._check_caches(cache_key, self._detail_cache)
        if cached is not None:
            return cached
        url = f"{self.base_url}/lawService.do"
        params = {"OC": self.api_key, "target": "admrul", "type": "XML", "ID": admrul_id}
        try:
            response = _request_with_retry(url, params)
            root = _parse_xml(response)
            # 조문 (있을 수도 없을 수도)
            articles = [
                {
                    "조문번호": a.findtext("조문번호", ""),
                    "조문제목": a.findtext("조문제목", ""),
                    # 6차 AI feedback P0: 다항조문은 본문이 <항>·<호>에 있음.
                    # _build_article_content가 조문내용 + 항(항내용 + 호) 모두 합침.
                    "조문내용": _build_article_content(a),
                }
                for a in root.findall(".//조문단위")
            ]
            # 별표 (Step 17 LIVE 검증: 별표내용 본문 직접 반환됨)
            annexes = [
                {
                    "별표번호": ann.findtext("별표번호", ""),
                    "별표제목": ann.findtext("별표제목", ""),
                    "별표내용": ann.findtext("별표내용", ""),
                    "별표서식파일링크": ann.findtext("별표서식파일링크", ""),
                }
                for ann in root.findall(".//별표단위")
            ]
            result = {
                "행정규칙ID": root.findtext(".//행정규칙ID", ""),
                "행정규칙일련번호": admrul_id,
                "행정규칙명": root.findtext(".//행정규칙명", ""),
                "소관부처명": root.findtext(".//소관부처명", ""),
                "시행일자": root.findtext(".//시행일자", ""),
                "articles": articles,
                "annexes": annexes,
            }
            if not articles and not annexes:
                raise LawApiError(ERROR_NOT_FOUND, f"행정규칙 상세 결과 없음: ID={admrul_id}")
            self._detail_cache[cache_key] = result
            return result
        except LawApiError as e:
            self._record_failure(cache_key, e)
            raise

    # --- 행정규칙 검색 ---
    def search_admin_rules(self, query: str, page: int = 1, page_size: int = 10) -> SearchResult:
        self._require_key()
        cache_key = ("search_admin_rules", query, page, page_size)
        cached = self._check_caches(cache_key, self._search_cache)
        if cached is not None:
            return cached
        url = f"{self.base_url}/lawSearch.do"
        params = {
            "OC": self.api_key,
            "target": "admrul",
            "type": "XML",
            "query": query,
            "display": min(page_size, 50),
            "page": page,
        }
        try:
            response = _request_with_retry(url, params)
            root = _parse_xml(response)
            items = []
            for elem in root.findall(".//admrul"):
                rid = elem.findtext("행정규칙일련번호", "")
                items.append(DocumentRef(
                    doc_type="admrul",
                    doc_id=rid,
                    title=elem.findtext("행정규칙명", ""),
                    extra={
                        "행정규칙일련번호": rid,
                        "행정규칙ID": elem.findtext("행정규칙ID", ""),
                        "소관부처명": elem.findtext("소관부처명", ""),
                        "제정일자": elem.findtext("제정일자", ""),
                        "시행일자": elem.findtext("시행일자", ""),
                    },
                ))
            total = int(root.findtext(".//totalCnt", "0") or "0")
            if total == 0 and not items:
                raise LawApiError(ERROR_NOT_FOUND, f"행정규칙 검색 결과 0건: query={query!r}")
            result = SearchResult(total=total, page=page, page_size=page_size, items=items)
            self._search_cache[cache_key] = result
            return result
        except LawApiError as e:
            self._record_failure(cache_key, e)
            raise
