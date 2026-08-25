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
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
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

# === v0.55.0: 시행일 기준 조회(eflaw) 전용 대기 예산 ===
# eflaw는 1차 시도이고 실패하면 곧바로 law 폴백이 직렬로 이어지므로, 기본 예산(8,12)·2회를 그대로
# 물려받으면 규정당 대기가 두 배가 되어 fan-out 예산(main._FANOUT_BUDGET_S=20s)을 깬다.
# 결정론 시뮬레이션(32워커·66과제·폴백 3s 가정, 2026-08-25): (3,5)=최악 22.1s로 예산 초과 /
# (2,4)=최악 18.1s로 예산 내. 정상 eflaw p90은 1,145ms 실측이라 read 4s 상한의 오탐 여지는 사실상 없다
# (read는 총 시간이 아니라 "바이트가 도착하지 않는 구간"의 상한이므로 대형 문서도 흐르는 한 끊기지 않는다).
_EFLAW_TIMEOUT = (2.0, 4.0)
# ★_request_with_retry(max_retries=N)의 N은 "재시도 횟수"가 아니라 `range(N)` = 실제 시도 횟수다.
#   0을 넘기면 네트워크 요청이 한 번도 발생하지 않는다(구현 diff 적대검토 Codex 적발 — 제로콜 버그).
#   "재시도 없음"의 올바른 표현은 1이다.
_EFLAW_ATTEMPTS = 1


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
    """Dynamic ID resolution result — search-first 패턴으로 최신 문서 ID를 확인한 결과.

    v0.37.0: 시행일이 미래인 검색 행은 현행 선택에서 제외된다(미시행 본문을 현행처럼
    제공하던 결함 해소 — 2026-08-06 정보처리기준 2100000283100 라이브 실측). 제외된 행 중
    가장 이른 예정 판본은 pending_* 필드로 보존해 응답 고지에 사용한다.
    """
    doc_id: str
    effective_date: str       # ISO format "2026-03-11" or raw "20260311"
    is_updated: bool          # True if doc_id differs from manifest_doc_id
    manifest_doc_id: str
    pending_doc_id: str = ""          # (v0.37.0) 미래 시행 예정 판본 ID — 없으면 ""
    pending_effective_date: str = ""  # (v0.37.0) 예정 판본 시행일 ISO — 없으면 ""
    resolve_failed: bool = False      # (v0.37.0) True = 검색 실패/일치 0행으로 manifest fallback


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

# v0.48.0 (B3): thread-local keep-alive Session — LIVE HTTP 연결 재사용.
# 종전에는 매 호출 bare requests.get이 새 TCP+TLS 연결을 열었다(requests.get은 내부적으로
# 호출마다 임시 Session 생성·폐기). law.go.kr은 Connection: Keep-Alive를 지원하고(실측
# 2026-08-11), fan-out 전용 executor(main._FANOUT_EXECUTOR) 스레드는 장수하므로 스레드당
# Session 1개로 연결을 재사용한다(실측 호출당 약 105ms 절감).
# 안전 불변식(계획 /disc 3-AI 수렴 — 위반 시 bare 의미론이 깨진다):
# - lazy 생성: import·부팅·health 경로에서 Session·소켓을 만들지 않는다(outage 비의존).
# - 쿠키는 매 최상위 호출 직전·직후 비운다 — bare requests.get[호출마다 빈 쿠키 시작]과
#   요청 동일성 유지. 리다이렉트 체인 내부 쿠키는 허용되고, 호출 간(사용자 oc 간) 이월만
#   차단된다.
# - Session 속성에 키·params·headers를 저장하지 않는다(멀티테넌트) — 매 호출 인자로만 전달.
# - trust_env·adapter retry·pool sizing은 requests 기본값 그대로 둔다(의미론 변경 금지).
# - RequestException 시 해당 스레드 Session을 폐기(_discard_thread_session)해 stale
#   keep-alive·오염된 연결 풀을 다음 attempt에서 새 연결로 격리한다.
_thread_http = threading.local()


def _http_get(url: str, params: dict, timeout: tuple[float, float]) -> requests.Response:
    """HTTP GET 단일 seam — thread-local Session 재사용. 단위테스트는 이 함수를 patch한다.

    쿠키 격리는 fail-closed(diff 적대검토 Codex MINOR 반영): clear()가 실패하면 그 Session을
    폐기하고 빈 쿠키의 새 Session으로 진행한다 — "사용자(oc) 간 상태 이월 차단" 불변식이
    clear 실패 시에도 유지된다(새 Session은 항상 빈 jar로 시작).
    """
    sess = getattr(_thread_http, "session", None)
    if sess is not None:
        try:
            sess.cookies.clear()
        except Exception:
            # 격리 보장 불가 → fail-closed: 폐기하고 아래에서 새 Session(빈 jar) 생성
            _discard_thread_session()
            sess = None
    if sess is None:
        try:
            sess = requests.Session()
        except Exception:
            # Session 생성 실패(이론 경계) — 이번 attempt만 bare 호출로 폴백
            return requests.get(url, params=params, timeout=timeout)
        _thread_http.session = sess
    try:
        return sess.get(url, params=params, timeout=timeout)
    finally:
        try:
            sess.cookies.clear()
        except Exception:
            # 사후 비움 실패도 fail-closed — 다음 호출이 빈 jar의 새 Session으로 시작하게 폐기
            _discard_thread_session()


def _discard_thread_session() -> None:
    """현재 스레드의 Session 폐기 — 전송 오류 후 stale keep-alive·풀 오염 격리용(never-raise)."""
    sess = getattr(_thread_http, "session", None)
    if sess is None:
        return
    _thread_http.session = None
    try:
        sess.close()
    except Exception:
        pass


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
            response = _http_get(url, params, timeout)
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
            # (v0.48.0 B3) 전송 오류가 난 Session은 폐기 — stale keep-alive 연결·오염 풀이
            # 다음 attempt(또는 다음 호출)로 이어지지 않게 새 연결로 격리한다.
            _discard_thread_session()
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
        self._detail_cache: TTLCache = TTLCache(maxsize=96, ttl=86400)  # v0.24.0: 64→96 — N=60(국방 2차) 등록으로 headroom 4로 축소되던 것을 상향(fan-out 1회=60엔트리 점유·BP/JO 상세 조회의 warm 엔트리 축출 방지, headroom 36). 이력: v0.4.0 50→64. ★N>96 확대 시 재상향 검토
        self._failure_cache: TTLCache = TTLCache(maxsize=200, ttl=300)
        self._id_resolution_cache: TTLCache = TTLCache(maxsize=96, ttl=86400)  # v0.24.0: 64→96 (detail cache와 동상 — 단일 fan-out이 규정당 1엔트리 생성)
        self._id_resolution_failure_cache: TTLCache = TTLCache(maxsize=50, ttl=300)
        # v0.18.0: 신구조문대비표(oldAndNew) 전용 소형 캐시 — opt-in 상세 경로 한정이라 소형으로 충분.
        # _detail_cache(maxsize 96·검색 fan-out warm-hit 상주)와 분리해, 대비표 조회가 detail warm
        # 엔트리를 축출해 cold fan-out latency를 되돌리는 간섭을 원천 차단.
        self._old_and_new_cache: TTLCache = TTLCache(maxsize=16, ttl=86400)
        # v0.55.0: eflaw 전용 캐시 2종.
        # - _eflaw_failure_cache: eflaw 실패 기억(서킷 브레이커). 기존 _failure_cache와 물리 분리한다 —
        #   _check_caches는 실패 키를 발견하면 즉시 raise하므로 같은 캐시를 쓰면 law 폴백 경로 자체가
        #   차단된다(구현 diff 적대검토 지적). eflaw 성공 본문은 키가 disjoint하므로 _detail_cache 공유.
        # - _law_fallback_cache: eflaw 실패 시 대신 제공한 공포 합본 본문. 24h _detail_cache에 넣으면
        #   열화 본문이 하루 고착되므로 실패 기억과 같은 TTL(300s)로 함께 만료시킨다.
        self._eflaw_failure_cache: TTLCache = TTLCache(maxsize=48, ttl=300)
        self._law_fallback_cache: TTLCache = TTLCache(maxsize=40, ttl=300)
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
    def _law_detail_request(
        self,
        mst: str,
        target: str = "law",
        efyd: str = "",
        timeout: tuple[float, float] = _REQUEST_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
    ) -> dict:
        """lawService 상세 1회 조회+파싱 — 캐시 무관 (v0.55.0에서 get_law_detail 본문을 그대로 추출).

        target="eflaw"는 efyd(YYYYMMDD)가 그 MST의 실제 시행 단계와 짝이 맞을 때만 본문을 반환하고,
        어긋나면 HTTP 200 + 빈 <Law/>(126B)를 돌려준다(2026-08-25 실측). 아래 not_found 가드가 그
        빈 응답을 잡으므로 호출자는 예외로 일관되게 처리할 수 있다.

        캐시 접근을 이 함수에서 분리한 이유: eflaw 실패 시의 law 폴백이 24h _detail_cache를 읽지도
        쓰지도 않아야 하기 때문이다(열화 본문 24h 고착 차단 — 구현 diff 적대검토 조건).
        """
        response = _request_with_retry(
            f"{self.base_url}/lawService.do",
            {"OC": self.api_key, "target": target, "type": "XML", "MST": mst,
             **({"efYd": efyd} if efyd else {})},
            max_retries=max_retries,
            timeout=timeout,
        )
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
        return result

    def get_law_detail(self, mst: str) -> dict:
        """법령 상세 (공포 합본, target=law) — 종전 동작 그대로. 성공 24h·실패 300s 캐시."""
        self._require_key()
        cache_key = ("get_law_detail", mst)
        cached = self._check_caches(cache_key, self._detail_cache)
        if cached is not None:
            return cached
        try:
            result = self._law_detail_request(mst)
        except LawApiError as e:
            self._record_failure(cache_key, e)
            raise
        with self._cache_lock:  # v0.9.1(B2): 캐시 write 직렬화
            self._detail_cache[cache_key] = result
        return result

    @staticmethod
    def normalize_efyd(effective_date: str) -> str:
        """표시용 시행일(YYYY-MM-DD)을 efYd 파라미터 형식(YYYYMMDD)으로 정규화. 부적합하면 ""."""
        d = (effective_date or "").strip().replace("-", "")
        return d if len(d) == 8 and d.isdigit() else ""

    def _eflaw_success(self, key: tuple) -> dict | None:
        with self._cache_lock:
            hit = self._detail_cache.get(key, _CACHE_MISS)
        return None if hit is _CACHE_MISS else hit

    def _eflaw_breaker_open(self, key: tuple) -> bool:
        """직전 eflaw 실패가 아직 기억에 남아 있는가(=네트워크 없이 폴백할 것인가)."""
        with self._cache_lock:
            return self._eflaw_failure_cache.get(key) is not None

    def _eflaw_store_success(self, key: tuple, result: dict) -> None:
        """성공 저장 + 상충 실패 기억 제거를 한 critical section에서(경합 시 성공 우선)."""
        with self._cache_lock:
            self._detail_cache[key] = result
            self._eflaw_failure_cache.pop(key, None)

    def _eflaw_store_failure(self, key: tuple, err: LawApiError) -> None:
        """실패 기록 직전 성공을 재확인 — 동시 요청의 성공을 실패가 덮지 못하게 한다."""
        with self._cache_lock:
            if self._detail_cache.get(key, _CACHE_MISS) is not _CACHE_MISS:
                return
            self._eflaw_failure_cache[key] = err

    def get_law_detail_staged(
        self, mst: str, efyd: str = "", expected_title: str = ""
    ) -> tuple[dict, str]:
        """(v0.55.0) 시행일 기준 본문 우선 조회 + 공포 합본 폴백. 반환 = (detail, stage_basis).

        stage_basis 의미(원인별로 정확히 하나):
          - "eflaw"        : 유효 efyd로 조회해 4중 판정을 모두 통과한 시행 본문
          - "law_fallback" : 유효 efyd로 시도했으나 실패해 공포 합본으로 대체
          - "law"          : efyd 부재(resolve 실패 등)로 eflaw를 아예 시도하지 않음 = 종전 경로

        ★stage_basis는 캐시된 dict에 쓰지 않고 별도 값으로 반환한다 — 같은 dict가 여러 경로로
        공유되므로 본문에 출처를 부착하면 호출 순서·스레드 경합에 따라 오염된다(적대검토 조건).
        ★인증 실패(auth_failed)는 폴백하지 않고 즉시 전파한다 — 같은 키로 law를 다시 불러도 동일하게
        실패하므로 요청만 2배가 된다.

        ★캐시 적중에도 _verify_eflaw를 다시 돌린다(네트워크 0 — 순수 필드 비교뿐). expected_title은
        캐시 키(mst, efyd)에 포함되지 않으므로, 재검증이 없으면 제목 미지정으로 적재된 본문이 이후
        다른 제목의 호출에 그대로 통과한다(최종 재검증 라운드에서 결정론 프로브로 재현·수정).
        """
        self._require_key()
        efyd = self.normalize_efyd(efyd)
        if not efyd:
            return self.get_law_detail(mst), "law"

        key = ("get_law_detail", "eflaw", mst, efyd)
        hit = self._eflaw_success(key)
        if hit is not None:
            # ★캐시 적중에도 4중 판정을 다시 돌린다(네트워크 0 — 순수 필드 비교뿐).
            #   expected_title은 캐시 키에 없으므로, 재검증이 없으면 다른 규정 제목으로 들어온 호출이
            #   캐시된 본문을 그대로 통과시킨다(구현 diff 적대검토에서 결정론 프로브로 재현).
            #   불일치면 eflaw를 재시도하지 않고 곧장 폴백한다 — 재시도해도 같은 본문이 와서
            #   브레이커만 오염시키기 때문이다.
            try:
                self._verify_eflaw(hit, mst, efyd, expected_title)
                return hit, "eflaw"
            except LawApiError:
                logger.info("eflaw 캐시 본문이 요청과 불일치 → 공포 합본 폴백: MST=%s", mst)
                return self._fallback_preferring_eflaw(mst, key, efyd, expected_title)

        if not self._eflaw_breaker_open(key):
            try:
                result = self._law_detail_request(
                    mst, target="eflaw", efyd=efyd,
                    timeout=_EFLAW_TIMEOUT, max_retries=_EFLAW_ATTEMPTS,
                )
                self._verify_eflaw(result, mst, efyd, expected_title)
                self._eflaw_store_success(key, result)
                return result, "eflaw"
            except LawApiError as e:
                if e.code == ERROR_AUTH_FAILED:
                    raise
                logger.info("eflaw 조회 실패 → 공포 합본 폴백: MST=%s code=%s", mst, e.code)
                self._eflaw_store_failure(key, e)

        return self._fallback_preferring_eflaw(mst, key, efyd, expected_title)

    def _eflaw_hit_verified(self, key: tuple, mst: str, efyd: str, expected_title: str) -> dict | None:
        """검증 통과한 eflaw 성공 캐시 본문 — 없거나 요청과 불일치하면 None(never-raise)."""
        hit = self._eflaw_success(key)
        if hit is None:
            return None
        try:
            self._verify_eflaw(hit, mst, efyd, expected_title)
            return hit
        except LawApiError:
            return None

    def _fallback_preferring_eflaw(
        self, mst: str, key: tuple, efyd: str, expected_title: str
    ) -> tuple[dict, str]:
        """폴백을 수행하되, 그 사이 성립한 eflaw 성공이 있으면 항상 그것을 우선한다.

        ★최종 재검증 라운드에서 재현된 두 경합을 함께 닫는다: (a) 성공이 성립했는데 폴백 본문이
        나가는 창 (b) 폴백까지 실패해 성공이 캐시에 있는데도 오류가 반환되는 창. 폴백 반환·오류
        전파 직전에 각각 성공을 재확인한다. 재확인 본문도 4중 판정을 거친다(경로 단일화 —
        "캐시에서 나온 본문은 항상 재검증" 원칙).
        """
        try:
            result, basis = self._law_fallback(mst)
        except LawApiError:
            hit = self._eflaw_hit_verified(key, mst, efyd, expected_title)
            if hit is not None:
                return hit, "eflaw"
            raise
        hit = self._eflaw_hit_verified(key, mst, efyd, expected_title)
        if hit is not None:
            return hit, "eflaw"
        return result, basis

    def _law_fallback(self, mst: str) -> tuple[dict, str]:
        """공포 합본 폴백 — 24h _detail_cache에 **쓰지 않는** 별도 경로(열화 본문 고착 차단).

        ★읽기는 한다(최종 재검증 라운드 Codex 공격으로 정정): 유효한 24h law 성공 본문이 살아 있는데
        그것을 무시하고 네트워크를 타면, 실패 시 공유 실패 기억이 그 성공 캐시를 가려 efyd-부재
        경로(get_law_detail — 실패를 성공보다 먼저 검사)까지 5분간 오류가 된다. 성공 본문의 내용은
        폴백이 반환하려는 공포 합본과 동일하므로 읽기는 무해하고, 성공이 있으면 실패가 기록될 일
        자체가 없어져 "실패 기록은 성공-미스 상태에서만"이라는 종전 불변식이 복원된다.

        ★실패 기억(_failure_cache·300s)은 종전 get_law_detail과 공유한다 — 공유하지 않으면 상위 API
        전면 장애 시 매 호출이 재시도 전량(최악 41s)을 다시 태워 outage를 증폭한다. 기록 직전에
        락 안에서 law 성공을 재확인해, 경합으로 성립한 성공을 실패가 가리지 못하게 한다.
        """
        fb_key = ("law_fallback", mst)
        law_key = ("get_law_detail", mst)
        with self._cache_lock:
            cached_fb = self._law_fallback_cache.get(fb_key, _CACHE_MISS)
            law_hit = self._detail_cache.get(law_key, _CACHE_MISS)
            law_failed = self._failure_cache.get(law_key, _CACHE_MISS)
        if cached_fb is not _CACHE_MISS:
            return cached_fb, "law_fallback"
        if law_hit is not _CACHE_MISS:
            return law_hit, "law_fallback"
        if law_failed is not _CACHE_MISS:
            raise law_failed
        try:
            result = self._law_detail_request(mst)
        except LawApiError as e:
            with self._cache_lock:
                law_hit = self._detail_cache.get(law_key, _CACHE_MISS)
                if law_hit is _CACHE_MISS and e.code not in (ERROR_AUTH_FAILED,):
                    self._failure_cache[law_key] = e
            if law_hit is not _CACHE_MISS:
                return law_hit, "law_fallback"
            raise
        with self._cache_lock:
            self._law_fallback_cache[fb_key] = result
        return result, "law_fallback"

    def _verify_eflaw(self, result: dict, mst: str, efyd: str, expected_title: str) -> None:
        """eflaw 성공 4중 판정 — 하나라도 어긋나면 LawApiError로 폴백을 유발한다.

        ①조문 ≥ 1 ②법령명 비공백 ③법령명이 요청 규정과 일치 ④응답 시행일자 == 요청 efyd.
        ③은 "다른 법령인데 시행일만 같은" 응답이 통과하는 구멍을 막는다(적대검토 지적). manifest 제목이
        비어 있으면(호출자 미지정) 이 조건만 건너뛴다 — 나머지 3중은 항상 적용.
        ④는 감사 스크립트의 efyd_provenance_mismatch 가드와 동형이며, 우리가 요청한 시행 단계의
        본문임을 응답 스스로 증명하게 한다.
        """
        if not result.get("articles"):
            raise LawApiError(ERROR_NOT_FOUND, f"eflaw 조문 0건: MST={mst} efYd={efyd}")
        title = (result.get("법령명한글") or "").strip()
        if not title:
            raise LawApiError(ERROR_NOT_FOUND, f"eflaw 법령명 없음: MST={mst} efYd={efyd}")
        if expected_title and self._normalize_title(title) != self._normalize_title(expected_title):
            raise LawApiError(ERROR_NOT_FOUND, f"eflaw 법령 불일치: MST={mst} efYd={efyd}")
        served = (result.get("시행일자") or "").strip().replace("-", "")
        if served != efyd:
            raise LawApiError(ERROR_NOT_FOUND, f"eflaw 시행일자 불일치: MST={mst} efYd={efyd} 응답={served}")


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

    @staticmethod
    def _today_kst() -> str:
        """오늘 날짜(KST) — YYYYMMDD. 시행일 도래 판정은 한국 법령 기준이므로 서버 TZ와 무관하게 KST 고정.

        (v0.37.0) 주의: resolve 결과는 TTL 캐시(24h)를 타므로 시행일 도래 직후 최대 캐시 TTL만큼
        직전 판정이 유지될 수 있다(수용 — 경계 정밀화는 과설계로 배제).
        """
        return datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")

    @staticmethod
    def _is_future_date(raw_date: str, today: str) -> bool:
        """검색 행 시행일자가 미래인지 판정. 방어 정규화(공백·하이픈 제거 — diff 적대검토 반영:
        상류 포맷 변형 시 필터 무력화 방지) 후 8자리 숫자 형식일 때만 판정하고, 그 외 형식 이상은
        미래로 단정하지 않는다(기존 현행 후보 거동 보존 — 과필터로 인한 가용성 저하 방지).
        당일 시행(== today)은 현행이다."""
        d = (raw_date or "").strip().replace("-", "")
        return len(d) == 8 and d.isdigit() and d > today

    @classmethod
    def _resolution_due(cls, resolved: ResolvedDocId, today: str | None = None) -> bool:
        """예정 판본의 시행일이 도래했는가 — 도래했으면 resolve 성공 캐시를 만료로 취급한다(never-raise).

        왜 필요한가: resolve 성공 캐시는 TTL 24h이고 client가 OC 키별로 분리돼 있어, 시행 전환일 0시가
        지나도 사용자마다 최대 24시간 동안 어제 판본이 서빙된다. 이번 릴리스의 표적인 2026-09-11
        전환이 하루 늦게 반영되는 것을 막는다.

        재평가 폭풍이 없는 이유: 재판정 시점에 그 행은 더 이상 미래가 아니므로(_is_future_date는
        today 초과만 미래로 본다) best 후보로 선택되고, pending에는 그 다음 예정일만 남는다.
        즉 새 결과는 due가 아니어서 정상적으로 24h 캐시된다(2026-09-11 → 다음 pending 2027-01-01).
        """
        try:
            raw = (resolved.pending_effective_date or "").strip().replace("-", "")
            if len(raw) != 8 or not raw.isdigit():
                return False
            return raw <= (today or cls._today_kst())
        except Exception:  # pragma: no cover - 방어선(판정 실패가 resolve 경로를 막지 않게)
            return False

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
            if cached is not None and self._resolution_due(cached):
                # (v0.55.0) 예정 판본의 시행일이 도래 — "무시"가 아니라 성공·실패 기억을 실제로 제거하고
                # 즉시 재판정한다. 무시만 하면 due 엔트리가 남아 매 호출 재평가가 반복된다(적대검토 조건).
                self._id_resolution_cache.pop(cache_key, None)
                self._id_resolution_failure_cache.pop(cache_key, None)
                cached = cached_fail = None
            else:
                cached_fail = self._id_resolution_failure_cache.get(cache_key)
            if cached is not None:
                return cached
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
            failed = replace(fallback, resolve_failed=True)  # (v0.37.0) silent fallback 해소 — 발동 사실 보존
            with self._cache_lock:  # v0.9.1(B2): 캐시 write 직렬화
                self._id_resolution_failure_cache[cache_key] = failed
            return failed

        norm_title = self._normalize_title(title)
        today = self._today_kst()
        best: ResolvedDocId | None = None
        pending_raw = ""   # (v0.37.0) 미래 시행 행 중 가장 이른 시행일자(raw 8자리)
        pending_id = ""
        for item in sr.items:
            if self._normalize_title(item.title) != norm_title:
                continue
            if not self._ministry_matches(ministry, item.extra.get("소관부처명", "")):
                continue
            raw_date = item.extra.get("시행일자", "")
            if self._is_future_date(raw_date, today):
                # (v0.37.0) 미시행 판본은 현행 선택 대상에서 제외 — 가장 이른 예정만 고지용으로 보존
                if not pending_raw or raw_date < pending_raw:
                    pending_raw, pending_id = raw_date, item.doc_id
                continue
            resolved = ResolvedDocId(
                doc_id=item.doc_id,
                effective_date=self._format_date(raw_date),
                is_updated=(item.doc_id != manifest_doc_id),
                manifest_doc_id=manifest_doc_id,
            )
            if best is None or raw_date > (best.effective_date.replace("-", "") if best else ""):
                best = resolved

        if best is None:
            # 일치 행이 전부 미래이거나 0건 — manifest fallback. 미래 행만 있던 경우는 resolve 실패가
            # 아니라 "현행 = manifest 스냅샷" 판정이므로 resolve_failed는 일치 0행일 때만 True.
            result = replace(fallback, resolve_failed=(not pending_raw))
        else:
            result = best
        if pending_raw:
            result = replace(
                result,
                pending_doc_id=pending_id,
                pending_effective_date=self._format_date(pending_raw),
            )
        if result.resolve_failed:
            # (v0.37.0 diff 적대검토 MAJOR 반영) 일치 0행 fallback은 검색 예외와 같은 실패 클래스 —
            # 24h 성공 캐시에 고착시키지 않고 단기 failure cache(TTL 300s)로 저장해 재확인을 연다.
            # 한계: 하위 _search_cache(24h)가 같은 검색 응답을 재공급하면 무매치가 그 TTL 내 반복될 수
            # 있음(계약 §5.28 문서화 — 검색 캐시 계층 변경은 본 릴리스 범위 밖).
            with self._cache_lock:
                self._id_resolution_failure_cache[cache_key] = result
            return result
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
