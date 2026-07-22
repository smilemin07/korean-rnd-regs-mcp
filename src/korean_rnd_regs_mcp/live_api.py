"""국가법령정보 OpenAPI client — generalized from korean-law-mcp/src/tools.py.

See docs/api_contract.md for endpoint mapping, ID conventions, and error codes.
Sync API; wrap with asyncio.to_thread when called from FastMCP tools.
"""
import html
import logging
import os
import re
import threading
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
    """조문 element의 전체 본문 reconstruct: 조문내용 + 항(항내용 + 호(호내용 + 목)) 합침.

    국가법령정보 OpenAPI 응답 구조:
    - <조문내용>: 짧은 조문(항 없음)은 본문 전체. 다항조문(예: 혁신법 제15조)은 title repeat만 ("제15조(...)").
    - <항>: 각 항이 <항내용>(예: "① ...본문...")과 <호>들(<호내용>="1. ...")을 포함.
    - <호>: 일부 호는 <목>들(<목내용>="가.  ...")을 포함 — 실제 기준값이 목에만 있는 경우가 있어
      (예: 인정기준 호내용="다음 각 목의 구분에 따른…" 도입문 + 목별 수치) 목 본문도 content에 포함 (v0.10.1).

    본 헬퍼는 이를 합쳐 사용자가 read 가능한 단일 본문으로 반환 (plain text verbatim).
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
            # v0.10.1: 호 아래 목(目 — 가.나.다.)은 별도 <목내용> element에만 있고 호내용엔 도입문만 들어가는
            # 경우가 있어(LIVE 실측: 시행령 인정기준 등) content에서 누락되던 것을 보강.
            # fault-isolation: findtext + (x or "") + strip + omit — never raise.
            # (get_law_detail의 articles 조립에는 per-article try/except가 없으므로 목 순회가 예외를
            #  던지면 문서 detail 전체가 실패 → 절대 raise하지 않는 형태로만 작성.)
            for mok in ho.findall("목"):
                mok_text = (mok.findtext("목내용") or "").strip()
                if mok_text:
                    parts.append("    " + mok_text)  # 4-space indent (호 하위 계층)
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

    가지조문(제15조의2 등)도 지원 (v0.14.0).
    - 정규식이 가지번호(group 2)를 캡처 → 조문가지번호로 노출. main._article_unit_id가 JO 6자리
      (JO000702 = 제7조의2)로 인코딩해 본조문(제15조)과 collision 없이 조회 가능(가지별표 BP 동형).
    - 예: rnd_funding_standard에 제10조의2/제11조의2/제15조의2/제16조의2/제17조의2 등 8건 LIVE.
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
    first_line = text.split('\n', 1)[0]
    return {
        "조문번호": no,
        "조문가지번호": gaji or "",  # v0.14.0: 가지조문(제N조의M)의 가지 M — 본조문은 ""
        "조문제목": title or "",
        "조문내용": text,
        # 평면 schema는 항·호 hierarchy element가 없음 — paragraphs 빈 list 반환
        # (항·호·목 structured 분해는 별건 백로그 C4 — 가지조문도 content 전문은 반환).
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

# v0.9.1(B2): TTLCache 조회용 sentinel — `key in cache` 후 `cache[key]` 2단계 대신
# `cache.get(key, _CACHE_MISS)` 단일 조회로 TTL 만료 경계의 이론적 KeyError까지 차단.
_CACHE_MISS = object()


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
        self._detail_cache: TTLCache = TTLCache(maxsize=64, ttl=86400)  # v0.4.0: 50→64 — 규정 확대 선제 마진(v0.22.0 현재 N=55<64, warm-hit 보존·headroom 9). N>64 확대 시 warm-hit 무력화 대비 상향 검토
        self._failure_cache: TTLCache = TTLCache(maxsize=200, ttl=300)
        self._id_resolution_cache: TTLCache = TTLCache(maxsize=64, ttl=86400)  # v0.4.0: 50→64 (detail cache와 동상 — 단일 fan-out이 규정당 1엔트리 생성)
        self._id_resolution_failure_cache: TTLCache = TTLCache(maxsize=50, ttl=300)
        # v0.18.0: 신구조문대비표(oldAndNew) 전용 소형 캐시 — opt-in 상세 경로 한정이라 소형으로 충분.
        # _detail_cache(maxsize 64·검색 fan-out warm-hit 상주)와 분리해, 대비표 조회가 detail warm
        # 엔트리를 축출해 cold fan-out latency를 되돌리는 간섭을 원천 차단.
        self._old_and_new_cache: TTLCache = TTLCache(maxsize=16, ttl=86400)
        # v0.9.1(B2): TTLCache 6종은 thread-safe 아님(in/get/[] read도 expire+링크 변경=mutation).
        # B2가 fan-out 동시성을 8→32로 키워 같은 client 캐시에 동시 접근이 늘므로, 캐시 touch를
        # 이 Lock으로 직렬화해 내부 링크 corruption을 막는다. ★Lock은 cache 접근에만 — network
        # (_request_with_retry)·XML 파싱은 절대 lock 밖(그 안에 들어가면 최악 ~82s 점유로 전체
        # 캐시 경로 차단). 현 설계는 nesting 없음 → RLock 불요(plain Lock이라 실수로 network를
        # 감싸면 deadlock으로 fail-loud).
        self._cache_lock = threading.Lock()

    def _require_key(self) -> None:
        if not self.api_key:
            raise LawApiError(
                ERROR_AUTH_FAILED,
                "LAW_API_KEY가 설정되지 않음 — 로컬(stdio)은 .env의 LAW_API_KEY, "
                "원격(HTTP)은 커넥터 URL의 ?oc= 값 설정 확인",
            )

    def _check_caches(self, cache_key: tuple, success_cache: TTLCache) -> Any:
        # v0.9.1(B2): failure/success 두 TTLCache 접근을 한 critical section으로(동시 expire 직렬화).
        # `in`+`[]` 2단계 대신 `.get(key, _CACHE_MISS)` 단일 조회 — TTL 만료 경계의 이론적 KeyError까지
        # 차단(캐시 값은 None일 수 없어 miss는 None 반환으로 표현). network 없음(raise/return도 lock 안).
        with self._cache_lock:
            failed = self._failure_cache.get(cache_key, _CACHE_MISS)
            if failed is not _CACHE_MISS:
                raise failed
            hit = success_cache.get(cache_key, _CACHE_MISS)
            if hit is not _CACHE_MISS:
                return hit
        return None

    def _record_failure(self, cache_key: tuple, err: LawApiError) -> None:
        # do not cache auth_failed (user might fix key) or parse on first attempt
        if err.code not in (ERROR_AUTH_FAILED,):
            with self._cache_lock:  # v0.9.1(B2): 캐시 write 직렬화
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
            with self._cache_lock:  # v0.9.1(B2): 캐시 write 직렬화
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
            # 가지조문(<조문가지번호> 채워진 element, 예: 제7조의2)도 포함 (v0.14.0) — JO 6자리 가지
            # 인코딩(JO000702)으로 본조문(제7조)과 collision 없이 표현(가지별표 BP 6자리 동형). 조문가지번호는
            # main._article_unit_id/_article_branch_no가 (번호,가지) id 생성·매칭에 사용. findtext라 never-raise
            # (articles 조립 comprehension에 per-article try 없음 — 신규 필드도 예외를 던지지 않아야 함).
            articles = [
                {
                    "조문번호": a.findtext("조문번호", ""),
                    "조문가지번호": a.findtext("조문가지번호", ""),  # v0.14.0: 가지조문 (번호,가지) 인코딩용
                    "조문제목": a.findtext("조문제목", ""),
                    # 다항조문은 본문이 <항>·<호>에 있음.
                    # _build_article_content가 조문내용 + 항(항내용 + 호) 모두 합침.
                    "조문내용": _build_article_content(a),
                    # v0.15.0: 조문참고자료 — 대괄호 개정 이력 마커([본조신설 날짜]·[전문개정 날짜]·
                    # [제목개정 날짜]·[종전 …으로 이동 <날짜>] 등)의 유일 위치. content 꺾쇠 마커와 병용해
                    # main._article_amendment_history가 조문별 최신 공포일(개정 발견성)을 도출한다. ★신설 조문
                    # (제N조의M)은 content 마커가 없고 이 태그에만 [본조신설 …]이 있어(GT5) 캡처 필수.
                    # findtext라 never-raise (articles 조립 comprehension에 per-article try 없음 — 조문가지번호와 동일).
                    "조문참고자료": a.findtext("조문참고자료", ""),
                    # machine-readable nested hierarchy (LLM 재포맷 방어).
                    "structured": _build_article_structure(a),
                }
                for a in root.findall(".//조문단위")
                if (a.findtext("조문여부") or "").strip() == "조문"
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
                # v0.17.0: 개정 전/후 대조(redline) 최소형 — 이미 받아오지만 버리던 개정문 필드 캡처(추가 네트워크 0).
                # <개정문내용> = 최신 개정분의 개정지시문 산문("제N조 중 'A'를 'B'로 한다" 식 실질 delta),
                # <제개정구분> = "일부개정"/"제정"/"타법개정" 등. 문서레벨 get_provision_detail(law)에서 amendment_text·
                # amendment_kind로 additive 노출(main._attach_amendment_meta). findtext라 never-raise(검색 fan-out
                # 공유 경로 안전 — 이 필드는 search가 소비하지 않아 blast radius 0). LIVE census: 단일 element·자식 0·
                # HTML 이스케이프 0(unescape 불요)·개정문내용에 별지 서식 이미지 참조 <img> 태그가 포함될 수 있음(verbatim 유지).
                "개정문내용": root.findtext(".//개정문내용", ""),
                "제개정구분": root.findtext(".//제개정구분", ""),
                "articles": articles,
                "annexes": annexes,
                "annex_parse_error": annex_parse_error,
            }
            if not articles and not result["법령명한글"]:
                raise LawApiError(ERROR_NOT_FOUND, f"법령 상세 결과 없음: MST={mst}")
            with self._cache_lock:  # v0.9.1(B2): 캐시 write 직렬화
                self._detail_cache[cache_key] = result
            return result
        except LawApiError as e:
            self._record_failure(cache_key, e)
            raise

    # --- 신구조문대비표 (v0.18.0) ---
    def get_old_and_new(self, mst: str) -> dict:
        """법령 신구조문대비표(oldAndNew) 조회 — 개정 전/후 조문 원문 2열 대조 (law 전용).

        ★lawService만 사용: lawSearch.do?target=oldAndNew(검색 변형)는 응답 행의 신구법상세링크
        필드에 OC 인증키 원문이 포함되어 반환됨(2026-07-14 LIVE 실측) — 어떤 이유로도 사용 금지.
        lawService(상세) 응답에는 링크 필드가 없어 안전.

        LIVE 실측(2026-07-14·manifest law 29건 전수 sweep):
        - root <OldAndNewService> = 구조문_기본정보/신조문_기본정보(공포일자·공포번호·시행일자·
          현행여부 등) + 구조문목록/신조문목록(<조문 no="N"> 평면 행 나열·양측 행 수 항상 동일
          13/13…135/135 → no 순번 정렬 2열 표). 행 단위는 조문이 아니라 표 행(조문 헤더·항·호
          혼재)이며 조문별 그룹핑은 하지 않는다(v0.18.0 최소형 — "제N조" 접두 재구성은 파서
          위험·scope 증가로 기각, /disc 3-AI 합의). 변경 구간은 텍스트 내 이스케이프된 <P> 마커,
          무변경부는 "(생  략)"/"(현행과 같음)" 축약, 신설 행은 "<신  설>" placeholder — verbatim 유지.
        - 대비표 부재 시 <신구법존재여부>N + 목록 부재(HTTP 200 유지) — 결정론 판별 신호.
          ★부재 ≠ 무개정(일부개정인데 부재 2건 실측: 286879·262117). 제개정구분으로 존재를 예측하지 말 것.
        - diff 기준은 "직전 공포 연혁 vs 해당 MST"(현행 대비 아님) — 구조문이 미시행 분리시행분일 수
          있음(혁신법 283849 실측: 구조문=283413·시행 20260820 미도래). 기본정보를 그대로 반환해
          호출부(main)가 데이터 앵커로 노출하게 한다.
        - admrul 미지원("일치하는 신구법 없습니다") — law 게이트는 호출부(main) 책임.
        반환: {"available": bool[, "old"/"new": 기본정보 dict(Korean key), "old_rows"/"new_rows": [str]]}.
        """
        self._require_key()
        cache_key = ("get_old_and_new", mst)
        cached = self._check_caches(cache_key, self._old_and_new_cache)
        if cached is not None:
            return cached
        url = f"{self.base_url}/lawService.do"
        params = {"OC": self.api_key, "target": "oldAndNew", "type": "XML", "MST": mst}
        try:
            response = _request_with_retry(url, params)
            if not (response.text or "").strip():
                # LIVE 프로브 중 1회 관측된 HTTP 200 + 빈 body — 1회만 재조회(그래도 비면 _parse_xml이
                # parse_failed로 표면화). opt-in 경로라 재조회 1회의 latency 추가는 수용 범위.
                response = _request_with_retry(url, params)
            root = _parse_xml(response)
            old_list = root.find(".//구조문목록")
            new_list = root.find(".//신조문목록")
            exists_flag = (root.findtext(".//신구법존재여부") or "").strip()
            if exists_flag == "N" or old_list is None or new_list is None:
                result: dict = {"available": False}
            else:
                def _basic_info(tag: str) -> dict:
                    el = root.find(f".//{tag}")

                    def _get(name: str) -> str:
                        return (el.findtext(name) or "").strip() if el is not None else ""

                    return {
                        "법령일련번호": _get("법령일련번호"),
                        "공포일자": _get("공포일자"),
                        "공포번호": _get("공포번호"),
                        "시행일자": _get("시행일자"),
                        "현행여부": _get("현행여부"),
                    }

                def _rows(parent: ET.Element) -> list[str]:
                    # no 속성은 실측 전건 1..N 순번이나 방어적으로: 전건 유효 정수일 때만 no 정렬,
                    # 아니면 문서 순서 유지(행 순서가 곧 표 순서). isascii 가드는 상위첨자 '²'
                    # (isdigit=True) 함정 회피 — 조문번호 처리(main)와 동일 방침.
                    # 양측 no 시퀀스 교차 대조는 하지 않음(의도적 최소형): no는 표 행 인덱스라
                    # 정렬 후 positional pairing이 곧 표 의미론이고, 한쪽 행 결손은 행 수 차이로
                    # 표면화되어 main의 min-zip + row_count_mismatch가 방어(LIVE 실측 전건 동수).
                    entries = []
                    for row in parent.findall("조문"):
                        no_raw = (row.get("no") or "").strip()
                        no = int(no_raw) if (no_raw.isascii() and no_raw.isdigit()) else None
                        entries.append((no, (row.text or "").strip()))
                    if entries and all(no is not None for no, _ in entries):
                        entries.sort(key=lambda x: x[0])
                    return [text for _, text in entries]

                result = {
                    "available": True,
                    "old": _basic_info("구조문_기본정보"),
                    "new": _basic_info("신조문_기본정보"),
                    "old_rows": _rows(old_list),
                    "new_rows": _rows(new_list),
                }
            with self._cache_lock:  # v0.9.1(B2): 캐시 write 직렬화
                self._old_and_new_cache[cache_key] = result
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
            # 조문 (있을 수도 없을 수도). wrapper(장/절/관) element는 제외; 가지조문(조문가지번호)은
            # v0.14.0부터 포함(JO 6자리 가지 인코딩·법령 파서와 동일). 조문가지번호 findtext는 never-raise.
            articles = [
                {
                    "조문번호": a.findtext("조문번호", ""),
                    "조문가지번호": a.findtext("조문가지번호", ""),  # v0.14.0: 가지조문 (번호,가지) 인코딩용
                    "조문제목": a.findtext("조문제목", ""),
                    # 다항조문은 본문이 <항>·<호>에 있음.
                    # _build_article_content가 조문내용 + 항(항내용 + 호) 모두 합침.
                    "조문내용": _build_article_content(a),
                    # v0.15.0: 조문참고자료(law 파서와 동일) — 중첩 schema admrul은 현 manifest 0건이나
                    # 스키마 정합 위해 캡처(findtext never-raise). 평면 admrul은 이 태그·꺾쇠 마커 모두 없어
                    # (GT6) 개정 이력 필드가 자연히 부재 → main 헬퍼가 .get()로 graceful 처리.
                    "조문참고자료": a.findtext("조문참고자료", ""),
                    # machine-readable nested hierarchy (LLM 재포맷 방어).
                    "structured": _build_article_structure(a),
                }
                for a in root.findall(".//조문단위")
                if (a.findtext("조문여부") or "").strip() == "조문"
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
                # v0.19.0: admrul redline 확장 — law(get_law_detail)와 동일하게 <개정문내용> 캡처.
                # LIVE 전수(2026-07-15·admrul 23건): 존재 15/부재 8(부재=태그 자체 부재라 "" — 결정론)·
                # 전건 <개정문> wrapper 아래 단일 text node(root 직속 아님 → .//필수)·복수 출현 0·
                # 최대 3,836자·HTML 이스케이프/<img> 0. ★부재≠무개정(연구개발비 사용 기준이 일부개정인데
                # 부재 — 소비 가이드는 프롬프트 표면). findtext never-raise(검색 fan-out 공유 경로 안전 —
                # search는 이 필드를 소비하지 않아 blast radius 0).
                "개정문내용": root.findtext(".//개정문내용", ""),
                # v0.19.0: ★admrul XML엔 law의 <제개정구분> 태그가 없음(LIVE 23건 전건) — <제개정구분명>
                # (값 "일부개정" 18/"제정" 4/"전부개정" 1·전건 존재)을 law와 같은 "제개정구분" 키로 정규화
                # 저장해 main._attach_amendment_meta를 무변경 재사용. 동반 <제개정구분코드>는 소비 가치
                # 없어 미캡처(스코프 최소화).
                "제개정구분": (root.findtext(".//제개정구분명") or "").strip(),
                "articles": articles,
                "annexes": annexes,
            }
            if not articles and not annexes:
                raise LawApiError(ERROR_NOT_FOUND, f"행정규칙 상세 결과 없음: ID={admrul_id}")
            with self._cache_lock:  # v0.9.1(B2): 캐시 write 직렬화
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
        # v0.9.1(B2): id-resolution 캐시 직접 get 2건을 한 critical section으로(_check_caches 미경유).
        with self._cache_lock:
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
            with self._cache_lock:  # v0.9.1(B2): 캐시 write 직렬화
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
        with self._cache_lock:  # v0.9.1(B2): 캐시 write 직렬화
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
            with self._cache_lock:  # v0.9.1(B2): 캐시 write 직렬화
                self._search_cache[cache_key] = result
            return result
        except LawApiError as e:
            self._record_failure(cache_key, e)
            raise
