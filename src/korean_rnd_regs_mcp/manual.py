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

# main.py의 _ANNEX_DETAIL_CHAR_BUDGET(16000)·_ANNEX_DETAIL_HEADROOM(300)·
# _ANNEX_CHUNK_CONTENT_BUDGET(12000)과 동일 값 — 변경 시 양쪽 함께(테스트 잠금).
MANUAL_DETAIL_CHAR_BUDGET = 16000
MANUAL_DETAIL_HEADROOM = 300
MANUAL_CHUNK_CONTENT_BUDGET = 12000

SECTION_ID_RE = re.compile(r"^(\d+-\d+|ref-\d+)$")

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
            message="매뉴얼 데이터 파일(manual_body.json)이 패키지에 없습니다 — 패키징 누락 가능. 기존 규정 도구는 정상입니다.",
        )
    try:
        with open(_DATA_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except (ValueError, OSError) as exc:
        return ManualLoadError(
            reason="json_parse_failed",
            message=f"매뉴얼 데이터 파일 파싱 실패({type(exc).__name__}) — 기존 규정 도구는 정상입니다.",
        )
    meta = payload.get("meta")
    sections = payload.get("sections")
    if not isinstance(meta, dict) or not isinstance(sections, list) or not sections:
        return ManualLoadError(
            reason="schema_invalid",
            message="매뉴얼 데이터 스키마 이상(meta/sections 부재) — 기존 규정 도구는 정상입니다.",
        )
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
    return data


def _reset_cache_for_tests() -> None:
    """테스트 전용 — 캐시 초기화(운영 코드에서 호출 금지)."""
    global _CACHE
    with _LOCK:
        _CACHE = None


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


def build_standard_footer(notice: str, manual_content_included: bool) -> str:
    """답변 하단 표준 안내 완성형 블록 (v0.28.0·v0.30.0 매뉴얼 원문 안내 줄 추가).

    manual_content_included = 이 응답이 매뉴얼 해설 텍스트를 실제로 실어 보냈는가
    (검색 매치 발췌 존재 / 상세 content_available). 참이면 매뉴얼 인용 고지·판번 notice까지
    포함하고, 거짓이면(검색 0건·본문 미수록 포인터) 법령 확인·매뉴얼 원문 안내 두 줄만 —
    매뉴얼을 전달하지 않은 응답에 매뉴얼 인용 면책을 붙이면 근거 출처를 사실과 다르게
    고지하게 되므로 서버가 아는 범위에서 결정론으로 차단한다(검증 /disc).
    처음 두 줄은 규정 상세(_attach_std_footer)와 동일 문자열 — 호스트 dedup 자연 성립.
    """
    lines = [FOOTER_LAW_LINE, FOOTER_MANUAL_SOURCE_LINE]
    if manual_content_included:
        lines.append(FOOTER_MANUAL_LINE)
        lines.append(f"※ {notice}")
    return "\n".join(lines)


def manual_meta_block(meta: dict, manual_content_included: bool = False) -> dict:
    """규범성 메타 블록 — 두 매뉴얼 도구의 모든 비오류 응답에 상시 동반(계획 /disc 3/3).

    값은 데이터 파일 meta에서 복사(판번·기준일 하드코딩 금지 — 갱신 지점 = 데이터 파일 한 곳).
    notice는 서버 완성형(계획 문서 §3-5) — edition 부재 시 판번 생략(확인 불가 처리).
    standard_footer(v0.28.0)는 답변 하단에 그대로 옮겨 붙일 완성형 블록.
    """
    edition = meta.get("edition") or ""
    basis = meta.get("manual_basis_date") or ""
    if edition and basis:
        notice = f"인용 매뉴얼: {edition}판 · 법령 시행일 {basis} 기준"
    elif basis:
        notice = f"인용 매뉴얼: 법령 시행일 {basis} 기준"
    else:
        notice = "인용 매뉴얼: 판번·기준일 확인 불가"
    basis_phrase = f"법령 시행일 {basis} 기준으로 작성되어" if basis else "특정 시점 기준으로 작성되어"
    # v0.30.0: 임베드 판의 정확한 출처(게시물 URL) — 기계 가독 출처 귀속. footer 문면(홈페이지
    # 안내형)과 분리되며, 구데이터(키 부재)에서는 필드 자체를 생략(fail-safe).
    source_url = meta.get("source_url") or None
    return {
        "source_type": meta.get("source_type", "manual_explanation"),
        "legal_effect": meta.get("legal_effect", "not_binding"),
        "source_title": meta.get("source_title", "국가연구개발혁신법 매뉴얼(본권)"),
        "edition": edition or None,
        "manual_basis_date": basis or None,
        "basis_note": meta.get("basis_note"),
        "basis_laws": meta.get("basis_laws", []),
        **({"source_url": source_url} if source_url else {}),
        "law_priority_note": (
            "본 내용은 「국가연구개발혁신법 매뉴얼」의 해설이며 법령·행정규칙이 아닙니다. "
            "조문 원문 확인은 search_provision·get_provision_detail을 사용하고, "
            "매뉴얼과 법령·행정규칙 내용이 다르면 법령·행정규칙 원문이 우선합니다. "
            f"매뉴얼은 {basis_phrase} 이후 법령 개정이 반영되지 않았을 수 있고, "
            "매뉴얼 미수록·검색 0건이 규정의 부재를 뜻하지 않습니다."
        ),
        "notice": notice,
        "standard_footer": build_standard_footer(notice, manual_content_included),
        "standard_footer_note": (
            "위 standard_footer는 답변 마지막에 그대로(요약·윤문 없이) 1회 표시할 완성형 안내입니다. "
            "한 답변에서 매뉴얼 응답을 여러 개 받았다면 값이 서로 다를 수 있으니, 최종 답변에 매뉴얼 "
            "내용을 인용했다면 매뉴얼 인용 고지가 포함된 값을(어느 응답에서 받았든) 표시하고, 어느 매뉴얼 "
            "내용도 인용하지 않았다면 규정 조회(get_provision_detail) 응답의 값을(없으면 이 블록의 "
            "처음 두 줄만) 표시하십시오. 같은 취지의 안내를 따로 만들어 중복 부착하지 마십시오."
        ),
    }


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
