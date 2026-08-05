"""혁신법 매뉴얼(본권) 데이터 로더·헬퍼 (R1-P2, contract 0.18.0).

- 데이터: 같은 디렉터리의 `manual_body.json` (P1 산출물 — `scripts/extract_manual.py`로 재생성).
- lazy 싱글턴: import 시 미로드(부팅·기존 도구 무접촉 — outage 격리), 최초 도구 호출 시 1회 파싱.
  로드+사전계산 실측 ~3ms(기존 load_manifest가 매 요청 ~24ms 인라인인 것 대비 노이즈 수준)라
  executor offload 없이 인라인 수행(계획 /disc 3-AI 실측 tiebreak).
- 실패 fail-safe: 파일 부재·파싱 실패·스키마 이상은 예외 전파 없이 ManualLoadError로 캐시
  → 도구가 `manual_unavailable` 오류 envelope을 반환(기존 5종 도구·부팅에 무영향).
- 예산 상수는 main.py의 annex 상수와 동일 값·동일 사상(25k 토큰 한도의 보수 char proxy).
  순환 import 회피를 위해 본 모듈에 독립 정의하며, 값 일치는 테스트로 잠근다.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

# main.py의 _ANNEX_DETAIL_CHAR_BUDGET(16000)·_ANNEX_DETAIL_HEADROOM(600)·
# _ANNEX_CHUNK_CONTENT_BUDGET(12000)과 동일 값 — 변경 시 양쪽 함께(테스트 잠금).
# v0.37.0: 헤드룸 300→600 동반 상향(annex 쪽 resolve 상태 고지 2종 사후주입 대비 — parity 원칙 유지.
# 매뉴얼 응답에는 해당 고지가 없으나 상수 사상 통일이 우선·강등 경계 보수화는 안전 방향).
MANUAL_DETAIL_CHAR_BUDGET = 16000
MANUAL_DETAIL_HEADROOM = 600
MANUAL_CHUNK_CONTENT_BUDGET = 12000

SECTION_ID_RE = re.compile(
    r"^(?:\d+-\d+|ref-\d+|b3-(?:\d+-\d+|ref-\d+)|b2-(?:\d+-\d+|ref-\d+)|b1-(?:\d+-\d+|ref-\d+)"
    r"|eval-(?:\d+-\d+|ref-\d+)|b4-(?:\d+|ref-\d+))$"
)
# ★b4는 단일 레벨(b4-0~b4-9·b4-ref-1) — 별권 4는 장(章) 없는 평면 편제라 인위 2레벨을 만들지
# 않는다(v0.39.0 계획 /disc 3/3). b4-1-1형은 매치 실패 = invalid_section_id(의도 동작).
# b4-99처럼 형식은 유효하나 실재하지 않는 id는 not_found로 안내된다.

_DATA_PATH = Path(__file__).parent / "manual_body.json"


@dataclass
class ManualLoadError:
    """데이터 로드 실패(파일 부재·파싱 실패·스키마 이상) — 예외 대신 캐시되는 fail-safe 객체."""

    reason: str  # file_missing | json_parse_failed | schema_invalid
    message: str


@dataclass
class ManualData:
    meta: dict
    sections: list  # 원본 순서(section_index) 유지
    by_id: dict = field(default_factory=dict)
    full_text: dict = field(default_factory=dict)  # id -> "\n".join(page texts)
    norm_body: dict = field(default_factory=dict)  # id -> 매칭용 정규화 본문
    norm_title: dict = field(default_factory=dict)  # id -> 매칭용 정규화 제목군


_LOCK = threading.Lock()
_CACHE: ManualData | ManualLoadError | None = None

# 별권 3 「국가연구개발사업 제재처분 가이드라인」 — 본권과 독립된 파일·캐시·오류
# (R2-P0 동결 D4: 별권 결함이 본권 서빙에 전파되지 않도록 작은 병렬 경로로 복제·본권 로더 무변).
_B3_DATA_PATH = Path(__file__).parent / "manual_b3.json"
_B3_LOCK = threading.Lock()
_B3_CACHE: ManualData | ManualLoadError | None = None

# 별권 2 「국가연구개발사업 기술료 제도 매뉴얼」 — 동일 사상의 독립 병렬 경로 (R3-P0 D4).
_B2_DATA_PATH = Path(__file__).parent / "manual_b2.json"
_B2_LOCK = threading.Lock()
_B2_CACHE: ManualData | ManualLoadError | None = None

# 별권 1 「학생인건비통합관리 제도 매뉴얼」 — 동일 사상의 독립 병렬 경로 (R4-P0 D9).
_B1_DATA_PATH = Path(__file__).parent / "manual_b1.json"
_B1_LOCK = threading.Lock()
_B1_CACHE: ManualData | ManualLoadError | None = None

# 「국가연구개발 과제평가 표준지침」(25.12) — 매뉴얼 트랙 최초의 비(非)혁신법-매뉴얼 독립 소스
# (v0.38.0). 동일 사상의 독립 병렬 경로 — 한 소스 실패는 그 소스 조회에만 격리된다.
_EVAL_DATA_PATH = Path(__file__).parent / "manual_eval.json"
_EVAL_LOCK = threading.Lock()
_EVAL_CACHE: ManualData | ManualLoadError | None = None

# 별권 4 「연구시설･장비비 통합관리제 운영･관리 매뉴얼」 — 동일 사상의 독립 병렬 경로 (v0.39.0 R5).
_B4_DATA_PATH = Path(__file__).parent / "manual_b4.json"
_B4_LOCK = threading.Lock()
_B4_CACHE: ManualData | ManualLoadError | None = None


def mdot_normalize(s: str) -> str:
    """매칭 전용 가운뎃점 정규화 — ㆍ(U+318D)·･(U+FF65) → ·(U+00B7).

    P1 데이터는 ･(반각)이 지배적(1,792회)인데 사용자·호스트는 ·/ㆍ로 입력하므로 3형을 통합.
    발췌·content는 raw 유지(원문 보존) — annex_locate의 _locate_normalize와 동일 사상.
    """
    return s.replace("ㆍ", "·").replace("･", "·")


def _json_escaped_len(s: str) -> int:
    """JSON 직렬화 본문 길이(감싸는 따옴표 2자 제외) — main.py 동명 헬퍼와 동일(순환 import 회피 독립 정의)."""
    return len(json.dumps(s, ensure_ascii=False)) - 2


def load_manual() -> ManualData | ManualLoadError:
    """manual_body.json lazy 싱글턴 로드 (double-checked locking·실패도 캐시)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        _CACHE = _load_uncached()
        return _CACHE


def _load_uncached() -> ManualData | ManualLoadError:
    if not _DATA_PATH.exists():
        return ManualLoadError(
            reason="file_missing",
            message=(
                "매뉴얼 데이터 파일(manual_body.json)이 패키지에 없습니다 — 패키징 누락 가능. "
                "이 오류는 매뉴얼 데이터 로드에 한정되며 기존 규정 도구 경로에는 전파되지 않습니다."
            ),
        )
    try:
        with open(_DATA_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except (ValueError, OSError) as exc:
        return ManualLoadError(
            reason="json_parse_failed",
            message=(
                f"매뉴얼 데이터 파일 파싱 실패({type(exc).__name__}) — 이 오류는 매뉴얼 데이터 "
                "로드에 한정되며 기존 규정 도구 경로에는 전파되지 않습니다."
            ),
        )
    meta = payload.get("meta")
    sections = payload.get("sections")
    if not isinstance(meta, dict) or not isinstance(sections, list) or not sections:
        return ManualLoadError(
            reason="schema_invalid",
            message=(
                "매뉴얼 데이터 스키마 이상(meta/sections 부재) — 이 오류는 매뉴얼 데이터 로드에 "
                "한정되며 기존 규정 도구 경로에는 전파되지 않습니다."
            ),
        )
    # v0.39.0(diff 적대검토 Codex MAJOR 반영): 인덱스 구축 중 예외(유효 JSON이나 원소가 null·
    # 타입 이상인 구조 손상)를 envelope로 격리 — 종전에는 예외가 도구 호출로 누출되어
    # manual_unavailable 대신 스택 오류가 됐다(별권 로더들의 기존 try/except와 동형화.
    # 검증 규칙 추가는 하지 않음 — 현행 정상 데이터의 수용 거동 불변).
    try:
        data = ManualData(meta=meta, sections=sections)
        for sec in sections:
            sid = sec.get("id", "")
            data.by_id[sid] = sec
            full = "\n".join(p.get("text", "") for p in sec.get("pages", []))
            data.full_text[sid] = full
            data.norm_body[sid] = mdot_normalize(full)
            title_fields = " ".join(
                [sec.get("section_title", ""), sec.get("chapter_title", ""), sec.get("section_label", "")]
                + list(sec.get("subsection_titles", []))
            )
            data.norm_title[sid] = mdot_normalize(title_fields)
    except Exception as exc:
        return ManualLoadError(
            reason="schema_invalid",
            message=(
                f"매뉴얼 데이터 구조 손상({type(exc).__name__}) — 인덱스 구축 실패. 이 오류는 "
                "매뉴얼 데이터 로드에 한정되며 기존 규정 도구 경로에는 전파되지 않습니다."
            ),
        )
    return data


def load_manual_b3() -> ManualData | ManualLoadError:
    """manual_b3.json lazy 싱글턴 로드 — 본권 load_manual과 동일 패턴의 독립 병렬 경로.

    실패는 별권 조회·검색 병합에서만 격리 처리되고 본권·규정 도구에 영향을 주지 않는다(동결 D4·D5).
    """
    global _B3_CACHE
    if _B3_CACHE is not None:
        return _B3_CACHE
    with _B3_LOCK:
        if _B3_CACHE is not None:
            return _B3_CACHE
        _B3_CACHE = _load_b3_uncached()
        return _B3_CACHE


def _load_b3_uncached() -> ManualData | ManualLoadError:
    """메시지는 별권 자신의 상태만 말한다 — 본권·규정 도구 상태 단정은 호출부(envelope)가
    실제 확인 후 조립(P2 적대검토: 모두 불가 조합에서 허위 "정상" 단정 차단)."""
    if not _B3_DATA_PATH.exists():
        return ManualLoadError(
            reason="file_missing",
            message="별권 3 데이터 파일(manual_b3.json)이 패키지에 없습니다 — 패키징 누락 가능.",
        )
    try:
        with open(_B3_DATA_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except (ValueError, OSError) as exc:
        return ManualLoadError(
            reason="json_parse_failed",
            message=f"별권 3 데이터 파일 파싱 실패({type(exc).__name__}).",
        )
    if not isinstance(payload, dict):
        return ManualLoadError(
            reason="schema_invalid",
            message="별권 3 데이터 스키마 이상(최상위가 객체 아님).",
        )
    meta = payload.get("meta")
    sections = payload.get("sections")
    if not isinstance(meta, dict) or not isinstance(sections, list) or not sections:
        return ManualLoadError(
            reason="schema_invalid",
            message="별권 3 데이터 스키마 이상(meta/sections 부재).",
        )
    # 인덱스 구축 전체를 방어 — 구조가 어긋난 손상 파일(비객체 section·비리스트 pages 등)이
    # 예외를 전파하면 병합 검색까지 죽어 "별권 결함 격리" 계약(D4)이 깨진다(P2 적대검토 MAJOR).
    try:
        data = ManualData(meta=meta, sections=sections)
        for sec in sections:
            if not isinstance(sec, dict):
                raise TypeError(f"section 원소 타입 이상: {type(sec).__name__}")
            sid = sec.get("id", "")
            if not isinstance(sid, str) or not sid:
                raise TypeError("section id 이상")
            pages = sec.get("pages", [])
            if not isinstance(pages, list):
                raise TypeError("pages 타입 이상")
            data.by_id[sid] = sec
            full = "\n".join(p.get("text", "") for p in pages if isinstance(p, dict))
            data.full_text[sid] = full
            data.norm_body[sid] = mdot_normalize(full)
            title_fields = " ".join(
                [str(sec.get("section_title", "")), str(sec.get("chapter_title", "")), str(sec.get("section_label", ""))]
                + [str(x) for x in sec.get("subsection_titles", []) if isinstance(x, str)]
            )
            data.norm_title[sid] = mdot_normalize(title_fields)
    except Exception as exc:
        return ManualLoadError(
            reason="schema_invalid",
            message=f"별권 3 데이터 구조 손상({type(exc).__name__}) — 인덱스 구축 실패.",
        )
    return data


def load_manual_b2() -> ManualData | ManualLoadError:
    """manual_b2.json lazy 싱글턴 로드 — 별권 3와 동일 사상의 독립 병렬 경로 (R3-P0 D4)."""
    global _B2_CACHE
    if _B2_CACHE is not None:
        return _B2_CACHE
    with _B2_LOCK:
        if _B2_CACHE is not None:
            return _B2_CACHE
        _B2_CACHE = _load_b2_uncached()
        return _B2_CACHE


def _load_b2_uncached() -> ManualData | ManualLoadError:
    """별권 3 방어 로더 복제 + R3-P0 D4 추가 검증(신규 로더 한정 — 기존 로더 무변).

    추가 검증: id 중복 0·b2- 프리픽스·section_index 연속·pages 비어 있지 않음·printed_page
    정수·text 문자열·meta.section_count 일치. 손상 파일이 부분 성공(중복 id 덮어쓰기 등)으로
    보이는 공백 차단(P1 적대검토). 메시지는 별권 자신의 상태만 말한다.
    """
    if not _B2_DATA_PATH.exists():
        return ManualLoadError(
            reason="file_missing",
            message="별권 2 데이터 파일(manual_b2.json)이 패키지에 없습니다 — 패키징 누락 가능.",
        )
    try:
        with open(_B2_DATA_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except (ValueError, OSError) as exc:
        return ManualLoadError(
            reason="json_parse_failed",
            message=f"별권 2 데이터 파일 파싱 실패({type(exc).__name__}).",
        )
    if not isinstance(payload, dict):
        return ManualLoadError(
            reason="schema_invalid",
            message="별권 2 데이터 스키마 이상(최상위가 객체 아님).",
        )
    meta = payload.get("meta")
    sections = payload.get("sections")
    if not isinstance(meta, dict) or not isinstance(sections, list) or not sections:
        return ManualLoadError(
            reason="schema_invalid",
            message="별권 2 데이터 스키마 이상(meta/sections 부재).",
        )
    try:
        data = ManualData(meta=meta, sections=sections)
        for idx, sec in enumerate(sections):
            if not isinstance(sec, dict):
                raise TypeError(f"section 원소 타입 이상: {type(sec).__name__}")
            sid = sec.get("id", "")
            if not isinstance(sid, str) or not sid.startswith("b2-"):
                raise TypeError(f"section id 이상: {sid!r}")
            if sid in data.by_id:
                raise TypeError(f"section id 중복: {sid!r}")
            if sec.get("section_index") != idx:
                raise TypeError(f"section_index 불연속: {sid!r}")
            pages = sec.get("pages")
            if not isinstance(pages, list) or not pages:
                raise TypeError(f"pages 비어 있음/타입 이상: {sid!r}")
            for p in pages:
                if not isinstance(p, dict) or not isinstance(p.get("printed_page"), int) \
                        or not isinstance(p.get("text"), str):
                    raise TypeError(f"page 항목 타입 이상: {sid!r}")
            data.by_id[sid] = sec
            full = "\n".join(p.get("text", "") for p in pages)
            data.full_text[sid] = full
            data.norm_body[sid] = mdot_normalize(full)
            title_fields = " ".join(
                [str(sec.get("section_title", "")), str(sec.get("chapter_title", "")), str(sec.get("section_label", ""))]
                + [str(x) for x in sec.get("subsection_titles", []) if isinstance(x, str)]
            )
            data.norm_title[sid] = mdot_normalize(title_fields)
        if meta.get("section_count") != len(sections):
            raise TypeError(f"meta.section_count {meta.get('section_count')!r} != 실제 {len(sections)}")
    except Exception as exc:
        return ManualLoadError(
            reason="schema_invalid",
            message=f"별권 2 데이터 구조 손상({type(exc).__name__}) — 인덱스 구축 실패.",
        )
    return data


def load_manual_b1() -> ManualData | ManualLoadError:
    """manual_b1.json lazy 싱글턴 로드 — 별권 2·3와 동일 사상의 독립 병렬 경로 (R4-P0 D9)."""
    global _B1_CACHE
    if _B1_CACHE is not None:
        return _B1_CACHE
    with _B1_LOCK:
        if _B1_CACHE is not None:
            return _B1_CACHE
        _B1_CACHE = _load_b1_uncached()
        return _B1_CACHE


def _load_b1_uncached() -> ManualData | ManualLoadError:
    """별권 2 강화 로더 복제(b1- 프리픽스) — 기존 로더 무변.

    추가 검증: id 중복 0·b1- 프리픽스·section_index 연속·pages 비어 있지 않음·printed_page
    정수·text 문자열·meta.section_count 일치. 메시지는 별권 자신의 상태만 말한다.
    """
    if not _B1_DATA_PATH.exists():
        return ManualLoadError(
            reason="file_missing",
            message="별권 1 데이터 파일(manual_b1.json)이 패키지에 없습니다 — 패키징 누락 가능.",
        )
    try:
        with open(_B1_DATA_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except (ValueError, OSError) as exc:
        return ManualLoadError(
            reason="json_parse_failed",
            message=f"별권 1 데이터 파일 파싱 실패({type(exc).__name__}).",
        )
    if not isinstance(payload, dict):
        return ManualLoadError(
            reason="schema_invalid",
            message="별권 1 데이터 스키마 이상(최상위가 객체 아님).",
        )
    meta = payload.get("meta")
    sections = payload.get("sections")
    if not isinstance(meta, dict) or not isinstance(sections, list) or not sections:
        return ManualLoadError(
            reason="schema_invalid",
            message="별권 1 데이터 스키마 이상(meta/sections 부재).",
        )
    try:
        data = ManualData(meta=meta, sections=sections)
        for idx, sec in enumerate(sections):
            if not isinstance(sec, dict):
                raise TypeError(f"section 원소 타입 이상: {type(sec).__name__}")
            sid = sec.get("id", "")
            # ★prefix에 더해 라우팅 정규식 일치까지 강제(R4 diff 적대검토 Codex 반영) —
            # 검색에는 노출되나 상세 조회는 invalid_section_id가 되는 불일치 id 차단.
            if not isinstance(sid, str) or not sid.startswith("b1-") or not SECTION_ID_RE.match(sid):
                raise TypeError(f"section id 이상: {sid!r}")
            if sid in data.by_id:
                raise TypeError(f"section id 중복: {sid!r}")
            if sec.get("section_index") != idx:
                raise TypeError(f"section_index 불연속: {sid!r}")
            pages = sec.get("pages")
            if not isinstance(pages, list) or not pages:
                raise TypeError(f"pages 비어 있음/타입 이상: {sid!r}")
            for p in pages:
                # printed_page는 type is int(bool은 int의 서브클래스라 isinstance로는 통과 — 거부)
                if not isinstance(p, dict) or type(p.get("printed_page")) is not int \
                        or not isinstance(p.get("text"), str):
                    raise TypeError(f"page 항목 타입 이상: {sid!r}")
            data.by_id[sid] = sec
            full = "\n".join(p.get("text", "") for p in pages)
            data.full_text[sid] = full
            data.norm_body[sid] = mdot_normalize(full)
            title_fields = " ".join(
                [str(sec.get("section_title", "")), str(sec.get("chapter_title", "")), str(sec.get("section_label", ""))]
                + [str(x) for x in sec.get("subsection_titles", []) if isinstance(x, str)]
            )
            data.norm_title[sid] = mdot_normalize(title_fields)
        if meta.get("section_count") != len(sections):
            raise TypeError(f"meta.section_count {meta.get('section_count')!r} != 실제 {len(sections)}")
    except Exception as exc:
        return ManualLoadError(
            reason="schema_invalid",
            message=f"별권 1 데이터 구조 손상({type(exc).__name__}) — 인덱스 구축 실패.",
        )
    return data


def load_manual_eval() -> ManualData | ManualLoadError:
    """manual_eval.json lazy 싱글턴 로드 — 별권 1·2·3와 동일 사상의 독립 병렬 경로 (v0.38.0)."""
    global _EVAL_CACHE
    if _EVAL_CACHE is not None:
        return _EVAL_CACHE
    with _EVAL_LOCK:
        if _EVAL_CACHE is not None:
            return _EVAL_CACHE
        _EVAL_CACHE = _load_eval_uncached()
        return _EVAL_CACHE


def _load_eval_uncached() -> ManualData | ManualLoadError:
    """별권 1 강화 로더 복제(eval- 프리픽스) — 기존 로더 무변.

    추가 검증: id 중복 0·eval- 프리픽스·라우팅 정규식 일치·section_index 연속·pages 비어 있지
    않음·printed_page 정수·text 문자열·meta.section_count 일치. 메시지는 이 소스 자신의 상태만 말한다.
    """
    if not _EVAL_DATA_PATH.exists():
        return ManualLoadError(
            reason="file_missing",
            message="과제평가 표준지침 데이터 파일(manual_eval.json)이 패키지에 없습니다 — 패키징 누락 가능.",
        )
    try:
        with open(_EVAL_DATA_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except (ValueError, OSError) as exc:
        return ManualLoadError(
            reason="json_parse_failed",
            message=f"과제평가 표준지침 데이터 파일 파싱 실패({type(exc).__name__}).",
        )
    if not isinstance(payload, dict):
        return ManualLoadError(
            reason="schema_invalid",
            message="과제평가 표준지침 데이터 스키마 이상(최상위가 객체 아님).",
        )
    meta = payload.get("meta")
    sections = payload.get("sections")
    if not isinstance(meta, dict) or not isinstance(sections, list) or not sections:
        return ManualLoadError(
            reason="schema_invalid",
            message="과제평가 표준지침 데이터 스키마 이상(meta/sections 부재).",
        )
    try:
        data = ManualData(meta=meta, sections=sections)
        for idx, sec in enumerate(sections):
            if not isinstance(sec, dict):
                raise TypeError(f"section 원소 타입 이상: {type(sec).__name__}")
            sid = sec.get("id", "")
            if not isinstance(sid, str) or not sid.startswith("eval-") or not SECTION_ID_RE.match(sid):
                raise TypeError(f"section id 이상: {sid!r}")
            if sid in data.by_id:
                raise TypeError(f"section id 중복: {sid!r}")
            if sec.get("section_index") != idx:
                raise TypeError(f"section_index 불연속: {sid!r}")
            pages = sec.get("pages")
            if not isinstance(pages, list) or not pages:
                raise TypeError(f"pages 비어 있음/타입 이상: {sid!r}")
            for p in pages:
                if not isinstance(p, dict) or type(p.get("printed_page")) is not int \
                        or not isinstance(p.get("text"), str):
                    raise TypeError(f"page 항목 타입 이상: {sid!r}")
            data.by_id[sid] = sec
            full = "\n".join(p.get("text", "") for p in pages)
            data.full_text[sid] = full
            data.norm_body[sid] = mdot_normalize(full)
            title_fields = " ".join(
                [str(sec.get("section_title", "")), str(sec.get("chapter_title", "")), str(sec.get("section_label", ""))]
                + [str(x) for x in sec.get("subsection_titles", []) if isinstance(x, str)]
            )
            data.norm_title[sid] = mdot_normalize(title_fields)
        if meta.get("section_count") != len(sections):
            raise TypeError(f"meta.section_count {meta.get('section_count')!r} != 실제 {len(sections)}")
    except Exception as exc:
        return ManualLoadError(
            reason="schema_invalid",
            message=f"과제평가 표준지침 데이터 구조 손상({type(exc).__name__}) — 인덱스 구축 실패.",
        )
    return data


def load_manual_b4() -> ManualData | ManualLoadError:
    """manual_b4.json lazy 싱글턴 로드 — 별권 1·2·3·과제평가 표준지침과 동일 사상의 독립 병렬 경로 (v0.39.0 R5)."""
    global _B4_CACHE
    if _B4_CACHE is not None:
        return _B4_CACHE
    with _B4_LOCK:
        if _B4_CACHE is not None:
            return _B4_CACHE
        _B4_CACHE = _load_b4_uncached()
        return _B4_CACHE


def _load_b4_uncached() -> ManualData | ManualLoadError:
    """별권 1 강화 로더 복제(b4- 프리픽스) — 기존 로더 무변.

    추가 검증: id 중복 0·b4- 프리픽스·라우팅 정규식 일치(단일 레벨 b4-N·b4-ref-N — 평면 편제)·
    section_index 연속·pages 비어 있지 않음·printed_page 정수·text 문자열·meta.section_count 일치.
    메시지는 별권 자신의 상태만 말한다.
    """
    if not _B4_DATA_PATH.exists():
        return ManualLoadError(
            reason="file_missing",
            message="별권 4 데이터 파일(manual_b4.json)이 패키지에 없습니다 — 패키징 누락 가능.",
        )
    try:
        with open(_B4_DATA_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except (ValueError, OSError) as exc:
        return ManualLoadError(
            reason="json_parse_failed",
            message=f"별권 4 데이터 파일 파싱 실패({type(exc).__name__}).",
        )
    if not isinstance(payload, dict):
        return ManualLoadError(
            reason="schema_invalid",
            message="별권 4 데이터 스키마 이상(최상위가 객체 아님).",
        )
    meta = payload.get("meta")
    sections = payload.get("sections")
    if not isinstance(meta, dict) or not isinstance(sections, list) or not sections:
        return ManualLoadError(
            reason="schema_invalid",
            message="별권 4 데이터 스키마 이상(meta/sections 부재).",
        )
    try:
        data = ManualData(meta=meta, sections=sections)
        for idx, sec in enumerate(sections):
            if not isinstance(sec, dict):
                raise TypeError(f"section 원소 타입 이상: {type(sec).__name__}")
            sid = sec.get("id", "")
            if not isinstance(sid, str) or not sid.startswith("b4-") or not SECTION_ID_RE.match(sid):
                raise TypeError(f"section id 이상: {sid!r}")
            if sid in data.by_id:
                raise TypeError(f"section id 중복: {sid!r}")
            if sec.get("section_index") != idx:
                raise TypeError(f"section_index 불연속: {sid!r}")
            pages = sec.get("pages")
            if not isinstance(pages, list) or not pages:
                raise TypeError(f"pages 비어 있음/타입 이상: {sid!r}")
            for p in pages:
                if not isinstance(p, dict) or type(p.get("printed_page")) is not int \
                        or not isinstance(p.get("text"), str):
                    raise TypeError(f"page 항목 타입 이상: {sid!r}")
            data.by_id[sid] = sec
            full = "\n".join(p.get("text", "") for p in pages)
            data.full_text[sid] = full
            data.norm_body[sid] = mdot_normalize(full)
            title_fields = " ".join(
                [str(sec.get("section_title", "")), str(sec.get("chapter_title", "")), str(sec.get("section_label", ""))]
                + [str(x) for x in sec.get("subsection_titles", []) if isinstance(x, str)]
            )
            data.norm_title[sid] = mdot_normalize(title_fields)
        if meta.get("section_count") != len(sections):
            raise TypeError(f"meta.section_count {meta.get('section_count')!r} != 실제 {len(sections)}")
    except Exception as exc:
        return ManualLoadError(
            reason="schema_invalid",
            message=f"별권 4 데이터 구조 손상({type(exc).__name__}) — 인덱스 구축 실패.",
        )
    return data


def _reset_cache_for_tests() -> None:
    """테스트 전용 — 캐시 초기화(운영 코드에서 호출 금지)."""
    global _CACHE, _B3_CACHE, _B2_CACHE, _B1_CACHE, _EVAL_CACHE, _B4_CACHE
    with _LOCK:
        _CACHE = None
    with _B3_LOCK:
        _B3_CACHE = None
    with _B2_LOCK:
        _B2_CACHE = None
    with _B1_LOCK:
        _B1_CACHE = None
    with _EVAL_LOCK:
        _EVAL_CACHE = None
    with _B4_LOCK:
        _B4_CACHE = None


# 답변 하단 표준 안내 — 서버 프롬프트(instructions·review 템플릿)와 문면이 일치해야 하는
# 고정 문구. 호스트가 조립하지 않고 그대로 옮기도록 서버가 완성형으로 제공한다(v0.28.0).
FOOTER_LAW_LINE = (
    "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 관련 규정 원문을 기준으로 해주시기 바랍니다."
)
# v0.30.0: 매뉴얼 원문 안내(Andy 확정 문안) — 게시물 URL·판번을 넣지 않는 홈페이지 안내형이라
# 판 개정·게시물 이동에도 문면이 유효(링크 로트·구판 오인 없음). 전 footer 경로 공통 2번째 줄.
FOOTER_MANUAL_SOURCE_LINE = (
    "※ 「국가연구개발혁신법 매뉴얼」 등 연구행정 관련 매뉴얼 원문은 "
    "KISTEP 홈페이지(www.kistep.re.kr)에서 확인하시기 바랍니다."
)
FOOTER_MANUAL_LINE = (
    "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다. "
    "매뉴얼은 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다."
)


def build_standard_footer(notice: str, manual_content_included: bool, manual_line: str | None = None) -> str:
    """답변 하단 표준 안내 완성형 블록 (v0.28.0·v0.30.0 매뉴얼 원문 안내 줄 추가).

    manual_content_included = 이 응답이 매뉴얼 해설 텍스트를 실제로 실어 보냈는가
    (검색 매치 발췌 존재 / 상세 content_available). 참이면 매뉴얼 인용 고지·판번 notice까지
    포함하고, 거짓이면(검색 0건·본문 미수록 포인터) 법령 확인·매뉴얼 원문 안내 두 줄만 —
    매뉴얼을 전달하지 않은 응답에 매뉴얼 인용 면책을 붙이면 근거 출처를 사실과 다르게
    고지하게 되므로 서버가 아는 범위에서 결정론으로 차단한다(검증 /disc).
    처음 두 줄은 규정 상세(_attach_std_footer)와 동일 문자열 — 호스트 dedup 자연 성립.

    manual_line(v0.38.0): 3번째 줄 per-source 문면 — 기본 문면이 「국가연구개발혁신법 매뉴얼」을
    명시하므로 비시리즈 독립 자료(과제평가 표준지침)는 데이터 meta.footer_manual_line로 자기
    문면을 공급한다(기존 4소스는 키 부재 → 기본 문면·기존 응답 byte 불변).
    """
    lines = [FOOTER_LAW_LINE, FOOTER_MANUAL_SOURCE_LINE]
    if manual_content_included:
        lines.append(manual_line or FOOTER_MANUAL_LINE)
        lines.append(f"※ {notice}")
    return "\n".join(lines)


# v0.34.0: 표·산식 구조 손실 완성형 안내 — v0.33.0 라이브 eval에서 warnings 배열 원소는
# 호스트 답변에 전이되지 않음이 관측됨(같은 응답의 citation·standard_footer 완성형 블록은 복사됨).
# 사용자에게 전달돼야 하는 구조 손실 고지를 완성형 블록으로 승격한다. 값은 데이터
# table_structure_notes 원문의 결정론 조립(generic 요약 금지 — 무엇이 소실됐는지가 도달해야 의미).
STRUCTURE_NOTICE_HEADER = "※ 표·산식 구조 안내(추출 한계):"
STRUCTURE_NOTICE_CHUNK_LINE = (
    "- 위 안내는 절 전체 기준이며, 이 청크에 해당 표·산식·도식이 포함되었다는 뜻은 아닙니다."
)
STRUCTURE_NOTICE_NOTE = (
    "위 structure_notice는 이 절의 표·산식·도식 구조가 추출 텍스트에 보존되지 않은 부분에 대한 "
    "완성형 안내입니다. 이 절의 수치·산식·표 내용을 답변에 인용했다면 이 블록을 답변에 그대로"
    "(요약·윤문 없이) 1회 표시하십시오. 같은 내용이 warnings에도 있으니 warnings 쪽을 중복 "
    "표시하지 마십시오."
)


def build_structure_notice(section: dict, is_chunk: bool = False) -> str | None:
    """표·산식 구조 손실 완성형 안내 블록 (v0.34.0) — 답변에 그대로 옮길 수 있는 형태.

    데이터 table_structure_notes(절 수준 문자열 목록)의 원소 전부가 유효 문자열일 때만
    블록을 만들고, 없거나 원소 하나라도 비정형이면 None(전체 생략 fail-closed — 일부만
    조립하면 불완전한 안내가 완전한 안내처럼 보인다·diff 적대검토 반영. 기존 warnings
    표면은 원소별 필터를 유지하므로 정보 자체는 남는다).
    청크 응답에는 절 전체 기준 주의 줄을 덧붙인다(그 청크에 해당 표가 없을 수 있음 —
    over-claim 차단. 페이지별 선택 부착은 데이터 스키마·QA 추가가 필요해 범위 밖).
    """
    notes = section.get("table_structure_notes")
    if not isinstance(notes, list) or not notes:
        return None
    if not all(isinstance(n, str) and n for n in notes):
        return None
    lines = [STRUCTURE_NOTICE_HEADER]
    lines.extend(f"- {n}" for n in notes)
    if is_chunk:
        lines.append(STRUCTURE_NOTICE_CHUNK_LINE)
    return "\n".join(lines)


def manual_meta_block(
    meta: dict, manual_content_included: bool = False, section_id: str | None = None
) -> dict:
    """규범성 메타 블록 — 두 매뉴얼 도구의 모든 비오류 응답에 상시 동반(계획 /disc 3/3).

    값은 데이터 파일 meta에서 복사(판번·기준일 하드코딩 금지 — 갱신 지점 = 데이터 파일 한 곳).
    notice는 서버 완성형(계획 문서 §3-5) — edition 부재 시 판번 생략(확인 불가 처리).
    standard_footer(v0.28.0)는 답변 하단에 그대로 옮겨 붙일 완성형 블록.

    section_id(v0.31.0): get_manual_section 비오류 응답에서만 전달 — 데이터 meta의
    renumbering_note(판 전환 절 번호 이동 고지)를 대상 절(renumbering_note_section_ids)에만
    조건부 부착한다. search_manual은 현행 제목·id를 함께 반환하므로 미부착(설계 /disc 라운드 2).
    """
    edition = meta.get("edition") or ""
    basis = meta.get("manual_basis_date") or ""
    # 별권 계열(시리즈 필드 보유)은 자료명을 notice에 병기 — 혼합 답변에서 어느 자료의 판번인지 식별
    series_title = meta.get("series_title") or ""
    series_part = meta.get("series_part") or ""
    src_title = _one_line(meta.get("source_title"))
    if series_title and series_part and src_title:
        subject = f"「{src_title}」({series_title} {series_part})"
    elif src_title and not basis:
        # v0.38.0: 비시리즈 독립 자료(과제평가 표준지침 등) — 자료명 단독 병기(혼합 답변 식별).
        # 본권(basis 보유)은 이 분기에 오지 않아 기존 notice 문면 불변.
        subject = f"「{src_title}」"
    else:
        subject = None
    if edition and basis:
        notice = f"인용 매뉴얼: {edition}판 · 법령 시행일 {basis} 기준"
    elif edition:
        # v0.32.0(R2-P0 D7): 판번만 있고 기준일이 원문에 없는 자료(별권 3) — "확인 불가"로
        # 뭉개지 않고 사실대로 표기. provenance 단서는 데이터 edition_note 보유 시에만
        # (v0.38.0: edition_provenance 보유 자료는 그 문면을 우선 사용 — 게시 세트 아닌 판번 출처 지원).
        head = f"인용 자료: {subject} " if subject else "인용 매뉴얼: "
        custom_prov = _one_line(meta.get("edition_provenance"))
        if custom_prov:
            provenance = f"({custom_prov})"
        else:
            provenance = "(판번은 게시 세트 기준)" if meta.get("edition_note") else ""
        notice = f"{head}{edition}판{provenance} · 법령 기준일 원문 미표기"
    elif basis:
        notice = f"인용 매뉴얼: 법령 시행일 {basis} 기준"
    else:
        notice = "인용 매뉴얼: 판번·기준일 확인 불가"
    # v0.30.0: 임베드 판의 정확한 출처(게시물 URL) — 기계 가독 출처 귀속. footer 문면(홈페이지
    # 안내형)과 분리되며, 구데이터(키 부재)·비문자열 값에서는 필드 자체를 생략(fail-safe).
    raw_source_url = meta.get("source_url")
    source_url = raw_source_url if isinstance(raw_source_url, str) and raw_source_url else None
    # v0.31.0: 판 전환 재번호 고지 — 데이터 키 2종이 모두 유효(str·list[str])하고 조회 절이
    # 대상 목록에 있을 때만 부착(구데이터·비정형 값·비대상 절은 필드 자체 생략 fail-safe).
    # 재번호 없는 판에서는 데이터에서 두 키를 비우면 코드 무변으로 소멸(수명 = 수록 판 연동).
    renumbering_note = None
    if section_id is not None:
        raw_note = meta.get("renumbering_note")
        raw_ids = meta.get("renumbering_note_section_ids")
        if (
            isinstance(raw_note, str)
            and raw_note
            and isinstance(raw_ids, list)
            and all(isinstance(x, str) for x in raw_ids)
            and section_id in raw_ids
        ):
            renumbering_note = raw_note
    return {
        "source_type": meta.get("source_type", "manual_explanation"),
        "legal_effect": meta.get("legal_effect", "not_binding"),
        "source_title": meta.get("source_title", "국가연구개발혁신법 매뉴얼(본권)"),
        "edition": edition or None,
        "manual_basis_date": basis or None,
        "basis_note": meta.get("basis_note"),
        "basis_laws": meta.get("basis_laws", []),
        **({"source_url": source_url} if source_url else {}),
        **({"renumbering_note": renumbering_note} if renumbering_note else {}),
        "law_priority_note": _law_priority_note(meta, subject, basis, edition),
        "notice": notice,
        # v0.38.0: footer 3번째 줄 per-source 문면(meta.footer_manual_line) — 키 부재 소스는 기본 문면(byte 불변)
        "standard_footer": build_standard_footer(
            notice, manual_content_included, _one_line(meta.get("footer_manual_line")) or None
        ),
        "standard_footer_note": (
            "위 standard_footer는 답변 마지막에 그대로(요약·윤문 없이) 1회 표시할 완성형 안내입니다. "
            "한 답변에서 매뉴얼 응답을 여러 개 받았다면 값이 서로 다를 수 있으니, 최종 답변에 매뉴얼 "
            "내용을 인용했다면 매뉴얼 인용 고지가 포함된 값을(어느 응답에서 받았든) 표시하고, 어느 매뉴얼 "
            "내용도 인용하지 않았다면 규정 조회(get_provision_detail) 응답의 값을(없으면 이 블록의 "
            "처음 두 줄만) 표시하십시오. 같은 취지의 안내를 따로 만들어 중복 부착하지 마십시오."
        ),
    }


def _law_priority_note(meta: dict, subject: str | None, basis: str, edition: str) -> str:
    """규범성 안내 문면 조립 — 본권(basis 보유)은 기존 문면과 글자 단위 동일 유지(v0.28.0 잠금).

    별권 3(basis 없음·시리즈 필드 보유): 자료명 병기 + 기준일 미표기 사실 문면 + 데이터
    law_priority_extra(별표 6·7 교차확인·제5장 비일반화 — R2-P0 D8 동결 문장) append.
    비정형 데이터는 폴백 문면으로 fail-safe(기존 else 분기 문면 유지).
    """
    label = subject if subject else "「국가연구개발혁신법 매뉴얼」"
    if basis:
        basis_sentence = f"매뉴얼은 법령 시행일 {basis} 기준으로 작성되어 이후 법령 개정이 반영되지 않았을 수 있고, "
    elif edition and meta.get("basis_note"):
        basis_sentence = "이 자료는 법령 기준일이 원문에 명시되어 있지 않아 이후 법령 개정 반영 여부를 알 수 없고, "
    else:
        basis_sentence = "매뉴얼은 특정 시점 기준으로 작성되어 이후 법령 개정이 반영되지 않았을 수 있고, "
    note = (
        f"본 내용은 {label}의 해설이며 법령·행정규칙이 아닙니다. "
        "조문 원문 확인은 search_provision·get_provision_detail을 사용하고, "
        "매뉴얼과 법령·행정규칙 내용이 다르면 법령·행정규칙 원문이 우선합니다. "
        + basis_sentence
        + "매뉴얼 미수록·검색 0건이 규정의 부재를 뜻하지 않습니다."
    )
    extra = meta.get("law_priority_extra")
    if isinstance(extra, list) and extra and all(isinstance(x, str) for x in extra):
        note = note + " " + " ".join(extra)
    return note


def _josa_eun_neun(word: str) -> str:
    """은/는 조사 선택 — 숫자 끝(한국어 독음 받침)·한글 받침 처리, 그 외 '은(는)' 폴백."""
    if not word:
        return "은(는)"
    last = word[-1]
    if last.isdigit():
        return "은" if last in "013678" else "는"  # 영·일·삼·육·칠·팔(받침) vs 이·사·오·구
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        return "은" if (code - 0xAC00) % 28 else "는"
    return "은(는)"


def _series_part_label(meta: dict) -> str:
    """병기 문면용 자료 라벨 — series_part("별권 3") 우선·결측 시 source_title 폴백."""
    return _one_line(meta.get("series_part")) or _one_line(meta.get("source_title")) or "별권"


def _sources_entry(block: dict) -> dict:
    """sources.{id} 항목 — 소스별 구조화 provenance 공통 shape."""
    return {
        "source_title": block.get("source_title"),
        "edition": block.get("edition"),
        "manual_basis_date": block.get("manual_basis_date"),
        **({"source_url": block["source_url"]} if block.get("source_url") else {}),
    }


def mixed_manual_meta_block(
    primary: tuple[str, dict], others: list[tuple[str, dict]], manual_content_included: bool = False
) -> dict:
    """복수 소스 매치가 한 검색 응답에 함께 반환될 때의 병기 완성형 meta 블록 (R2-P0 D7 → R3-P0 D5 일반화).

    primary/others = (source_id, meta) 쌍. primary는 실제 반환 소스 중 최저 source_rank —
    구조 단일 값 필드(edition·manual_basis_date 등)는 primary 기준이며, 나머지 소스는
    sources.{id}·notice 병기·law_priority_note 확장으로 식별한다. (본권, [별권 3]) 조합의
    출력은 v0.32.0 문면과 글자 단위 동일(보존 잠금 — R3-P0 D5 보존 표면 ③).
    """
    primary_id, primary_meta = primary
    primary_block = manual_meta_block(primary_meta, manual_content_included)
    other_blocks = [(oid, manual_meta_block(m, manual_content_included), m) for oid, m in others]
    notice = " / ".join([primary_block["notice"]] + [b["notice"] for _oid, b, _m in other_blocks])
    # 별권 기준일 부재를 law_priority_note에도 명시 — 구조 필드(manual_basis_date 등)가 primary
    # 값이라 다른 소스에 전이 오독될 수 있는 벡터 차단(P2 적대검토 MAJOR — v0.32.0).
    law_note = primary_block["law_priority_note"]
    for _oid, _block, m in other_blocks:
        part = _series_part_label(m)
        if not (m.get("manual_basis_date") or ""):
            law_note += (
                f" {part}{_josa_eun_neun(part)} 법령 기준일이 원문에 명시되어 있지 않아 "
                "이후 법령 개정 반영 여부를 알 수 없습니다."
            )
        extra = m.get("law_priority_extra")
        if isinstance(extra, list) and extra and all(isinstance(x, str) for x in extra):
            law_note = law_note + " " + " ".join(extra)
    primary_label = "본권" if primary_id == "main" else _series_part_label(primary_meta)
    if len(other_blocks) == 1:
        oid, _b, m = other_blocks[0]
        part = _series_part_label(m)
        prov_tail = (
            f"{part}의 판번·기준일은 sources.{oid}와 notice를 따르십시오"
            f"({part}{_josa_eun_neun(part)} 법령 기준일 원문 미표기)."
        )
    else:
        parts = "·".join(_series_part_label(m) for _oid, _b, m in other_blocks)
        refs = "·".join(f"sources.{oid}" for oid, _b, _m in other_blocks)
        prov_tail = f"{parts}의 판번·기준일은 {refs}와 notice를 따르십시오(각 별권은 법령 기준일 원문 미표기)."
    out = dict(primary_block)
    out.update({
        "source_titles": [primary_block.get("source_title")] + [b.get("source_title") for _oid, b, _m in other_blocks],
        # 소스별 구조화 provenance — 단일 필드(edition·manual_basis_date·source_url 등)는 primary
        # 기준임을 기계 가독으로 보완(호스트가 구조 필드만 읽고 타 소스에 전이 적용하는 오독 차단)
        "sources": {
            primary_id: _sources_entry(primary_block),
            **{oid: _sources_entry(b) for oid, b, _m in other_blocks},
        },
        "provenance_note": (
            "이 블록의 단일 값 필드(edition·manual_basis_date·basis_note·basis_laws·source_url)는 "
            f"{primary_label} 기준입니다. {prov_tail}"
        ),
        "notice": notice,
        "law_priority_note": law_note,
        # v0.38.0(diff 적대검토 Codex MAJOR 반영): 혼합 footer 3번째 줄 — 전 소스가 기본 문면이면
        # 기본(기존 조합 byte 불변·v0.32.0 보존 잠금), 전 소스가 같은 커스텀이면 그 문면, 기본+커스텀
        # 혼합이면 일반 지칭 문면(primary 문면만 쓰면 다른 소스 발췌가 오귀속 — 자료 열거는 notice 담당).
        "standard_footer": build_standard_footer(
            notice, manual_content_included,
            _mixed_manual_line([primary_meta] + [m for _oid, m in others]),
        ),
    })
    return out


def _mixed_manual_line(metas: list[dict]) -> str | None:
    """혼합 응답 footer 3번째 줄 선택 — None 반환 = 기본 문면(FOOTER_MANUAL_LINE)."""
    customs = {_one_line(m.get("footer_manual_line")) for m in metas}
    customs.discard("")
    if not customs:
        return None
    if len(customs) == 1 and all(_one_line(m.get("footer_manual_line")) for m in metas):
        return customs.pop()
    return FOOTER_MANUAL_LINE_MIXED


def _one_line(value: object) -> str:
    """citation 조각 정규화 — 비문자 타입 허용(str 강제)·줄바꿈/중복 공백 축약(한 줄 보장).

    데이터 재생성 오류로 필드 타입이 어긋나도 도구가 예외 대신 짧은 문자열을 내도록 한다
    (로더는 meta/sections 최상위 구조만 검증하므로 내부 필드는 여기서 방어).
    """
    if value is None:
        return ""
    return " ".join(str(value).split())


def build_citation(
    meta: dict,
    section: dict,
    page_start: int | None = None,
    page_end: int | None = None,
) -> str:
    """완성형 인용 문자열 — 호스트가 그대로 옮겨 적을 수 있는 한 줄 (v0.28.0).

    형식: 「{source_title}」({edition}판) 제N장 {section_label} {section_title}, 인쇄 p.A~B
    - 값은 전부 meta·section에서 복사(문자열 하드코딩 금지 — 갱신 지점은 데이터 파일 한 곳).
    - 참고 자료(ref-N: chapter_no=0)는 '제0장'이 되지 않도록 장을 생략 — section_label("참고 1")이
      자체 앵커 역할을 한다.
    - 청크 응답은 page_start/page_end에 chunk_pages를 넘겨 그 청크가 실제 담은 인쇄쪽만 말하게 한다
      (절 전체 범위를 대면 확인 범위를 넘겨 말하는 over-claim).
    - 결측 필드는 예외 없이 해당 마디만 생략(never-raise) — 문자열이 짧아질 뿐 호출부 분기 불요.
    """
    title = _one_line(meta.get("source_title")) or "국가연구개발혁신법 매뉴얼(본권)"
    edition = _one_line(meta.get("edition"))
    head = f"「{title}」" + (f"({edition}판)" if edition else "")

    parts: list[str] = []
    try:
        chapter_no = int(section.get("chapter_no") or 0)
    except (TypeError, ValueError, OverflowError):
        chapter_no = 0
    if chapter_no >= 1:
        parts.append(f"제{chapter_no}장")
    for key in ("section_label", "section_title"):
        val = _one_line(section.get(key))
        if val:
            parts.append(val)

    ps = page_start if page_start is not None else section.get("page_start")
    pe = page_end if page_end is not None else section.get("page_end")
    if ps is not None and pe is not None and ps != pe:
        pages = f"인쇄 p.{ps}~{pe}"
    elif ps is not None:
        pages = f"인쇄 p.{ps}"
    else:
        pages = ""

    out = head
    if parts:
        out += " " + " ".join(parts)
    if pages:
        out += ", " + pages
    return out


MANUAL_FORMAT_NOTE = (
    "본 content는 「국가연구개발혁신법 매뉴얼」 본권 PDF에서 추출한 해설 텍스트 그대로입니다"
    "(법령 원문 아님·법적 효력 없음). 표 포함 페이지는 PDF 추출 특성상 셀 텍스트 순서·제목 위치가 "
    "원본 배치와 다를 수 있으므로, 수치·조건을 인용할 때는 표기된 인쇄쪽으로 원문 대조를 권장합니다."
)

# 별권 3 전용 format note — 본권 문면의 "본권 PDF" 하드코딩을 소스별로 분리(R2-P0 D7·P1 검토).
MANUAL_FORMAT_NOTE_B3 = (
    "본 content는 「국가연구개발사업 제재처분 가이드라인」(국가연구개발혁신법 매뉴얼 별권 3) PDF에서 "
    "추출한 해설 텍스트 그대로입니다(법령 원문 아님·법적 효력 없음). 표 포함 페이지는 PDF 추출 특성상 "
    "셀 텍스트 순서·제목 위치가 원본 배치와 다를 수 있으므로, 수치·조건을 인용할 때는 표기된 인쇄쪽으로 "
    "원문 대조를 권장합니다."
)

# 별권 2 전용 format note (R3-P0 D5 — 소스별 문면 동형).
MANUAL_FORMAT_NOTE_B2 = (
    "본 content는 「국가연구개발사업 기술료 제도 매뉴얼」(국가연구개발혁신법 매뉴얼 별권 2) PDF에서 "
    "추출한 해설 텍스트 그대로입니다(법령 원문 아님·법적 효력 없음). 표 포함 페이지는 PDF 추출 특성상 "
    "셀 텍스트 순서·제목 위치가 원본 배치와 다를 수 있으므로, 수치·조건을 인용할 때는 표기된 인쇄쪽으로 "
    "원문 대조를 권장합니다."
)

# 별권 1 전용 format note (R4-P0 D9 — 소스별 문면 동형).
MANUAL_FORMAT_NOTE_B1 = (
    "본 content는 「학생인건비통합관리 제도 매뉴얼」(국가연구개발혁신법 매뉴얼 별권 1) PDF에서 "
    "추출한 해설 텍스트 그대로입니다(법령 원문 아님·법적 효력 없음). 표 포함 페이지는 PDF 추출 특성상 "
    "셀 텍스트 순서·제목 위치가 원본 배치와 다를 수 있으므로, 수치·조건을 인용할 때는 표기된 인쇄쪽으로 "
    "원문 대조를 권장합니다."
)

# 혼합 footer 3번째 줄 (v0.38.0 — diff 적대검토 Codex MAJOR 반영): 기본 문면 소스(혁신법 매뉴얼
# 시리즈)와 커스텀 문면 소스(과제평가 표준지침 등)가 한 검색 응답에 함께 반환될 때, primary 문면만
# 쓰면 다른 소스 발췌가 오귀속된다 — 자료 열거는 4번째 줄(notice 병기)이 담당하므로 일반 지칭 문면.
FOOTER_MANUAL_LINE_MIXED = (
    "※ 매뉴얼·지침 해설 부분은 아래에 표기된 인용 자료들을 참고한 설명입니다. "
    "해당 자료는 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다."
)

# 별권 4 전용 format note (v0.39.0 R5 — 소스별 문면 동형).
MANUAL_FORMAT_NOTE_B4 = (
    "본 content는 「연구시설･장비비 통합관리제 운영･관리 매뉴얼」(국가연구개발혁신법 매뉴얼 별권 4) "
    "PDF에서 추출한 해설 텍스트 그대로입니다(법령 원문 아님·법적 효력 없음). 표 포함 페이지는 PDF 추출 "
    "특성상 셀 텍스트 순서·제목 위치가 원본 배치와 다를 수 있으므로, 수치·조건을 인용할 때는 표기된 "
    "인쇄쪽으로 원문 대조를 권장합니다."
)

# 과제평가 표준지침 전용 format note (v0.38.0 — 비시리즈 독립 소스라 문서 성격을 정확히 기재).
MANUAL_FORMAT_NOTE_EVAL = (
    "본 content는 「국가연구개발 과제평가 표준지침」(과학기술정보통신부·KISTEP 발행, 2025.12) PDF에서 "
    "추출한 텍스트 그대로입니다. 이 지침은 연구성과평가법 제13조에 따라 과학기술정보통신부가 마련한 "
    "범부처 표준지침이며 법령·행정규칙 원문이 아닙니다(각 부처는 이를 고려해 자체 평가지침을 마련). "
    "표 포함 페이지는 PDF 추출 특성상 셀 텍스트 순서·제목 위치가 원본 배치와 다를 수 있으므로, "
    "수치·조건을 인용할 때는 표기된 인쇄쪽으로 원문 대조를 권장합니다."
)


def build_section_chunks(section: dict) -> list[dict]:
    """대형 절 본문을 페이지 경계 우선으로 분할 (결정론·재조립 무손실).

    - full_text = "\\n".join(페이지 text)의 연속 substring들로 분할 — "".join(chunks) == full_text
      (annex _annex_chunk_texts와 동일 불변식·검증 테스트로 잠금).
    - 분할점은 페이지 시작 오프셋 우선(각 청크가 인쇄쪽 범위를 정확히 말할 수 있음 — PDF 대조 앵커).
    - 각 청크 escaped 길이 ≤ MANUAL_CHUNK_CONTENT_BUDGET. 단일 페이지가 예산 초과하는
      미래 케이스(현 데이터 최대 페이지 ~3k자·미관측)는 문자 단위 폴백으로 진행 보장.
    - 반환: [{"text", "page_start", "page_end"}] (인쇄쪽 기준).
    """
    pages = section.get("pages", [])
    texts = [p.get("text", "") for p in pages]
    printed = [p.get("printed_page") for p in pages]
    full = "\n".join(texts)
    if not pages:
        return [{"text": full, "page_start": section.get("page_start"), "page_end": section.get("page_end")}]

    chunks: list[dict] = []
    cur_parts: list[str] = []
    cur_cost = 0
    cur_pg_start: int | None = None
    cur_pg_end: int | None = None

    def _flush():
        nonlocal cur_parts, cur_cost, cur_pg_start, cur_pg_end
        if cur_parts:
            chunks.append({"text": "".join(cur_parts), "page_start": cur_pg_start, "page_end": cur_pg_end})
        cur_parts, cur_cost, cur_pg_start, cur_pg_end = [], 0, None, None

    for i, (pg, txt) in enumerate(zip(printed, texts)):
        seg = txt + ("\n" if i + 1 < len(texts) else "")  # 페이지 뒤 조인자 포함 substring
        cost = _json_escaped_len(seg)
        if cost > MANUAL_CHUNK_CONTENT_BUDGET:
            # 단일 페이지 초과 — 문자 단위 폴백(연속 substring 유지)
            _flush()
            buf: list[str] = []
            bcost = 0
            for ch in seg:
                c = _json_escaped_len(ch)
                if buf and bcost + c > MANUAL_CHUNK_CONTENT_BUDGET:
                    chunks.append({"text": "".join(buf), "page_start": pg, "page_end": pg})
                    buf, bcost = [ch], c
                else:
                    buf.append(ch)
                    bcost += c
            if buf:
                chunks.append({"text": "".join(buf), "page_start": pg, "page_end": pg})
            continue
        if cur_parts and cur_cost + cost > MANUAL_CHUNK_CONTENT_BUDGET:
            _flush()
        if not cur_parts:
            cur_pg_start = pg
        cur_parts.append(seg)
        cur_cost += cost
        cur_pg_end = pg
    _flush()
    return chunks


def find_excerpts(section: dict, tokens: list[str], cap: int = 2, excerpt_max: int = 400) -> list[dict]:
    """매치 발췌 — 매치 줄 ±1줄 윈도우(페이지 내)·발췌당 excerpt_max 상한·인쇄쪽 앵커 동반.

    매칭은 정규화(ㆍ·･→·) 기준·발췌 텍스트는 raw 원문 유지. 모든 토큰을 담은 줄을 우선하고,
    부족하면 일부 토큰 줄로 보충(문서 순서·결정론).
    """
    norm_tokens = [mdot_normalize(t) for t in tokens]
    full_hits: list[tuple] = []
    partial_hits: list[tuple] = []
    for page in section.get("pages", []):
        pg = page.get("printed_page")
        lines = page.get("text", "").split("\n")
        norm_lines = [mdot_normalize(l) for l in lines]
        for i, nl in enumerate(norm_lines):
            present = [t for t in norm_tokens if t in nl]
            if not present:
                continue
            window = "\n".join(lines[max(0, i - 1): i + 2])
            if len(window) > excerpt_max:
                window = window[:excerpt_max]
            item = (pg, window)
            if len(present) == len(norm_tokens):
                full_hits.append(item)
            else:
                partial_hits.append(item)
    out: list[dict] = []
    seen: set = set()
    for pg, window in full_hits + partial_hits:
        key = (pg, window[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append({"printed_page": pg, "text": window})
        if len(out) >= cap:
            break
    return out
