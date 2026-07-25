#!/usr/bin/env python3
"""국가연구개발혁신법 매뉴얼(본권) 본문 해설부 추출 파이프라인 (R1-P1).

사용법:
    /Users/andykim/my_project/venv/bin/python scripts/extract_manual.py
    (옵션) --pdf <경로> --out-json <경로> --out-report <경로>

의존성: PyMuPDF(fitz) — 이 오프라인 스크립트 전용이며 패키지 런타임 의존성이 아님.
    shared venv(/Users/andykim/my_project/venv)에 설치되어 있음. pyproject.toml에 추가하지 말 것.

산출물:
    src/korean_rnd_regs_mcp/manual_body.json   (절 단위 구조화 데이터 — 패키지 데이터 동봉 대상)
    scripts/manual_extract_report.md           (품질 리포트 — 경계 감사·검수용)

결정론: 같은 PDF + 같은 스크립트 + 같은 PyMuPDF 버전이면 JSON은 byte-identical.
    (추출 일시는 JSON에 넣지 않고 리포트에만 기록.)

차년도 판 갱신 절차(연 1회, 매년 3~5월 개정판 배포 시):
    1. 새 판 PDF로 본 스크립트 실행 → 목차가 EXPECTED 스냅샷과 다르면 fail-closed 오류로 중단됨.
    2. 오류 메시지의 목차 대조표를 보고 아래 EXPECTED_* 상수(장·절 제목/시작쪽·부록 시작쪽·오프셋)와
       EDITION/BASIS 상수를 새 판에 맞게 갱신.
    3. 재실행 → 리포트의 경계 감사표를 육안 검수 → JSON 교체 커밋.
    이 fail-closed 게이트는 편집 구조가 바뀐 판을 침묵 속에 오추출하는 사고를 막기 위한 것임.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = Path(
    "/Users/andykim/mhk/31 - 규정/91-1 - 국가연구개발혁신법 매뉴얼(26.4) - 본권.pdf"
)
DEFAULT_JSON = REPO_ROOT / "src" / "korean_rnd_regs_mcp" / "manual_body.json"
DEFAULT_REPORT = REPO_ROOT / "scripts" / "manual_extract_report.md"

# ── 판(edition) 메타 — 차년도 갱신 대상 ──────────────────────────────────────
EDITION = "26.4"
MANUAL_BASIS_DATE = "2026-03"
BASIS_NOTE = "이 매뉴얼에 기재되어 있는 법령의 시행일(2026.3월 기준) — PDF p.2 머리말"
# PDF p.2 머리말의 법령 기준표를 기재 그대로 옮김 (혁신법 시행일은 매뉴얼 자체 기재값)
BASIS_LAWS = [
    {"name": "국가연구개발혁신법", "effective": "2026-09-11", "amended": "2026-03-10", "number": "법률 제21421호"},
    {"name": "국가연구개발혁신법 시행령", "effective": "2026-06-11", "amended": "2026-03-10", "number": "대통령령 제36163호"},
    {"name": "국가연구개발혁신법 시행규칙", "effective": "2026-03-25", "amended": "2026-03-25", "number": "과학기술정보통신부령 제166호"},
    {"name": "국가연구개발사업 연구개발비 사용기준", "effective": "2026-03-11", "amended": "2026-03-11", "number": "과학기술정보통신부고시 제2026-13호"},
]

# ── EXPECTED 스냅샷 (fail-closed 정본 — 26.4판 인쇄 목차 실측) ────────────────
EXPECTED_PAGE_OFFSET = 10  # PDF쪽 = 인쇄쪽 + 10 (본문부 마커 308쪽 전수 단일값 실측)
EXPECTED_BODY_END = 326  # 인쇄쪽 기준 본문 끝
EXPECTED_APPENDIX_START = 327  # [부록] 관련 서식 시작(제외 대상)

EXPECTED_CHAPTERS = [
    (1, "국가연구개발혁신법 개요", 1),
    (2, "국가연구개발사업의 추진", 47),
    (3, "연구개발비의 지급 및 관리", 173),
    (4, "국가연구개발사업 정보 관리 시스템", 283),
    (5, "국가연구개발사업 추진 지원", 299),
]

# (chapter_no, section_no, title, start_printed)
EXPECTED_SECTIONS = [
    (1, 1, "개요", 3),
    (1, 2, "주요 용어", 18),
    (1, 3, "적용 범위", 33),
    (1, 4, "주체별 책임과 역할", 41),
    (1, 5, "경과 조치", 43),
    (2, 1, "기획 및 예고", 49),
    (2, 2, "사전검토 및 선정", 56),
    (2, 3, "연구개발과제의 협약", 63),
    (2, 4, "연구개발과제 수행의 평가 및 보고", 84),
    (2, 5, "연구개발성과의 귀속 및 활용", 96),
    (2, 6, "기술료 징수･납부･사용", 107),
    (2, 7, "국가연구개발사업의 보안", 114),
    (2, 8, "연구시설･장비 구축･관리･활용", 128),
    (2, 9, "연구개발 수행의 전념", 131),
    (2, 10, "연구윤리 확보 및 제재처분", 145),
    (2, 11, "혁신도전형 앞으로(APRO) R&D", 160),
    (3, 1, "연구개발비의 구성･지급･이관", 175),
    (3, 2, "연구개발비 공통 계상기준 및 사용기준", 182),
    (3, 3, "인건비의 사용용도 및 사용기준", 188),
    (3, 4, "학생인건비 사용용도 및 사용기준", 200),
    (3, 5, "연구시설･장비비 사용용도 및 사용기준", 219),
    (3, 6, "연구재료비 사용용도 및 사용기준", 223),
    (3, 7, "연구활동비 사용용도 및 사용기준", 225),
    (3, 8, "연구수당 사용용도 및 사용기준", 239),
    (3, 9, "보안수당 사용용도 및 사용기준", 243),
    (3, 10, "위탁연구개발비 사용용도 및 사용기준", 245),
    (3, 11, "국제공동연구개발비 및 연구개발부담비 사용용도 및 사용기준", 247),
    (3, 12, "간접비 사용용도 및 사용기준", 249),
    (3, 13, "사용절차 및 사전승인대상", 256),
    (3, 14, "연구개발비 이자 사용용도", 263),
    (3, 15, "연구개발비 정산･회수 절차", 265),
    (3, 16, "간접비고시비율 산출", 273),
    (3, 17, "연구비통합관리시스템", 275),
    (3, 18, "학생인건비통합관리", 277),
    (3, 19, "연구시설･장비비 통합관리", 280),
    (4, 1, "연구개발정보의 관리", 285),
    (4, 2, "범부처 통합 연구지원시스템(IRIS)", 289),
    (5, 1, "연구지원기준 및 연구지원체계평가", 301),
    (5, 2, "전문기관 지정･운영 실태조사", 305),
]

# [참고] 2건 — 제N절 헤딩 없음, 페이지 경계 정렬(시작쪽 상단부터 시작)
EXPECTED_REFS = [
    (1, "초기 중견기업의 기관부담 연구개발비 가이드라인", 313),
    (2, "국외수혜정보 보고 가이드", 315),
]

# ── 러닝헤더/푸터 제거 규칙 (bbox 제한 — 과제거 방지) ─────────────────────────
# 실측: 헤더 y0 ≈ 5.4~5.7%·본문 시작 ≈ 9.2% → 상단 7.5% / 쪽번호 마커 y0 ≈ 93.6% → 하단 90%
_TOP_FRAC = 0.075
_BOTTOM_FRAC = 0.90
_CH_HDR = re.compile(r"^(제\s*\d+\s*장\s+.*|참고\s*)￭+\s*$")
_TITLE_HDR = "「국가연구개발혁신법」 매뉴얼"
_PAGE_MARK = re.compile(r"^[/\\]\s*(\d+)\s*[/\\]$")

_SEC_HEAD = re.compile(r"^제\s*(\d+)\s*절\s*(.*)$")


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


# ── 목차(TOC) 파싱 — 연 1회 판 갱신 드리프트 감지기 ──────────────────────────

_TOC_SKIP = re.compile(r"^(CONTENTS|목\s*차|표 목차|그림 목차|◆.*별권.*)$")
_TOC_ENTRY = re.compile(r"^(제\s*(\d+)\s*장|제\s*(\d+)\s*절|(\d+)\.)\s*(.+?)\s*·{2,}\s*(\d+)\s*$")


def parse_printed_toc(doc):
    """인쇄 목차(장·절 구조 페이지)를 파싱해 chapters/sections/refs/appendix_start/subsections 반환."""
    # 구조 목차 페이지 = 첫 30쪽 중 '목 차' 마커 + 제N장/제N절 점선 엔트리 보유 쪽
    toc_lines = []
    for i in range(min(30, doc.page_count)):
        text = doc[i].get_text()
        if not re.search(r"목\s*차", text[:60]):
            continue
        if not re.search(r"제\s*\d+\s*[장절].*·{2,}\s*\d+", text):
            continue  # 표 목차·그림 목차 쪽 제외
        toc_lines.extend(text.split("\n"))

    # 줄 병합: 점선+쪽번호로 끝나야 엔트리 확정 (긴 제목 줄바꿈 대응)
    merged = []
    buf = ""
    for raw in toc_lines:
        line = raw.strip()
        if not line:
            continue
        if _TOC_SKIP.match(line) or line.startswith("[참고]") or line.startswith("[부록]"):
            if buf:
                merged.append(buf)
                buf = ""
            merged.append(line)
            continue
        buf = (buf + " " + line).strip() if buf else line
        if re.search(r"·{2,}\s*\d+\s*$", buf):
            merged.append(buf)
            buf = ""
    if buf:
        merged.append(buf)

    chapters, sections, refs, subsections = [], [], [], {}
    appendix_start = None
    mode = "body"
    cur_chapter = None
    cur_section_key = None
    for line in merged:
        if line.startswith("[참고]"):
            mode = "ref"
            continue
        if line.startswith("[부록]"):
            mode = "appendix"
            continue
        m = _TOC_ENTRY.match(line)
        if not m:
            continue
        title, page = m.group(5).strip(), int(m.group(6))
        if m.group(2):  # 제N장
            cur_chapter = int(m.group(2))
            chapters.append((cur_chapter, title, page))
            cur_section_key = None
        elif m.group(3):  # 제N절
            sec_no = int(m.group(3))
            sections.append((cur_chapter, sec_no, title, page))
            cur_section_key = (cur_chapter, sec_no)
        else:  # "N." 하위 항목 / 참고 / 부록
            no = int(m.group(4))
            if mode == "ref":
                refs.append((no, title, page))
            elif mode == "appendix":
                if appendix_start is None:
                    appendix_start = page
            elif cur_section_key is not None:
                subsections.setdefault(cur_section_key, []).append(f"{no}. {title}")
    return chapters, sections, refs, appendix_start, subsections


def validate_toc(parsed, errors: list[str]):
    chapters, sections, refs, appendix_start, _subs = parsed
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
        errors.append(f"[참고] 목차 불일치:\n  기대: {exp_rf}\n  파싱: {got_rf}")
    if appendix_start != EXPECTED_APPENDIX_START:
        errors.append(f"[부록] 시작쪽 불일치: 기대 {EXPECTED_APPENDIX_START} vs 파싱 {appendix_start}")


# ── 페이지 텍스트 추출 (bbox 기반 러닝헤더/푸터 제거) ─────────────────────────

def extract_page_lines(page, printed_page: int, audit: dict) -> list[str]:
    """fitz dict 순서로 줄 재구성. 상단 러닝헤더·하단 쪽번호만 bbox 제한 제거."""
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
            header_like = bool(_CH_HDR.match(s)) or s == _TITLE_HDR
            mark = _PAGE_MARK.match(s)
            if header_like and y0 <= top_limit:
                audit["removed"] += 1
                audit["removed_by_page"][printed_page] = audit["removed_by_page"].get(printed_page, 0) + 1
                continue
            if mark and y0 >= bottom_limit and int(mark.group(1)) == printed_page:
                audit["removed"] += 1
                audit["removed_by_page"][printed_page] = audit["removed_by_page"].get(printed_page, 0) + 1
                continue
            if header_like or (mark and int(mark.group(1)) == printed_page):
                # 패턴 일치이나 bbox 영역 밖 → 본문으로 보존 + 감사 기록
                audit["kept_outside_region"].append((printed_page, s[:40], round(y0 / height * 100, 1)))
            kept.append(text)
    return kept


def find_heading_index(lines: list[str], sec_no: int, title: str):
    """절 시작쪽에서 '제N절' 헤딩 줄 index 탐색 — 제목 전방일치 결박(인용문 오분리 방지)."""
    tnorm = norm_title(title)
    anchor = tnorm[: min(4, len(tnorm))]
    for i, ln in enumerate(lines):
        m = _SEC_HEAD.match(ln.strip())
        if not m or int(m.group(1)) != sec_no:
            continue
        rest = norm_title(m.group(2))
        if rest:
            if rest.startswith(anchor) or tnorm.startswith(rest[: max(2, len(rest))]):
                return i
        else:
            follow = norm_title("".join(l.strip() for l in lines[i + 1 : i + 3]))
            if follow.startswith(anchor):
                return i
    return None


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="혁신법 매뉴얼 본권 본문 추출 (R1-P1)")
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-report", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args()

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

    # 2) 쪽번호 오프셋 균일성 검증 (본문부 전수)
    offsets = {}
    marker_pages = 0
    for i in range(doc.page_count):
        printed_guess = (i + 1) - off
        if printed_guess < 1 or printed_guess > EXPECTED_BODY_END:
            continue
        t = doc[i].get_text()
        m = re.search(r"[/\\]\s*(\d+)\s*[/\\]", t)
        if m:
            marker_pages += 1
            o = (i + 1) - int(m.group(1))
            offsets[o] = offsets.get(o, 0) + 1
    if list(offsets.keys()) != [off]:
        errors.append(f"쪽번호 오프셋 불균일: {offsets} (기대 단일값 {off})")

    if errors:
        print("[fail-closed BLOCK] 목차/오프셋이 EXPECTED 스냅샷과 다릅니다 — JSON 미생성.", file=sys.stderr)
        print("새 판(개정판)이라면 스크립트 상단 docstring의 '차년도 판 갱신 절차'에 따라", file=sys.stderr)
        print("EXPECTED_* 상수를 새 판 목차에 맞게 갱신한 뒤 재실행하십시오.", file=sys.stderr)
        for e in errors:
            print(" - " + e, file=sys.stderr)
        return 2

    _chapters, _sections, _refs, _appendix, subsections_toc = parsed

    # 3) 본문 페이지 전처리 (클린 줄·이미지·표 플래그)
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

    # 4) 간지(장 표제지) 산정: [장 시작, 첫 절 시작-1]
    first_sec_of_chapter = {}
    for c, n, _t, p in EXPECTED_SECTIONS:
        first_sec_of_chapter.setdefault(c, p)
    interstitials: set[int] = set()
    for c, _t, cp in EXPECTED_CHAPTERS:
        for pp in range(cp, first_sec_of_chapter[c]):
            interstitials.add(pp)

    # 5) 절 단위 조립 (유닛 순서: 39절 + 참고 2건)
    units = []
    for c, n, t, p in EXPECTED_SECTIONS:
        units.append({
            "id": f"{c}-{n}", "chapter_no": c,
            "chapter_title": dict((x[0], x[1]) for x in EXPECTED_CHAPTERS)[c],
            "section_label": f"제{n}절", "section_no": n, "section_title": t,
            "start": p, "is_ref": False,
            "first_of_chapter": (p == first_sec_of_chapter[c]),
        })
    for n, t, p in EXPECTED_REFS:
        units.append({
            "id": f"ref-{n}", "chapter_no": 0, "chapter_title": "[참고]",
            "section_label": f"참고 {n}", "section_no": n, "section_title": t,
            "start": p, "is_ref": True, "first_of_chapter": True,
        })

    assembled = []  # unit별 pages: [{printed_page, partial, lines}]
    boundary_notes = []
    for k, u in enumerate(units):
        next_start = units[k + 1]["start"] if k + 1 < len(units) else EXPECTED_BODY_END + 1
        pages = []
        # 시작쪽 처리 (in-page split)
        start_lines = page_lines[u["start"]]
        if u["is_ref"] or u["first_of_chapter"]:
            pages.append({"printed_page": u["start"], "partial": False, "lines": start_lines})
        else:
            idx = find_heading_index(start_lines, u["section_no"], u["section_title"])
            if idx is None:
                pages.append({"printed_page": u["start"], "partial": False, "lines": start_lines})
                boundary_notes.append(f"{u['id']}: 시작쪽 p.{u['start']}에서 헤딩 미발견 — 쪽 전체를 본 절에 귀속(warning)")
                u.setdefault("warnings", []).append(f"heading_not_found_on_start_page:{u['start']}")
            else:
                pre = start_lines[:idx]
                post = start_lines[idx:]
                if pre and assembled:
                    prev = assembled[-1]
                    prev["pages"].append({"printed_page": u["start"], "partial": True, "lines": pre})
                    boundary_notes.append(
                        f"{u['id']}: p.{u['start']} 쪽 중간 분리 — 앞부분 {len(pre)}줄은 {prev['unit']['id']}에 귀속"
                    )
                pages.append({"printed_page": u["start"], "partial": bool(pre), "lines": post})
        # 나머지 쪽 (간지 제외)
        for pp in range(u["start"] + 1, next_start):
            if pp in interstitials:
                continue
            pages.append({"printed_page": pp, "partial": False, "lines": page_lines[pp]})
        assembled.append({"unit": u, "pages": pages})

    # 6) 커버리지 검증: 본문 1~326 = 간지 ∪ (각 절 전체쪽) — 분리쪽은 두 절에 걸치되 1회만 계수
    covered = set(interstitials)
    for a in assembled:
        for pg in a["pages"]:
            covered.add(pg["printed_page"])
    missing = [p for p in range(1, EXPECTED_BODY_END + 1) if p not in covered]
    if missing:
        print(f"[fail-closed BLOCK] 커버리지 누락 쪽: {missing}", file=sys.stderr)
        return 2

    # 7) JSON 구성
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
            "subsection_titles": subsections_toc.get(sec_key, []),
            "image_only_pages": sorted(p["printed_page"] for p in pages_json if p["printed_page"] in image_pages),
            "table_pages": sorted(p["printed_page"] for p in pages_json if p["printed_page"] in table_pages),
            "warnings": u.get("warnings", []),
            "pages": pages_json,
        })

    meta = {
        "schema_version": "1.0",
        "source_title": "국가연구개발혁신법 매뉴얼(본권)",
        "edition": EDITION,
        "manual_basis_date": MANUAL_BASIS_DATE,
        "basis_note": BASIS_NOTE,
        "basis_laws": BASIS_LAWS,
        "source_type": "manual_explanation",
        "legal_effect": "not_binding",
        "pdf_sha256": pdf_sha,
        "pdf_pages": doc.page_count,
        "page_offset": off,
        "body_pages_printed": [1, EXPECTED_BODY_END],
        "excluded_note": "[부록] 관련 서식(인쇄 p.327~527)과 별권 4종은 수록 제외 — 장 표제 간지쪽 제외",
        "pymupdf_version": fitz.__version__ if hasattr(fitz, "__version__") else fitz.VersionBind,
        "extractor": "scripts/extract_manual.py",
        "id_format": "^(\\d+-\\d+|ref-\\d+)$",
        "section_count": len(sections_json),
        "chapters": [
            {"no": c, "title": t, "page_start": p} for c, t, p in EXPECTED_CHAPTERS
        ],
    }
    payload = {"meta": meta, "sections": sections_json}

    # 8) 자체 정합성 assert (fail-closed)
    ids = [s["id"] for s in sections_json]
    assert len(ids) == len(set(ids)) == 41, f"절 id 수 이상: {len(ids)}"
    for s in sections_json:
        assert s["char_count"] == len("\n".join(p["text"] for p in s["pages"]))
    total_chars = sum(s["char_count"] for s in sections_json)

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    json_sha = sha256_of(args.out_json)

    # 9) 품질 리포트
    today = datetime.date.today().isoformat()
    special_chars = {}
    for ch in ("･", "ㆍ", "·", "｢", "｣", "￭", "｢", "•"):
        cnt = sum(s["char_count"] and ("\n".join(p["text"] for p in s["pages"])).count(ch) for s in sections_json)
        if cnt:
            special_chars[ch] = cnt

    rep = []
    rep.append("# 매뉴얼 본권 추출 품질 리포트 (R1-P1)\n")
    rep.append(f"- 실행일: {today} · PyMuPDF {meta['pymupdf_version']}")
    rep.append(f"- PDF: `{args.pdf.name}` · {doc.page_count}쪽 · sha256 `{pdf_sha[:20]}…`")
    rep.append(f"- JSON: `{args.out_json.relative_to(REPO_ROOT)}` · sha256 `{json_sha[:20]}…`")
    rep.append(f"- 목차 검증: PASS (장 5·절 39·참고 2·부록 시작 {EXPECTED_APPENDIX_START}) · 오프셋 +{off} 균일(마커 {marker_pages}쪽)")
    rep.append(f"- 절 {len(sections_json)}개 · 총 {total_chars:,}자 · 러닝헤더/푸터 제거 {audit['removed']}줄")
    if table_flag_error:
        rep.append(f"- ⚠ 표 플래그 일부 실패(advisory): {table_flag_error}")
    rep.append("")

    rep.append("## 절 목록\n")
    rep.append("| id | 절 | 인쇄쪽 | 자수 | 표쪽 | 이미지쪽 | 경고 |")
    rep.append("|---|---|---|---|---|---|---|")
    for s in sections_json:
        rep.append(
            f"| {s['id']} | {s['section_label']} {s['section_title'][:24]} | {s['page_start']}~{s['page_end']} "
            f"| {s['char_count']:,} | {len(s['table_pages'])} | {s['image_only_pages'] or ''} | {'; '.join(s['warnings'])} |"
        )
    rep.append("")

    rep.append("## 경계 감사 (각 절 시작/끝 60자 — PDF 원문과 육안 대조용)\n")
    for s in sections_json:
        t = "\n".join(p["text"] for p in s["pages"])
        head = re.sub(r"\s+", " ", t[:60]).strip()
        tail = re.sub(r"\s+", " ", t[-60:]).strip()
        rep.append(f"- `{s['id']}` (p.{s['page_start']}~{s['page_end']})")
        rep.append(f"  - 시작: {head}")
        rep.append(f"  - 끝:   {tail}")
    rep.append("")

    rep.append("## 페이지 중간 분리·경계 노트\n")
    rep.extend(f"- {n}" for n in boundary_notes) if boundary_notes else rep.append("- (분리 없음)")
    rep.append("")

    rep.append("## 간지(장 표제지) 검증 — 제외 쪽별 잔여 자수 (300자 초과 시 구조 변경 의심)\n")
    for pp in sorted(interstitials):
        n_chars = len("\n".join(page_lines[pp]).strip())
        flag = " ⚠" if n_chars > 300 else ""
        rep.append(f"- 인쇄 p.{pp}: {n_chars}자{flag}")
    rep.append("")

    rep.append("## 러닝헤더 제거 감사\n")
    anomalies = {p: c for p, c in audit["removed_by_page"].items() if c >= 4}
    zero_removed = [p for p in range(3, EXPECTED_BODY_END + 1) if p not in interstitials and audit["removed_by_page"].get(p, 0) == 0]
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

    rep.append("## 알려진 추출 아티팩트 (2026-07-25 검수 5쪽 시각 대조 확정 — 원문 유래·재구성 금지 정책상 유지)\n")
    rep.append("- 표 페이지에서 페이지 상단 제목·표 캡션이 추출 순서상 본문 뒤로 밀릴 수 있음(예: 인쇄 p.231 '<표 3-17>' 캡션이 말미). 셀-값 결속은 시각 대조 5쪽(p.5·135·204·231·314) 전건 보존 확인.")
    rep.append("- 일부 불릿 글리프(•)가 텍스트 레이어에서 '쉒' 등 한글 음절로 매핑됨(폰트 서브셋 아티팩트 — ref-1에서 3회 실측). 값·문장에는 영향 없음.")
    rep.append("- 표 셀 텍스트의 붙어쓰기(예: '기업또는')·공백 유실이 드물게 존재 — PDF 텍스트 레이어 원문 그대로임.")
    rep.append("")

    rep.append("## P2 이월 메모\n")
    rep.append("- pyproject.toml wheel force-include에 `manual_body.json` 추가 필요(현재 rule_sets.yaml만) + 패키지 포함 테스트.")
    rep.append("- 대형 절(최대 27k자대) 분할 서빙은 get_manual_section에서 annex_chunk 패턴 재사용.")
    rep.append("- source_type/legal_effect 등 규범성 메타는 meta 1곳에 있음 — P2가 응답마다 복사해 동반할 것.")
    rep.append("")

    with open(args.out_report, "w", encoding="utf-8") as f:
        f.write("\n".join(rep))

    print(f"[OK] JSON {args.out_json} ({args.out_json.stat().st_size:,} bytes, 절 {len(sections_json)}개, {total_chars:,}자)")
    print(f"[OK] 리포트 {args.out_report}")
    doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
