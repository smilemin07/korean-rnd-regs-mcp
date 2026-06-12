"""korean-rnd-regs-mcp main entry — stdio / HTTP MCP server."""
import argparse
import asyncio
import contextvars
import json
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

mcp = FastMCP("korean-rnd-regs-mcp", version=__version__)

_DISCLAIMER = "본 결과는 검토 후보일 뿐 법률 판단이 아닙니다. 출처를 직접 확인하세요."
_SNIPPET_MAX = 2000
_SEARCH_RESPONSE_CHAR_BUDGET = 16000  # v0.2.5: search_provision 전체 응답 직렬화 예산 (25k token 한도의 보수 proxy — suggest와 동일 사상)
_RESULTS_MAX = 30
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
# 전문 verbatim 판정 시 호출부가 사후 추가하는 필드(revision_notice 등, ~100자)용 헤드룸을 예산에서 차감(보수적).
_ANNEX_DETAIL_HEADROOM = 300


def _build_annex_detail(provision_id: str, unit_id: str, rs, ann: dict, eff_date: str) -> dict:
    """별표 단위 상세 응답 (v0.2, size-tiered + verbatim 정확성 가드).

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
    # 호출부가 사후 추가하는 revision_notice 등을 고려해 헤드룸만큼 차감한 보수 예산으로 판정
    if len(json.dumps(full, ensure_ascii=False)) <= _ANNEX_DETAIL_CHAR_BUDGET - _ANNEX_DETAIL_HEADROOM:
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
    errors: list[dict] = []

    async def _fetch_rule_set(rs):
        resolved = await _resolve_doc_id(rs, client)
        doc_id = resolved.doc_id
        if rs.api_target == ApiTarget.LAW:
            detail = await asyncio.to_thread(client.get_law_detail, doc_id)
            return (rs, resolved, detail.get("articles", []),
                    detail.get("annexes", []), detail.get("annex_parse_error"))
        else:
            detail = await asyncio.to_thread(client.get_admin_rule_detail, doc_id)
            return (rs, resolved, detail.get("articles", []),
                    detail.get("annexes", []), None)

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
                        matches.append(_build_match(rs, f"JO{int(art_no):04d}", "article", title, snippet, resolved))

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
                        matches.append(_build_match(rs, unit_id, "annex", title, snippet, resolved))

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
    """본 도구는 법률 판단을 하지 않습니다. 사용자 질문과 핵심 검색 키워드로 검토할 rule set·후보 조문·검토 순서만 반환합니다.

    가능하면 keywords 인자에 호스트 LLM이 추출한 핵심 검색어 배열을 함께 전달하십시오(question에는 검토 상황 전체).
    keywords가 제공되면 서버의 단순 규칙 추출보다 우선 사용되며, 생략·무효 시에만 규칙 추출로 대체됩니다.
    응답의 candidates는 상위 일부만 포함합니다(cap). cap에 밀린 조문은 overflow_candidates에
    [label·provision_id]로 함께 반환되니, 관련 있어 보이면 그 provision_id로 get_provision_detail을 호출해 확인하십시오.
    최종 판단은 사용자의 책임이며, 별표·매뉴얼·기관 운영규정 별도 확인이 필요합니다.
    """
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
        matches: dict[str, dict] = {}
        errors: list[dict] = []
        term_cache: dict[str, dict] = {}
        for term, origin in _build_search_terms(kw_list):
            if term not in term_cache:
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
    - unit_id 생략 시 document-level 요약 반환 — annexes 목록(별표 제목·provision_id·deleted 표시,
      v0.2.1)이 포함되므로, 별표 번호가 불확실하면 추측하지 말고 이 목록에서 선택할 것.
    - unit_id가 JO… 면 조문 본문 + article_structure, BP… 면 별표 본문 (행정규칙·법령 시행령 모두,
      v0.2; size-tiered). BP는 4자리(본별표, 예: BP0001=별표 1) 또는 6자리(가지별표 번호4+가지2,
      예: BP000102=별표 1의2, v0.2.1). 별지·서식은 별표가 아니므로 BP로 조회 불가.
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
        annex_parse_error: str | None = None
        if pid.doc_type == "law":
            detail = await asyncio.to_thread(client.get_law_detail, doc_id)
            articles = detail.get("articles", [])
            annexes = detail.get("annexes", [])
            annex_parse_error = detail.get("annex_parse_error")
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
        # v0.2.2: 막다른 길 신호 — 별지·서식은 BP 조회 불가 + hints 미검증 경고 (기존 warnings 문자열만, 신규 필드 없음)
        forms_count = sum(v for k, v in kind_counts.items() if k in ("별지", "서식"))
        if forms_count:
            result["warnings"] = result["warnings"] + [
                f"별지·서식 {forms_count}건은 본 도구로 본문 조회 불가 — document_source_url의 공식 원문에서 확인할 것."
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

== MCP 적용 범위 (25개 규정) ==
- Tier 1 (혁신법 family): 혁신법(일반법)·시행령·시행규칙
- Tier 1 (Sector — 국토교통 R&D family): 국토교통과학기술 육성법(특별법)·시행령·시행규칙
- Tier 1 (Sector — 산업기술 R&D family): 산업기술혁신 촉진법·시행령·시행규칙
- Tier 1 (Sector — 중소기업 R&D family): 중소기업 기술혁신 촉진법·시행령·시행규칙
- Tier 2 (행정규칙): 연구개발비 사용 기준·동시수행 제한·시설장비 표준지침·연구노트 지침, 국토교통부소관 연구개발사업 운영규정, 산업기술혁신사업 공통 운영요령, 중소기업기술개발 지원사업 운영요령
- Supplementary (법률·시행령 6개): 부패방지·청탁금지·공익신고자보호
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
   - Supplementary (해당 시):
     신고/포상금/부패행위 → anti_corruption_act + decree | 부정청탁/금품수수 → improper_solicitation_act + decree
     공익신고/신변보호 → public_interest_whistleblower_act + decree

4. 위계 순서에 따른 상세 조회
   - 법률 → 시행령 → 시행규칙 → 행정규칙 → Supplementary 순서로 검토할 것
   - 각 provision_id로 get_provision_detail을 호출할 것.
   - content는 OpenAPI 원문을 그대로 사용할 것.
     - OpenAPI로부터 입수한 조문의 원문을 임의로 수정(요약, paraphrase 등)하지 말 것.
     - OpenAPI로부터 입수한 조문의 항·호·목 번호를 유지할 것.
     - 단, content_format이 plain_text_verbatim이 아닌 경우(예: oversized_pointer, external_file_only)에는 그 content가 규정 원문이 아니라 안내 텍스트이므로 근거로 인용하지 말고, attached_file_url·document_source_url의 공식 원문을 확인할 것.

5. 참조 조항 추적
   - 조문이 "제X조에 따라", "시행령 제X조", "별표", "고시로 정하는" 등을 참조하면 해당 조항도 조회할 것.
   - 별표(BP)는 행정규칙·시행령 모두 get_provision_detail로 조회 가능하다(v0.2). 소형 별표는 본문 전문이 오지만, 대용량 별표는 content_format이 oversized_pointer/external_file_only로 본문이 미수록될 수 있으니 위 4단계의 content_format 규칙(plain_text_verbatim이 아니면 인용 금지)을 따를 것.
   - 별표 상세 응답에 dependent_article_hints가 있으면, 힌트에 적힌 조문을 같은 문서에서 get_provision_detail로 함께 조회할 것. 힌트는 별표 제목에서 뽑은 미검증 단서이므로 힌트 자체를 근거로 인용하지 말고, 조회된 조문 원문만 근거로 삼을 것. 이 동반 조회는 힌트에 적힌 조문 1단계까지만 자동 수행하고, 그 조문에서 이어지는 참조는 본 5단계의 일반 규칙에 따를 것.
   - 별표 번호나 가지번호가 불확실하면 BP provision_id를 추측해 호출하지 말 것. 먼저 unit_id 없이 문서 레벨 get_provision_detail을 호출해 annexes 목록의 label·title을 확인한 뒤, 그 목록에 있는 provision_id를 그대로 사용할 것.
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
