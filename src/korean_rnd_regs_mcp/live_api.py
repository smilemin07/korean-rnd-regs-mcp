"""국가법령정보 OpenAPI client — generalized from korean-law-mcp/src/tools.py.

See docs/api_contract.md for endpoint mapping, ID conventions, and error codes.
Sync API; wrap with asyncio.to_thread when called from FastMCP tools.
"""
import html
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from cachetools import TTLCache

from .provision_id import CONTRACT_VERSION

# 평면 schema(root 직속 <조문내용>) 행정규칙 파싱용 정규식.
# "제N조[의M](제목) 본문..." 패턴. LIVE 검증: 동시수행 과제 수 제한, 연구노트 지침, 연구개발비 사용 기준 등.
# 제목 내부 괄호 대응 위해 `.+?` lazy match 사용 (단순 `[^)]*`는
# "(중소기업(A) 기준)" 같은 중첩 괄호에서 매칭 끊김). 괄호 자체는 필수 — 장/절/관 wrapper
# ("제1장 총칙" 등) 자동 제외 효과 유지.
_FLAT_ARTICLE_PATTERN = re.compile(r'제(\d+)조(?:의(\d+))?\s*\((.+?)\)\s*(.*)', re.DOTALL)

logger = logging.getLogger("rnd-regs-mcp.live_api")

DEFAULT_LAW_API_URL = "https://www.law.go.kr/DRF"

# Standard error codes (docs/api_contract.md §4)
ERROR_AUTH_FAILED = "auth_failed"
ERROR_RATE_LIMITED = "rate_limited"
ERROR_PARSE_FAILED = "parse_failed"
ERROR_NOT_FOUND = "not_found"

# === 외부 OpenAPI 대기 상한 (v0.2.7: 구동 안정성 강화 — 외부 API 대기 상한 보수화) ===
# requests timeout을 (connect, read) 튜플로 분리해 read 단계를 보수적으로 bound한다.
# 종전 정수 30s는 connect·read *각 단계*에 30s를 허용 → 단일 to_thread 호출이 최악 ~30s 점유 +
# 재시도 폭주로 worst-case 스레드 점유가 과대(186s/task)했다. read 12s로 낮추고 max_retries를
# 3→2로 줄여 worst-case를 ~82s/task로 보수화(2회 × ~20s wall + backoff 1s).
# 부등식 정합: _READ_TIMEOUT_S(12) < main._FANOUT_BUDGET_S(20) < 커넥터 타임아웃 — read 단계가
# 끊겨도 fan-out 예산 안에서 흡수된다. fan-out 예산은 *응답*만 풀고 진행 중인 to_thread blocking은
# 못 끊으므로, 실제 blocking 상한은 이 timeout만이 보장한다.
_CONNECT_TIMEOUT_S = 8.0
_READ_TIMEOUT_S = 12.0
_REQUEST_TIMEOUT = (_CONNECT_TIMEOUT_S, _READ_TIMEOUT_S)
_MAX_RETRIES = 2


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
class ResolvedDocId:
    """Dynamic ID resolution result — search-first 패턴으로 최신 문서 ID를 확인한 결과."""
    doc_id: str
    effective_date: str       # ISO format "2026-03-11" or raw "20260311"
    is_updated: bool          # True if doc_id differs from manifest_doc_id
    manifest_doc_id: str


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
    max_retries: int = _MAX_RETRIES,
    timeout: tuple[float, float] = _REQUEST_TIMEOUT,
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
                        f"HTTP {response.status_code} — LAW_API_KEY 확인 필요. "
                        "원격(HTTP) 사용 시 커넥터 URL의 ?oc= 값이 올바른지 확인",
                    )
                raise LawApiError(
                    ERROR_PARSE_FAILED,
                    f"HTTP {response.status_code} (4xx)",
                )
            return response
        except requests.exceptions.RequestException as e:
            # Timeout/ConnectionError 외 SSLError·ChunkedEncodingError·
            # InvalidURL 등도 catch — 누수 시 호출 URL(OC=<key>)가 trace에 노출되는 것을 차단.
            # type 이름만 logger·재시도 message에 사용하여 e 본문 누출 방지.
            last_err = e
            err_type = type(e).__name__
            if attempt < max_retries - 1:
                logger.warning("%s (attempt %d/%d), backoff %.1fs", err_type, attempt + 1, max_retries, backoff)
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error("%s after %d attempts", err_type, max_retries)
    # SECURITY: last_err를 str()화하면 requests 라이브러리가 URL(OC=<key>)을 포함시킴 → key 누설.
    # type 이름만 사용하여 호출 URL과 query params가 절대 message·log·tool response에 노출되지 않게 함.
    err_type = type(last_err).__name__ if last_err else "Unknown"
    raise LawApiError(ERROR_PARSE_FAILED, f"네트워크 오류 (재시도 {max_retries}회 실패, 종류={err_type})")


def _build_article_content(article_elem: ET.Element) -> str:
    """조문 element의 전체 본문 reconstruct: 조문내용 + 항(항내용 + 호) 합침.

    국가법령정보 OpenAPI 응답 구조:
    - <조문내용>: 짧은 조문(항 없음)은 본문 전체. 다항조문(예: 혁신법 제15조)은 title repeat만 ("제15조(...)").
    - <항>: 각 항이 <항내용>(예: "① ...본문...")과 <호>들(<호내용>="1. ...")을 포함.

    본 헬퍼는 둘을 합쳐 사용자가 read 가능한 단일 본문으로 반환 (plain text verbatim).
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


def _build_subparagraph(ho_elem: ET.Element) -> dict:
    """호 element를 number·text·source_text dict로 변환.

    XML의 <호번호>("1.")와 <호내용>("1.  본문...")을 분리하여 외부 사용자가
    번호와 본문을 따로 처리할 수 있게 함. source_text는 원문 보존.
    """
    number = (ho_elem.findtext("호번호") or "").strip()
    source_text = (ho_elem.findtext("호내용") or "").strip()
    # 호내용은 number prefix를 포함하므로(예: "1.  본문..."), text에서는 제거
    if number and source_text.startswith(number):
        text = source_text[len(number):].lstrip()
    else:
        text = source_text
    return {"number": number, "text": text, "source_text": source_text}


def _build_paragraph(hang_elem: ET.Element) -> dict:
    """항 element를 number·text·source_text·subparagraphs dict로 변환."""
    number = (hang_elem.findtext("항번호") or "").strip()
    source_text = (hang_elem.findtext("항내용") or "").strip()
    if number and source_text.startswith(number):
        text = source_text[len(number):].lstrip()
    else:
        text = source_text
    return {
        "number": number,
        "text": text,
        "source_text": source_text,
        "subparagraphs": [_build_subparagraph(ho) for ho in hang_elem.findall("호")],
    }


def _build_article_structure(article_elem: ET.Element) -> dict:
    """조문 element를 machine-readable nested hierarchy로 변환.

    plain text content와 같은 데이터를 외부 사용자 코드가 파싱 없이 활용 가능한 형태.
    chat LLM이 임의로 재포맷하는 risk 방어 (원문 hierarchy를 명시).
    """
    return {
        "title": (article_elem.findtext("조문내용") or "").strip(),  # "제N조(제목)" 형태
        "paragraphs": [_build_paragraph(h) for h in article_elem.findall("항")],
    }


def _parse_flat_article(elem: ET.Element) -> Optional[dict]:
    """평면 schema(root 직속 <조문내용>) 행정규칙 한 element를 article dict로 변환.

    일부 행정규칙(예: 동시수행 과제 수 제한, 연구노트 지침, 연구개발비 사용 기준)은 `<조문단위>`
    wrapper 없이 `<조문내용>` element가 root 직속으로 평면 배치됨. 이 schema를 fallback으로 지원.

    가지조문(제15조의2 등) silent skip.
    - 현행 provision_id의 JO unit_id는 숫자만 지원 — 조문 가지번호 표현 불가(가지별표 BP는 v0.2.1 지원)
    - 정규식이 가지조문 매칭하면 본 조문(제15조)과 동일 조문번호=15로 collision 발생
    - 예: rnd_funding_standard에 제10조의2/제11조의2/제15조의2/제16조의2/제17조의2 등 8건 LIVE 발견
    - skip + logger.warning으로 누락 통지. v0.3 JO prefix 확장 시 자동 활성화 예정.
    """
    text = (elem.text or "").strip()
    if not text:
        return None
    m = _FLAT_ARTICLE_PATTERN.match(text)
    if not m:
        # wrapper element("제1장 총칙", "제1절 사용용도" 등) 또는 매칭 실패 — silent skip 정상
        # 매칭 실패 진단을 위해 head만 debug log (사용자 응답에는 노출 안 됨)
        if text and text.startswith("제") and "조" in text[:20]:
            logger.debug("flat schema parse miss: head=%s...", text[:80])
        return None
    no, gaji, title, _body = m.groups()
    if gaji:
        # 가지조문 — JO 가지번호 미지원(현행 contract 동일), skip하여 collision 방지
        logger.warning(
            "flat schema: 가지조문 제%s조의%s(%s) skip — JO 가지번호 미지원 (v0.3 prefix 확장 예정)",
            no, gaji, title,
        )
        return None
    first_line = text.split('\n', 1)[0]
    return {
        "조문번호": no,
        "조문제목": title or "",
        "조문내용": text,
        # 평면 schema는 항·호 hierarchy element가 없음 — paragraphs 빈 list 반환
        "structured": {"title": first_line, "paragraphs": []},
    }


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
        self._detail_cache: TTLCache = TTLCache(maxsize=64, ttl=86400)  # v0.4.0: 50→64 — 규정 확대 선제 마진(v0.8.0 현재 N=39<64, warm-hit 보존). N>50 확대 시 50이면 warm-hit 무력화 대비
        self._failure_cache: TTLCache = TTLCache(maxsize=200, ttl=300)
        self._id_resolution_cache: TTLCache = TTLCache(maxsize=64, ttl=86400)  # v0.4.0: 50→64 (detail cache와 동상 — 단일 fan-out이 규정당 1엔트리 생성)
        self._id_resolution_failure_cache: TTLCache = TTLCache(maxsize=50, ttl=300)

    def _require_key(self) -> None:
        if not self.api_key:
            raise LawApiError(
                ERROR_AUTH_FAILED,
                "LAW_API_KEY가 설정되지 않음 — 로컬(stdio)은 .env의 LAW_API_KEY, "
                "원격(HTTP)은 커넥터 URL의 ?oc= 값 설정 확인",
            )

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
            # LIVE 검증: <조문여부>=전문 element는 장/절/관 wrapper(예: "제1장 총칙")로
            # 실제 조문이 아님. 동일 조문번호로 wrapper + 실제 조문이 함께 등장하여 (혁신법·시행령 7건 collision)
            # JO0001 검색·상세조회 시 wrapper만 반환되는 silent bug 발생. 조문여부="조문"만 articles에 포함.
            # 가지조문(<조문가지번호> 채워진 element)도 skip — 현행 contract에서도
            # JO unit_id가 숫자만 지원하므로 가지조문은 본 조문과 collision (예: 제15조 ↔ 제15조의2).
            articles = [
                {
                    "조문번호": a.findtext("조문번호", ""),
                    "조문제목": a.findtext("조문제목", ""),
                    # 다항조문은 본문이 <항>·<호>에 있음.
                    # _build_article_content가 조문내용 + 항(항내용 + 호) 모두 합침.
                    "조문내용": _build_article_content(a),
                    # machine-readable nested hierarchy (LLM 재포맷 방어).
                    "structured": _build_article_structure(a),
                }
                for a in root.findall(".//조문단위")
                if (a.findtext("조문여부") or "").strip() == "조문"
                and not (a.findtext("조문가지번호") or "").strip()
            ]
            # 별표 (v0.2): 법령(시행령) 별표 inline 텍스트 지원. fault-isolation —
            # 별표 파싱 실패가 조문(articles) 반환 경로를 깨뜨리지 않도록 독립 try/except로 격리하고,
            # 실패는 버리지 않고 annex_parse_error로 표면화한다 (get_admin_rule_detail의 별표 schema와 동일).
            annexes: list[dict] = []
            annex_parse_error: str | None = None
            try:
                annexes = [
                    {
                        "별표번호": ann.findtext("별표번호", ""),
                        # v0.2.1: 가지별표(별표 N의M)·별지/서식 구분 — BP id 충돌(오도달) 해소의 전제.
                        "별표가지번호": ann.findtext("별표가지번호", ""),
                        "별표구분": ann.findtext("별표구분", ""),
                        # v0.2.1: 소스가 CDATA 안에 사전 이스케이프 텍스트를 담는 경우가 있어
                        # (예: 삭제 별표 제목 '삭제 &lt;2016.1.22.&gt;') 제목만 단일 관문에서 unescape.
                        # 본문·조문은 LIVE 실측상 실문자라 적용하지 않음 (이중 unescape 방지).
                        "별표제목": html.unescape(ann.findtext("별표제목", "")),
                        "별표내용": ann.findtext("별표내용", ""),
                        "별표서식파일링크": ann.findtext("별표서식파일링크", ""),
                    }
                    for ann in root.findall(".//별표단위")
                ]
            except Exception as exc:  # noqa: BLE001 — 별표 파싱 실패가 조문 반환을 막지 않게
                annex_parse_error = type(exc).__name__
                logger.warning("get_law_detail: MST=%s 별표 파싱 실패: %s", mst, annex_parse_error)
                annexes = []
            result = {
                "법령ID": root.findtext(".//법령ID", ""),
                "법령일련번호": mst,
                "법령명한글": root.findtext(".//법령명_한글", ""),
                "법령구분명": root.findtext(".//법종구분", ""),
                "소관부처명": root.findtext(".//소관부처", ""),
                "시행일자": root.findtext(".//시행일자", ""),
                "공포일자": root.findtext(".//공포일자", ""),
                "articles": articles,
                "annexes": annexes,
                "annex_parse_error": annex_parse_error,
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
        LIVE 검증: 일부 행정규칙은 조문 0개 + 별표만 30개 구성.
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
            # 조문 (있을 수도 없을 수도). 8차/wrapper element + 가지조문 동일 filter 적용.
            articles = [
                {
                    "조문번호": a.findtext("조문번호", ""),
                    "조문제목": a.findtext("조문제목", ""),
                    # 다항조문은 본문이 <항>·<호>에 있음.
                    # _build_article_content가 조문내용 + 항(항내용 + 호) 모두 합침.
                    "조문내용": _build_article_content(a),
                    # machine-readable nested hierarchy (LLM 재포맷 방어).
                    "structured": _build_article_structure(a),
                }
                for a in root.findall(".//조문단위")
                if (a.findtext("조문여부") or "").strip() == "조문"
                and not (a.findtext("조문가지번호") or "").strip()
            ]
            # 평면 schema fallback: 일부 행정규칙은 <조문단위> 없이 root 직속 <조문내용> 사용.
            # LIVE 검증: 동시수행 과제 수 제한(ID 2100000196149), 연구노트 지침(ID 2100000207982).
            if not articles:
                articles = [
                    parsed
                    for elem in root.findall("./조문내용")
                    if (parsed := _parse_flat_article(elem)) is not None
                ]
            # 별표 (LIVE 검증: 별표내용 본문 직접 반환됨)
            annexes = [
                {
                    "별표번호": ann.findtext("별표번호", ""),
                    # v0.2.1: 가지별표·별지/서식 구분 + 제목 unescape — law 파서와 동일 (단일 관문)
                    "별표가지번호": ann.findtext("별표가지번호", ""),
                    "별표구분": ann.findtext("별표구분", ""),
                    "별표제목": html.unescape(ann.findtext("별표제목", "")),
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
                # v0.5.0: 발령번호·행정규칙종류 — <행정규칙기본정보> 안에 nested/flat 무관 항상 존재
                # (LIVE 19건 실측). findtext+strip만 — 누락 시 "" (예외 없음·검색 fan-out 공유 안전).
                "발령번호": (root.findtext(".//발령번호") or "").strip(),
                "행정규칙종류": (root.findtext(".//행정규칙종류") or "").strip(),
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

    # --- 최신 문서 ID 동적 해석 (search-first 패턴) ---
    @staticmethod
    def _normalize_title(title: str) -> str:
        t = re.sub(r'\s+', '', title)
        t = t.replace('ㆍ', '·')  # HANGUL LETTER ARAEA → MIDDLE DOT
        return t

    @staticmethod
    def _format_date(raw: str) -> str:
        raw = (raw or "").strip()
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return raw

    @staticmethod
    def _ministry_matches(want: str, got: str) -> bool:
        """검색 행 소관부처명(콤마로 구분된 다부처 가능)에 want가 정확일치로 포함되는지.

        substring 매칭 금지("환경부" ⊂ "기후에너지환경부" 오탐 차단). want가 빈 값이면 True(필터 미적용).
        """
        want = (want or "").strip()
        if not want:
            return True
        candidates = [p.strip() for p in (got or "").split(",")]
        return want in candidates

    def resolve_latest_doc_id(
        self,
        title: str,
        api_target: str,
        manifest_doc_id: str,
        ministry: str | None = None,
    ) -> ResolvedDocId:
        """manifest title로 검색하여 최신 문서 ID를 반환. 실패 시 manifest ID fallback.

        ministry가 지정되면 검색 행의 소관부처명을 ','로 분리한 목록에 ministry가 정확일치로 포함된
        행만 후보로 삼는다(동명 타부처 규정 오집 방지). 일치 행이 없으면 manifest fallback(가용성 유지).
        """
        cache_key = ("resolve", api_target, title, ministry or "")
        cached = self._id_resolution_cache.get(cache_key)
        if cached is not None:
            return cached
        cached_fail = self._id_resolution_failure_cache.get(cache_key)
        if cached_fail is not None:
            return cached_fail

        fallback = ResolvedDocId(
            doc_id=manifest_doc_id,
            effective_date="",
            is_updated=False,
            manifest_doc_id=manifest_doc_id,
        )
        try:
            if api_target == "law":
                sr = self.search_laws(title, page_size=5)
            else:
                sr = self.search_admin_rules(title, page_size=5)
        except LawApiError:
            logger.warning("resolve_latest_doc_id: search 실패, manifest ID fallback (target=%s)", api_target)
            self._id_resolution_failure_cache[cache_key] = fallback
            return fallback

        norm_title = self._normalize_title(title)
        best: ResolvedDocId | None = None
        for item in sr.items:
            if self._normalize_title(item.title) != norm_title:
                continue
            if not self._ministry_matches(ministry, item.extra.get("소관부처명", "")):
                continue
            raw_date = item.extra.get("시행일자", "")
            resolved = ResolvedDocId(
                doc_id=item.doc_id,
                effective_date=self._format_date(raw_date),
                is_updated=(item.doc_id != manifest_doc_id),
                manifest_doc_id=manifest_doc_id,
            )
            if best is None or raw_date > (best.effective_date.replace("-", "") if best else ""):
                best = resolved

        result = best if best is not None else fallback
        if result.is_updated:
            logger.info(
                "resolve_latest_doc_id: %s updated %s -> %s (시행일 %s)",
                title, manifest_doc_id, result.doc_id, result.effective_date,
            )
        self._id_resolution_cache[cache_key] = result
        return result

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
