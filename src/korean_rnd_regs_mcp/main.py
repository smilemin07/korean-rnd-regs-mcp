"""korean-rnd-regs-mcp main entry — stdio / HTTP MCP server."""
import argparse
import asyncio
import contextvars
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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
    unit_label,
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

# v0.2.9: 서버 레벨 instructions — 호스트가 규정 질의에 일반 학습지식으로 단정하지 말고
# 본 서버 도구를 먼저 호출하도록 유도(MCP initialize 응답 payload에 실림). 과호출은 비싸므로
# ("본 서버 범위" fan-out cold 5.5~9.7s) 적용 범위를 한정하고 WHEN-NOT 절을 명시.
# 검색·랭킹·응답 schema·실행 로직 불변(메타데이터 텍스트만 — contract 0.6.0 유지).
# 주의: FastMCP 2번째 positional 인자가 instructions이므로 version은 반드시 keyword로 전달.
_SERVER_INSTRUCTIONS = (
    "본 서버는 대한민국 국가연구개발사업 및 부처별 R&D 연구행정 규정"
    "(국가연구개발혁신법·시행령·시행규칙, 부처별 R&D 법령, 연구개발비 사용기준·기술료·보안·성과평가 등 행정규칙) "
    "검토 전용입니다. 사용자가 법령·규정·조문·연구개발비·협약변경·기술료·성과관리·연구보안 등 본 서버 범위의 "
    "사실 확인이나 검토를 요청하면, '폭넓게 알려줘'처럼 표현이 넓더라도 일반 학습지식으로 답하지 말고 "
    "먼저 suggest_review_sources 또는 search_provision을 호출하고, 인용할 근거는 get_provision_detail로 "
    "원문을 확인하십시오. 단순 인사·순수 번역·문장 다듬기·코딩 질문·해외 제도만의 설명 등 "
    "본 서버 범위 밖 질문에는 호출하지 마십시오. "
    "현재 대화에 규정 도구가 보이지 않거나 호출에 실패하여 질문의 근거를 확인할 수 없으면, "
    "일반 학습지식으로 규정의 수치·요건·결론을 단정하지 말고 도구 미가용 사실을 밝힌 뒤 "
    "새 대화에서 다시 시도하거나 stdio 클라이언트(Claude Desktop·Claude Code 등)에서 재조회하도록 안내하십시오. "
    "도구 호출 결과 질문 대상이 지원 49개 규정 밖이면 본 서버 근거로 확인되지 않았음을 밝히고, "
    "답변을 덧붙일 경우 일반 학습지식에 따른 설명임을 명시하되 고시번호·시행일·조문 번호·금액·비율·기한 등 "
    "변동 가능한 구체값을 현행 사실로 단정하지 말며, 현행 식별자와 원문은 1차 출처(국가법령정보센터 등)에서 확인하도록 안내하십시오. "
    "한편 지원 범위 내 규정의 조문·별표 본문은 임의의 외부 웹검색이나 law.go.kr 직접 열람으로 대체하지 말고 "
    "get_provision_detail의 content로 확인하되(content_format이 plain_text_verbatim이 아니면 응답이 제공한 공식 원문 링크를 확인), "
    "응답에 없는 고시·예규 번호는 현행으로 단정하지 마십시오. "
    "행정규칙(고시·예규·훈령)의 발령번호·종류는 get_provision_detail 응답의 "
    "issuance_number·regulation_kind·version_label 필드로 확인하되, 이 값은 조회된 규정의 것이며 현행임을 보증하지 않습니다"
    "(검색 실패 시 등록(manifest) 버전일 수 있고 개정 안내가 없어도 현행이라는 뜻은 아니므로, 현행 여부 단정이 필요하면 1차 출처에서 확인). "
    "MCP에 등록되었거나 list_rule_sets·search_provision으로 검색·조회된 규정을 외부 검색에서 찾지 못했다는 이유만으로 "
    "존재하지 않는다고 단정하지 말고 get_provision_detail 결과와 응답이 제공한 공식 URL로 확인하십시오."
)

mcp = FastMCP("korean-rnd-regs-mcp", instructions=_SERVER_INSTRUCTIONS, version=__version__)

_DISCLAIMER = "본 결과는 검토 후보일 뿐 법률 판단이 아닙니다. 출처를 직접 확인하세요."
_SNIPPET_MAX = 2000
_SEARCH_RESPONSE_CHAR_BUDGET = 16000  # v0.2.5: search_provision 전체 응답 직렬화 예산 (25k token 한도의 보수 proxy — suggest와 동일 사상)
_RESULTS_MAX = 30
# v0.2.6: search_provision 전건 fan-out 응답 시간 예산(초). 한 규정의 detail fetch가 hang/재시도
# 폭주로 전체 질의를 커넥터 타임아웃까지 끄는 것을 차단 — 예산 초과 규정은 graceful skip하여 errors로
# 표면화하고 완료분으로 응답(부분 응답 > 전체 타임아웃). 정상 cold(전건 완료)는 이 예산 한참 아래라 무영향.
# 대형 규정(ICT 관리규정 139k 등) 확대로 cold tail 증가에 대한 안전 가드.
# v0.2.7(구동 안정성 강화): live_api의 외부 API 대기 상한을 (connect 8s, read 12s) + max_retries 2로
# 보수화. 부등식 정합: read 12s < _FANOUT_BUDGET_S 20s < 커넥터 타임아웃 — read 단계가 끊겨도 fan-out
# 예산 안에서 흡수된다. 단일 규정 worst-case 스레드 점유 ≈ 82s(2회 × ~20s wall + backoff 1s, 종전 186s).
# 주의: fan-out 예산은 *응답*만 풀고 진행 중인 to_thread blocking은 못 끊으므로 실제 blocking 상한은
# live_api timeout만이 보장 — 예산값(20)은 유지하고 timeout만 보수화한 이유.
_FANOUT_BUDGET_S = 20.0

# v0.2.10(관측성): fan-out 개별 규정 지연이 이 값(ms) 이상이면 search_fanout_summary의
# slow_rule_count로 집계한다 — B2(전용 executor) 풀 크기 N 산정용 tail 휴리스틱.
# 주의: 예산 초과로 cancel된 규정의 실제 스레드 완료 시간은 미포함(완료 task 기준 집계).
# 동작·응답 schema 무영향(서버 측 로그 지표일 뿐).
_SLOW_RULE_MS = 3000.0


class _FanoutSkipped:
    """search_provision fan-out 응답 예산 초과로 조회를 생략한 규정의 sentinel(v0.2.6)."""
_SUGGEST_KEYWORDS_MAX = 10  # suggest_review_sources: 클라이언트(LLM) 제공 키워드 사용 상한
_FALLBACK_KEYWORDS_MAX = 10  # suggest fallback: 규칙추출 키워드 상한 (v0.1.7: 등장순 뒤 핵심어 보존; 제목우선 랭킹이 노이즈 키워드 중화)
_SUGGEST_CANDIDATES_MAX = 15  # suggest_review_sources: 반환 후보 개수 상한 (토큰 한도 회피)
_SUGGEST_SNIPPET_MAX = 300   # suggest_review_sources: 반환 후보 snippet 단축 길이 (포인터 도구)
_OVERFLOW_CANDIDATES_MAX = 30  # suggest overflow_candidates: cap 밖 조문 노출 최대 건수 (v0.1.8)
# overflow_candidates 추가 시 전체 응답 직렬화가 넘지 않도록 하는 char 상한 (overflow 추가분에 대한 게이트).
# MCP 도구 응답 token hard limit(25,000) 회피용 보수 proxy — 서버에 tokenizer가 없어 char로 강제하며,
# 한국어 char↔token 비율 불확실분을 흡수하려 보수치(16k) 사용. base 응답(candidates 등) 우선 — base가
# 단독으로 이 값을 넘으면 overflow는 비움(전체를 16k로 줄이지는 않음; question echo 등 base는 v0.1.7과
# 동일하게 무제한). 라이브 4경로 스모크로 실측 검증.
_SUGGEST_RESPONSE_CHAR_BUDGET = 16000
# v0.1.9: keyword_source가 fallback/client+fallback이거나 무키워드(early-return)일 때 응답 note에 넣는
# 명령형 degraded 신호. 답변 품질이 keyword_source 품질에 크게 좌우되므로, 서버 표면추출로 대체된
# 경우 호스트가 법령 절차·개념어를 추론해 keywords로 "재호출"하도록 강하게 유도한다.
# M2 soft-gate: candidates는 그대로 반환(보류 없음) — outage·빈손·루프 위험 0. gate는 신호일 뿐.
# 세 문구 모두 공통 재호출 지시(_RECALL_DIRECTIVE)와 마커 "[degraded]"를 포함(테스트 불변식).
_RECALL_DIRECTIVE = (
    "이 상황에 적용될 법령상 절차·개념어(예: 사전 승인·협약 변경·연구개발과제협약·이관 등)를 "
    "추론하여 keywords 배열로 suggest_review_sources를 다시 호출하십시오"
)
_DEGRADED_NOTE_FALLBACK = (
    "[degraded] keywords 없이 질문 표면에서 자동 추출한 키워드로 검색했습니다 — 이 사안의 핵심 "
    "절차·근거 조문이 누락됐을 가능성이 높습니다. 답변을 생성하기 전에, " + _RECALL_DIRECTIVE +
    "(아래 candidates는 재호출 전 임시 참고용입니다)."
)
_DEGRADED_NOTE_EMPTY = (
    "[degraded] keywords 없이 질문 표면에서 자동 추출한 키워드로는 관련 조문을 찾지 못했습니다. "
    + _RECALL_DIRECTIVE + "."
)
_DEGRADED_NOTE_CLIENT_FB = (
    "[degraded] 제공된 keywords로는 매칭 결과가 없어 질문 표면 추출 키워드로 대체 검색했습니다 — "
    "더 넓거나 정식 법령 용어의 keywords가 필요합니다. 답변을 생성하기 전에, " + _RECALL_DIRECTIVE +
    "(아래 candidates는 재호출 전 임시 참고용입니다)."
)
_LAW_GO_KR_BASE = "https://www.law.go.kr"
_VERBATIM_INSTRUCTIONS = (
    "본 응답의 content / article_structure는 국가법령정보 OpenAPI에서 직접 받은 법령 원문을 "
    "재구성한 것입니다 (plain text verbatim). 사용자에게 표시할 때 다음 정책을 엄격히 준수: "
    "(1) 임의 부제·요약·paraphrase 추가 금지 — 원문에 없는 '(중앙행정기관 직권 변경·중단)' 같은 "
    "헤더 발명 금지. (2) 항(①②③) 번호와 호(1./2./3.) 번호 prefix를 stripping 금지. "
    "(3) 줄바꿈·들여쓰기를 유지. (4) 항·호 hierarchy는 article_structure 필드로 machine-readable "
    "제공되므로 LLM이 직접 reformat할 필요 없음. 법령 검토의 정확성 훼손 방지를 위해 verbatim 인용."
)
# v0.6.0: 대용량 조문에서 article_structure가 응답 예산을 넘겨 생략될 때의 정확성 안내(구조 미참조 변형).
_VERBATIM_INSTRUCTIONS_NO_STRUCTURE = (
    "본 응답의 content는 국가법령정보 OpenAPI에서 직접 받은 법령 원문입니다 (plain text verbatim). "
    "사용자에게 표시할 때 다음 정책을 엄격히 준수: (1) 임의 부제·요약·paraphrase 추가 금지. "
    "(2) 항(①②③) 번호와 호(1./2./3.) 번호 prefix를 stripping 금지. (3) 줄바꿈·들여쓰기를 유지. "
    "(article_structure는 응답 한도 때문에 생략됐으나 content 본문이 전문이므로 그대로 인용하면 됩니다.)"
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
    # v0.1.6: 노이즈 토큰 추가 (검토 대상 식별에 무의미한 일반어)
    "일부", "다른", "해당", "여부", "위해", "통해",
    # v0.1.7: fallback 질문 필러 추가 (안전망 품질 — 등장 앞순서를 점유하던 노이즈 제거)
    "참여", "중인", "중이다", "올해", "그에", "구성", "싶다", "따라야", "알려달라", "억원",
})
# 흔한 한국어 조사 (긴 것부터 정렬 — endswith 매칭 우선순위)
# 1글자 조사 중 "이/가/에/도/만/로"는 명사 끝 음절에 자주 등장(false positive risk) → strip 안 함.
# "을/를/은/는/과/와"는 strip. 예: "특별평가" + "가" 조사 strip로 "특별평" 되는 버그 방지.
# v0.1.6: 속격 "의"를 추가 — 단, _strip_particle의 len-guard(잔여 ≥2자)로 짧은 명사는 보호.
#   "정의"(2자) → 2-1=1 < 2 이므로 strip 안 함(보존). "주관연구개발기관의"(9자) → "주관연구개발기관".
_PARTICLES = (
    "에서는", "에서도", "으로는", "에게는",
    "에서", "으로", "에게", "한테", "까지", "부터", "조차", "마저",
    "와의", "과의",
    "을", "를", "은", "는", "과", "와", "의",
)
# 주의: 끝 "의" strip은 속격(규정의→규정·개발의→개발) 정리에 net-positive지만, "사전심의"(심의)·
#   "본회의"(회의)처럼 명사 일부 "의"인 복합어는 prefix로 잘린다("사전심"). 2자 "X의" 예외목록 방식은
#   "규정의/개발의/조문의" 같은 핵심 속격을 오보존해 net-negative라 채택 안 함(검증 완료). 형태소
#   분석 없이는 양립 불가 — 명사-의 복합어 보존은 v0.2 과제. 현재는 속격 정리 이득을 우선해 전부 strip.


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


# v0.1.6 (Pillar B): R&D 도메인 동의어/표기변형 — 작고 큐레이션된 1-hop 사전.
# 같은 개념을 부처·법령마다 다른 용어로 쓰는 경우(예: 현장용어 "정출금" vs 혁신법 "정부지원연구개발비"
# vs 육성법·운영규정 "출연금")를 사용자 키워드 1개로 union 검색하기 위함.
# 설계 원칙(과설계·노이즈 방지): 재귀 확장 금지(1-hop), 광범위 절차어(승인/보고/변경/신청 등)는
# 동의어로 만들지 않고 토큰 AND 매칭(search_provision)으로 처리하여 precision을 보호한다.
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"정출금", "정부지원연구개발비", "출연금", "정부출연금"}),
    frozenset({"기관부담연구개발비", "기관부담금"}),
    # 원문은 "협약의 변경/협약을 변경" — 붙임/띄움 표기차 흡수(토큰 AND와 병행)
    frozenset({"협약변경", "협약 변경"}),
    frozenset({"사전승인", "사전 승인"}),
)

# term -> 같은 그룹의 나머지 term들 (1-hop)
_SYNONYM_LOOKUP: dict[str, tuple[str, ...]] = {}
for _grp in _SYNONYM_GROUPS:
    for _t in _grp:
        _SYNONYM_LOOKUP[_t] = tuple(x for x in _grp if x != _t)

# v0.2.1: 단방향 현장어 alias — alias 입력 시에만 정식어로 확장(역방향 미확장).
# 현장어 3종은 corpus-dead(LIVE 검색 0건, 2026-06-10 실측)라 검색 term 가치가 0 —
# 양방향 그룹에 넣으면 정식어 입력 시 dead term이 _SUGGEST_SEARCH_TERMS_MAX(16) 슬롯만
# 소비하므로 단방향으로 격리 (R2 적대검증 2/3 합의). 명사 표기변형만(절차어 금지 원칙 동일).
_SYNONYM_ALIASES: dict[str, tuple[str, ...]] = {
    "정부출연연구비": ("정부지원연구개발비", "출연금", "정부출연금"),
    "정출연연구비": ("정부지원연구개발비", "출연금", "정부출연금"),
    "출연연구비": ("정부지원연구개발비", "출연금", "정부출연금"),
}
for _a, _ts in _SYNONYM_ALIASES.items():
    # 기존 양방향 멤버와 충돌 시 덮어쓰기 방지 — 기존 확장을 보존하고 alias 확장을 병합(dedupe)
    _SYNONYM_LOOKUP[_a] = tuple(dict.fromkeys((*_SYNONYM_LOOKUP.get(_a, ()), *_ts)))

# 동의어 확장 후 실제 검색할 term 총 상한 (호출·latency 폭증 방지).
# search_provision의 17 rule set 상세조회는 doc 단위 24h 캐시라 동일 요청 내 추가 term은
# 네트워크 호출 없이 in-memory 재스캔이지만, term 폭증 자체를 보수적으로 cap.
_SUGGEST_SEARCH_TERMS_MAX = 16


def _build_search_terms(keywords: list[str]) -> list[tuple[str, str]]:
    """suggest 검색용 (search_term, origin_keyword) 쌍 목록 — 1-hop 동의어 확장.

    origin은 matched_keywords 집계 단위가 되어 distinct 매칭 수(관련도)가 변형 개수가 아니라
    사용자 의도 기준으로 계산되게 한다. 전체 term 수는 _SUGGEST_SEARCH_TERMS_MAX로 cap.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kw in keywords:
        for term in (kw, *_SYNONYM_LOOKUP.get(kw, ())):
            if term in seen:
                continue
            seen.add(term)
            pairs.append((term, kw))
            if len(pairs) >= _SUGGEST_SEARCH_TERMS_MAX:
                return pairs
    return pairs


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


def _title_token_match(keyword: str, title: str) -> bool:
    """search_provision과 동일한 의미로 keyword가 조문 제목(title)에 매칭되는지 판정.

    - 의미토큰(2자 이상)이 2개 이상이면 토큰 AND(모든 토큰이 title에 존재).
    - 1개 이하면 keyword 전체를 리터럴 부분문자열로 판정.
    search_provision의 매칭은 (제목 또는 본문)을 보지만, 여기서는 '제목 매칭'만 판정하므로 title에 한정.
    예: "협약 변경"은 제목 "연구개발과제협약의 변경 등"에 협약·변경 둘 다 있어 매칭.
    """
    if not keyword or not title:
        return False
    meaningful = [t for t in keyword.split() if len(t) >= 2]
    tokens = meaningful if len(meaningful) >= 2 else [keyword]
    return all(t in title for t in tokens)


def _title_hits(candidate: dict) -> int:
    """후보 조문 제목에 매칭된 origin 키워드(matched_keywords)의 distinct 수.

    matched_keywords에는 origin 키워드(사용자 의도 단위)만 기록되므로(동의어 변형 미포함),
    제목 매칭 수가 변형 개수로 부풀지 않고 의도 단위로 계산된다.
    """
    title = candidate.get("title", "") or ""
    return sum(1 for kw in set(candidate.get("matched_keywords") or [])
               if _title_token_match(kw, title))


def _match_count(candidate: dict) -> int:
    """후보가 매칭한 distinct origin 키워드 수 (관련도 2차 신호). None-가드."""
    return len(set(candidate.get("matched_keywords") or []))


def _relevance_key(candidate: dict, rank_of) -> tuple:
    """suggest 후보 relevance 정렬키 — 제목매칭 우선 → 관련도 → 위계 → provision_id(결정성).
    _select_capped_candidates(cap 선별)와 overflow_candidates(cap 밖 노출, v0.1.8)가 공유하여
    두 목록의 정렬 기준 동일성을 보장한다.
    """
    return (-_title_hits(candidate), -_match_count(candidate),
            rank_of(candidate), candidate["provision_id"])


def _overflow_label(candidate: dict) -> str:
    """overflow_candidates 항목 라벨: '문서명 제N조(조문제목)'. unit 라벨이 없으면 문서명+제목.
    호스트가 사람이 읽고 식별하도록, drill-down은 동봉된 provision_id로 수행."""
    doc = candidate.get("document_title", "") or ""
    ulabel = unit_label(candidate.get("unit_id"))
    title = candidate.get("title", "") or ""
    if ulabel:
        return f"{doc} {ulabel}({title})" if title else f"{doc} {ulabel}"
    return f"{doc} ({title})" if title else doc


def _select_capped_candidates(candidates, used, rank_of, max_n=_SUGGEST_CANDIDATES_MAX):
    """후보가 max_n 초과 시 선별: 제목 매칭 우선 → 관련도 → 위계 + 각 문서 최소 1건 보장.

    - rank_of(candidate)->int(낮을수록 상위 위계).
    - v0.1.7 (랭킹 정상화): 선별 1차 기준을 '제목 매칭 키워드 수'(title_hits)로 둔다.
      질문의 핵심 개념은 정답 조문 제목에 직매칭되는 경향이 강하다(예: "협약의 변경"·"사전 승인").
      v0.1.6의 match_count-우선은 일반어를 우연히 많이 포함한 무관 조문을 정답 위로 올려 제목 직매칭
      조문을 cap 밖으로 탈락시켰다(시행령 제14조·사용기준 제73·74조 매몰). 또한 v0.1.6의 _priority
      (키워드 배열 앞 index 우선)는 사용자가 맨 앞에 둔 흔한 키워드를 맞힌 무관 조문이 동률을 싹쓸이하게
      만들어(제33조>제11조) 해로웠다 → 제거한다.
    - 정렬키 = (-title_hits, -match_count, rank, provision_id). match_count는 2차 신호로 유지하여
      v0.1.6의 anti-총칙(저번호 독식 방지) 속성을 보존한다. provision_id 최후미로 결정성 보장.
    - phase1: 문서별 최우선 후보 1건 → 상위 위계 문서가 cap을 독식해 하위 문서가 통째 누락되는 것 방지.
    - phase2: 남은 슬롯을 동일 정렬키로 채움.
    - 출력 순서는 (rank, provision_id) 위계순 유지 — recommended_review_order와 정합(검토는 상위법부터).
      max_n 이하면 입력을 그대로 반환(단축은 호출부 담당). used 인자는 v0.1.7부터 정렬에 미사용(호환 위해 유지).
    """
    if len(candidates) <= max_n:
        return candidates

    # 제목 매칭 우선 → 관련도 → 위계 → provision_id(결정성).
    # _relevance_key(모듈 레벨, v0.1.8)를 재사용 — overflow_candidates 정렬과 동일 기준 보장.
    def _score(c):
        return _relevance_key(c, rank_of)

    # phase1: 문서별 최우선 후보 1건
    by_doc: dict[str, list] = {}
    for c in candidates:
        by_doc.setdefault(c.get("rule_set_id", ""), []).append(c)
    reps = [min(group, key=_score) for group in by_doc.values()]
    reps.sort(key=_score)
    selected: list = reps[:max_n]
    selected_ids: set = {c["provision_id"] for c in selected}

    # phase2: 남은 슬롯을 동일 정렬키로 채움 (phase1 선택분 제외)
    if len(selected) < max_n:
        rest = [c for c in candidates if c["provision_id"] not in selected_ids]
        rest.sort(key=_score)
        selected += rest[: max_n - len(selected)]

    selected.sort(key=lambda c: (rank_of(c), c["provision_id"]))
    return selected


def _append_overflow_candidates(response: dict, candidates: list, capped: list, rank_of) -> dict:
    """response에 overflow_candidates + overflow_truncated 추가 (v0.1.8). response를 in-place 갱신 후 반환.

    - overflow = candidates 중 cap(capped)에 들지 못한 후보. _relevance_key로 cap 선별과 동일 정렬.
    - 각 항목은 {provision_id, label} (label=_overflow_label). 호스트가 provision_id로 get_provision_detail.
    - base 응답(candidates 등) 우선: 항목을 1건씩 추가하며 전체 응답 직렬화가
      _SUGGEST_RESPONSE_CHAR_BUDGET을 넘기 직전 중단 + 최대 _OVERFLOW_CANDIDATES_MAX건.
    - overflow_truncated = cap/예산으로 일부라도 누락 시 True. overflow 없으면 [] / False.
    - 두 필드는 항상 포함(contract 0.3.0 일관성).
    """
    capped_ids = {c["provision_id"] for c in capped}
    overflow = [c for c in candidates if c["provision_id"] not in capped_ids]
    overflow.sort(key=lambda c: _relevance_key(c, rank_of))
    response["overflow_candidates"] = []
    response["overflow_truncated"] = False
    included: list[dict] = []
    for c in overflow[:_OVERFLOW_CANDIDATES_MAX]:
        item = {"provision_id": c["provision_id"], "label": _overflow_label(c)}
        response["overflow_candidates"] = included + [item]
        if len(json.dumps(response, ensure_ascii=False)) <= _SUGGEST_RESPONSE_CHAR_BUDGET:
            included.append(item)
        else:
            break
    response["overflow_candidates"] = included
    response["overflow_truncated"] = len(included) < len(overflow)
    return response


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


# v0.2.3 멀티윈도우 별표 스니펫: 마커 2형(전체 수록/발췌) + 질의 토큰 매칭 줄 합집합 발췌
_ANNEX_SNIPPET_MARKER_FULL = "[별표 본문 전체 수록 — 줄 생략 없음(원문 그대로). 수치 확정은 공식 원문 대조 권장]\n"
_ANNEX_SNIPPET_MARKER_EXCERPT = (
    "[별표 발췌 — 질의 매칭 행 중심 발췌(발췌 행 자체는 원문 그대로, 비연속 구간은 … 표시). "
    "표 제목·인접 행이 누락될 수 있어 표 전체·정확한 수치는 "
    "원문(get_provision_detail 또는 공식 링크) 확인 필요]\n"
)
_ANNEX_SNIPPET_GAP = "…"  # 비연속 윈도우 구분 줄 · 양끝 생략 표시
_ANNEX_SNIPPET_MATCH_LINES_MAX = 6  # 질의 토큰 매칭 줄 합집합 cap (문서 순서 유지·중복 없음)


def _annex_snippet(content: str, anchors: list[str], max_len: int = _SNIPPET_MAX) -> str:
    """별표(표) 전용 멀티윈도우 스니펫 (v0.2.3) — 공백 정렬 표의 행 중간 절단을 막기 위해
    개행(줄) 경계로 자르고, anchors(질의 토큰들)의 매칭 줄 합집합(cap 6) 각각에 ±1줄 맥락
    윈도우를 만들어 예산 내 앞 윈도우 우선 배치 + 라운드로빈 줄 확장한다. 종전의 '첫 매칭
    줄 1곳' 발췌가 substring 선점(예: '서울대학교' 질의가 앞쪽 '남서울대학교' 줄에 선점돼
    본교 행 누락)으로 후순위 매칭 행을 침묵 누락하던 결함 해소. 대용량 별표는 detail에서
    본문 미수록이라 이 스니펫이 호스트가 보는 유일한 별표 텍스트일 수 있어, 본문 전체
    수록 여부를 마커 2형으로 구분 표기한다."""
    if len(content) <= max(1, max_len - len(_ANNEX_SNIPPET_MARKER_FULL)):
        return _ANNEX_SNIPPET_MARKER_FULL + content
    body_budget = max(1, max_len - len(_ANNEX_SNIPPET_MARKER_EXCERPT))
    lines = content.split("\n")
    terms = [a for a in anchors if a]
    # v0.2.4: 토큰별 매칭 행 quota — 빈출 토큰(반복 표 머리글 등)이 cap을 선점해 희소
    # 토큰의 매칭 행이 수집에서 탈락하던 기아 방지 (라이브 실증: [간접비, 서울대학교]에서
    # "간접비" 머리글 5줄이 cap 6을 소진 → 본교 행 탈락). 토큰별 ceil(cap/토큰수)개를
    # 먼저 확보하고, 잔여 cap은 문서 순서 합집합으로 충원한다.
    matched_set: set[int] = set()
    if terms:
        quota = max(1, -(-_ANNEX_SNIPPET_MATCH_LINES_MAX // len(terms)))
        for t in terms:
            taken = 0
            for i, ln in enumerate(lines):
                if len(matched_set) >= _ANNEX_SNIPPET_MATCH_LINES_MAX:
                    break
                if t in ln:
                    matched_set.add(i)
                    taken += 1
                    if taken >= quota:
                        break
    for i, ln in enumerate(lines):
        if len(matched_set) >= _ANNEX_SNIPPET_MATCH_LINES_MAX:
            break
        if i not in matched_set and any(t in ln for t in terms):
            matched_set.add(i)
    matched = sorted(matched_set)
    if not matched:
        matched = [0]  # 제목만 매칭 등 본문 무매칭 → 문서 머리 폴백(종전 동작 보존)

    def _merged(segs: list[list[int]]) -> list[list[int]]:
        # 중첩·인접 윈도우 병합 — 병합되면 사이 구분 줄도 자연 소멸
        out: list[list[int]] = []
        for lo, hi in segs:
            if out and lo <= out[-1][1] + 1:
                out[-1][1] = max(out[-1][1], hi)
            else:
                out.append([lo, hi])
        return out

    def _render(segs: list[list[int]]) -> str:
        # 윈도우 본문 + 비연속 구간 "…" 구분 줄 + 문서 양끝 미도달 시 "…" 표시
        parts = ["\n".join(lines[lo:hi + 1]) for lo, hi in segs]
        body = ("\n" + _ANNEX_SNIPPET_GAP + "\n").join(parts)
        if segs[0][0] > 0:
            body = _ANNEX_SNIPPET_GAP + "\n" + body
        if segs[-1][1] < len(lines) - 1:
            body = body + "\n" + _ANNEX_SNIPPET_GAP
        return body

    windows = _merged([[max(0, m - 1), min(len(lines) - 1, m + 1)] for m in matched])
    placed: list[list[int]] = []
    for w in windows:
        cand = placed + [list(w)]
        if len(_render(cand)) <= body_budget:
            placed = cand
        else:
            break  # 예산 초과 시 이후 윈도우 생략 — 앞(문서 순서) 윈도우 우선 배치
    if not placed:
        m0 = matched[0]
        if len(_render([[m0, m0]])) <= body_budget:
            placed = [[m0, m0]]
        else:
            # 매칭 줄 단독도 예산 초과(개행 없는 장문 별표 등) → char 단위 안전 절단 + 생략표시
            cut = max(1, body_budget - 1)
            return (_ANNEX_SNIPPET_MARKER_EXCERPT + lines[m0][:cut] + _ANNEX_SNIPPET_GAP)[:max_len]
    # 잔여 예산: 윈도우 라운드로빈 ±1줄 확장 (종전 단일 윈도우 greedy 확장의 일반화)
    grew = True
    while grew:
        grew = False
        k = 0
        while k < len(placed):
            for delta in (-1, 1):
                lo, hi = placed[k]
                if delta < 0 and lo - 1 < 0:
                    continue
                if delta > 0 and hi + 1 > len(lines) - 1:
                    continue
                cand = [list(s) for s in placed]
                if delta < 0:
                    cand[k][0] = lo - 1
                else:
                    cand[k][1] = hi + 1
                cand = _merged(cand)
                if len(_render(cand)) <= body_budget:
                    placed = cand
                    grew = True
                    if k >= len(placed):
                        k = len(placed) - 1
            k += 1
    return (_ANNEX_SNIPPET_MARKER_EXCERPT + _render(placed))[:max_len]

_request_api_key: contextvars.ContextVar[str] = contextvars.ContextVar("_request_api_key", default="")

_client_instance: LawApiClient | None = None
_client_by_key: dict[str, LawApiClient] = {}
_CLIENT_BY_KEY_MAX = 100

# v0.9.1(B2): fan-out 전용 bounded executor.
# 측정상 NAS 기본 8스레드 default pool 큐잉이 cold fan-out latency의 ~40%를 차지(8→64스레드
# 8.35s→4.88s, slow_rule 42→5). law.go.kr offload(resolve+detail)를 이 전용 풀로 격리해 큐잉을
# 줄인다. 모듈 전역이라 전 사용자(_client_by_key) 합산 동시 law.go.kr 연결을 max_workers로
# bound(backpressure)한다. import 시 생성하나 ThreadPoolExecutor는 submit 시까지 스레드를
# spawn하지 않아 boot 무의존(set_default_executor와 달리 transport/loop 비의존). atexit shutdown은
# 미추가(서버 생존 중 오작동 시 "cannot schedule new futures" 위험).
# 사이징 32: N=49 cold peak 동시성 ≈49 → 32는 일부 잠깐 큐잉(~5s대)·48은 law.go.kr 동시연결
# rate-limit/예의 위험. 게이트(NAS cold)에서 rate_limited 관측 시 24로 하향.
_FANOUT_MAX_WORKERS = 32
_FANOUT_EXECUTOR = ThreadPoolExecutor(
    max_workers=_FANOUT_MAX_WORKERS, thread_name_prefix="rnd-fanout"
)


async def _run_offloaded(fn, *args):
    """동기 law.go.kr 호출을 fan-out 전용 executor로 offload (asyncio.to_thread 등가).

    asyncio.to_thread와 동일하게 현재 contextvars를 복사해 스레드 안에서 실행하되(submit마다
    새 copy_context — 작업 간 컨텍스트 공유 금지), default pool이 아닌 _FANOUT_EXECUTOR를 쓴다.
    호출부는 모두 positional args(run_in_executor는 kwargs 미전달).
    """
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    return await loop.run_in_executor(_FANOUT_EXECUTOR, ctx.run, fn, *args)


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


# v0.2.11: HTTP 멀티테넌트 키 보호 — ?oc= 없는 HTTP 요청이 server env 키로 silent fallback하여
# Andy 키로 과금/감사 누출되는 것을 차단. stdio(Claude Desktop/uvx)는 env 키가 정상 경로이므로
# _is_http_request 기본 False(미들웨어 미실행)로 영향 없음(구조적 무회귀). _get_client에서 raise하면
# 호출부(search_provision·get_provision_detail)가 try 밖이라 uncaught crash가 되므로, 도구
# 진입부에서 구조화된 auth_failed를 early-return한다.
_is_http_request: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_is_http_request", default=False
)

_HTTP_NO_KEY_MESSAGE = (
    "원격(HTTP) 호출에는 커넥터 URL에 ?oc=<발급키>가 필요합니다. "
    "키 없이는 법령 조회를 수행하지 않습니다."
)


def _http_no_key_error() -> dict | None:
    """HTTP 요청인데 ?oc= 키가 비면 표준 auth_failed envelope를 반환(아니면 None).

    stdio(=_is_http_request False)는 env 키가 정상 경로이므로 항상 None → 무회귀.
    메시지는 정적(키·동적값 미포함)이라 _sanitize_error_message 불요.
    """
    if _is_http_request.get(False) and not _request_api_key.get(""):
        return {
            "errors": [{"code": "auth_failed", "message": _HTTP_NO_KEY_MESSAGE}],
            "contract_version": CONTRACT_VERSION,
            "disclaimer": _DISCLAIMER,
        }
    return None


async def _resolve_doc_id(rs, client: LawApiClient) -> ResolvedDocId:
    return await _run_offloaded(
        client.resolve_latest_doc_id,
        rs.title,
        rs.api_target.value,
        rs.api_doc_id,
        rs.ministry,
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


def _relevance_sort_key(rs, tokens, unit_title, content, unit_type, ordinal):
    """search_provision match의 결정적 관련도 정렬키 (v0.2.8).

    절단(_RESULTS_MAX·16k 예산) *직전*에 matches를 이 키로 정렬해, 가장 관련 높은
    결과가 절단에서 생존하게 한다. 오름차순 정렬용 tuple(앞쪽=상위), count는 음수화.

    핵심: 문서 제목(rs.title) 적중을 최상위 신호로 둔다 — 광역 질의에서 manifest
    후순위지만 제목이 직접 일치하는 규정(예: '연구개발비'→「연구개발비 사용 기준」)이
    앞순위 규정에 예산을 빼앗겨 매몰되던 결함(v0.2.7 LIVE eval)을 해소한다.
    hierarchy_rank는 *하위* tie-break — 상위에 두면 법률이 후순위 규정을 다시 매몰시킨다.
    본문 적중은 '존재하는 distinct 토큰 수'(≤len(tokens))라 대형 문서 반복 편향이 없다.
    정렬키·점수는 응답에 노출하지 않는다(내부 전용, schema 무변 — contract 0.6.0 유지).
    """
    doc_title = rs.title or ""
    uniq = set(tokens)   # 중복 토큰("협약 변경 협약")이 적중수를 부풀리지 않도록 distinct화
    return (
        -sum(1 for t in uniq if t in doc_title),       # 1) 문서 제목 적중 (PRIMARY)
        -sum(1 for t in uniq if t in unit_title),      # 2) 단위(조문/별표) 제목 적중
        -sum(1 for t in uniq if t in content),         # 3) 본문 적중 (distinct, 편향 없음)
        0 if unit_type == "article" else 1,            # 4) 단위유형 minor tie-break (조문 우선)
        rs.hierarchy_rank.value,                        # 5) 위계 (1=법률…6=Supp) — 하위 tie-break
        ordinal,                                        # 6) 기존 append 순서 — 최종 결정성·현행 순서 보존
    )


# --- 별표 단위 공유 헬퍼 (v0.2.1: 가지별표·별지 구분·의존조문 단서) ---
# search emit·detail 매칭·doc-level 목록이 단일 인코딩/판정을 공유해야 id 정합이 유지된다.

def _is_annex_kind(ann: dict) -> bool:
    """별표구분이 '별표'인 항목만 BP 노출 대상 (v0.2.1).

    별지·서식은 별표와 번호가 독립 채번이라 BP id가 충돌(별표1·별지1 모두 BP0001 →
    별지 조회 시 별표가 반환되는 오도달 결함)하므로 검색·목록·상세 매칭에서 제외.
    키 부재(단위 테스트 mock 등)는 별표로 간주(하위호환).
    """
    kind = (ann.get("별표구분") or "").strip()
    return kind in ("", "별표")


def _annex_unit_id(ann: dict) -> str | None:
    """별표단위 dict → BP unit_id (가지-aware, v0.2.1). 별표번호 비숫자 → None.

    가지번호 0(키 부재·비숫자 포함) → BP{번호4} (기존 4자리 — 본별표 id 불변, 하위호환).
    가지번호 != 0 → BP{번호4}{가지2} 6자리 (예: BP000102 = 별표 1의2).
    """
    no = (ann.get("별표번호") or "").strip()
    if not no.isdigit():
        return None
    branch_raw = (ann.get("별표가지번호") or "").strip()
    branch = int(branch_raw) if branch_raw.isdigit() else 0
    if branch:
        return f"BP{int(no):04d}{branch:02d}"
    return f"BP{int(no):04d}"


def _annex_branch_no(ann: dict) -> int:
    """별표단위 dict의 가지번호 int (키 부재·비숫자 → 0 = 본별표)."""
    branch_raw = (ann.get("별표가지번호") or "").strip()
    return int(branch_raw) if branch_raw.isdigit() else 0


def _is_deleted_annex_title(title: str) -> bool:
    """제목 기반 삭제 별표 판정 (v0.2.1).

    law형 '삭제 <날짜>'(제목은 live_api 단일 관문에서 unescape 완료)·admrul형 '삭제'(정확 일치)
    양형으로 한정 — '삭제○○기준' 류 활성 제목 오탐 방지(R2 적대검증 합의).
    content 기반 판정은 admrul 삭제 별표('<삭 제>' 공백형·60자 초과)를 전건 미탐해 재사용 불가.
    """
    t = title.strip()
    return t == "삭제" or t.startswith("삭제 <")


# 별표 제목의 조문 참조(예: '(제19조제3항 관련)') 추출 — 제N조 / 제N조의M / 제N조제K항 / 제N조의M제K항
_ARTICLE_REF_PATTERN = re.compile(r"제\d+조(?:의\d+)?(?:제\d+항)?")


def _dependent_article_hints(title: str) -> list[str]:
    """별표 제목에서 의존 조문 참조를 전건 추출 (v0.2.1, 복수 list).

    제목 기반 미검증 단서 — provision_id로 변환하지 않는다(미검증 id 생성 금지).
    다중 참조('제59조제1항 및 제60조제2항')에서 단일 추출의 주조문 오선택 함정을 회피.
    """
    return _ARTICLE_REF_PATTERN.findall(title)


# 별표 detail 응답 size 예산 — 직렬화된 detail JSON이 이 char 예산을 넘으면 본문 미수록(포인터) 처리.
# MCP 응답 token 한도(Claude Code 25,000 token)의 보수 proxy (v0.1.8 overflow와 동일 사상; 서버에 tokenizer 없음).
# 4경로 최저선 보수 적용 — LIVE 4경로 실측 통과 후 별도 최적화로 상향 가능(별표2·7 17.5k+자는 현재 포인터).
_ANNEX_DETAIL_CHAR_BUDGET = 16000
# 전문 verbatim 판정 시 호출부가 사후 추가하는 필드용 헤드룸을 예산에서 차감(보수적).
# 사후주입: revision_notice(~100자) + v0.5.0 admrul version 메타(issuance_number·regulation_kind·version_label ~80자)
# → 합 ~200자 < 300 헤드룸이라 verbatim/oversized 경계 불변(B2: 최종 직렬화 ≤ _ANNEX_DETAIL_CHAR_BUDGET 보장).
_ANNEX_DETAIL_HEADROOM = 300
# v0.7.0: 문서 레벨 articles 출력 목록 상한 — 예산(16k)상 수록 가능한 항목 수(최소 항목 ~45자 → ~350개)를
# 크게 상회하는 방어적 cap. 현행 49규정 최대 117조문이라 평시 미도달. 출력 목록 크기를 600으로 cap해
# 절단 pop(O(k²)) 직렬화·메모리를 bound (입력 articles 순회 자체는 전체; 초과분은 size 백스톱이 truncated 처리).
_DOC_ARTICLES_MAX = 600


def _build_annex_detail(provision_id: str, unit_id: str, rs, ann: dict, eff_date: str, force_oversized: bool = False) -> dict:
    """별표 단위 상세 응답 (v0.2, size-tiered + verbatim 정확성 가드).

    force_oversized=True면 전문 분기를 건너뛰고 oversized_pointer로 강등(v0.5.0 — 호출부가 사후주입(version 메타·
    revision_notice) 포함 최종 직렬화가 예산을 넘겼을 때의 airtight 백스톱).

    분기:
      1) 빈 별표내용 + 서식파일만 → content_format=external_file_only (본문 텍스트 없음, 인용 금지).
      2) 삭제 stub(짧은 '삭제' 문구) → annex_status=deleted_stub (활성 규정 오인 방지).
      3) 직렬화 JSON ≤ _ANNEX_DETAIL_CHAR_BUDGET → 전문 verbatim(plain_text_verbatim).
      4) 초과 → 본문 미수록 명시 notice + oversized_pointer (인용 금지·공식 링크·search 안내).
    content_format != plain_text_verbatim 이면 verbatim_quote_allowed=False — 호스트는 그 content를
    규정 원문으로 인용하지 말고 공식 원문을 확인해야 한다 (프롬프트에 동일 규칙 명문화).
    """
    title = (ann.get("별표제목") or "").strip()
    content = (ann.get("별표내용") or "").strip()
    attached = (ann.get("별표서식파일링크") or "").strip()
    if attached and not attached.startswith(("http://", "https://")):
        attached = urljoin(_LAW_GO_KR_BASE, attached)
    base = {
        "provision_id": provision_id,
        "document_title": rs.title,
        "document_source_url": rs.source_url,
        "unit_type": "annex",
        "unit_id": unit_id,
        "title": title,
        "attached_file_url": attached or None,
        "effective_date": eff_date,
        "contract_version": CONTRACT_VERSION,
        "disclaimer": _DISCLAIMER,
        "warnings": list(rs.known_limitations),
    }
    # v0.2.1 (B): 제목의 의존 조문 참조를 미검증 단서로 노출 — 호스트가 적용값 확정을 위해 동반 조회.
    hints = _dependent_article_hints(title)
    if hints:
        base["dependent_article_hints"] = hints
        base["dependent_article_hints_note"] = (
            "별표 제목에서 추출한 미검증 단서 — 이 값 자체를 근거로 인용하지 말고, "
            "같은 문서에서 해당 조문을 get_provision_detail로 직접 조회할 것"
        )
    # 1) 본문 텍스트 없음 (서식파일만 있거나, 파싱 누락으로 본문·첨부 모두 빈 경우 모두) → external_file_only
    #    (빈 content를 plain_text_verbatim으로 떨구면 content_available=True+빈본문 오인 → 차단)
    if not content:
        base.update({
            "content": "[본문 텍스트 없음 — 본 별표는 텍스트로 제공되지 않습니다. attached_file_url(있는 경우) 또는 document_source_url의 공식 원문을 확인하십시오.]",
            "content_available": False,
            "content_format": "external_file_only",
            "verbatim_quote_allowed": False,
            "required_action": "attached_file_url 또는 document_source_url의 공식 원문 확인",
            "warnings": base["warnings"] + ["별표 본문이 텍스트로 제공되지 않습니다 — 첨부파일·공식 원문 직접 확인 필수."],
        })
        return base
    # 2) 삭제 stub — 개정 삭제 표기('삭제 <날짜>')로 한정. 동사 '삭제한다'를 담은 짧은 활성 별표 오탐 방지.
    #    v0.2.1: 제목 기반 보조 판정 추가 — admrul 삭제 별표는 content가 '<삭 제>'(공백형·60자 초과)라
    #    content 술어를 전건 미탐, doc-level deleted 표시(제목 기반)와의 모순 신호 방지.
    if (len(content) <= 60 and "삭제" in content and "<" in content) or _is_deleted_annex_title(title):
        base.update({
            "content": content,
            "content_available": True,
            "content_format": "plain_text_verbatim",
            "annex_status": "deleted_stub",
            "verbatim_quote_allowed": True,
            "warnings": base["warnings"] + ["본 별표는 삭제된 별표입니다 — 활성 규정으로 적용하지 마십시오."],
        })
        return base
    # 3) 전문 시도 — 직렬화 JSON 길이로 예산 판정
    full = dict(base)
    full.update({
        "content": content,
        "content_available": True,
        "content_format": "plain_text_verbatim",
        "verbatim_quote_allowed": True,
        "format_instructions": _VERBATIM_INSTRUCTIONS,
    })
    # 호출부가 사후 추가하는 revision_notice·version 메타 등을 고려해 헤드룸만큼 차감한 보수 예산으로 판정.
    # force_oversized면(사후주입 포함 최종이 예산 초과한 백스톱 재호출) 전문 분기를 건너뛴다.
    if not force_oversized and len(json.dumps(full, ensure_ascii=False)) <= _ANNEX_DETAIL_CHAR_BUDGET - _ANNEX_DETAIL_HEADROOM:
        return full
    # 4) 초과 → 본문 미수록 포인터
    base.update({
        "content": (
            f"[본문 생략: 별표 분량이 응답 한도를 초과합니다(약 {len(content):,}자). "
            "이 안내 텍스트를 규정 원문으로 인용하지 마십시오. 전문은 document_source_url"
            "(법제처 공식 원문)을 1순위로 확인하고, 특정 부분이 필요하면 search_provision으로 "
            "키워드를 좁혀 매칭 행 발췌를 조회하십시오. attached_file_url 첨부(있는 경우)는 "
            "HWP·HWPX 등 기계 열람이 불가할 수 있는 형식입니다.]"
        ),
        "content_available": False,
        "content_format": "oversized_pointer",
        "verbatim_quote_allowed": False,
        "is_complete": False,
        "omitted_reason": "oversized_tool_response",
        "omitted_char_count": len(content),
        "required_action": (
            "1순위: document_source_url(법제처 공식 원문) 확인, 2순위: search_provision으로 부분 검색. "
            "attached_file_url 첨부는 HWP·HWPX 등 기계 열람이 불가할 수 있는 형식"
        ),
        "warnings": base["warnings"] + ["대용량 별표 — 본문 미수록. 표시된 안내 텍스트를 규정 원문으로 인용 금지."],
    })
    return base


def _build_article_detail(provision_id: str, unit_id: str, rs, art: dict, eff_date: str, force_oversized: bool = False) -> dict:
    """조문(JO) 단위 상세 응답 (v0.6.0, size-tiered — 별표 _build_annex_detail와 동일 사상).

    force_oversized=True면 전문 분기를 건너뛰고 oversized_pointer로 강등(호출부가 사후주입(version 메타·
    revision_notice) 포함 최종 직렬화가 예산을 넘겼을 때의 airtight 백스톱).

    분기 (예산 = _ANNEX_DETAIL_CHAR_BUDGET - _ANNEX_DETAIL_HEADROOM):
      1) content + article_structure ≤ 예산 → 전문 verbatim + structure (종전 동일 — 공통 경로 무변경).
      2) content ≤ 예산 < content+structure → 중복 머신뷰 article_structure 생략, content는 전문 유지
         (중대형 조문도 본문 인용 가능 — oversized로 본문을 버리지 않음).
      3) content > 예산(또는 force_oversized) → 본문 미수록 oversized_pointer (인용 금지·공식 링크·search 안내).
    content_format != plain_text_verbatim 이면 verbatim_quote_allowed=False — 호스트는 그 content를
    규정 원문으로 인용하지 말고 공식 원문을 확인해야 한다 (별표 정책과 동일).
    """
    title = (art.get("조문제목") or "").strip()
    content = (art.get("조문내용") or "").strip()
    budget = _ANNEX_DETAIL_CHAR_BUDGET - _ANNEX_DETAIL_HEADROOM
    head = {
        "provision_id": provision_id,
        "document_title": rs.title,
        "document_source_url": rs.source_url,
        "unit_type": "article",
        "unit_id": unit_id,
        "title": title,
    }
    tail = {
        "effective_date": eff_date,
        "contract_version": CONTRACT_VERSION,
        "disclaimer": _DISCLAIMER,
        "warnings": list(rs.known_limitations),
    }
    if not force_oversized:
        # 1) 전문 + structure (종전 조문 응답과 동일 필드·순서)
        full = dict(head)
        full.update({
            "content": content,
            "content_format": "plain_text_verbatim",
            "article_structure": art.get("structured"),
            "format_instructions": _VERBATIM_INSTRUCTIONS,
        })
        full.update(tail)
        if len(json.dumps(full, ensure_ascii=False)) <= budget:
            return full
        # 2) 중복 article_structure 생략, content 전문 유지
        no_struct = dict(head)
        no_struct.update({
            "content": content,
            "content_format": "plain_text_verbatim",
            "article_structure": None,
            "structure_omitted": True,
            "format_instructions": _VERBATIM_INSTRUCTIONS_NO_STRUCTURE,
        })
        no_struct.update(tail)
        no_struct["warnings"] = no_struct["warnings"] + [
            "조문 구조(article_structure)가 응답 한도로 생략됨 — content 본문은 전문(verbatim)이며 정확합니다."
        ]
        if len(json.dumps(no_struct, ensure_ascii=False)) <= budget:
            return no_struct
    # 3) content 단독 초과(또는 백스톱) → oversized_pointer
    over = dict(head)
    over.update({
        "content": (
            f"[본문 생략: 조문 분량이 응답 한도를 초과합니다(약 {len(content):,}자). "
            "이 안내 텍스트를 규정 원문으로 인용하지 마십시오. 전문은 document_source_url"
            "(법제처 공식 원문)을 확인하고, 특정 부분이 필요하면 search_provision으로 키워드를 좁혀 "
            "매칭 행 발췌를 조회하십시오.]"
        ),
        "content_available": False,
        "content_format": "oversized_pointer",
        "article_structure": None,
        "verbatim_quote_allowed": False,
        "is_complete": False,
        "omitted_reason": "oversized_tool_response",
        "omitted_char_count": len(content),
        "required_action": (
            "1순위: document_source_url(법제처 공식 원문) 확인, 2순위: search_provision으로 부분 검색."
        ),
    })
    over.update(tail)
    over["warnings"] = over["warnings"] + [
        "대용량 조문 — 본문 미수록. 표시된 안내 텍스트를 규정 원문으로 인용 금지."
    ]
    return over


# v0.5.0: 행정규칙(admrul) version 식별자 — 발령번호·종류를 응답에 노출(번호先 stale·false-negative 해소).
# 발령번호·행정규칙종류는 get_admin_rule_detail이 OpenAPI 상세 <행정규칙기본정보>에서 파싱(없으면 "").
# effective_date(검색행 resolve)는 별도 필드 — 여기 미포함(라벨에 시행일을 넣어 cross-source 불일치 만들지 않음).
_REGULATION_KINDS = frozenset({"예규", "고시", "훈령"})
# 발령번호 형식: 순번형 "179"(예규·훈령) / 연도형 "2026-25"(고시) — LIVE 19건 실측. ASCII 숫자만([0-9], \d의 유니코드 숫자 배제).
_ISSUANCE_NUMBER_PATTERN = re.compile(r"^[0-9]+(?:-[0-9]+)?$")
# 비정상 장문(파싱 오염·악성 응답) 방어 상한 — 실측 발령번호 ≤8자·종류 ≤2자. 사후주입 size를 _ANNEX_DETAIL_HEADROOM 내로 보장(B2).
_ISSUANCE_MAX_LEN = 16
_KIND_MAX_LEN = 8


def _admrul_version_meta(pid, detail: dict) -> dict:
    """admrul 발령번호·종류 version 메타데이터 (v0.5.0, additive).

    admrul만 — pid.doc_type != 'admrul'이면 빈 dict(law·오류 경로 미주입).
    issuance_number(raw "179"/"2026-25")·regulation_kind("예규/고시/훈령") 노출,
    version_label("예규 제179호")은 종류가 허용값이고 번호가 검증 패턴일 때만 엄격 합성(omit 규칙·부처 prepend 금지).
    값은 resolve된 문서의 발령번호·종류이며 resolve-fail 시 manifest fallback일 수 있어 '현행 보증'이 아님(docstring·instructions에서 현행 단정 안 함).
    비정상 장문(_ISSUANCE_MAX_LEN/_KIND_MAX_LEN 초과)은 omit — 별표 사후주입 size를 헤드룸 내로 결정론적 보장(B2).
    """
    if pid.doc_type != "admrul":
        return {}
    issuance = (detail.get("발령번호") or "").strip()
    kind = (detail.get("행정규칙종류") or "").strip()
    if len(issuance) > _ISSUANCE_MAX_LEN:   # 비정상 장문 → raw·label 모두 미노출(주입 size 상한)
        issuance = ""
    if len(kind) > _KIND_MAX_LEN:
        kind = ""
    meta: dict = {}
    if issuance:
        meta["issuance_number"] = issuance
    if kind:
        meta["regulation_kind"] = kind
    if kind in _REGULATION_KINDS and _ISSUANCE_NUMBER_PATTERN.match(issuance):
        meta["version_label"] = f"{kind} 제{issuance}호"
    return meta


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
    """사용 시점: 국가연구개발·R&D 연구행정 규정의 조문·용어·현행 여부를 묻는 질문에는 일반 학습지식 답변 전에 호출하십시오. 본 서버 범위 밖 일반 대화·번역·문장 다듬기에는 호출하지 마십시오.

    규정 조문·별표 본문에서 query 키워드를 찾아 후보 list 반환.

    manifest의 live_api 문서들을 대상으로:
      - law(혁신법·시행령·시행규칙): 조문(`조문내용`) + 별표(`별표내용`) 검색 (v0.2: 시행령 별표 지원)
      - admrul(연구개발비 사용 기준 등): 조문 + 별표(`별표내용`) 검색
        - 각 항목의 `unit_types` (article/annex/both)에 따라 검색 범위 결정
        - 별표는 별표구분=='별표'만 노출 — 별지·서식 제외 (v0.2.1, BP 번호 충돌 오도달 방지)

    응답 최상위에 짧은 `disclaimer` 1개만 두고, 각 결과에는 manifest 특유의 `warnings`만 첨부.
    snippet은 _SNIPPET_MAX (2000자)로 제한, 전체 응답은 16k char 예산 내(초과 시 뒤쪽
    결과 절단·truncated=true — 광역 질의는 키워드를 좁혀 재검색할 것) — MCP output size limit 회피.

    매칭 (v0.1.6): query를 공백으로 토큰 분해하여 모든 토큰(2자 이상)이 한 조문/별표의
    제목 또는 본문에 존재하면 매칭(토큰 AND). 단일 토큰 query는 종전과 동일한 부분문자열 매칭.
    원문이 "협약의 변경/협약을 변경"으로 써서 "협약 변경"이 안 잡히던 띄어쓰기 불일치를 해소.
    """
    _e = _http_no_key_error()
    if _e is not None:
        return {**_e, "results": []}
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

    # 토큰 AND 매칭 준비: 의미 토큰(2자 이상)이 2개 이상일 때만 토큰 AND.
    # 1개 이하면(단일 개념어, 또는 "별표 1"처럼 짧은 식별 토큰이 탈락한 경우) 리터럴 query로 검색.
    # → "별표 1"이 "별표" 1토큰으로 과확장돼 59건 superset이 _RESULTS_MAX(30) truncation에
    #   정밀 매칭(18건 중 12건)을 잃던 회귀 방지. "협약 변경"(의미토큰 2개)은 토큰 AND 유지.
    _meaningful = [t for t in query.split() if len(t) >= 2]
    tokens = _meaningful if len(_meaningful) >= 2 else [query]

    def _content_matches(title: str, content: str) -> bool:
        return all((t in title) or (t in content) for t in tokens)

    def _snippet_for(content: str) -> str:
        # 본문에 존재하는 첫 토큰을 anchor로 snippet 생성(다중 토큰이면 query 전체는 안 잡힘)
        anchor = next((t for t in tokens if t in content), query)
        return _make_snippet(content, anchor)

    items = load_manifest()
    live_items = [rs for rs in items if rs.retrieval == Retrieval.LIVE_API]
    client = _get_client()

    matches: list[dict] = []
    # v0.2.8: 절단(_RESULTS_MAX·16k 예산) 전 관련도 정렬용 — (정렬키, match) 수집.
    _scored: list[tuple] = []
    _ordinal = 0
    errors: list[dict] = []
    # v0.2.10(관측성): 규정별 fan-out 지연(ms) 수집 — 요약 INFO의 max_rule_ms/slow_rule_count 산출용.
    # 완료(정상·오류) task만 기록하고, 예산 초과로 cancel된 task는 제외(skipped로 별도 집계).
    _rule_ms: list[float] = []

    async def _fetch_rule_set(rs):
        _t0 = time.monotonic()
        _status = "ok"
        _record = True
        try:
            resolved = await _resolve_doc_id(rs, client)
            doc_id = resolved.doc_id
            if rs.api_target == ApiTarget.LAW:
                detail = await _run_offloaded(client.get_law_detail, doc_id)
                return (rs, resolved, detail.get("articles", []),
                        detail.get("annexes", []), detail.get("annex_parse_error"))
            else:
                detail = await _run_offloaded(client.get_admin_rule_detail, doc_id)
                return (rs, resolved, detail.get("articles", []),
                        detail.get("annexes", []), None)
        except asyncio.CancelledError:
            # 예산 초과 skip — timing 미기록(skipped로 요약에 별도 집계). 취소 의미 보존 위해 re-raise.
            _record = False
            raise
        except BaseException as _e:
            _status = type(_e).__name__  # 클래스명만 — 예외 message·URL·키 미로깅(보안)
            raise
        finally:
            if _record:
                _el = (time.monotonic() - _t0) * 1000.0
                _rule_ms.append(_el)
                logger.debug(
                    "event=fanout_rule rule_set_id=%s api_target=%s status=%s elapsed_ms=%.0f",
                    rs.id, rs.api_target.value, _status, _el,
                )

    # v0.2.6: 전건 fan-out을 응답 시간 예산으로 bound — pathological 지연(법령정보 행/재시도 폭주)이
    # 전체 질의를 커넥터 타임아웃까지 끄는 것을 차단. 예산 내 완료분만 사용하고, 미완 규정은 graceful skip.
    _fanout_start = time.monotonic()
    _tasks = [asyncio.ensure_future(_fetch_rule_set(rs)) for rs in live_items]
    _done, _pending = await asyncio.wait(_tasks, timeout=_FANOUT_BUDGET_S)
    _fanout_wall_ms = (time.monotonic() - _fanout_start) * 1000.0
    for _t in _pending:
        _t.cancel()
    if _pending:
        logger.warning(
            "search_provision: fan-out 응답 예산(%.0fs) 초과 — %d/%d 규정 graceful skip",
            _FANOUT_BUDGET_S, len(_pending), len(live_items),
        )
    fetch_results: list = []
    for _t in _tasks:
        if _t in _done:
            try:
                fetch_results.append(_t.result())
            except BaseException as _e:  # LawApiError 포함 — 아래 루프에서 분류
                fetch_results.append(_e)
        else:
            fetch_results.append(_FanoutSkipped())

    for i, result in enumerate(fetch_results):
        if isinstance(result, _FanoutSkipped):
            rs = live_items[i]
            errors.append({"rule_set_id": rs.id, "code": "timeout",
                           "message": "이 규정은 응답 시간이 길어 이번 검색에서 제외했습니다(다른 규정 결과는 정상). "
                                      "서비스 중단이 아니라 부분 결과이며, 키워드를 좁혀 다시 검색하면 포함될 수 있습니다."})
            continue
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
        rs, resolved, articles, annexes, annex_parse_error = result
        if annex_parse_error and rs.unit_types in (UnitTypes.ANNEX, UnitTypes.BOTH):
            logger.warning("search_provision: rule_set=%s 별표 파싱 실패: %s", rs.id, annex_parse_error)
            errors.append({"rule_set_id": rs.id, "code": "annex_parse_failed", "message": annex_parse_error})

        # article 검색
        if rs.unit_types in (UnitTypes.ARTICLE, UnitTypes.BOTH):
            for art in articles:
                title = (art.get("조문제목") or "").strip()
                content = (art.get("조문내용") or "").strip()
                if _content_matches(title, content):
                    art_no = (art.get("조문번호") or "").strip()
                    if art_no.isdigit():
                        snippet = _snippet_for(content)
                        _scored.append((
                            _relevance_sort_key(rs, tokens, title, content, "article", _ordinal),
                            _build_match(rs, f"JO{int(art_no):04d}", "article", title, snippet, resolved)))
                        _ordinal += 1

        # annex 검색 — 별표구분=='별표' 한정 + 가지-aware BP id (v0.2.1: 별지·서식은
        # 번호 독립 채번이라 BP 충돌(오도달)로 제외, 가지별표는 6자리 id로 도달 가능)
        if rs.unit_types in (UnitTypes.ANNEX, UnitTypes.BOTH):
            for ann in annexes:
                if not _is_annex_kind(ann):
                    continue
                title = (ann.get("별표제목") or "").strip()
                content = (ann.get("별표내용") or "").strip()
                if _content_matches(title, content):
                    unit_id = _annex_unit_id(ann)
                    if unit_id:
                        # v0.2.3: 본문에 존재하는 전 토큰을 전달 — 매칭 줄 합집합 멀티윈도우
                        present = [t for t in tokens if t in content]
                        snippet = _annex_snippet(content, present or [query])
                        _scored.append((
                            _relevance_sort_key(rs, tokens, title, content, "annex", _ordinal),
                            _build_match(rs, unit_id, "annex", title, snippet, resolved)))
                        _ordinal += 1

    # v0.2.10(관측성): fan-out 요약 1줄(INFO·key=value) — B2 풀 크기 N 산정용.
    # wall_ms ≫ max_rule_ms이면 8스레드 풀 큐잉(격리 필요), 근사하면 네트워크 지연 우세.
    # 시크릿(키·URL·query·keywords·예외 message) 미포함 — rule 식별자·정수 지표만.
    _max_rule_ms = max(_rule_ms, default=0.0)
    _slow_rule_count = sum(1 for _m in _rule_ms if _m >= _SLOW_RULE_MS)
    logger.info(
        "event=search_fanout_summary live_rules=%d done=%d skipped=%d wall_ms=%.0f "
        "budget_ms=%.0f max_rule_ms=%.0f slow_rule_count=%d errors_count=%d",
        len(live_items), len(_done), len(_pending), _fanout_wall_ms,
        _FANOUT_BUDGET_S * 1000.0, _max_rule_ms, _slow_rule_count, len(errors),
    )

    # v0.2.8: 절단 전 관련도 정렬 — 정렬키는 결정적(마지막 요소가 append 순서)이라
    # 동률 시 현행 순서를 보존한다. 정렬키는 내부 전용(응답 schema·필드 무변).
    _scored.sort(key=lambda x: x[0])
    matches = [m for _, m in _scored]
    limited = matches[:_RESULTS_MAX]
    # v0.2.5: 전체 응답 char 예산 — 25개 규정 확대로 광역 질의 응답이 40k+자(25k token
    # 한도 초과 위험)로 실측됨에 따라, suggest(16k)와 동일한 보수 proxy 예산을 적용.
    # 직렬화 누적이 예산을 넘으면 뒤쪽 결과를 절단(최소 1건 보장) — schema 무변,
    # 기존 returned/truncated 필드가 절단 사실을 신호.
    base_size = len(json.dumps({
        "query": query,
        "total": len(matches),
        "returned": len(limited),
        "truncated": True,
        "contract_version": CONTRACT_VERSION,
        "disclaimer": _DISCLAIMER,
        "results": [],
        "errors": errors,
    }, ensure_ascii=False))
    kept: list[dict] = []
    size = base_size
    for item in limited:
        item_size = len(json.dumps(item, ensure_ascii=False)) + 2  # 구분자 여유
        if kept and size + item_size > _SEARCH_RESPONSE_CHAR_BUDGET:
            break
        kept.append(item)
        size += item_size
    truncated = len(matches) > len(kept)
    response = {
        "query": query,
        "total": len(matches),
        "returned": len(kept),
        "truncated": truncated,
        "contract_version": CONTRACT_VERSION,
        "disclaimer": _DISCLAIMER,
        "results": kept,
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
                "호스트 LLM이 작성한 검색 키워드 배열. 사실상 항상 제공할 것 — 생략 시 서버가 질문 표면에서 "
                "규칙으로만 추출하여 품질이 크게 떨어짐(degraded fallback). 1~10개, 권장 3~8, 중요한 키워드를 앞쪽에. "
                "핵심: 질문 원문에 없더라도 그 상황에 적용될 법령상 절차·개념어를 추론해 포함할 것 — 표면 단어 복사가 아님. "
                "예) 기관 간 비용·과업을 '이관·변경'하는 상황이면 사용자가 그 단어를 쓰지 않았어도 "
                "'협약 변경'·'사전 승인'·'연구개발과제협약'을 키워드에 넣을 것. "
                "법령 정식 용어를 우선할 것(현장 약어→정식명, 예: 정출금→정부지원연구개발비). "
                "매칭은 토큰 AND(공백으로 나뉜 모든 단어가 한 조문/별표에 있으면 매칭)이므로 '협약 변경'처럼 띄어쓴 구와 "
                "핵심 명사('협약','변경')를 함께 넣어 recall 확보. 국가·사업·연구개발처럼 지나치게 광범위한 단어만 제외(승인·통보·보고 등 절차어는 포함). "
                "서버가 정출금↔정부지원연구개발비↔출연금 등 일부 동의어는 자동 확장하나, 정식 용어로 제공하는 편이 안전함. "
                "규정 검토 질문에는 keywords 없이 호출하지 말 것 — 생략하면 응답이 degraded(품질 낮음)로 표시되고 "
                "핵심 절차·근거 조문이 누락될 수 있으므로, 그 경우 keywords를 추론해 즉시 재호출해야 함."
            )
        ),
    ] = None,
) -> dict:
    """사용 시점: 국가연구개발·부처별 R&D 연구행정 규정의 검토·절차·준수사항·근거 조항을 묻는 경우 먼저 호출하십시오. '알려줘'처럼 넓은 표현도 규정 사실 확인이면 호출 대상입니다. 본 서버 범위 밖 질문에는 호출하지 마십시오.

    본 도구는 법률 판단을 하지 않습니다. 사용자 질문과 핵심 검색 키워드로 검토할 rule set·후보 조문·검토 순서만 반환합니다.

    가능하면 keywords 인자에 호스트 LLM이 추출한 핵심 검색어 배열을 함께 전달하십시오(question에는 검토 상황 전체).
    keywords가 제공되면 서버의 단순 규칙 추출보다 우선 사용되며, 생략·무효 시에만 규칙 추출로 대체됩니다.
    응답의 candidates는 상위 일부만 포함합니다(cap). cap에 밀린 조문은 overflow_candidates에
    [label·provision_id]로 함께 반환되니, 관련 있어 보이면 그 provision_id로 get_provision_detail을 호출해 확인하십시오.
    최종 판단은 사용자의 책임이며, 별표·매뉴얼·기관 운영규정 별도 확인이 필요합니다.
    """
    _e = _http_no_key_error()
    if _e is not None:
        return _e
    _suggest_start = time.monotonic()
    _search_calls = 0  # v0.2.10(관측성): suggest 1회가 유발한 search_provision 호출 수
    provided = _sanitize_keywords(keywords)
    if provided:
        used = provided
        keyword_source = "client"
    else:
        used = _extract_keywords(question, max_count=_FALLBACK_KEYWORDS_MAX)
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
            "overflow_candidates": [],
            "overflow_truncated": False,
            "note": _DEGRADED_NOTE_EMPTY,
            "disclaimer": _DISCLAIMER,
            "contract_version": CONTRACT_VERSION,
        }

    async def _search_union(kw_list: list[str]) -> tuple[dict[str, dict], list[dict]]:
        """키워드들을 1-hop 동의어로 확장해 search_provision union (dedupe).

        - v0.1.6 (Pillar B): 각 origin 키워드를 _build_search_terms로 동의어 변형까지 확장.
          동일 search_term은 1회만 호출(memoize)하고, matched_keywords에는 origin 키워드만
          기록 → 관련도(distinct 매칭 수)가 변형 개수가 아니라 사용자 의도 단위로 계산됨.
        - search 실패는 "후보 없음"으로 위장하지 말 것: errors에 origin 키워드를 달아 전파.
        """
        nonlocal _search_calls
        matches: dict[str, dict] = {}
        errors: list[dict] = []
        term_cache: dict[str, dict] = {}
        for term, origin in _build_search_terms(kw_list):
            if term not in term_cache:
                _search_calls += 1
                term_cache[term] = await search_provision(term)
            res = term_cache[term]
            for err in res.get("errors", []):
                errors.append({**err, "keyword": origin})
            for m in res.get("results", []):
                pid = m["provision_id"]
                if pid in matches:
                    if origin not in matches[pid]["matched_keywords"]:
                        matches[pid]["matched_keywords"].append(origin)
                else:
                    m_copy = dict(m)
                    m_copy["matched_keywords"] = [origin]
                    matches[pid] = m_copy
        return matches, errors

    all_matches, all_errors = await _search_union(used)

    # post-search 안전망: 클라이언트 키워드가 결과 0건 + 오류 없음이면(과협소 복합어 등)
    # 규칙 추출 키워드로 보강 — question-only 대비 recall 저하 방지. 클라이언트 검색에 오류가 있으면 보강 생략(원인 은폐 방지).
    if keyword_source == "client" and not all_matches and not all_errors:
        fb = _extract_keywords(question, max_count=_FALLBACK_KEYWORDS_MAX)
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
        snip = c2.get("snippet", "")
        # v0.2.3: 별표 마커는 search_provision 전용 신호 — 300자 절단을 거치는 suggest 후보에
        # 남기면 절단본에 "전체 수록" 주장이 잔존(오신호)하므로 마커 첫 줄을 제거 후 단축
        if snip.startswith((_ANNEX_SNIPPET_MARKER_FULL, _ANNEX_SNIPPET_MARKER_EXCERPT)):
            snip = snip.split("\n", 1)[1] if "\n" in snip else ""
        c2["snippet"] = _shorten_snippet(snip)
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
    notes: list[str] = []
    if keyword_source == "fallback":
        notes.append(_DEGRADED_NOTE_FALLBACK)
    elif keyword_source == "client+fallback":
        notes.append(_DEGRADED_NOTE_CLIENT_FB)
    if len(candidates) > len(returned_candidates):
        notes.append(
            "검색 결과가 많아 상위 후보만 candidates에 반환했습니다. "
            "cap에 밀린 조문은 overflow_candidates에 제목·provision_id로 제공되니 먼저 확인하고, "
            "overflow_truncated가 true이거나 누락이 의심되면 recommended_review_order·search_provision으로 추가 검색하십시오."
        )
    if notes:
        response["note"] = " ".join(notes)
    if all_errors:
        response["errors"] = all_errors

    # v0.1.8: overflow_candidates — cap(15)에 밀린 조문을 label+provision_id로 노출(호스트 drill-down 용).
    _append_overflow_candidates(response, candidates, capped, _rank_of)
    # v0.2.10(관측성): suggest 요약 1줄(INFO) — 1회가 유발한 내부 search 호출 수·소요·후보 수.
    # 시크릿 미포함(keyword_source는 client/fallback 범주 문자열). early-return(무키워드)에는 미기록.
    logger.info(
        "event=suggest_search_summary keyword_source=%s search_calls=%d wall_ms=%.0f "
        "errors_count=%d candidates_count=%d",
        keyword_source, _search_calls, (time.monotonic() - _suggest_start) * 1000.0,
        len(all_errors), len(candidates),
    )
    return response


@mcp.tool()
async def get_provision_detail(provision_id: str) -> dict:
    """사용 시점: search_provision 또는 suggest_review_sources가 반환한 provision_id의 원문·삭제 여부·현행 내용을 확인할 때 호출하십시오. provision_id 없이 조문 내용을 추측하지 마십시오. 이 도구의 content가 규정 조문·별표 본문의 권위 출처이므로, 본문은 외부 웹(law.go.kr 직접 열람·웹검색 결과)에서 가져오지 말고 이 도구로 확인하십시오. content_format이 plain_text_verbatim이 아니면 응답이 제공한 attached_file_url·document_source_url의 공식 원문을 확인하십시오. 행정규칙(admrul) 응답에는 발령번호·종류가 issuance_number·regulation_kind·version_label 필드로 포함되니 이를 사용하되, 이 값은 조회된 규정의 것이며 현행임을 보증하지 않으므로(검색 실패 시 등록 버전일 수 있음) 현행 여부 단정이 필요하면 1차 출처에서 확인하고, 응답에 없는 고시·예규 번호 등은 외부 값으로 단정하지 마십시오.

    provision_id로 단일 조문/별표 본문 재조회 — 응답은 법령 원문 verbatim.

    중요 (LLM 표시 정책): 응답의 `content`와 `article_structure` 는 국가법령정보 OpenAPI의
    법령 원문을 그대로 재구성한 것입니다. 사용자에게 표시할 때 임의 부제 추가·요약·paraphrase
    를 절대 추가하지 말고, 항(①②③)·호(1./2./3.) 번호와 줄바꿈을 모두 유지하여 원문을
    그대로 인용해야 합니다 (법령 검토의 정확성 훼손 방지). 자세한 정책은 응답의
    `format_instructions` 필드 참조.

    provision_id 포맷: {doc_type}:{doc_id}[:{unit_id}]
    - unit_id 생략 시 document-level 요약 반환 — annexes 목록(별표 제목·provision_id·deleted 표시,
      v0.2.1)과 articles 목록(조문 제목·provision_id, v0.7.0 — 응답 한도 초과 시 articles_truncated)이
      포함되므로, 특정 별표·조문의 provision_id가 불확실하면 추측하지 말고 이 목록에서 선택할 것.
    - unit_id가 JO… 면 조문 본문 + article_structure (v0.6.0 size-tiered — 대용량 조문은
      article_structure 생략 또는 본문 미수록 oversized_pointer), BP… 면 별표 본문 (행정규칙·법령
      시행령 모두, v0.2; size-tiered). BP는 4자리(본별표, 예: BP0001=별표 1) 또는 6자리(가지별표
      번호4+가지2, 예: BP000102=별표 1의2, v0.2.1). 별지·서식은 별표가 아니므로 BP로 조회 불가.
    """
    _e = _http_no_key_error()
    if _e is not None:
        return _e
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
        annex_parse_error: str | None = None
        if pid.doc_type == "law":
            detail = await _run_offloaded(client.get_law_detail, doc_id)
            articles = detail.get("articles", [])
            annexes = detail.get("annexes", [])
            annex_parse_error = detail.get("annex_parse_error")
        else:  # admrul
            detail = await _run_offloaded(client.get_admin_rule_detail, doc_id)
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
    # v0.5.0: admrul 발령번호·종류 version 메타 1회 계산 — 3 반환점(문서·조문·별표)에 균일 주입.
    # law·오류 경로는 {} (helper의 doc_type 가드) → update no-op. effective_date는 별도 필드 유지.
    _version_meta = _admrul_version_meta(pid, detail)

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
        result.update(_version_meta)  # v0.5.0: admrul issuance_number·regulation_kind·version_label
        result["annexes_count"] = len(annexes)  # 별표단위 전건 집계(별표·별지·서식 포함) — 하위호환 유지
        # v0.2.1 (A): 별표(구분=='별표')만 제목·provision_id 목록으로 노출 — 호스트가 추측 대신
        # 제목을 보고 BP를 선택(첫 실사용의 '별표 guess' 경로 폐쇄). 본문 미포함(제목만).
        # 별지·서식은 BP 번호 충돌(오도달)로 목록 제외 — 구성은 annexes_count_by_kind로 표시.
        annex_list: list[dict] = []
        kind_counts: dict[str, int] = {}
        for ann in annexes:
            kind = (ann.get("별표구분") or "").strip() or "별표"
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            if not _is_annex_kind(ann):
                continue
            ann_unit_id = _annex_unit_id(ann)
            if ann_unit_id is None:
                continue
            ann_title = (ann.get("별표제목") or "").strip()
            item = {
                "provision_id": build_provision_id(pid.doc_type, pid.doc_id, ann_unit_id),
                "label": unit_label(ann_unit_id),
                "title": ann_title,
            }
            ann_hints = _dependent_article_hints(ann_title)
            if ann_hints:
                item["dependent_article_hints"] = ann_hints
            if _is_deleted_annex_title(ann_title):
                item["deleted"] = True
            annex_list.append(item)
        result["annexes"] = annex_list
        result["annexes_count_by_kind"] = kind_counts
        # v0.2.2: 막다른 길 신호 — 별표 외 부속문서(별지·서식·별첨·붙임)는 BP 조회 불가 + hints 미검증 경고
        # v0.2.6: 별지·서식 하드코딩 → 비'별표' 전 kind 일반화 (신종 '별첨'·'붙임'도 경고 포함)
        forms_count = sum(v for k, v in kind_counts.items() if k != "별표")
        if forms_count:
            result["warnings"] = result["warnings"] + [
                f"별표 외 부속문서(별지·서식·별첨 등) {forms_count}건은 본 도구로 본문 조회 불가 — document_source_url의 공식 원문에서 확인할 것."
            ]
        if any("dependent_article_hints" in a for a in annex_list):
            result["warnings"] = result["warnings"] + [
                "annexes의 dependent_article_hints는 별표 제목에서 추출한 미검증 단서 — 근거로 인용하지 말고 해당 조문을 직접 조회할 것."
            ]
        # v0.2.1 (G): law 별표 파싱 실패 시 정직성 표면화 — annexes_count=0이 '별표 없음'으로
        # 오인되는 거짓 신호 차단 (annex_parse_error는 get_law_detail 전용 — admrul은 미발화).
        if annex_parse_error:
            result["annexes_unavailable"] = True
            result["annex_parse_error"] = annex_parse_error
            result["warnings"] = result["warnings"] + [
                "별표 파싱 실패 — annexes_count·annexes 목록을 신뢰하지 말고 공식 원문을 확인할 것."
            ]
        if _revision:
            result["revision_notice"] = _revision
        # v0.7.0: 문서 레벨 articles(조문) 목록 — 호스트가 특정 조문의 JO provision_id를 추측하거나
        # 외부(law.go.kr)로 우회하지 않고 선택하도록 노출(v0.6.0 eval 실관측: admrul 평면 schema
        # 특정조문 외부 우회). 별표 annexes 목록과 동형 {provision_id, label, title}·본문 미포함.
        # ASCII 숫자 조문번호만 수록 — live_api 파서가 가지조문·wrapper는 이미 제외(중첩 403/평면 256)하고,
        # 상위첨자('²'=isdigit True·isascii False)·비정상 장문 숫자(CPython int 변환 4,300자리 상한)는 int()
        # 예외를 내므로 isascii 가드 + try/except로 skip(죽은 id·문서 레벨 조회 crash 방지). build는 _DOC_ARTICLES_MAX로
        # bound(비정상 대량 입력 O(n²)·메모리 방어). dedup은 방어적(정상 데이터엔 중복 없음·첫 등장=JO first-match 정합).
        _articles_list: list[dict] = []
        _seen_jo: set[str] = set()
        for art in articles:
            if len(_articles_list) >= _DOC_ARTICLES_MAX:
                break  # 예산상 수록 불가능한 초과분 — 아래 size 백스톱이 articles_truncated 처리
            no = (art.get("조문번호") or "").strip()
            if not (no.isascii() and no.isdigit()):
                continue
            try:
                art_unit_id = f"JO{int(no):04d}"
            except ValueError:
                continue  # CPython int 변환 상한(>4,300자리) 등 비정상 — JO 조회 불가
            if art_unit_id in _seen_jo:
                continue
            _seen_jo.add(art_unit_id)
            _articles_list.append({
                "provision_id": build_provision_id(pid.doc_type, pid.doc_id, art_unit_id),
                "label": unit_label(art_unit_id),
                "title": (art.get("조문제목") or "").strip(),
            })
        result["articles"] = _articles_list
        # size 백스톱: articles 목록 항목들이 응답을 예산(16,000) 너머로 키우지 않도록, 최종 직렬화(절단
        # 플래그·경고 포함)를 실제 json.dumps로 측정해 초과 시 목록을 뒤에서 제거(추정 산식 아님 →
        # separator·메타데이터 누적 오차에 안전). 현행 49규정 최악 117조문 ~12.9k자라 평시 미발동.
        # ★base(annexes·revision_notice 등 무한 비-본문 필드)만으로 이미 예산 한계 근처/초과면, 목록을
        #   비우고 본 feature가 추가한 절단 플래그·경고를 되돌려 base를 더 키우지 않는다(graceful degrade).
        #   이때 빈 additive `articles` 키(~16자)는 남으며, base가 예산-16자 근처인 극단에서는 그 16자가
        #   예산을 미세 초과할 수 있으나 — 이는 모든 additive 필드(v0.5.0 version 메타 ~106자 등)가 공유하는
        #   pre-existing R5 system-wide base-bloat 사안(단일 의도 밖). v0.7.0의 빈 키 16자는 기존 R5 주원인을
        #   실질적으로 확대하지 않는다(106자보다 작음). 16,000은 25,000 TOKEN 한도의 보수 proxy(char≠token).
        if len(json.dumps(result, ensure_ascii=False)) > _ANNEX_DETAIL_CHAR_BUDGET:
            _trunc_warning = (
                "조문 목록이 응답 한도로 일부만 수록됨(articles_truncated) — 누락 조문은 "
                "search_provision으로 조회하거나 document_source_url의 공식 원문에서 확인할 것."
            )
            result["articles_truncated"] = True
            result["warnings"] = result["warnings"] + [_trunc_warning]
            while _articles_list and len(json.dumps(result, ensure_ascii=False)) > _ANNEX_DETAIL_CHAR_BUDGET:
                _articles_list.pop()
                result["articles"] = _articles_list
            if not _articles_list and len(json.dumps(result, ensure_ascii=False)) > _ANNEX_DETAIL_CHAR_BUDGET:
                del result["articles_truncated"]
                result["warnings"] = result["warnings"][:-1]  # 직전 append한 절단 경고만 제거(중복 문자열 안전)
        return result

    # article (JO)
    if pid.unit_id.startswith("JO"):
        target_no = int(pid.unit_id[2:])
        for art in articles:
            no = (art.get("조문번호") or "").strip()
            # v0.7.0: 비ASCII·비정상 장문 숫자(상위첨자·>4,300자리)는 int() 예외를 내므로 가드 후 skip
            # — 앞선 비정상 조문번호 1건이 목표 조문 도달 전에 전체 조회를 깨뜨리지 않도록(doc-level
            #   articles 목록 필터와 정합 → 노출한 정상 JO id가 실제로 조회 가능함을 보장).
            if not (no.isascii() and no.isdigit()):
                continue
            try:
                if int(no) != target_no:
                    continue
            except ValueError:
                continue
            resp = _build_article_detail(provision_id, pid.unit_id, rs, art, eff_date)
            resp.update(_version_meta)  # v0.5.0: admrul version 식별자(조문+번호 동반 질의 시 외부행 차단)
            if _revision:
                resp["revision_notice"] = _revision
            # v0.6.0 백스톱: 사후주입(version 메타·revision_notice) 후 최종 직렬화가 예산을 넘으면
            # oversized 강등(별표 BP와 동일). 본문(content)이 size 주범인 경우를 해소 — 본문 외 무한
            # 공급 필드(revision_notice·title 등)가 단독 초과하는 경우는 pre-existing R5 backlog(단일 의도 밖).
            if (
                resp.get("content_format") == "plain_text_verbatim"
                and len(json.dumps(resp, ensure_ascii=False)) > _ANNEX_DETAIL_CHAR_BUDGET
            ):
                resp = _build_article_detail(provision_id, pid.unit_id, rs, art, eff_date, force_oversized=True)
                resp.update(_version_meta)
                if _revision:
                    resp["revision_notice"] = _revision
            return resp

    # annex (BP)
    elif pid.unit_id.startswith("BP"):
        # 별표 파싱 실패(law fault-isolation)로 annexes가 비었으면 not_found가 아니라 정직하게 표면화
        if annex_parse_error and not annexes:
            return {
                "errors": [{
                    "code": "annex_unavailable_parse_failed",
                    "message": f"별표 파싱 실패({annex_parse_error}) — 공식 원문 확인 필요",
                }],
                "document_source_url": rs.source_url,
                "contract_version": CONTRACT_VERSION,
                "disclaimer": _DISCLAIMER,
            }
        # v0.2.1: 길이 기반 디코드(4자리=본별표, 6자리=번호4+가지2) + (번호,가지) 엄격 매칭.
        # 첫-일치 우연 반환(오도달)을 제거 — 해당 (번호,가지)의 별표가 없으면 not_found.
        # 별지·서식은 매칭 대상에서 제외(_is_annex_kind) — 별표와 번호 충돌 차단.
        digits = pid.unit_id[2:]
        if len(digits) == 6:
            target_no, target_branch = int(digits[:4]), int(digits[4:])
        else:
            target_no, target_branch = int(digits), 0
        for ann in annexes:
            if not _is_annex_kind(ann):
                continue
            no = (ann.get("별표번호") or "").strip()
            if not (no.isdigit() and int(no) == target_no):
                continue
            if _annex_branch_no(ann) != target_branch:
                continue
            resp = _build_annex_detail(provision_id, pid.unit_id, rs, ann, eff_date)
            resp.update(_version_meta)  # v0.5.0: oversized 별표도 version은 도구에서(프롬프트4 외부행 차단)
            if _revision:
                resp["revision_notice"] = _revision
            # v0.5.0 B2 백스톱: 전문 별표에 사후주입(version 메타·revision_notice) 후 최종 직렬화가 예산을 넘으면
            # oversized로 강등(비정상 장문 사후주입 대비 airtight; version 메타는 상한 bounded라 정상 입력선 미발동).
            if (
                resp.get("content_format") == "plain_text_verbatim"
                and "annex_status" not in resp
                and len(json.dumps(resp, ensure_ascii=False)) > _ANNEX_DETAIL_CHAR_BUDGET
            ):
                resp = _build_annex_detail(provision_id, pid.unit_id, rs, ann, eff_date, force_oversized=True)
                resp.update(_version_meta)
                if _revision:
                    resp["revision_notice"] = _revision
            return resp

    _msg = f"{provision_id}의 unit을 detail 응답에서 찾지 못함"
    if pid.unit_id.startswith("BP"):
        # v0.2.2: BP 미스 복구 안내 — 다른 BP 번호 추측 재시도(오도달) 대신 doc-level annexes 목록으로 유도.
        _msg += (
            " — 별표 번호를 추측해 재시도하지 말 것: unit_id 없이 "
            f"{build_provision_id(pid.doc_type, pid.doc_id)} 로 get_provision_detail을 호출해 "
            "annexes 목록의 provision_id에서 선택할 것(별지·서식은 BP 조회 불가)"
        )
    return {
        "errors": [{
            "code": "not_found",
            "message": _msg,
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

== MCP 적용 범위 (49개 규정) ==
- Tier 1 (혁신법 family): 혁신법(일반법)·시행령·시행규칙
- Tier 1 (Sector — 국토교통 R&D family): 국토교통과학기술 육성법(특별법)·시행령·시행규칙
- Tier 1 (Sector — 산업기술 R&D family): 산업기술혁신 촉진법·시행령·시행규칙
- Tier 1 (Sector — 중소기업 R&D family): 중소기업 기술혁신 촉진법·시행령·시행규칙
- Tier 1 (Sector — 보건의료 R&D family): 보건의료기술 진흥법·시행령·시행규칙
- Tier 1 (Sector — 학술진흥 R&D family): 학술진흥법·시행령·시행규칙(교육부)
- Tier 1 (Sector — 산학협력 R&D family): 산업교육진흥 및 산학연협력촉진법·시행령·시행규칙(교육부)
- Tier 1 (Sector — 기업부설연구소 R&D family): 기업부설연구소등의 연구개발 지원에 관한 법률·시행령·시행규칙(과기정통부)
- Tier 1 (Sector — 연구산업 R&D family): 연구산업진흥법·시행령·시행규칙(과기정통부)
- Tier 1 (성과평가 family): 국가연구개발사업 등의 성과평가 및 성과관리에 관한 법률·시행령
- Tier 2 (공통 행정규칙): 연구개발비 사용 기준·동시수행 제한·시설장비 표준지침·연구노트 지침·국가연구개발정보처리기준·국가연구개발사업 보안대책·과학기술정보통신부 소관 과학기술분야 연구개발사업 처리규정·정보통신·방송 연구개발 관리규정·정보통신·방송 연구윤리 진실성 확보 등에 관한 규정·연구윤리 확보를 위한 지침(교육부)
- Tier 2 (사업 운영규정·요령): 국토교통부소관 연구개발사업 운영규정, 산업기술혁신사업 공통 운영요령, 중소기업기술개발 지원사업 운영요령, 기술료 징수 및 관리에 관한 통합요령(산업부), 중소기업기술개발 지원사업 기술료 관리규정(중기부), 보건의료기술 연구개발사업 운영·관리규정(보건복지부)
- Tier 2 (Sector — 질병관리청 R&D 행정규칙): 질병관리청 연구개발 관리 규정, 전문기관 지정 고시, 시설·장비 관리 규정, 범부처 이어달리기 공통운영 지침(질병관리청 사본)
- 미커버: 국가연구개발혁신법 매뉴얼, 기관 내부 기준, 기타 부처별 매뉴얼·가이드
- 미커버 자료가 결론에 필요하면 단정하지 말고 "추가 확인 필요"로 표시할 것.
- 일반법 vs 특별법 적용 우선순위는 사안의 특성에 따라 판단할 것.

== 검토 절차 (반드시 본 순서 준수) ==

1. 핵심 쟁점 파악 및 검색 키워드 작성
   - 상황의 핵심 행위·주체·절차·금액·기간 등을 분해하여 검토할 것.
   - 권한 있는 기관(중앙행정기관·전문기관·연구개발기관 등)의 승인·보고·통보 대상인지 확인할 것.
   - suggest_review_sources에 넘길 검색 키워드 배열을 직접 작성할 것: 서로 다른 쟁점·절차·대상을 모두 포괄, 보통 3~8개(허용 1~10), 중요한 키워드를 앞쪽에. 국가·사업·연구개발 같은 지나치게 광범위한 단어는 제외하되 승인·통보·보고 같은 절차어는 포함할 것. 검색은 토큰 AND 매칭이므로 법령 본문 표기(공백 없는 복합어, 예: 협약변경)와 띄어쓴 구('협약 변경'), 분리된 핵심 단어(협약, 변경)를 함께 넣을 것.
   - 키워드는 상황 표면의 단어를 복사하는 데 그치지 말고, 그 상황에 적용될 법령상 절차·개념어를 추론하여 채울 것. 사용자가 쓴 표현이 일상어이면 대응하는 정식 법령 용어로 변환할 것. 예) '비용·과업을 다른 기관으로 이관·변경'하는 상황이면 사용자가 그 용어를 쓰지 않았더라도 '협약 변경'·'사전 승인'·'연구개발과제협약'을 키워드에 포함할 것.
   - keywords는 본 검토의 필수 입력이다 — keywords 없이 suggest_review_sources를 호출하지 말 것. 검토 결과 품질은 keywords 품질에 직접 좌우된다.

2. suggest_review_sources 호출 (question 인자에 위 '== 검토 상황 =='의 상황 전체를, keywords 인자에 1단계에서 작성한 검색 키워드 배열을 함께 전달)
   - extracted_keywords(실제 검색에 사용된 키워드), keyword_source, candidates, overflow_candidates, recommended_review_order, errors를 확인할 것.
   - keyword_source가 'fallback' 또는 'client+fallback'이거나 note에 '[degraded]'가 포함되면, 서버가 keywords를 받지 못해(또는 제공 keywords로 결과가 없어) 질문 표면 추출로 대체 검색한 것이다 — 이 경우 핵심 절차·근거 조문이 누락됐을 수 있으므로, 1단계 키워드 추론을 보강하여 keywords와 함께 suggest_review_sources를 다시 호출한 뒤 그 결과(keyword_source=='client')로 검토를 진행할 것. degraded 응답의 candidates만으로 결론을 내지 말 것. 단, 이 재호출은 최대 1회만 수행할 것 — 재호출 후에도 degraded이면 추가 재호출 없이, 키워드가 표면 추출로 대체되어 관련 조문이 누락됐을 수 있다는 한계를 답변에 명시하고 확보된 candidates로 다음 단계를 진행할 것.
   - recommended_review_order는 기본 검토 순서로 삼되, 후보가 적으면 3단계에서 보완할 것.
   - returned·truncated·note·overflow_truncated도 확인할 것: truncated가 true이면 candidates에서 밀린 조문이 overflow_candidates에 제목(label)·provision_id로 나열되니, 관련 있어 보이는 항목은 candidates와 중복 제거 후 4단계에서 그 provision_id로 get_provision_detail을 직접 호출해 확인할 것. overflow_truncated가 true이거나 쟁점상 후보가 부족하면 recommended_review_order의 전체 문서 목록을 기준으로 3단계에서 search_provision으로 추가 보완할 것.

3. search_provision(query=...)으로 추가 검색 및 주제별 cross-check
   - 핵심 키워드, 법령상 유사어, 절차어(승인, 통보, 보고, 협약변경, 정산, 제재 등)로 검색할 것.
   - suggest_review_sources 후보와 중복 제거 후 통합할 것.
   - 주제별 Tier 2 cross-check (해당 시):
     연구개발비/예산/비목/집행 → rnd_funding_standard | 동시수행/과제 수 → simultaneous_research_limit
     시설/장비/기자재 → facility_equipment_standard | 연구노트/실험노트 → research_note_guideline
   - 공통/사업 행정규칙 cross-check (해당 시):
     정보등록/IRIS/NTIS → rnd_info_processing | 보안과제/연구보안 → rnd_security_measures | 성과평가/성과관리 → performance_eval_act + decree
     기술료/정부납부기술료 → tech_fee_integrated · sme_tech_fee | 정보통신·방송 R&D → ict_rnd_management · ict_research_ethics
     보건의료기술 R&D/병원연구/의료기기 → health_tech_act · health_tech_decree · health_tech_rule · health_rnd_operating
     감염병·질병관리·질병관리청 R&D → kdca_rnd_management · kdca_agency_designation · kdca_facility_equipment · kdca_relay_operating
     산학협력/산학연협력/기술지주회사/협력연구소 → sanhak_act · sanhak_decree · sanhak_rule | 연구윤리/연구부정행위/연구진실성 → research_ethics_guideline
     기업부설연구소/연구개발전담부서/연구소 인정 → corp_lab_act · corp_lab_decree · corp_lab_rule
     연구산업/연구개발서비스업/연구장비산업 → research_industry_act · research_industry_decree · research_industry_rule

4. 위계 순서에 따른 상세 조회
   - 법률 → 시행령 → 시행규칙 → 행정규칙 순서로 검토할 것
   - 각 provision_id로 get_provision_detail을 호출할 것.
   - content는 OpenAPI 원문을 그대로 사용할 것.
     - OpenAPI로부터 입수한 조문의 원문을 임의로 수정(요약, paraphrase 등)하지 말 것.
     - OpenAPI로부터 입수한 조문의 항·호·목 번호를 유지할 것.
     - 단, content_format이 plain_text_verbatim이 아닌 경우(예: oversized_pointer, external_file_only)에는 그 content가 규정 원문이 아니라 안내 텍스트이므로 근거로 인용하지 말고, attached_file_url·document_source_url의 공식 원문을 확인할 것.
   - 규정의 조문·별표 본문은 임의 웹검색 결과나 law.go.kr 직접 열람 등 외부 웹에서 가져와 대체·보충하지 말고 get_provision_detail이 반환한 content로 확인할 것. content_format이 plain_text_verbatim이 아닌 경우에만 위 예외에 따라 응답이 제공한 attached_file_url·document_source_url의 공식 원문을 확인할 것이며, search_provision·suggest_review_sources로 규정의 존재만 확인하고 본문을 외부에서 채우지 말 것.
   - 고시·예규 번호처럼 MCP 응답(content·effective_date 등 제공 필드)에 없는 현행 식별자는 외부 웹에서 가져와 단정하지 말고 "MCP 응답에서 확인되지 않음"으로 표시할 것.
   - 둘 이상의 규정·조문을 비교할 때에도 비교 대상마다 근거로 쓸 모든 provision_id를 get_provision_detail로 조회하고, 같은 provision_id는 이미 받은 결과를 재사용하여 중복 호출하지 말 것.

5. 참조 조항 추적
   - 조문이 "제X조에 따라", "시행령 제X조", "별표", "고시로 정하는" 등을 참조하면 해당 조항도 조회할 것.
   - 별표(BP)는 행정규칙·시행령 모두 get_provision_detail로 조회 가능하다(v0.2). 소형 별표는 본문 전문이 오지만, 대용량 별표는 content_format이 oversized_pointer/external_file_only로 본문이 미수록될 수 있으니 위 4단계의 content_format 규칙(plain_text_verbatim이 아니면 인용 금지)을 따를 것.
   - 별표 상세 응답에 dependent_article_hints가 있으면, 힌트에 적힌 조문을 같은 문서에서 get_provision_detail로 함께 조회할 것. 힌트는 별표 제목에서 뽑은 미검증 단서이므로 힌트 자체를 근거로 인용하지 말고, 조회된 조문 원문만 근거로 삼을 것. 이 동반 조회는 힌트에 적힌 조문 1단계까지만 자동 수행하고, 그 조문에서 이어지는 참조는 본 5단계의 일반 규칙에 따를 것.
   - 별표 번호나 가지번호가 불확실하면 BP provision_id를 추측해 호출하지 말 것. 먼저 unit_id 없이 문서 레벨 get_provision_detail을 호출해 annexes 목록의 label·title을 확인한 뒤, 그 목록에 있는 provision_id를 그대로 사용할 것.
   - 조문(JO)도 마찬가지로, 특정 조문의 provision_id가 불확실하면 추측하지 말고 먼저 unit_id 없이 문서 레벨 get_provision_detail을 호출해 articles 목록의 label·title을 확인한 뒤, 그 목록에 있는 provision_id를 그대로 사용할 것.
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
- 아래 1~7절의 제목과 순서는 항상 그대로 사용할 것. 8절(절차 흐름)은 조건부 절이므로, 아래 8절의 조건에 해당할 때만 7절 뒤에 추가하고, 해당하지 않으면 제목도 작성하지 말 것.
- 중요한 정보 위주로 답변을 구성할 것.
- 불필요한 정보가 답변에 포함되지 않도록 주의할 것.
  - 단, 근거 조항의 원문 인용은 생략·요약하지 말 것.

## 【규정 검토 결과】

### 1. 상황 요약
[1-2문장으로 핵심 사실과 쟁점을 요약할 것.]

### 2. 검토 규정
- Tier 1 법률·시행령·시행규칙: [규정명 목록]
- Tier 2 행정규칙: [규정명 목록, 없으면 "해당 없음"]

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

### 8. 절차 흐름
[검토 결과의 핵심이 둘 이상의 시간순 단계(예: 신청 → 협의 → 승인 → 보고) 또는 [예]/[아니오] 조건 분기를 포함하는 경우에만 작성할 것. 단순 정의·단일 조항 설명·단일 승인/보고 필요 여부 판단이면 본 절 전체(제목 포함)를 생략할 것.]
- 흐름은 언어 지정 없는 Markdown 코드블록 안에 번호 단계와 화살표(→)로 작성하여 모든 클라이언트에서 읽히도록 할 것.
- 각 단계에는 근거 규정명·조문번호를 함께 표시하고, 4절 근거 조항 및 7절 권고 조치와 일치시킬 것.
- 4절 또는 7절에서 직접 확인되지 않은 접수·검토·결재·통보 등 일반 실무 단계는 흐름을 매끄럽게 만들기 위해 임의로 추가하지 말 것.
- 조건 분기는 [예]/[아니오]로 표시하고, 규정상 선후관계가 확인되지 않으면 순서로 단정하지 말고 "추가 확인 필요"로 표시할 것.
"""


@mcp.prompt(
    name="review_regulation",
    title="규정 검토 (표준 워크플로 기반 1차 검토)",
    description=(
        "본 MCP 적용 범위 내 국가연구개발 및 국토교통·산업·중소기업·보건의료·질병관리 R&D 연구행정 규정 검토 — 혁신법·시행령·시행규칙·"
        "부처별 R&D family·핵심 행정규칙(연구개발비 사용기준·정보처리·보안·성과평가·기술료 등)의 근거 조항을 "
        "verbatim 인용과 함께 답변. Tier 1 → Tier 2 위계 순서 + provision_id 인용을 "
        "본 MCP server 도구(suggest_review_sources, get_provision_detail)로 자동 적용. "
        "OpenAPI 미수록 매뉴얼·기관 내부 기준·본 manifest 미등록 전문기관 지침은 본 server 미커버 — 별도 자료 확인 필요."
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
                "ministry": rs.ministry,
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
            token_http = _is_http_request.set(True)  # v0.2.11: HTTP transport 신호(no-oc 차단용)
            try:
                await self.app(scope, receive, send)
            finally:
                _is_http_request.reset(token_http)
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
        uvicorn_config={"access_log": False},  # v0.2.11: ?oc= 키가 uvicorn access log에 기록되는 것 차단
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
