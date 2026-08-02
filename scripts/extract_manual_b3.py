#!/usr/bin/env python3
"""국가연구개발혁신법 매뉴얼 별권 3 「국가연구개발사업 제재처분 가이드라인」 추출 파이프라인 (R2-P1).

사용법:
    /Users/andykim/my_project/venv/bin/python scripts/extract_manual_b3.py \
        --source-url "https://www.kistep.re.kr/board.es?...&list_no=<게시물번호>"
    (옵션) --pdf <경로> --out-json <경로> --out-report <경로>

의존성: PyMuPDF(fitz) — 오프라인 스크립트 전용·패키지 런타임 의존성 아님(본권 extract_manual.py와 동일).

산출물:
    src/korean_rnd_regs_mcp/manual_b3.json     (절 단위 구조화 데이터 — 패키지 데이터 동봉 대상)
    scripts/manual_b3_extract_report.md        (품질 리포트 — 경계 감사·검수용)

본권 스크립트와의 구조 차이 (R2-P0 설계 동결 문서 D1~D7 근거 — 본권 스크립트는 무변 유지):
    - 절 헤딩 = "N. 제목"(별권은 제N절 체계가 아님) · 소절 "(N)" 43개 + 내포 참고 블록 제목 3개
      (<참고: 연혁>·<부칙>·<참고: 재검토요청서 서식>)를 subsection_titles 검색 제목군에 포함(46개).
    - 한 인쇄쪽에 여러 절이 시작하는 경우(쪽 1에 3개 절·쪽 34에 2개 절)를 같은 쪽 다중 분할로 처리.
    - 장 표제 간지 없음(전 장에서 장 시작쪽 = 첫 절 시작쪽·장 표제 줄은 첫 절 본문에 verbatim 포함).
    - 러닝헤더 = 화이트리스트 정확일치(문서 제목·장 제목 5종·부록 제목) + 상단 bbox / 쪽번호 = 하단
      bbox의 맨숫자(본권의 /N/ 마커와 다름).
    - ★헤딩 미발견·분할 순서 역전은 BLOCK(본권의 warning fallback을 fail-closed로 강화 — 동결 D4).
    - meta: manual_basis_date 없음(원문 무명시 — null·본권 기준일 비준용), edition은 게시 세트
      기준임을 edition_note로 명시(동결 D7).

결정론: 같은 PDF + 같은 --source-url + 같은 스크립트 + 같은 PyMuPDF 버전이면 JSON은 byte-identical.

판 갱신 절차: 본권 extract_manual.py docstring과 동일 — 새 판 게시 시 EXPECTED_* 불일치로
fail-closed 중단되면 목차 대조표를 보고 상수 갱신·구판↔신판 id→제목 전수 대조로 재번호 판정.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = Path(
    "/Users/andykim/mhk/31 - 규정/91-1-3 - 국가연구개발혁신법 매뉴얼(26.7) - 별권 3 - 제재처분 가이드라인.pdf"
)
DEFAULT_JSON = REPO_ROOT / "src" / "korean_rnd_regs_mcp" / "manual_b3.json"
DEFAULT_REPORT = REPO_ROOT / "scripts" / "manual_b3_extract_report.md"

# ── 판(edition) 메타 — 판 갱신 대상 (동결 D7) ────────────────────────────────
EDITION = "26.7"
EDITION_NOTE = (
    "판번은 KISTEP 게시 세트·파일명 기준입니다(별권 PDF 본문·표지에 판번 텍스트 표기 없음). "
    "본권 26.7판과 같은 KISTEP 게시물로 배포되었습니다."
)
BASIS_NOTE = (
    "별권 3 원문에는 본권과 달리 법령 기준일이 명시되어 있지 않습니다. "
    "본권의 기준일(2026-06)을 별권에 준용하지 않았습니다."
)
# 규범성 확장 문장 (R2-P0 D8 동결 문면 — law_priority_note 말미에 append·데이터 단일 출처)
LAW_PRIORITY_EXTRA = [
    "참여제한 기간·제재부가금 비율 등 구체값을 인용할 때는 get_provision_detail로 시행령 별표 6·별표 7 원문을 교차 확인하십시오.",
    "이 가이드라인 중 제5장의 쟁점·검토결과는 개별 사안별 검토 결과 모음이므로, 사실관계가 다른 유사 사안에 그대로 일반화할 수 없습니다.",
]

# ── EXPECTED 스냅샷 (fail-closed 정본 — 별권3 26.7판 인쇄 목차 실측 2026-08-02) ──
EXPECTED_PAGE_OFFSET = 10  # PDF쪽 = 인쇄쪽 + 10
EXPECTED_BODY_END = 89  # 인쇄쪽 기준 본문 끝 (PDF p.99 — p.100은 마커 없는 뒤표지)

EXPECTED_CHAPTERS = [
    (1, "제재처분 가이드라인 소개", 1),
    (2, "제재처분제도 개요", 3),
    (3, "제재처분 절차", 25),
    (4, "제재처분 기준", 48),
    (5, "제재처분재검토 주요쟁점사항 및 검토결과", 81),
]

# (chapter_no, section_no, title, start_printed) — "N." 레벨 절 22개 (동결 D2)
EXPECTED_SECTIONS = [
    (1, 1, "배경", 1),
    (1, 2, "목적(활용대상 및 활용방법)", 1),
    (1, 3, "주요내용 및 구성", 1),
    (2, 1, "법적 근거", 3),
    (2, 2, "주요용어 정리", 9),
    (2, 3, "혁신법에 따라 변경된 제재처분 주요내용", 17),
    (3, 1, "제재처분 사유 발생에 따른 조사･검증 및 보고", 25),
    (3, 2, "제재처분 평가단 검토", 28),
    (3, 3, "제재처분 사전통지", 29),
    (3, 4, "제재처분 재검토", 30),
    (3, 5, "확정통보", 34),
    (3, 6, "사전통지 및 확정통보의 방식 : 처분효력의 발생", 34),
    (3, 7, "제재정보 등록 및 공개", 38),
    (3, 8, "제재부가금･환수금 납부 및 사후관리", 39),
    (3, 9, "국세 강제징수처분", 41),
    (4, 1, "제재처분 일반 기준", 48),
    (4, 2, "제재처분사유별 가중･감경 세부기준", 57),
    (5, 1, "혁신법 시행 이전 행위에 우선 적용 가능한 혁신법 규정", 81),
    (5, 2, "연구자 등이 타 과제로 인해 참여제한 처분을 받은 이후 수행중인 기존 과제의 중단 여부", 82),
    (5, 3, "연구개발비 사용용도 기준 위반 금액의 자진반납 시 환수처분 금액 산정 기준", 83),
    (5, 4, "수사･소송 등 진행 중인 사안에 대한 제재처분", 85),
    (5, 5, "행정심판･소송 진행 시 조치사항", 86),
]

# <부록> 1건 — 비장절 독립자료(동결 D3: chapter_no 0·section_label "<부록>")
EXPECTED_REFS = [
    (1, "연구자를 위한 신고·보상 제도 안내", 88),
]

# 검색 제목군 46개 전수 스냅샷 (fail-closed — 총수만 검증하면 제목 내용 드리프트를 놓침·P1 적대검토 적발)
EXPECTED_SUBSECTIONS = {
    "b3-1-3": ["<참고 : 제재처분 관련규정 연혁>"],
    "b3-2-1": ["(1) 국가연구개발혁신법(이하 ‘법’)", "(2) 국가연구개발혁신법 시행령(이하 ‘시행령’)", "(3) 국가연구개발혁신법 시행규칙(이하 ‘시행규칙’)", "<부칙>"],
    "b3-2-2": ["(1) 제재처분 주체", "(2) 제재처분 대상자", "(3) 국가연구개발사업 및 연구개발과제", "(4) 참여제한", "(5) 제재부가금", "(6) 연구개발비 회수금", "(7) 연구개발비 환수", "(8) 부정행위"],
    "b3-2-3": ["(1) 제재처분 적용범위", "(2) 제재처분 제척기간 도입", "(3) 제재처분 사유의 변경 등", "(4) 제재처분의 종류 및 참여제한 기간･범위 조정", "(5) 제재처분의 재검토를 위한 ‘연구자권익보호위원회’ 신설", "(6) 제재처분 공개"],
    "b3-3-1": ["(1) 부정행위의 경우", "(2) 그 외의 경우"],
    "b3-3-2": ["(1) 제재처분 평가단 구성", "(2) 제재처분 평가단 역할"],
    "b3-3-4": ["<참고 : 재검토요청서 서식>"],
    "b3-3-6": ["(1) 문서 송달의 방식", "(2) 송달의 효력 발생"],
    "b3-3-9": ["(1) 국세 강제징수의 개념", "(2) 국세 강제징수 절차", "(3) 압류 해제 및 유예", "(4) 납부 대상기관의 부도･폐업･회생･파산 시 처리 방법", "(5) 소멸시효"],
    "b3-4-1": ["(1) 참여제한 처분 기준", "(2) 제재부가금 처분 기준"],
    "b3-4-2": ["(1) 수행과정 및 결과의 극히 불량", "(2) 법 또는 협약 상 의무 위반", "(3) 연구개발 자료･성과의 위조･변조･표절 및 부당한 저자 표시", "(4) 연구개발비의 사용용도 및 사용기준 위반", "(5) 연구개발성과의 소유･관리 위반", "(6) 보안대책 위반", "(7) 보안사항 국내 누설 및 유출", "(8) 보안사항 국외 누설 및 유출", "(9) 거짓 또는 부정한 방법으로 연구개발과제 신청 또는 수행", "(10) 그 밖에 국가연구개발활동의 건전성 저해 행위", "(11) 연구개발과제의 수행 포기", "(12) 기술료 또는 연구개발성과 수익 미납", "(13) 연구개발비 회수 금액 미납"],
}

# 표 구조 손실 표적 고지 (P1 시각 대조 실측 — 값 오결속은 아니나 구조 정보가 텍스트에 없음.
# 데이터 필드 table_structure_notes로 동봉 — P2에서 응답 표면화 방식 결정·D9 보강)
TABLE_STRUCTURE_NOTES = {
    "b3-4-2": [
        "이 절의 처분 기준표 중 세로 병합 셀(예: 감경·가중 '2분의 1의 범위')은 추출 텍스트에서 "
        "첫 행 그룹에만 나타나며 병합 범위(어느 행까지 적용되는지) 정보가 소실되어 있습니다. "
        "행별 적용 여부는 표기된 인쇄쪽 원문 또는 시행령 별표 6·별표 7 원문으로 확인하십시오.",
        "각 기준표 하단의 감경요소/가중요소 예시표(2열 목록)는 열 단위로 직렬화되어 두 목록의 "
        "경계 구분이 텍스트에 없습니다. 어느 항목이 감경/가중인지는 인쇄쪽 원문으로 확인하십시오.",
    ],
}

# ── 러닝헤더/푸터 제거 규칙 (동결: 화이트리스트 정확일치 + bbox 이중 조건) ──────
# 실측: 헤더 y0 ≈ 6.4%·본문 헤딩 ≥ 10.2% → 상단 8% / 쪽번호(맨숫자) y0 ≈ 92.5% → 하단 90%
_TOP_FRAC = 0.08
_BOTTOM_FRAC = 0.90
_DOC_TITLE_HDR = "국가연구개발사업 제재처분 가이드라인"
_HEADER_WHITELIST = frozenset(
    [_DOC_TITLE_HDR]
    + [f"제{n}장 {t}" for n, t, _p in EXPECTED_CHAPTERS]
    + [f"<부록> {t}" for _n, t, _p in EXPECTED_REFS]
)
_PAGE_MARK = re.compile(r"^(\d+)$")

_SEC_HEAD = re.compile(r"^(\d+)\.\s*(.*)$")


def norm_title(s: str) -> str:
    """제목 대조용 정규화: 공백 제거 + 가운뎃점 이형(･ U+FF65, ㆍ U+318D) → · U+00B7."""
    s = re.sub(r"\s+", "", s)
    return s.replace("･", "·").replace("ㆍ", "·")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 목차(TOC) 파싱 — 판 갱신 드리프트 감지기 ─────────────────────────────────

_TOC_SKIP = re.compile(r"^(CONTENTS|목\s*차)$")
# 별권 목차 엔트리: 제N장 / "N." 절 / "(N)" 소절 / <꺾쇠> 블록 — 전부 점선+쪽번호로 끝남
_TOC_ENTRY = re.compile(
    r"^(제\s*(\d+)\s*장|(\d+)\.|\((\d+)\)|(<[^>]+>))\s*(.*?)\s*·{1,}\s*(\d+)\s*$"
)


def parse_printed_toc(doc):
    """별권 인쇄 목차를 파싱해 chapters/sections/refs/subsections 반환.

    subsections: (chapter_no, section_no) -> 제목 목록. 소절 "(N)"과 내포 꺾쇠 블록
    (<참고:…>·<부칙>)을 현재 절의 검색 제목군으로 귀속(동결 D2 — 제목군 46개).
    <부록>으로 시작하는 꺾쇠 엔트리만 독립 단위(refs)로 분리.
    """
    toc_lines = []
    for i in range(min(15, doc.page_count)):
        text = doc[i].get_text()
        if "목  차" not in text[:60] and "CONTENTS" not in text[:60]:
            continue
        if not re.search(r"제\s*\d+\s*장.*·{1,}\s*\d+", text) and not re.search(
            r"^\(?\d+[.)]\s*.+·{1,}\s*\d+", text, re.M
        ):
            continue
        toc_lines.extend(text.split("\n"))

    # 줄 병합: 점선+쪽번호로 끝나야 엔트리 확정 (2줄 꺾임 제목 대응 — 제5장 2·3절 실측)
    merged = []
    buf = ""
    for raw in toc_lines:
        line = raw.strip()
        if not line:
            continue
        if _TOC_SKIP.match(line):
            if buf:
                merged.append(buf)
                buf = ""
            continue
        buf = (buf + " " + line).strip() if buf else line
        if re.search(r"·{1,}\s*\d+\s*$", buf):
            merged.append(buf)
            buf = ""
    if buf:
        merged.append(buf)

    chapters, sections, refs = [], [], []
    subsections: dict[tuple[int, int], list[str]] = {}
    cur_chapter = None
    cur_section_key = None
    ref_no = 0
    for line in merged:
        m = _TOC_ENTRY.match(line)
        if not m:
            continue
        title, page = m.group(6).strip(), int(m.group(7))
        if m.group(2):  # 제N장
            cur_chapter = int(m.group(2))
            chapters.append((cur_chapter, title, page))
            cur_section_key = None
        elif m.group(3):  # "N." 절
            sec_no = int(m.group(3))
            sections.append((cur_chapter, sec_no, title, page))
            cur_section_key = (cur_chapter, sec_no)
        elif m.group(4):  # "(N)" 소절 — 현재 절 제목군
            if cur_section_key is not None:
                subsections.setdefault(cur_section_key, []).append(
                    f"({int(m.group(4))}) {title}"
                )
        else:  # <꺾쇠> 블록
            bracket = m.group(5)
            if bracket.startswith("<부록>") or bracket == "<부록>":
                ref_no += 1
                refs.append((ref_no, title if title else bracket, page))
            elif cur_section_key is not None:
                label = f"{bracket} {title}".strip() if title else bracket
                subsections.setdefault(cur_section_key, []).append(label)
    return chapters, sections, refs, subsections


def validate_toc(parsed, errors: list[str]):
    chapters, sections, refs, subs = parsed
    exp_ch = [(n, norm_title(t), p) for n, t, p in EXPECTED_CHAPTERS]
    got_ch = [(n, norm_title(t), p) for n, t, p in chapters]
    if got_ch != exp_ch:
        errors.append(f"장 목차 불일치:\n  기대: {exp_ch}\n  파싱: {got_ch}")
    exp_se = [(c, n, norm_title(t), p) for c, n, t, p in EXPECTED_SECTIONS]
    got_se = [(c, n, norm_title(t), p) for c, n, t, p in sections]
    if got_se != exp_se:
        for a, b in zip(exp_se, got_se):
            if a != b:
                errors.append(f"절 목차 불일치: 기대 {a} vs 파싱 {b}")
        if len(exp_se) != len(got_se):
            errors.append(f"절 개수 불일치: 기대 {len(exp_se)} vs 파싱 {len(got_se)}")
    exp_rf = [(n, norm_title(t), p) for n, t, p in EXPECTED_REFS]
    got_rf = [(n, norm_title(t), p) for n, t, p in refs]
    if got_rf != exp_rf:
        errors.append(f"<부록> 목차 불일치:\n  기대: {exp_rf}\n  파싱: {got_rf}")
    # 검색 제목군 전수 내용 대조 (동결 D2: 소절 43 + 내포 블록 3 = 46 — 총수만 검증하면
    # 제목 드리프트를 놓침·P1 적대검토 fault injection 적발로 내용 대조로 강화)
    id_by_key = {(c, n): f"b3-{c}-{n}" for c, n, _t, _p in EXPECTED_SECTIONS}
    got_subs = {id_by_key.get(k): [norm_title(x) for x in v] for k, v in subs.items()}
    exp_subs = {k: [norm_title(x) for x in v] for k, v in EXPECTED_SUBSECTIONS.items()}
    if got_subs != exp_subs:
        for k in sorted(set(exp_subs) | set(got_subs), key=str):
            if exp_subs.get(k) != got_subs.get(k):
                errors.append(f"검색 제목군 불일치[{k}]:\n  기대: {exp_subs.get(k)}\n  파싱: {got_subs.get(k)}")
    n_subs = sum(len(v) for v in subs.values())
    if n_subs != 46:
        errors.append(f"검색 제목군 수 불일치: 기대 46(소절 43+내포 블록 3) vs 파싱 {n_subs}")


# ── 페이지 텍스트 추출 (화이트리스트+bbox 러닝헤더/푸터 제거) ─────────────────

def extract_page_lines(page, printed_page: int, audit: dict) -> list[str]:
    """fitz dict 순서로 줄 재구성. 화이트리스트 일치 상단 헤더·하단 쪽번호만 제거."""
    d = page.get_text("dict")
    height = page.rect.height
    top_limit = height * _TOP_FRAC
    bottom_limit = height * _BOTTOM_FRAC
    kept = []
    for block in d["blocks"]:
        if block.get("type") != 0:
            continue
        for ln in block["lines"]:
            text = "".join(sp["text"] for sp in ln["spans"])
            s = text.strip()
            if not s:
                continue
            y0 = ln["bbox"][1]
            header_like = s in _HEADER_WHITELIST
            mark = _PAGE_MARK.match(s)
            if header_like and y0 <= top_limit:
                audit["removed"] += 1
                audit["removed_by_page"][printed_page] = audit["removed_by_page"].get(printed_page, 0) + 1
                continue
            if mark and y0 >= bottom_limit and int(mark.group(1)) == printed_page:
                audit["removed"] += 1
                audit["removed_by_page"][printed_page] = audit["removed_by_page"].get(printed_page, 0) + 1
                continue
            if (header_like and y0 > top_limit) or (
                mark and int(mark.group(1)) == printed_page and y0 < bottom_limit
            ):
                # 패턴 일치이나 bbox 영역 밖 → 본문으로 보존 + 감사 기록 (과제거 방지)
                audit["kept_outside_region"].append((printed_page, s[:40], round(y0 / height * 100, 1)))
            kept.append(text)
    return kept


def find_heading_indices(lines: list[str], sec_no: int, title: str) -> list[int]:
    """절 시작쪽에서 'N. 제목' 헤딩 줄 index 전수 탐색 — 제목 전방일치 결박(본문 번호목록 오포착 방지).

    호출부가 유일성(정확히 1개)을 검증한다 — 중복 후보 시 첫 후보 묵시 채택은 오귀속 위험
    (P1 적대검토 적발로 유일성 검사 추가).
    """
    tnorm = norm_title(title)
    anchor = tnorm[: min(4, len(tnorm))]
    hits: list[int] = []
    for i, ln in enumerate(lines):
        m = _SEC_HEAD.match(ln.strip())
        if not m or int(m.group(1)) != sec_no:
            continue
        rest = norm_title(m.group(2))
        if rest:
            if rest.startswith(anchor) or tnorm.startswith(rest[: max(2, len(rest))]):
                hits.append(i)
        else:
            follow = norm_title("".join(l.strip() for l in lines[i + 1 : i + 3]))
            if follow.startswith(anchor):
                hits.append(i)
    return hits


def unique_heading_index(lines: list[str], unit: dict) -> tuple[int | None, str | None]:
    """헤딩 index를 유일성 검증과 함께 반환 — (index, 오류메시지)."""
    hits = find_heading_indices(lines, unit["section_no"], unit["section_title"])
    if not hits:
        return None, f"{unit['id']}: 시작쪽 p.{unit['start']}에서 헤딩 미발견"
    if len(hits) > 1:
        return None, f"{unit['id']}: 시작쪽 p.{unit['start']}에서 헤딩 후보 {len(hits)}개(줄 {hits}) — 유일성 위반"
    return hits[0], None


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="혁신법 매뉴얼 별권 3 제재처분 가이드라인 추출 (R2-P1)")
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument(
        "--source-url", required=True,
        help="추출한 판의 KISTEP 게시물 URL (필수 — meta.source_url로 기록. https + kistep.re.kr만 허용)",
    )
    args = ap.parse_args()

    host = urllib.parse.urlparse(args.source_url).hostname or ""
    if not args.source_url.startswith("https://") or not (
        host == "kistep.re.kr" or host.endswith(".kistep.re.kr")
    ):
        print(f"[오류] --source-url은 https://…kistep.re.kr… 형태여야 합니다: {args.source_url}", file=sys.stderr)
        return 1

    if not args.pdf.exists():
        print(f"[오류] PDF가 없습니다: {args.pdf}", file=sys.stderr)
        return 1

    doc = fitz.open(args.pdf)
    pdf_sha = sha256_of(args.pdf)
    off = EXPECTED_PAGE_OFFSET

    # 1) 목차 파싱 + fail-closed 검증
    parsed = parse_printed_toc(doc)
    errors: list[str] = []
    validate_toc(parsed, errors)

    # 2) 쪽번호 오프셋 균일성 검증 — 하단 bbox의 맨숫자 마커 (본권 /N/ 마커와 다름)
    offsets: dict[int, int] = {}
    marker_pages = 0
    for i in range(doc.page_count):
        printed_guess = (i + 1) - off
        if printed_guess < 1 or printed_guess > EXPECTED_BODY_END:
            continue
        page = doc[i]
        height = page.rect.height
        d = page.get_text("dict")
        found = None
        for block in d["blocks"]:
            if block.get("type") != 0:
                continue
            for ln in block["lines"]:
                s = "".join(sp["text"] for sp in ln["spans"]).strip()
                if _PAGE_MARK.match(s) and ln["bbox"][1] >= height * _BOTTOM_FRAC:
                    found = int(s)
        if found is not None:
            marker_pages += 1
            o = (i + 1) - found
            offsets[o] = offsets.get(o, 0) + 1
    if list(offsets.keys()) != [off]:
        errors.append(f"쪽번호 오프셋 불균일: {offsets} (기대 단일값 {off})")
    # 전 본문쪽 마커 존재 강제 — 일부 쪽 마커 부재 시 남은 마커만으로 통과하는 공백 차단(P1 적대검토 적발)
    if marker_pages != EXPECTED_BODY_END:
        errors.append(f"쪽번호 마커 쪽수 불일치: {marker_pages} (기대 {EXPECTED_BODY_END} — 전 본문쪽 마커 실측 전제)")

    if errors:
        print("[fail-closed BLOCK] 목차/오프셋이 EXPECTED 스냅샷과 다릅니다 — JSON 미생성.", file=sys.stderr)
        print("새 판(개정판)이라면 docstring의 판 갱신 절차에 따라 EXPECTED_* 상수를 갱신 후 재실행하십시오.", file=sys.stderr)
        for e in errors:
            print(" - " + e, file=sys.stderr)
        return 2

    _chapters, _sections, _refs, subsections_toc = parsed

    # 3) 본문 페이지 전처리
    audit = {"removed": 0, "removed_by_page": {}, "kept_outside_region": []}
    page_lines: dict[int, list[str]] = {}
    image_pages: set[int] = set()
    table_pages: set[int] = set()
    table_flag_error = None
    for printed in range(1, EXPECTED_BODY_END + 1):
        page = doc[printed + off - 1]
        lines = extract_page_lines(page, printed, audit)
        page_lines[printed] = lines
        joined = "\n".join(lines)
        if len(joined.strip()) < 100 and page.get_images():
            image_pages.add(printed)
        try:
            if page.find_tables().tables:
                table_pages.add(printed)
        except Exception as exc:  # 표 플래그는 advisory — 실패해도 파이프라인 중단 금지
            table_flag_error = f"{type(exc).__name__}: {exc}"

    # 4) 유닛 목록 (별권: 장 표제 간지 없음 — 전 장에서 장 시작쪽 = 첫 절 시작쪽 실측)
    first_sec_of_chapter = {}
    for c, n, _t, p in EXPECTED_SECTIONS:
        first_sec_of_chapter.setdefault(c, p)
    for c, _t, cp in EXPECTED_CHAPTERS:
        if first_sec_of_chapter[c] != cp:
            print(f"[fail-closed BLOCK] 제{c}장 시작쪽 {cp} != 첫 절 시작쪽 {first_sec_of_chapter[c]} — 간지 없음 전제 위반", file=sys.stderr)
            return 2

    units = []
    for c, n, t, p in EXPECTED_SECTIONS:
        units.append({
            "id": f"b3-{c}-{n}", "chapter_no": c,
            "chapter_title": dict((x[0], x[1]) for x in EXPECTED_CHAPTERS)[c],
            "section_label": f"{n}.", "section_no": n, "section_title": t,
            "start": p, "is_ref": False,
            "first_of_chapter": (p == first_sec_of_chapter[c] and n == min(
                sn for cc, sn, _tt, _pp in EXPECTED_SECTIONS if cc == c
            )),
        })
    for n, t, p in EXPECTED_REFS:
        units.append({
            "id": f"b3-ref-{n}", "chapter_no": 0, "chapter_title": "<부록>",
            "section_label": "<부록>", "section_no": n, "section_title": t,
            "start": p, "is_ref": True, "first_of_chapter": True,
        })

    # 5) 절 단위 조립 — 같은 쪽 다중 절 분할 지원 (동결 D4: 헤딩 미발견·순서 역전 = BLOCK)
    units_by_start: dict[int, list[dict]] = {}
    for u in units:
        units_by_start.setdefault(u["start"], []).append(u)

    assembled = []
    boundary_notes = []
    for k, u in enumerate(units):
        next_start = units[k + 1]["start"] if k + 1 < len(units) else EXPECTED_BODY_END + 1
        group = units_by_start[u["start"]]
        pos = group.index(u)
        start_lines = page_lines[u["start"]]

        # 내 시작 index: 쪽 첫 유닛이면서 장 첫 절/부록이면 쪽 처음부터(장 표제 줄 verbatim 포함).
        # 단 이 경우에도 헤딩 실재는 검증한다 — 존재 검사 생략 시 향후 판에서 헤딩 누락을
        # 침묵 통과하는 공백(P1 적대검토 적발).
        if pos == 0 and (u["is_ref"] or u["first_of_chapter"]):
            begin = 0
            if u["is_ref"]:
                marker = f"<부록> {u['section_title']}"
                if not any(norm_title(ln) == norm_title(marker) for ln in start_lines):
                    print(f"[fail-closed BLOCK] {u['id']}: 시작쪽 p.{u['start']}에서 부록 표제 미발견 — JSON 미생성", file=sys.stderr)
                    return 2
            else:
                _idx, err = unique_heading_index(start_lines, u)
                if err:
                    print(f"[fail-closed BLOCK] {err} — JSON 미생성", file=sys.stderr)
                    return 2
        else:
            begin, err = unique_heading_index(start_lines, u)
            if err:
                print(f"[fail-closed BLOCK] {err} — JSON 미생성", file=sys.stderr)
                return 2

        # 내 끝 index: 같은 쪽에서 다음 유닛이 시작하면 그 헤딩 직전까지
        if pos + 1 < len(group):
            nxt = group[pos + 1]
            end, err = unique_heading_index(start_lines, nxt)
            if err:
                print(f"[fail-closed BLOCK] 공유쪽 분할 상대 {err} — JSON 미생성", file=sys.stderr)
                return 2
            if end <= begin:
                print(f"[fail-closed BLOCK] p.{u['start']} 분할 순서 역전: {u['id']}({begin}) ≥ {nxt['id']}({end})", file=sys.stderr)
                return 2
        else:
            end = len(start_lines)

        # 쪽 첫 유닛인데 헤딩 앞 잔여가 있으면 직전 유닛 말미에 귀속
        if pos == 0 and begin > 0:
            pre = start_lines[:begin]
            if assembled:
                prev = assembled[-1]
                prev["pages"].append({"printed_page": u["start"], "partial": True, "lines": pre})
                boundary_notes.append(
                    f"{u['id']}: p.{u['start']} 쪽 중간 분리 — 앞부분 {len(pre)}줄은 {prev['unit']['id']}에 귀속"
                )
            else:
                print(f"[fail-closed BLOCK] {u['id']}: p.{u['start']} 헤딩 앞 잔여 {len(pre)}줄의 귀속처 없음", file=sys.stderr)
                return 2

        partial = begin > 0 or end < len(start_lines)
        pages = [{"printed_page": u["start"], "partial": partial, "lines": start_lines[begin:end]}]
        if partial:
            boundary_notes.append(
                f"{u['id']}: p.{u['start']} 줄 {begin}~{end - 1}/{len(start_lines) - 1} 구간 귀속"
            )

        # 이후 전체 쪽은 같은 쪽 그룹의 마지막 유닛만 소유
        if pos == len(group) - 1:
            for pp in range(u["start"] + 1, next_start):
                pages.append({"printed_page": pp, "partial": False, "lines": page_lines[pp]})
        assembled.append({"unit": u, "pages": pages})

    # 6) 커버리지 검증: 본문 1~EXPECTED_BODY_END 전 쪽이 정확히 귀속 + 분할쪽 줄 손실 0
    covered = set()
    for a in assembled:
        for pg in a["pages"]:
            covered.add(pg["printed_page"])
    missing = [p for p in range(1, EXPECTED_BODY_END + 1) if p not in covered]
    if missing:
        print(f"[fail-closed BLOCK] 커버리지 누락 쪽: {missing}", file=sys.stderr)
        return 2
    # 분할쪽 줄 재구성 검증: 각 쪽의 귀속 줄 합 == 원본 줄 (무손실·무중복)
    lines_by_page: dict[int, int] = {}
    for a in assembled:
        for pg in a["pages"]:
            lines_by_page[pg["printed_page"]] = lines_by_page.get(pg["printed_page"], 0) + len(pg["lines"])
    for pp in range(1, EXPECTED_BODY_END + 1):
        if lines_by_page.get(pp, 0) != len(page_lines[pp]):
            print(f"[fail-closed BLOCK] p.{pp} 줄 계수 불일치: 원본 {len(page_lines[pp])} vs 귀속 합 {lines_by_page.get(pp, 0)}", file=sys.stderr)
            return 2
    # 쪽별 헤더+쪽번호 정확 2줄 제거 강제 — 별권은 전 본문쪽에 헤더 1+쪽번호 1 실측(89×2=178).
    # 총합만 보면 쪽 간 상쇄를 놓침(P1 적대검토 적발).
    bad_removed = {pp: audit["removed_by_page"].get(pp, 0) for pp in range(1, EXPECTED_BODY_END + 1) if audit["removed_by_page"].get(pp, 0) != 2}
    if bad_removed:
        print(f"[fail-closed BLOCK] 쪽별 헤더/쪽번호 제거 수 이상(기대 쪽당 2): {bad_removed}", file=sys.stderr)
        return 2

    # 7) JSON 구성 (section_index는 파일 내 로컬 값 — 동결 D4: 전역 index 저장 금지)
    sections_json = []
    for si, a in enumerate(assembled):
        u = a["unit"]
        pages_json = []
        for pg in a["pages"]:
            pages_json.append({
                "printed_page": pg["printed_page"],
                "partial": pg["partial"],
                "text": "\n".join(pg["lines"]),
            })
        full_text = "\n".join(p["text"] for p in pages_json)
        pstart = pages_json[0]["printed_page"]
        pend = pages_json[-1]["printed_page"]
        sec_key = (u["chapter_no"], u["section_no"])
        sections_json.append({
            "id": u["id"],
            "section_index": si,
            "chapter_no": u["chapter_no"],
            "chapter_title": u["chapter_title"],
            "section_label": u["section_label"],
            "section_title": u["section_title"],
            "page_start": pstart,
            "page_end": pend,
            "pdf_page_start": pstart + off,
            "pdf_page_end": pend + off,
            "char_count": len(full_text),
            "subsection_titles": subsections_toc.get(sec_key, []) if not u["is_ref"] else [],
            "image_only_pages": sorted(p["printed_page"] for p in pages_json if p["printed_page"] in image_pages),
            "table_pages": sorted(p["printed_page"] for p in pages_json if p["printed_page"] in table_pages),
            "warnings": [],
            **(
                {"table_structure_notes": TABLE_STRUCTURE_NOTES[u["id"]]}
                if u["id"] in TABLE_STRUCTURE_NOTES
                else {}
            ),
            "pages": pages_json,
        })

    meta = {
        "schema_version": "1.0",
        "source_title": "국가연구개발사업 제재처분 가이드라인",
        "series_title": "국가연구개발혁신법 매뉴얼",
        "series_part": "별권 3",
        "edition": EDITION,
        "edition_note": EDITION_NOTE,
        "manual_basis_date": None,
        "basis_note": BASIS_NOTE,
        "basis_laws": [],
        "law_priority_extra": LAW_PRIORITY_EXTRA,
        "source_type": "manual_explanation",
        "legal_effect": "not_binding",
        "pdf_sha256": pdf_sha,
        "pdf_pages": doc.page_count,
        "page_offset": off,
        "body_pages_printed": [1, EXPECTED_BODY_END],
        "excluded_note": "표지·관련문의·요약문(로마자 쪽)·목차·뒤표지 미수록 — 인쇄쪽 1~89 전체 수록(간지 없음)",
        "pymupdf_version": fitz.__version__ if hasattr(fitz, "__version__") else fitz.VersionBind,
        "extractor": "scripts/extract_manual_b3.py",
        "source_url": args.source_url,
        "id_format": "^b3-(\\d+-\\d+|ref-\\d+)$",
        "section_count": len(sections_json),
        "chapters": [
            {"no": c, "title": t, "page_start": p} for c, t, p in EXPECTED_CHAPTERS
        ],
    }
    payload = {"meta": meta, "sections": sections_json}

    # 8) 자체 정합성 검증 (fail-closed — assert는 -O 실행에서 제거되므로 명시적 검사·P1 적대검토 적발)
    expected_units = len(EXPECTED_SECTIONS) + len(EXPECTED_REFS)
    ids = [s["id"] for s in sections_json]
    if not (len(ids) == len(set(ids)) == expected_units):
        print(f"[fail-closed BLOCK] 절 id 수 이상: {len(ids)} (기대 {expected_units})", file=sys.stderr)
        return 2
    for s in sections_json:
        if s["char_count"] != len("\n".join(p["text"] for p in s["pages"])):
            print(f"[fail-closed BLOCK] {s['id']}: char_count 불일치", file=sys.stderr)
            return 2
        pp_list = [p["printed_page"] for p in s["pages"]]
        if pp_list != sorted(pp_list):
            print(f"[fail-closed BLOCK] {s['id']}: 페이지 순서 이상 {pp_list}", file=sys.stderr)
            return 2
    total_chars = sum(s["char_count"] for s in sections_json)

    # 원자적 쓰기: 임시 파일에 완성 후 교체 — 중간 실패 시 잘린 JSON·구 JSON 혼재 차단(P1 적대검토 적발)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp_json = args.out_json.with_suffix(".json.tmp")
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp_json, args.out_json)
    json_sha = sha256_of(args.out_json)

    # 9) 품질 리포트
    today = datetime.date.today().isoformat()
    special_chars = {}
    for ch in ("･", "ㆍ", "·", "｢", "｣", "￭", "•", "þ"):
        cnt = sum(("\n".join(p["text"] for p in s["pages"])).count(ch) for s in sections_json)
        if cnt:
            special_chars[ch] = cnt

    rep = []
    rep.append("# 매뉴얼 별권 3 「제재처분 가이드라인」 추출 품질 리포트 (R2-P1)\n")
    rep.append(f"- 실행일: {today} · PyMuPDF {meta['pymupdf_version']}")
    rep.append(f"- PDF: `{args.pdf.name}` · {doc.page_count}쪽 · sha256 `{pdf_sha[:20]}…`")
    try:
        json_path_disp = args.out_json.relative_to(REPO_ROOT)
    except ValueError:
        json_path_disp = args.out_json
    rep.append(f"- JSON: `{json_path_disp}` · sha256 `{json_sha[:20]}…`")
    rep.append(
        f"- 목차 검증: PASS (장 {len(EXPECTED_CHAPTERS)}·절 {len(EXPECTED_SECTIONS)}·부록 {len(EXPECTED_REFS)}"
        f"·검색 제목군 46) · 오프셋 +{off} 균일(마커 {marker_pages}쪽)"
    )
    rep.append(f"- 단위 {len(sections_json)}개 · 총 {total_chars:,}자 · 러닝헤더/푸터 제거 {audit['removed']}줄")
    if table_flag_error:
        rep.append(f"- ⚠ 표 플래그 일부 실패(advisory): {table_flag_error}")
    rep.append("")

    rep.append("## 단위 목록\n")
    rep.append("| id | 라벨 | 절 제목 | 인쇄쪽 | 자수 | 표쪽 | 이미지쪽 |")
    rep.append("|---|---|---|---|---|---|---|")
    for s in sections_json:
        rep.append(
            f"| {s['id']} | {s['section_label']} | {s['section_title'][:28]} | {s['page_start']}~{s['page_end']} "
            f"| {s['char_count']:,} | {len(s['table_pages'])} | {s['image_only_pages'] or ''} |"
        )
    rep.append("")

    rep.append("## 경계 감사 (각 단위 시작/끝 60자 — PDF 원문과 육안 대조용)\n")
    for s in sections_json:
        t = "\n".join(p["text"] for p in s["pages"])
        head = re.sub(r"\s+", " ", t[:60]).strip()
        tail = re.sub(r"\s+", " ", t[-60:]).strip()
        rep.append(f"- `{s['id']}` (p.{s['page_start']}~{s['page_end']})")
        rep.append(f"  - 시작: {head}")
        rep.append(f"  - 끝:   {tail}")
    rep.append("")

    rep.append("## 같은 쪽 다중 절 분할·경계 노트\n")
    if boundary_notes:
        rep.extend(f"- {n}" for n in boundary_notes)
    else:
        rep.append("- (분리 없음)")
    rep.append("")

    rep.append("## 러닝헤더 제거 감사\n")
    anomalies = {p: c for p, c in audit["removed_by_page"].items() if c >= 4}
    zero_removed = [p for p in range(1, EXPECTED_BODY_END + 1) if audit["removed_by_page"].get(p, 0) == 0]
    rep.append(f"- 총 제거 {audit['removed']}줄 · 쪽당 4줄 이상 이상치: {anomalies or '없음'}")
    rep.append(f"- 제거 0줄 본문쪽(헤더 부재 — 빈/이미지쪽 가능): {zero_removed or '없음'}")
    if audit["kept_outside_region"]:
        rep.append("- 패턴 일치했으나 bbox 영역 밖이라 보존한 줄(과제거 방지 확인용):")
        for p, s, ypct in audit["kept_outside_region"]:
            rep.append(f"  - p.{p} (y {ypct}%): {s}")
    else:
        rep.append("- 패턴 일치·영역 밖 보존 줄: 없음")
    rep.append("")

    rep.append("## 특수문자 인벤토리 (verbatim 보존 — 정규화하지 않음)\n")
    for ch, cnt in special_chars.items():
        rep.append(f"- U+{ord(ch):04X} {ch!r}: {cnt:,}회")
    rep.append("")

    with open(args.out_report, "w", encoding="utf-8") as f:
        f.write("\n".join(rep))

    print(f"[OK] JSON {args.out_json} ({args.out_json.stat().st_size:,} bytes, 단위 {len(sections_json)}개, {total_chars:,}자)")
    print(f"[OK] 리포트 {args.out_report}")
    doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
