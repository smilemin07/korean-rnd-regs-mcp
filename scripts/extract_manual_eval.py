#!/usr/bin/env python3
"""「국가연구개발 과제평가 표준지침」(25.12) 추출 파이프라인 (v0.38.0 — 매뉴얼 트랙 신규 독립 소스).

사용법:
    /Users/andykim/my_project/venv/bin/python scripts/extract_manual_eval.py \
        --source-url "https://…(공식 게시물 URL)"
    (옵션) --pdf <경로> --out-json <경로> --out-report <경로>

의존성: PyMuPDF(fitz) — 오프라인 스크립트 전용·패키지 런타임 의존성 아님(기존 추출기 4종과 동일).

산출물:
    src/korean_rnd_regs_mcp/manual_eval.json   (절 단위 구조화 데이터 — 패키지 데이터 동봉 대상)
    scripts/manual_eval_extract_report.md      (품질 리포트 — 경계 감사·검수용)

문서 특성 (2026-08-06 실측 — 별권 시리즈와 다른 독립 문서):
    - 혁신법 매뉴얼 시리즈가 아니라 과기정통부·KISTEP 발행 「국가연구개발 과제평가 표준지침」
      (연구성과평가법 제13조 위임 — 각 부처 평가지침의 기준. 행정규칙 미등재라 OpenAPI 미수록).
    - ★판권지(물리 p65) 제목이 "국가연구개발 과제평가 표준지침 개정(안)"·인쇄/발행 2025년 12월.
      2023-12 판도 "개정(안)" 표기 그대로 국가과학기술자문회의 원안 의결·배포된 관행이 확인되어
      미확정본 단정은 하지 않되, meta에 표기 사실을 그대로 기재한다(현행성 단정 금지).
    - 인쇄쪽 마커 = 상단 "N •∙"(짝수쪽)·"∙• N"(홀수쪽) 교호. 인쇄 = 물리 − 4(전 60쪽 균일 실측).
    - 러닝 헤더 = 짝수쪽 문서 제목·홀수쪽 대목차 제목("Ⅰ. 표준지침 개요"류·참고부는 "참 고").
      쪽별 첫 2줄 = 헤더 1 + 마커 1(순서 가변) — 정확 2줄 제거를 쪽별 강제.
    - 편제 = 로마자 대목차 Ⅰ~Ⅲ + 번호 절 + 참고 1~6. 절 헤딩은 "번호 줄" + "제목 줄" 2줄 분리.
      Ⅲ장 도입(인쇄 12~13·단계별 평가절차 개관)은 간지가 아니라 실질 내용이라 eval-3-1(개관)로
      수록하고, 목차 절 1·2는 eval-3-2·eval-3-3에 배정(원문 번호는 section_label "1."·"2."가 보존
      — citation은 label 기준이라 원문 표기와 일치).
    - 수록 제외 = 물리 p1·2·4(무텍스트 표지·간지)·p3(목차)·p65(판권지 — 마커 없음).

결정론: 같은 PDF + 같은 --source-url + 같은 스크립트 + 같은 PyMuPDF 버전이면 JSON은 byte-identical.

판 갱신 절차: 기존 추출기와 동일 — 새 판 게시 시 EXPECTED_* 불일치로 fail-closed 중단되면 목차
대조표를 보고 상수 갱신·구판↔신판 id→제목 전수 대조로 재번호 판정. 산출 JSON은 서버 로더
(load_manual_eval)의 강화 검증(id 유일·eval- 프리픽스·section_index 연속·meta.section_count 일치)을
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
DEFAULT_PDF = Path("/Users/andykim/mhk/31 - 규정/91-2 - 국가연구개발 과제평가 표준지침(25.12).pdf")
DEFAULT_JSON = REPO_ROOT / "src" / "korean_rnd_regs_mcp" / "manual_eval.json"
DEFAULT_REPORT = REPO_ROOT / "scripts" / "manual_eval_extract_report.md"

# ── 승인 원본 고정 (fail-closed — 파일 교체 시 BLOCK) ────────────────────────
# 2026-08-06 실측(diff 적대검토 Gemini MAJOR 반영 — placeholder 방치 시 재현 검증 불능)
EXPECTED_PDF_SHA256 = "9cee1d9a6b451cb47c35a81fedea017dcd7d02e04174b8288441e7f7e9de7b81"
EXPECTED_PHYS_PAGES = 65
PRINT_OFFSET = 4                 # 인쇄쪽 = 물리쪽 − 4 (전 마커쪽 균일 실측)
EXPECTED_BODY_START = 1          # 인쇄 기준
EXPECTED_BODY_END = 60           # 인쇄 기준 (물리 p64) — p65 판권지는 마커 없음·미수록
DOC_TITLE = "국가연구개발 과제평가 표준지침"

# ── 판(edition) 메타 ─────────────────────────────────────────────────────────
EDITION = "25.12"
EDITION_PROVENANCE = "판번은 인쇄·발행 연월(2025.12) 표기 기준"
EDITION_NOTE = (
    "판번 25.12는 표지·판권지의 인쇄·발행 연월(2025년 12월) 표기 기준입니다. "
    "원문 판권지 제목은 「국가연구개발 과제평가 표준지침 개정(안)」으로 표기되어 있습니다"
    "(같은 표기 그대로 심의·배포된 전판 관행이 있어 미확정본을 뜻하지 않을 수 있음 — 확정·후속판 "
    "게시 여부는 과학기술정보통신부·KISTEP 게시 기준으로 확인)."
)
BASIS_NOTE = (
    "이 지침 원문에는 법령 기준일이 별도로 명시되어 있지 않습니다. "
    "연구성과평가법 제13조(표준지침 마련·제공)·같은 법 시행령 제17조(각 부처 평가지침 반영)에 "
    "근거한 과학기술정보통신부 발행 지침이며, 법령·행정규칙이 아닙니다."
)
BASIS_LAWS = [
    "국가연구개발사업 등의 성과평가 및 성과관리에 관한 법률 제13조",
    "국가연구개발사업 등의 성과평가 및 성과관리에 관한 법률 시행령 제17조",
]
# footer 3번째 줄 per-source 문면(v0.38.0) — 기본 문면은 「국가연구개발혁신법 매뉴얼」 하드코딩이라
# 본 지침 인용 응답에 그대로 쓰면 출처 오귀속. 데이터 단일 출처 원칙으로 여기서 공급.
FOOTER_MANUAL_LINE_EVAL = (
    "※ 지침 해설 부분은 「국가연구개발 과제평가 표준지침」을 참고한 설명입니다. "
    "이 지침은 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다."
)
LAW_PRIORITY_EXTRA = [
    "각 부처는 이 표준지침을 고려하여 자체 평가지침을 마련하므로(연구성과평가법 시행령 제17조), "
    "구체 과제에는 소관 부처·전문기관의 평가지침·사업 공고·평가계획이 함께 적용됩니다 — 실제 적용 "
    "기준은 해당 문서에서 확인하십시오.",
    "평가 절차·항목의 법령상 근거(선정·단계·특별·최종평가)는 국가연구개발혁신법 제9조~제16조와 같은 법 "
    "시행령 원문을 get_provision_detail로 교차 확인하십시오.",
    "이 문서의 판권지는 「국가연구개발 과제평가 표준지침 개정(안)」(인쇄·발행 2025년 12월)으로 표기되어 "
    "있으므로, 확정·후속 개정 여부가 중요한 사안에서는 과학기술정보통신부의 최신 게시본을 확인하십시오.",
]

# ── 편제 동결 (fail-closed) — (id, chapter_no, chapter_title, section_label, section_title,
#    start_printed, end_printed) ── end는 다음 유닛 시작 직전까지의 소유 범위(공유 쪽은 분할).
EXPECTED_UNITS = [
    ("eval-1-1", 1, "표준지침 개요", "1.", "법적근거", 1, 1),
    ("eval-1-2", 1, "표준지침 개요", "2.", "지침의 목적", 1, 1),
    ("eval-1-3", 1, "표준지침 개요", "3.", "적용 대상 및 활용", 1, 2),
    ("eval-1-4", 1, "표준지침 개요", "4.", "용어 정의", 2, 6),
    ("eval-1-5", 1, "표준지침 개요", "5.", "평가방식", 6, 7),
    ("eval-2-1", 2, "기본 방향", "", "기본 방향", 8, 11),
    ("eval-3-1", 3, "주요 내용", "", "주요 내용(단계별 평가절차 개관)", 12, 13),
    ("eval-3-2", 3, "주요 내용", "1.", "과제평가 세부기준", 14, 27),
    ("eval-3-3", 3, "주요 내용", "2.", "평가단계별 공통추진사항", 28, 45),
    ("eval-ref-1", 0, "참고", "참고 1", "전문기관 현황", 46, 46),
    ("eval-ref-2", 0, "참고", "참고 2", "과제 수준의 성과목표･지표 설정 방안", 47, 49),
    ("eval-ref-3", 0, "참고", "참고 3", "연구개발 단계별 구분 예시", 50, 50),
    ("eval-ref-4", 0, "참고", "참고 4", "연구개발 단계별 평가 주안점", 51, 51),
    ("eval-ref-5", 0, "참고", "참고 5", "경쟁형 R&D과제 관리 가이드라인", 52, 53),
    ("eval-ref-6", 0, "참고", "참고 6", "과제평가 Q&A", 54, 60),
]

# eval-3-3 하위 4개 평가 단계(같은 "번호 줄+제목 줄" 헤딩 형식·시작 인쇄쪽) — 검색 도달용
# subsection + 시작쪽 실재 fail-closed 검증 대상.
EXPECTED_33_SUBSECTIONS = [("1", "선정평가", 28), ("2", "단계평가", 34), ("3", "특별평가", 38), ("4", "최종평가", 42)]
# eval-ref-6 Q&A 구획(줄 실재만 검증 — 2026-08-06 실측: 인쇄 54·56·58·60 시작 4구획)
EXPECTED_REF6_GROUPS = ["사전검토 및 선정평가", "단계평가", "특별평가", "최종평가"]

_MARKER_EVEN = re.compile(r"^(\d{1,3})\s*•∙\s*$")
_MARKER_ODD = re.compile(r"^∙•\s*(\d{1,3})\s*$")
_HEADER_ODD = re.compile(r"^(Ⅰ\.\s*표준지침 개요|Ⅱ\.\s*기본 방향|Ⅲ\.\s*주요 내용|참\s*고)$")


def norm(s: str) -> str:
    return re.sub(r"[\s･·ㆍ]+", "", s or "")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_page_lines(page, printed: int, audit: dict) -> list[str]:
    """쪽 텍스트를 줄 리스트로 — 러닝 헤더 1줄 + 인쇄쪽 마커 1줄을 정확히 제거(그 외 제거 0)."""
    raw = [l.strip() for l in page.get_text().split("\n")]
    lines = [l for l in raw if l]
    removed = 0
    out = []
    for idx, l in enumerate(lines):
        if idx < 3:
            m = _MARKER_EVEN.match(l) or _MARKER_ODD.match(l)
            if m and int(m.group(1)) == printed and audit["marker_removed"].get(printed) is None:
                audit["marker_removed"][printed] = True
                removed += 1
                continue
            if (l == DOC_TITLE or _HEADER_ODD.match(l)) and audit["header_removed"].get(printed) is None:
                audit["header_removed"][printed] = True
                removed += 1
                continue
        out.append(l)
    audit["removed_by_page"][printed] = removed
    return out


def find_two_line_heading(lines: list[str], no_label: str, title: str) -> list[int]:
    """"번호 줄" + "제목 줄" 2줄 연속 헤딩의 시작 index 목록(번호 없는 유닛은 제목 줄 단독)."""
    hits = []
    tn = norm(title)
    if no_label:
        want_no = no_label.rstrip(".")
        for i in range(len(lines) - 1):
            if lines[i].strip() == want_no and norm(lines[i + 1]) == tn:
                hits.append(i)
    else:
        for i, l in enumerate(lines):
            if norm(l) == tn:
                hits.append(i)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--source-url", required=True,
                    help="공식 게시물 URL(https·kistep.re.kr 또는 msit.go.kr) — fail-closed")
    ap.add_argument("--accept-sha256", default=None,
                    help="최초 실행/판 교체 시 실측 sha256 승인값(EXPECTED_PDF_SHA256 갱신 전 임시 통과)")
    args = ap.parse_args()

    u = urllib.parse.urlparse(args.source_url)
    host = (u.hostname or "").lower()
    # kaia.re.kr 허용(diff 적대검토 Codex MAJOR 반영): 25.12판의 공식 게시처 = KAIA 규정·서식·매뉴얼
    # 목록(게시 PDF sha256이 승인 원본과 byte-identical 대조 완료 2026-08-06). msit 게시물은 24.4판이라
    # 임시 URL로 쓰면 판 불일치 — source_url은 반드시 수록 판이 실재 게시된 경로여야 한다.
    allowed = ("kistep.re.kr", "msit.go.kr", "kaia.re.kr")
    if u.scheme != "https" or not any(host.endswith(d) for d in allowed):
        print("[fail-closed BLOCK] --source-url은 https + kistep.re.kr/msit.go.kr/kaia.re.kr 게시물이어야 합니다", file=sys.stderr)
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

    # 1) 본문 쪽(인쇄 1~60) 추출 — 마커·헤더 정확 제거·오프셋 4 검증
    audit = {"marker_removed": {}, "header_removed": {}, "removed_by_page": {}}
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

    # 2) 유닛 경계 연속성 검증(동결 상수 자체 무결성)
    for k in range(len(EXPECTED_UNITS) - 1):
        cur, nxt = EXPECTED_UNITS[k], EXPECTED_UNITS[k + 1]
        if not (cur[5] <= cur[6] and (nxt[5] == cur[6] or nxt[5] == cur[6] + 1)):
            print(f"[fail-closed BLOCK] 동결 경계 불연속: {cur[0]} {cur[5]}~{cur[6]} → {nxt[0]} {nxt[5]}", file=sys.stderr)
            return 2
    if EXPECTED_UNITS[0][5] != EXPECTED_BODY_START or EXPECTED_UNITS[-1][6] != EXPECTED_BODY_END:
        print("[fail-closed BLOCK] 동결 경계가 본문 범위를 덮지 않음", file=sys.stderr)
        return 2

    # 3) 절 단위 조립 — 같은 쪽 다중 절 분할(인쇄 1 = 3절·인쇄 2 = 2절 등)
    units = [{
        "id": uid, "chapter_no": c, "chapter_title": ct, "section_label": lab,
        "section_title": t, "start": s, "end": e,
    } for uid, c, ct, lab, t, s, e in EXPECTED_UNITS]
    units_by_start: dict[int, list[dict]] = {}
    for uu in units:
        units_by_start.setdefault(uu["start"], []).append(uu)

    assembled = []
    boundary_notes = []
    for k, uu in enumerate(units):
        group = units_by_start[uu["start"]]
        pos = group.index(uu)
        start_lines = page_lines[uu["start"]]

        if uu["chapter_no"] == 0:
            hits = find_two_line_heading(start_lines, "", uu["section_label"])
            label_hits = [i for i in hits]
            if len(label_hits) != 1 or norm(uu["section_title"]) != norm(start_lines[label_hits[0] + 1]):
                print(f"[fail-closed BLOCK] {uu['id']}: p.{uu['start']} 참고 표제('{uu['section_label']}'+제목) 미확정", file=sys.stderr)
                return 2
            begin = label_hits[0]
        elif uu["section_label"]:
            hits = find_two_line_heading(start_lines, uu["section_label"], uu["section_title"])
            if len(hits) != 1:
                print(f"[fail-closed BLOCK] {uu['id']}: p.{uu['start']} 헤딩 '{uu['section_label']} {uu['section_title']}' {len(hits)}회", file=sys.stderr)
                return 2
            begin = hits[0]
            # 장의 첫 절(eval-1-1)은 앞선 장 표제 2줄("Ⅰ"·"표준지침 개요")까지 소유 — b2 규칙과 동일
            # (헤딩 실재는 위에서 이미 검증). 그 외 절은 헤딩부터.
            if uu["id"] == "eval-1-1":
                begin = 0
        else:
            # 장 표제형(eval-2-1·eval-3-1): 로마자 줄 + 장 제목 줄
            roman = {2: "Ⅱ", 3: "Ⅲ"}[uu["chapter_no"]]
            hits = [i for i in range(len(start_lines) - 1)
                    if start_lines[i].strip() == roman and norm(start_lines[i + 1]) == norm(uu["chapter_title"])]
            if len(hits) != 1:
                print(f"[fail-closed BLOCK] {uu['id']}: p.{uu['start']} 장 표제({roman}) {len(hits)}회", file=sys.stderr)
                return 2
            begin = hits[0]

        if pos + 1 < len(group):
            nxt = group[pos + 1]
            nxt_hits = find_two_line_heading(start_lines, nxt["section_label"], nxt["section_title"]) \
                if nxt["chapter_no"] != 0 else find_two_line_heading(start_lines, "", nxt["section_label"])
            if len(nxt_hits) != 1 or nxt_hits[0] <= begin:
                print(f"[fail-closed BLOCK] p.{uu['start']} 공유쪽 분할 실패: {uu['id']} → {nxt['id']}", file=sys.stderr)
                return 2
            end = nxt_hits[0]
        else:
            end = len(start_lines)

        if pos == 0 and begin > 0:
            pre = start_lines[:begin]
            if assembled:
                assembled[-1]["pages"].append({"printed_page": uu["start"], "partial": True, "lines": pre})
                boundary_notes.append(f"{uu['id']}: p.{uu['start']} 앞 {len(pre)}줄은 {assembled[-1]['unit']['id']}에 귀속")
            else:
                print(f"[fail-closed BLOCK] {uu['id']}: p.{uu['start']} 헤딩 앞 잔여 귀속처 없음", file=sys.stderr)
                return 2

        partial = begin > 0 or end < len(start_lines)
        pages = [{"printed_page": uu["start"], "partial": partial, "lines": start_lines[begin:end]}]
        if partial:
            boundary_notes.append(f"{uu['id']}: p.{uu['start']} 줄 {begin}~{end - 1} 구간 귀속")
        if pos == len(group) - 1:
            for pp in range(uu["start"] + 1, uu["end"] + 1):
                if pp in units_by_start:
                    break
                pages.append({"printed_page": pp, "partial": False, "lines": page_lines[pp]})
        assembled.append({"unit": uu, "pages": pages})

    # 4) 커버리지·줄 손실 0 검증
    lines_by_page: dict[int, int] = {}
    for a in assembled:
        for pg in a["pages"]:
            lines_by_page[pg["printed_page"]] = lines_by_page.get(pg["printed_page"], 0) + len(pg["lines"])
    for pp in range(EXPECTED_BODY_START, EXPECTED_BODY_END + 1):
        if lines_by_page.get(pp, 0) != len(page_lines[pp]):
            print(f"[fail-closed BLOCK] p.{pp} 줄 계수 불일치: 원본 {len(page_lines[pp])} vs 귀속 {lines_by_page.get(pp, 0)}", file=sys.stderr)
            return 2

    # 5) eval-3-3 하위 평가단계·ref-6 Q&A 구획 실재 검증(fail-closed) + subsection 등재
    a33 = next(a for a in assembled if a["unit"]["id"] == "eval-3-3")
    for no, t, sp in EXPECTED_33_SUBSECTIONS:
        pg = next((p for p in a33["pages"] if p["printed_page"] == sp), None)
        if pg is None or not find_two_line_heading(pg["lines"], no + ".", t):
            print(f"[fail-closed BLOCK] eval-3-3 하위 '{no} {t}' p.{sp} 미확정", file=sys.stderr)
            return 2
    ref6 = next(a for a in assembled if a["unit"]["id"] == "eval-ref-6")
    ref6_norm = [norm(l) for p in ref6["pages"] for l in p["lines"]]
    for g in EXPECTED_REF6_GROUPS:
        if norm(g) not in ref6_norm:
            print(f"[fail-closed BLOCK] eval-ref-6 구획 '{g}' 줄 미발견", file=sys.stderr)
            return 2

    # 5.5) 표 실재 쪽 자동 산출(find_tables) — diff 적대검토 Codex MAJOR 반영: 전 절 table_pages를
    # 빈 배열로 두면 표 경고 표면(main.py)이 죽는다. 결정론(같은 PDF·같은 PyMuPDF → 같은 결과).
    # ★실질 표 필터(행≥2 AND 열≥2): 이 문서는 강조 박스·구분선 레이아웃이 많아 무필터 find_tables는
    # 전 60쪽을 표로 오감지(1행 박스) — 셀 격자 구조가 실재하는 표만 기록해 경고 노이즈를 차단.
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
            # find_tables 실패는 표 없음으로 두지 않고 보수적으로 표 있음 처리(경고 과소 방지)
            table_pages_all.add(printed)

    # 6) JSON 조립
    sections = []
    for idx, a in enumerate(assembled):
        uu = a["unit"]
        pages_out = []
        for pg in a["pages"]:
            pages_out.append({
                "printed_page": pg["printed_page"],
                "partial": bool(pg["partial"]),
                "text": "\n".join(pg["lines"]),
            })
        pages_out.sort(key=lambda p: p["printed_page"])
        full = "\n".join(p["text"] for p in pages_out)
        subsection_titles: list[str] = []
        if uu["id"] == "eval-3-3":
            subsection_titles = [f"{no} {t}" for no, t, _ in EXPECTED_33_SUBSECTIONS]
        if uu["id"] == "eval-ref-6":
            subsection_titles = list(EXPECTED_REF6_GROUPS)
        sections.append({
            "id": uu["id"],
            "section_index": idx,
            "chapter_no": uu["chapter_no"],
            "chapter_title": uu["chapter_title"],
            "section_label": uu["section_label"],
            "section_title": uu["section_title"],
            "page_start": pages_out[0]["printed_page"],
            "page_end": pages_out[-1]["printed_page"],
            "pdf_page_start": pages_out[0]["printed_page"] + PRINT_OFFSET,
            "pdf_page_end": pages_out[-1]["printed_page"] + PRINT_OFFSET,
            "char_count": len(full),
            "subsection_titles": subsection_titles,
            "image_only_pages": [],   # 전 쪽 텍스트 실재 실측(2026-08-06 — 마커 60쪽 전건 본문 추출)
            "table_pages": sorted(
                p["printed_page"] for p in pages_out if p["printed_page"] in table_pages_all
            ),
            "warnings": [],
            "pages": pages_out,
        })

    meta = {
        "schema_version": "1.0",
        "source_title": DOC_TITLE,
        "edition": EDITION,
        "edition_provenance": EDITION_PROVENANCE,
        "edition_note": EDITION_NOTE,
        "manual_basis_date": None,
        "basis_note": BASIS_NOTE,
        "basis_laws": BASIS_LAWS,
        "law_priority_extra": LAW_PRIORITY_EXTRA,
        "footer_manual_line": FOOTER_MANUAL_LINE_EVAL,
        "source_type": "government_standard_guideline",
        "legal_effect": "not_binding",
        # 판권지 구분 표기(diff 적대검토 Codex MINOR 반영): 발행 = 과기정통부·KISTEP은 주관연구기관
        "publisher": "발행 과학기술정보통신부 · 주관연구기관 한국과학기술기획평가원(KISTEP)",
        "pdf_sha256": digest,
        "source_url": args.source_url,
        "extracted_at": datetime.date.today().isoformat(),
        "physical_pages": EXPECTED_PHYS_PAGES,
        "print_offset": PRINT_OFFSET,
        "section_count": len(sections),
        "excluded_note": "표지·간지(물리 p1·2·4)·목차(p3)·판권지(p65)는 본문이 아니라 수록하지 않았습니다.",
    }
    payload = {"meta": meta, "sections": sections}
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    total_chars = sum(s["char_count"] for s in sections)
    report = ["# manual_eval.json 추출 리포트", "",
              f"- 생성일: {meta['extracted_at']} · PDF sha256: {digest}",
              f"- 단위 {len(sections)}개 · 본문 인쇄 1~{EXPECTED_BODY_END}쪽 · 총 {total_chars:,}자",
              f"- 판권지 표기: 「국가연구개발 과제평가 표준지침 개정(안)」(인쇄·발행 2025-12) — meta.edition_note 기재",
              "", "## 단위별", ""]
    for s in sections:
        report.append(f"- {s['id']}: [{s['chapter_title']}] {s['section_label']} {s['section_title']} — "
                      f"인쇄 {s['page_start']}~{s['page_end']} · {s['char_count']:,}자")
    report += ["", "## 경계 감사", ""] + [f"- {n}" for n in boundary_notes]
    args.out_report.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"OK: {len(sections)}단위 · {total_chars:,}자 → {args.out_json}")
    print(f"리포트: {args.out_report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
