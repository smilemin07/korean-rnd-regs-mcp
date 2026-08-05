#!/usr/bin/env python3
"""혁신법 매뉴얼 별권 4 「연구시설･장비비 통합관리제 운영･관리 매뉴얼」 추출 파이프라인 (v0.39.0 R5).

사용법:
    /Users/andykim/my_project/venv/bin/python scripts/extract_manual_b4.py \
        --source-url "https://www.kistep.re.kr/board.es?mid=a10301000000&bid=0003&act=view&list_no=94788"
    (옵션) --pdf <경로> --out-json <경로> --out-report <경로>

의존성: PyMuPDF(fitz) — 오프라인 스크립트 전용·패키지 런타임 의존성 아님(기존 추출기 5종과 동일).

산출물:
    src/korean_rnd_regs_mcp/manual_b4.json   (절 단위 구조화 데이터 — 패키지 데이터 동봉 대상)
    scripts/manual_b4_extract_report.md      (품질 리포트 — 경계·장부 감사·검수용)

문서 특성 (2026-08-06 실측):
    - 장(章) 없는 평면 편제: 개요 + 로마숫자 Ⅰ~Ⅸ 9개 절 + 참고 1~3(본문 인터리브 박스) + 붙임.
      참고 1(인쇄 7)·참고 2(인쇄 9)는 Ⅱ 본문(5·6·8)과 인터리브라 별도 단위로 떼면 쪽 범위가
      비연속이 됨 → 부모 절(b4-2·b4-6)에 원문 순서대로 병합하고 subsection_titles로 검색 도달
      (계획 /disc 3-AI 3/3). id는 단일 레벨 b4-0(개요)·b4-1~b4-9(Ⅰ~Ⅸ)·b4-ref-1(붙임) —
      인위 2레벨은 존재하지 않는 장을 발명하므로 기각. citation은 chapter_no=0 장 생략 경로.
    - 인쇄쪽 마커 = 홀수쪽 "/ N /"·짝수쪽 "\\ N \\". 인쇄 = 물리 − 4(마커쪽 48쪽 전건 실측).
    - 러닝 헤더 = 홀수쪽 "연구시설･장비비 통합관리제 개요 ￭￭￭"(전 구간 고정)·짝수쪽 문서 제목.
      쪽별 첫 3줄 안에서 헤더 1 + 마커 1 = 정확 2줄 제거를 쪽별 강제. 절 시작 쪽의 배너
      (문서 제목 재등장 + 로마숫자 + 절 제목)는 본문으로 보존(별권 1 데이터와 동형).
    - 판번 텍스트 표기 0회(전문 검색 실측) — 판번은 KISTEP 게시 세트·파일명 기준(별권 1 동형).
    - ★붙임(인쇄 32~50) = 관련 규정 발췌 재수록. 「연구개발비 사용 기준」 발췌의 부칙 표기는
      <제2023-49호, 2023.12.28.>까지 — 현행 고시(제2026-38호·시행 2026-05-06·2026-08-06 LIVE
      재프로브)와 실질 문구 차이 실측 2건(제100조 표준지침 인용 조번호 7→6·제101조
      "참여연구원"→"참여연구자") + 형식 차이 2건(제103조 삭제호 stub 미표기·제111조 "(중략)").
      혁신법·시행령·시행규칙 양식 발췌의 기준 시점은 원문 미표기(확인 불가) — 스냅샷 범위를
      분리해 meta에 사실 기재하고 law_priority_extra로 현행 원문 확인을 유도한다.
    - 수록 제외 = 물리 p1·2·4·6·55(무텍스트)·p3(목차)·p5(개요 간지·인쇄 1) — 본문 마커 48쪽
      (인쇄 3~50) 전체 수록. 전체 장부(수록+제거+제외 = 원본 전체)를 fail-closed로 검증.

결정론: 같은 PDF + 같은 --source-url + 같은 스크립트 + 같은 PyMuPDF 버전이면 JSON은 byte-identical.

판 갱신 절차: 기존 추출기와 동일 — 새 판 게시 시 EXPECTED_* 불일치로 fail-closed 중단되면 목차
대조표를 보고 상수 갱신·구판↔신판 id→제목 전수 대조로 재번호 판정. 산출 JSON은 서버 로더
(load_manual_b4)의 강화 검증(id 유일·b4- 프리픽스·section_index 연속·meta.section_count 일치)을
본 추출기가 자동 충족한다 — JSON 수동 편집 금지(위반 시 로드 격리).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = Path(
    "/Users/andykim/mhk/31 - 규정/"
    "91-1-4 - 국가연구개발혁신법 매뉴얼(26.7) - 별권 4 - 연구시설·장비비 통합관리제 운영·관리 매뉴얼.pdf"
)
DEFAULT_JSON = REPO_ROOT / "src" / "korean_rnd_regs_mcp" / "manual_b4.json"
DEFAULT_REPORT = REPO_ROOT / "scripts" / "manual_b4_extract_report.md"

# ── 승인 원본 고정 (fail-closed — 파일 교체 시 BLOCK) ────────────────────────
EXPECTED_PDF_SHA256 = "41ecb2d753169c7d02c139014b83b8cafaa4cf0f6c0ceed610b2a95fba780e97"  # 2026-08-06 실측
EXPECTED_PHYS_PAGES = 55
PRINT_OFFSET = 4                 # 인쇄쪽 = 물리쪽 − 4 (마커쪽 48쪽 전건 균일 실측)
EXPECTED_BODY_START = 3          # 인쇄 기준 (물리 p7) — 인쇄 1(간지)·2(빈)는 마커 없음·미수록
EXPECTED_BODY_END = 50           # 인쇄 기준 (물리 p54)
EXCLUDED_PHYS = (1, 2, 3, 4, 5, 6, 55)  # 표지류·목차(p3)·개요 간지(p5)·빈 쪽 — 장부 검증 대상
DOC_TITLE = "연구시설･장비비 통합관리제 운영･관리 매뉴얼"   # 원문 반각 가운뎃점(U+FF65) 표기 그대로

# ── 판(edition)·시리즈 메타 ──────────────────────────────────────────────────
EDITION = "26.7"
SERIES_TITLE = "국가연구개발혁신법 매뉴얼"
SERIES_PART = "별권 4"
EDITION_NOTE = (
    "판번은 KISTEP 게시 세트·파일명 기준입니다(별권 PDF 본문·표지에 판번 텍스트 표기 없음). "
    "본권 26.7판과 같은 KISTEP 게시물로 배포되었으며, KISTEP은 26.7 게시 세트에서 별권은 표지만 "
    "변경되었다고 안내하고 있습니다 — 게시 세트 판번이 별권 내용의 2026-07 기준 현행화를 뜻하지 않습니다."
)
BASIS_NOTE = (
    "별권 4 원문에는 본권과 달리 법령 기준일이 명시되어 있지 않습니다. 붙임(관련 규정 발췌)의 "
    "「국가연구개발사업 연구개발비 사용 기준」 발췌는 수록된 부칙 표기 기준 과학기술정보통신부고시 "
    "제2023-49호(2023.12.28.)까지 반영된 스냅샷이고, 그 밖의 발췌(국가연구개발혁신법·같은 법 시행령·"
    "시행규칙 양식)의 기준 시점은 원문에 표기되어 있지 않습니다(확인 불가). 현행 조문은 규정 트랙 "
    "rnd_funding_standard 등으로 확인하십시오. 본권의 기준일(2026-06)을 별권에 준용하지 않았습니다."
)
BASIS_LAWS = [
    "국가연구개발혁신법 제13조제4항",
    "국가연구개발혁신법 시행령 제20조제4항",
    "국가연구개발사업 연구개발비 사용 기준 제7장(제100조~제111조)",
]
LAW_PRIORITY_EXTRA = [
    "연구시설·장비비의 적립·사용 요건, 통합관리기관 지정·취소 기준 등 구체값을 인용할 때는 "
    "get_provision_detail로 국가연구개발사업 연구개발비 사용 기준(rnd_funding_standard) "
    "제7장(제100조~제111조) 현행 원문을 교차 확인하십시오.",
    "이 매뉴얼의 붙임(관련 규정 발췌·b4-ref-1)은 부칙 표기 기준 고시 제2023-49호(2023.12.28.)까지 "
    "반영된 스냅샷이라 현행 고시와 문구가 다른 부분이 확인되었습니다(예: 제100조가 인용하는 "
    "시설·장비 표준지침 조번호, 제101조의 '참여연구자' 용어). 조문 인용은 붙임이 아니라 현행 "
    "원문을 기준으로 하십시오.",
    "붙임의 별지 제13호~제17호서식 발췌는 이 서버의 규정 트랙이 원문을 제공하지 않는 별지 "
    "서식이므로, 실제 작성·제출에는 국가법령정보센터(law.go.kr)의 현행 별지 서식 파일을 확인하십시오.",
]

# ── 편제 동결 (fail-closed) — (id, section_label, section_title, start_printed, end_printed)
#    장 없는 평면 편제: chapter_no=0 고정(citation 장 생략 경로)·전 단위 쪽 경계 시작(공유 쪽 없음).
EXPECTED_UNITS = [
    ("b4-0", "", "연구시설･장비비 통합관리제 개요", 3, 3),
    ("b4-1", "Ⅰ.", "용어의 정의", 4, 4),
    ("b4-2", "Ⅱ.", "통합관리제 시행기관의 지정", 5, 9),
    ("b4-3", "Ⅲ.", "통합관리제 적용 범위", 10, 11),
    ("b4-4", "Ⅳ.", "통합관리계정의 개설･운영", 12, 13),
    ("b4-5", "Ⅴ.", "통합 연구시설･장비비의 계상･지급･적립", 14, 17),
    ("b4-6", "Ⅵ.", "통합 연구시설･장비비의 사용(집행)", 18, 22),
    ("b4-7", "Ⅶ.", "통합관리기관 관리･감독", 23, 25),
    ("b4-8", "Ⅷ.", "통합관리기관 지정 취소", 26, 28),
    ("b4-9", "Ⅸ.", "기타 관리", 29, 31),
    ("b4-ref-1", "붙임", "연구시설･장비비 통합관리제 관련 규정", 32, 50),
]

# 참고 박스(본문 인터리브) — (부모 id, 페이지 내 표제 줄, 제목, 실재 인쇄쪽). 시작 쪽 실재
# fail-closed 검증 + 부모 절 subsection_titles 등재(제목 검색 tier 도달 — 계획 /disc Codex 조건).
EXPECTED_REFERENCES = [
    ("b4-2", "참고1", "공공기관의 운영에 관한 법률에 따른 연구개발 목적기관이란?", 7),
    ("b4-2", "참고2", "연구시설･장비비 통합관리기관 전산시스템 구축요건", 9),
    ("b4-6", "참고3", "ZEUS 국가연구시설･장비 정보 연계", 22),
]

_MARKER = re.compile(r"^([/\\])\s*(\d{1,3})\s*([/\\])$")
HDR_ODD = "연구시설･장비비 통합관리제 개요 ￭￭￭"   # 홀수 인쇄쪽 러닝헤더(전 구간 고정 실측)
HDR_EVEN = DOC_TITLE                                  # 짝수 인쇄쪽 러닝헤더 = 문서 제목
ROMAN_BY_UNIT = {f"b4-{i}": r for i, r in enumerate("ⅠⅡⅢⅣⅤⅥⅦⅧⅨ", start=1)}


def norm(s: str) -> str:
    return re.sub(r"[\s･·ㆍ]+", "", s or "")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_page_lines(page, printed: int, audit: dict) -> list[str]:
    """쪽 텍스트를 줄 리스트로 — 러닝 헤더 1줄 + 인쇄쪽 마커 1줄을 정확히 제거(그 외 제거 0).

    절 시작 쪽 배너의 문서 제목 재등장 줄은 헤더 1회 제거 원칙(audit 플래그)으로 보존된다.
    """
    raw = [l.strip() for l in page.get_text().split("\n")]
    lines = [l for l in raw if l]
    removed = 0
    removed_chars = 0
    out = []
    header = HDR_ODD if printed % 2 else HDR_EVEN
    for idx, l in enumerate(lines):
        if idx < 3:
            m = _MARKER.match(l)
            if m and int(m.group(2)) == printed and audit["marker_removed"].get(printed) is None:
                audit["marker_removed"][printed] = True
                removed += 1
                removed_chars += len(l)
                continue
            if l == header and audit["header_removed"].get(printed) is None:
                audit["header_removed"][printed] = True
                removed += 1
                removed_chars += len(l)
                continue
        out.append(l)
    audit["removed_by_page"][printed] = removed
    audit["removed_chars"] += removed_chars
    return out


def find_heading(lines: list[str], label: str, title: str) -> int | None:
    """표제 줄(label) + 제목 줄(1~2줄 결합 허용) 헤딩의 label 줄 index — 유일 실재 시 index."""
    tn = norm(title)
    hits = []
    for i, l in enumerate(lines):
        if l.strip() != label or i + 1 >= len(lines):
            continue
        j1 = norm(lines[i + 1])
        j2 = norm(lines[i + 1] + (lines[i + 2] if i + 2 < len(lines) else ""))
        if j1 == tn or j2 == tn:
            hits.append(i)
    return hits[0] if len(hits) == 1 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--source-url", required=True,
                    help="공식 게시물 URL(https·kistep.re.kr) — 별권 1~3과 같은 게시 세트")
    ap.add_argument("--accept-sha256", default=None,
                    help="최초 실행/판 교체 시 실측 sha256 승인값(EXPECTED_PDF_SHA256 갱신 전 임시 통과)")
    args = ap.parse_args()

    u = urllib.parse.urlparse(args.source_url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host.endswith("kistep.re.kr"):
        print("[fail-closed BLOCK] --source-url은 https + kistep.re.kr 게시물이어야 합니다", file=sys.stderr)
        return 2

    if not args.pdf.exists():
        print(f"[fail-closed BLOCK] PDF 없음: {args.pdf}", file=sys.stderr)
        return 2
    digest = sha256_of(args.pdf)
    expected = args.accept_sha256 or EXPECTED_PDF_SHA256
    if digest != expected:
        print(f"[fail-closed BLOCK] PDF sha256 불일치 — 승인 원본이 아님.\n  실측: {digest}", file=sys.stderr)
        return 2

    doc = fitz.open(args.pdf)
    if doc.page_count != EXPECTED_PHYS_PAGES:
        print(f"[fail-closed BLOCK] 물리쪽수 {doc.page_count} != {EXPECTED_PHYS_PAGES}", file=sys.stderr)
        return 2

    # 0) 전체 장부 준비 — 원본 전체 줄 수(빈 줄 제외)·글자 수(줄 단위)
    def page_nonempty_lines(idx: int) -> list[str]:
        return [l.strip() for l in doc[idx].get_text().split("\n") if l.strip()]

    total_lines_all = {p: page_nonempty_lines(p - 1) for p in range(1, EXPECTED_PHYS_PAGES + 1)}

    # 물리 쪽 전수 분류 fail-closed: 제외 목록 밖의 쪽은 전부 마커 실재 + 오프셋 4 정합이어야 한다.
    for phys in range(1, EXPECTED_PHYS_PAGES + 1):
        lines = total_lines_all[phys]
        has_marker = any(
            (m := _MARKER.match(l)) and int(m.group(2)) == phys - PRINT_OFFSET for l in lines[:3]
        )
        if phys in EXCLUDED_PHYS:
            if has_marker:
                print(f"[fail-closed BLOCK] 제외 대상 물리 p{phys}에 본문 마커 실재 — 제외 목록 재검토", file=sys.stderr)
                return 2
        elif not has_marker:
            print(f"[fail-closed BLOCK] 물리 p{phys} 마커 부재/오프셋 불일치(기대 인쇄 {phys - PRINT_OFFSET})", file=sys.stderr)
            return 2

    # 1) 본문 쪽(인쇄 3~50) 추출 — 마커·헤더 정확 제거
    audit = {"marker_removed": {}, "header_removed": {}, "removed_by_page": {}, "removed_chars": 0}
    page_lines: dict[int, list[str]] = {}
    for printed in range(EXPECTED_BODY_START, EXPECTED_BODY_END + 1):
        phys = printed + PRINT_OFFSET
        page_lines[printed] = extract_page_lines(doc[phys - 1], printed, audit)
    bad = {p: audit["removed_by_page"].get(p, 0)
           for p in range(EXPECTED_BODY_START, EXPECTED_BODY_END + 1)
           if audit["removed_by_page"].get(p, 0) != 2}
    if bad:
        print(f"[fail-closed BLOCK] 쪽별 헤더/마커 제거 수 이상(기대 쪽당 2): {bad}", file=sys.stderr)
        return 2

    # 2) 유닛 경계 연속성 검증(동결 상수 자체 무결성 — 전 단위 쪽 경계 시작·공유 쪽 없음)
    for k in range(len(EXPECTED_UNITS) - 1):
        cur, nxt = EXPECTED_UNITS[k], EXPECTED_UNITS[k + 1]
        if not (cur[3] <= cur[4] and nxt[3] == cur[4] + 1):
            print(f"[fail-closed BLOCK] 동결 경계 불연속: {cur[0]} {cur[3]}~{cur[4]} → {nxt[0]} {nxt[3]}", file=sys.stderr)
            return 2
    if EXPECTED_UNITS[0][3] != EXPECTED_BODY_START or EXPECTED_UNITS[-1][4] != EXPECTED_BODY_END:
        print("[fail-closed BLOCK] 동결 경계가 본문 범위를 덮지 않음", file=sys.stderr)
        return 2

    # 3) 절 시작 헤딩 실재 검증 — b4-0(개요)은 표제가 간지(미수록)에 있어 본문 비어있지 않음만 확인
    for uid, label, title, start, _end in EXPECTED_UNITS:
        lines = page_lines[start]
        if uid == "b4-0":
            if not lines:
                print("[fail-closed BLOCK] b4-0: 개요 본문(인쇄 3) 빈 쪽", file=sys.stderr)
                return 2
            continue
        want_label = ROMAN_BY_UNIT.get(uid, label.rstrip("."))
        if find_heading(lines, want_label, title) is None:
            print(f"[fail-closed BLOCK] {uid}: p.{start} 헤딩 '{want_label} {title}' 미확정", file=sys.stderr)
            return 2

    # 4) 참고 박스 실재 검증(부모 절 범위 안 + 표제·제목 실재)
    unit_range = {uid: (s, e) for uid, _l, _t, s, e in EXPECTED_UNITS}
    for parent, label, title, printed in EXPECTED_REFERENCES:
        s, e = unit_range[parent]
        if not (s <= printed <= e):
            print(f"[fail-closed BLOCK] {label}: 인쇄 {printed}가 부모 {parent} 범위({s}~{e}) 밖", file=sys.stderr)
            return 2
        if find_heading(page_lines[printed], label, title) is None:
            print(f"[fail-closed BLOCK] {label}: p.{printed} 표제·제목 미확정", file=sys.stderr)
            return 2

    # 5) 표 실재 쪽 자동 산출(find_tables·실질 표 필터 행≥2 AND 열≥2 — eval 추출기 동형)
    table_pages_all: set[int] = set()
    for printed in range(EXPECTED_BODY_START, EXPECTED_BODY_END + 1):
        page = doc[printed + PRINT_OFFSET - 1]
        try:
            for tb in page.find_tables().tables:
                ext = tb.extract()
                rows = len(ext)
                cols = max((len(r) for r in ext), default=0)
                if rows >= 2 and cols >= 2:
                    table_pages_all.add(printed)
                    break
        except Exception:
            table_pages_all.add(printed)  # find_tables 실패는 보수적으로 표 있음 처리(경고 과소 방지)

    # 6) JSON 조립 (공유 쪽 없음 — 단위 = 시작~끝 쪽 통짜)
    sections = []
    for idx, (uid, label, title, start, end) in enumerate(EXPECTED_UNITS):
        pages_out = [{
            "printed_page": pp,
            "partial": False,
            "text": "\n".join(page_lines[pp]),
        } for pp in range(start, end + 1)]
        full = "\n".join(p["text"] for p in pages_out)
        subsection_titles = [
            f"{lab} {t}" for parent, lab, t, _pp in EXPECTED_REFERENCES if parent == uid
        ]
        sections.append({
            "id": uid,
            "section_index": idx,
            "chapter_no": 0,               # 장 없는 평면 편제 — citation 장 생략 경로(계획 /disc 3/3)
            "chapter_title": "",
            "section_label": label,
            "section_title": title,
            "page_start": start,
            "page_end": end,
            "pdf_page_start": start + PRINT_OFFSET,
            "pdf_page_end": end + PRINT_OFFSET,
            "char_count": len(full),
            "subsection_titles": subsection_titles,
            "image_only_pages": [],        # 전 쪽 텍스트 실재 실측(2026-08-06 — 마커 48쪽 전건 본문 추출)
            "table_pages": sorted(p["printed_page"] for p in pages_out
                                  if p["printed_page"] in table_pages_all),
            "warnings": [],
            "pages": pages_out,
        })

    # 7) 커버리지·전체 장부 fail-closed — 수록 + 제거 = 본문 쪽 원본, 본문 + 제외 = 문서 전체
    lines_by_page: dict[int, int] = {}
    for s in sections:
        for pg in s["pages"]:
            lines_by_page[pg["printed_page"]] = (
                lines_by_page.get(pg["printed_page"], 0) + len(pg["text"].split("\n"))
            )
    for pp in range(EXPECTED_BODY_START, EXPECTED_BODY_END + 1):
        if lines_by_page.get(pp, 0) != len(page_lines[pp]):
            print(f"[fail-closed BLOCK] p.{pp} 줄 계수 불일치: 원본 {len(page_lines[pp])} vs 귀속 {lines_by_page.get(pp, 0)}", file=sys.stderr)
            return 2
    total_raw_chars = sum(len(l) for lines in total_lines_all.values() for l in lines)
    included_chars = sum(len(l) for pp in page_lines for l in page_lines[pp])
    excluded_chars = sum(len(l) for phys in EXCLUDED_PHYS for l in total_lines_all[phys])
    if included_chars + audit["removed_chars"] + excluded_chars != total_raw_chars:
        print(
            f"[fail-closed BLOCK] 전체 장부 불일치: 수록 {included_chars} + 제거 {audit['removed_chars']} "
            f"+ 제외 {excluded_chars} != 원본 {total_raw_chars}", file=sys.stderr)
        return 2

    meta = {
        "schema_version": "1.0",
        "source_title": DOC_TITLE,
        "series_title": SERIES_TITLE,
        "series_part": SERIES_PART,
        "edition": EDITION,
        "edition_note": EDITION_NOTE,
        "manual_basis_date": None,
        "basis_note": BASIS_NOTE,
        "basis_laws": BASIS_LAWS,
        "law_priority_extra": LAW_PRIORITY_EXTRA,
        "source_type": "manual_explanation",
        "legal_effect": "not_binding",
        "pdf_sha256": digest,
        "source_url": args.source_url,
        "extracted_at": datetime.date.today().isoformat(),
        "physical_pages": EXPECTED_PHYS_PAGES,
        "print_offset": PRINT_OFFSET,
        "id_format": "^b4-(\\d+|ref-\\d+)$",
        "section_count": len(sections),
        "excluded_note": (
            "표지·빈 쪽(물리 p1·2·4·6·55)·목차(p3)·개요 간지(p5·인쇄 1) 미수록 — "
            "본문 마커 48쪽(인쇄 3~50) 전체 수록"
        ),
    }
    payload = {"meta": meta, "sections": sections}
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    total_chars = sum(s["char_count"] for s in sections)
    report = ["# manual_b4.json 추출 리포트", "",
              f"- 생성일: {meta['extracted_at']} · PDF sha256: {digest}",
              f"- 단위 {len(sections)}개 · 본문 인쇄 {EXPECTED_BODY_START}~{EXPECTED_BODY_END}쪽 · 총 {total_chars:,}자",
              f"- 전체 장부: 원본 {total_raw_chars:,}자 = 수록 {included_chars:,}자 + 헤더/마커 제거 "
              f"{audit['removed_chars']:,}자 + 제외 쪽 {excluded_chars:,}자 (일치 검증 통과)",
              "- 붙임 스냅샷: 「연구개발비 사용 기준」 발췌 = 부칙 <제2023-49호, 2023.12.28.> 기준 — "
              "현행(제2026-38호·2026-05-06) 대비 실질 문구 차이 2건(제100조·제101조)·형식 차이 2건"
              "(제103조 삭제호 stub·제111조 '(중략)') 실측 기록(2026-08-06 LIVE 대조)",
              "", "## 단위별", ""]
    for s in sections:
        subs = f" · 참고 {len(s['subsection_titles'])}건 병합" if s["subsection_titles"] else ""
        report.append(f"- {s['id']}: {s['section_label']} {s['section_title']} — "
                      f"인쇄 {s['page_start']}~{s['page_end']} · {s['char_count']:,}자{subs}")
    args.out_report.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"OK: {len(sections)}단위 · {total_chars:,}자 → {args.out_json}")
    print(f"리포트: {args.out_report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
