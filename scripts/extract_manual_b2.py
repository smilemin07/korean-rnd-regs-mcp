#!/usr/bin/env python3
"""국가연구개발혁신법 매뉴얼 별권 2 「국가연구개발사업 기술료 제도 매뉴얼」 추출 파이프라인 (R3-P1).

사용법:
    /Users/andykim/my_project/venv/bin/python scripts/extract_manual_b2.py \
        --source-url "https://www.kistep.re.kr/board.es?...&list_no=<게시물번호>"
    (옵션) --pdf <경로> --out-json <경로> --out-report <경로>

의존성: PyMuPDF(fitz) — 오프라인 스크립트 전용·패키지 런타임 의존성 아님(본권·별권 3 추출기와 동일).

산출물:
    src/korean_rnd_regs_mcp/manual_b2.json     (절 단위 구조화 데이터 — 패키지 데이터 동봉 대상)
    scripts/manual_b2_extract_report.md        (품질 리포트 — 경계 감사·검수용)

별권 3 스크립트와의 구조 차이 (R3-P0 설계 동결 문서 D1~D12 근거 — 본권·별권 3 스크립트는 무변 유지):
    - 인쇄쪽 마커 = 하단 "/ N /"(홀수쪽)·"\\ N \\"(짝수쪽) 교호 (별권 3의 하단 맨숫자와 다름).
      쪽당 정확히 1개·홀짝 형식·번호 일치를 전부 강제.
    - 러닝 헤더 교호: 홀수쪽 "제N장 <장제목>￭￭￭" 또는 "[부록] <제목>￭￭￭" / 짝수쪽 문서 제목.
      쪽별 기대 헤더를 소유 장 기준으로 계산해 정규화 일치·상단 bbox 이중 조건으로 제거.
    - ★목차-본문 제목 불일치 1건(제2장 1절: 목차 "운영체계" vs 본문 "운영체제" — KISTEP 원문 오기)을
      TOC/BODY 독립 스냅샷 + diff 정확 1건 검증으로 처리(무제한 tolerance 아님 — 동결 D9).
      데이터 제목은 본문 canonical, 목차 표기는 b2-2-1 subsection_titles에 known-variant로 등록
      (기존 검색 제목 tier 메커니즘 재사용 — 검색 누락 방지·코드 무변).
    - 부록 표제가 3줄 꺾임("[부록]" / 제목 2줄) — 줄 단위 정확일치 대신 "[부록]" 줄 실재 +
      정규화 제목 포함으로 검증. 목차 부록 엔트리도 "[부록]" 접두(별권 3의 "<부록>"과 다름).
    - 부록 소제목 6개(EXPECTED_APPENDIX_SUBTITLES)를 실측 동결하고 부록 본문 내 실재를 fail-closed
      검증 후 b2-ref-1 subsection_titles로 등록(별권 3는 목차 소절에서 유도 — 별권 2 목차엔 소절 없음).
    - 승인 PDF sha256·물리 쪽수(17)를 상수로 고정(동결 D9) — 파일 교체 시 BLOCK.
    - 시각 객체 사실 기재(동결 D8 결속 객체 QA·렌더 대조 2026-08-04): 분류 병합 셀(인쇄 5 요율표)·
      [그림 1] 이미지 전용(인쇄 2)·분수식 평면화(인쇄 8~10)·빈 셀 열 귀속(인쇄 12) —
      TABLE_STRUCTURE_NOTES로 동봉.

결정론: 같은 PDF + 같은 --source-url + 같은 스크립트 + 같은 PyMuPDF 버전이면 JSON은 byte-identical.

판 갱신 절차: 본권 extract_manual.py docstring과 동일 — 새 판 게시 시 EXPECTED_* 불일치로
fail-closed 중단되면 목차 대조표를 보고 상수 갱신·구판↔신판 id→제목 전수 대조로 재번호 판정.
EXPECTED_PDF_SHA256·EXPECTED_APPENDIX_SUBTITLES·KNOWN_* 상수도 같은 절차로 재실측 갱신.
산출 JSON은 서버 로더(load_manual_b2)의 강화 검증(id 유일·b2- 프리픽스·section_index 연속·
meta.section_count 일치)을 본 추출기가 자동 충족한다 — JSON 수동 편집 금지(위반 시 로드 격리).
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
    "/Users/andykim/mhk/31 - 규정/91-1-2 - 국가연구개발혁신법 매뉴얼(26.7) - 별권 2 - 기술료제도 매뉴얼.pdf"
)
DEFAULT_JSON = REPO_ROOT / "src" / "korean_rnd_regs_mcp" / "manual_b2.json"
DEFAULT_REPORT = REPO_ROOT / "scripts" / "manual_b2_extract_report.md"

# ── 판(edition) 메타 — 판 갱신 대상 (동결 D7) ────────────────────────────────
EDITION = "26.7"
EDITION_NOTE = (
    "판번은 KISTEP 게시 세트·파일명 기준입니다(별권 PDF 본문·표지에 판번 텍스트 표기 없음). "
    "본권 26.7판과 같은 KISTEP 게시물로 배포되었습니다."
)
BASIS_NOTE = (
    "별권 2 원문에는 본권과 달리 법령 기준일이 명시되어 있지 않습니다. "
    "본권의 기준일(2026-06)을 별권에 준용하지 않았습니다."
)
# 규범성 확장 문장 (R3-P0 D7 동결 문면 — law_priority_note 말미에 append·데이터 단일 출처)
# ★3문장째(구판 용어)의 현행 용어 문자열은 P2 게이트에서 시행령 제38조·제39조 라이브 조문으로
#   재검증 후 확정한다(P0 동결 조건). 검증 실패 시 이 상수만 고쳐 재추출.
LAW_PRIORITY_EXTRA = [
    "기술료율·납부 상한·납부 기간 등 구체값을 인용할 때는 get_provision_detail로 국가연구개발혁신법 시행령 제38조~제41조 원문을 교차 확인하십시오.",
    "[부록]의 기술기여도 산정 예시와 협약 단계 가이드라인은 참고용이므로 개별 사안에 그대로 일반화할 수 없습니다.",
    "이 매뉴얼이 사용하는 '기술료등납부의무기관'은 현행 시행령에서 '정부납부기술료납부의무기관'으로 변경되었으므로, 현행 용어와 적용 범위는 시행령 제38조·제39조 원문을 기준으로 확인하십시오.",
]

# ── EXPECTED 스냅샷 (fail-closed 정본 — 별권2 26.7판 실측 2026-08-04) ─────────
EXPECTED_PDF_SHA256 = "0de99c80c062602d33801e286c31bd90f4f479bae15f819b36ec0f217e70161a"
EXPECTED_PHYSICAL_PAGES = 17
EXPECTED_PAGE_OFFSET = 4  # PDF쪽 = 인쇄쪽 + 4 (표지·간지·목차·간지)
EXPECTED_BODY_END = 12  # 인쇄쪽 기준 본문 끝 (물리 p.16 — p.17은 마커 없는 뒤표지)
EXPECTED_SOURCE_LIST_NO = "94788"  # 승인 KISTEP 게시물 번호 (판 갱신 시 재실측)

# 쪽별 추출 텍스트(헤더·마커 제거 후) sha256 — 검증 완료 산출물(2026-08-04) 기준 동결.
# ★목적: PyMuPDF 버전 드리프트·추출 로직 회귀로 인한 침묵 텍스트 변화 차단(P1 적대검토 채택).
# 판 갱신·라이브러리 갱신 시 불일치로 BLOCK되면 원문 대조 후 재실측 갱신.
EXPECTED_PAGE_TEXT_SHA256 = {
    1: "67001d2f226f2cd4e544259dffe411cf8ddd78308dbc50f834deb9cad84cf703",
    2: "600fa6bd222d627d83443f3fe41a2fb0bc0c4720c1af11535c293c4c59e33c25",
    3: "aa0263501f2fe0a214f5ed0306dad8b41120f299e0a183c85d2f7a2890b95a15",
    4: "458d509d5100c750097f85f71e39d919ccf1f6a694c81b6c48be328f27ae2c94",
    5: "f78f6966835b000eac00d10207884a7132d0986f1c4d23d1fbf269e79a268905",
    6: "c05e747707efde992e643aeadcd51229cba9dbdc5106f0d18374e0402cf20cbd",
    7: "8ac0ff75632dbf524c0e5ea620322628e760d0954674c79b502af3df8265764a",
    8: "5751d155cb191093f69842de027371f5e330559f3ad0023a88ae08942c71c440",
    9: "98e3f13d37b12febf3424d3a41646f002fe77272f3930fbb40557ddf1f1375d6",
    10: "d1366dd89d9de5d123c30d658d35a8bfccd17909f52ecb5b4d8928b232ccd0eb",
    11: "8894ed9f6ef54efc3534891fff54415f8dd59e49a42d51f8c2fc40cda96b4e82",
    12: "c1c9a7982fc1e3484367030cdda22e9952ad486cb0119e6a060ea1e5ea432f8c",
}
EXPECTED_TOTAL_CHARS = 9531  # 단위 char_count 합계 (분할 경계 개행 산술 포함) — 최종 JSON 잠금

EXPECTED_CHAPTERS = [
    (1, "기술료 제도의 개요", 1),
    (2, "기술료 제도의 운영", 2),
    (3, "정부납부기술료 세부 기준", 5),
]

# (chapter_no, section_no, title, start_printed) — 목차 스냅샷 (목차 원문 verbatim: "운영체계")
EXPECTED_TOC_SECTIONS = [
    (1, 1, "정의", 1),
    (1, 2, "목적", 1),
    (1, 3, "근거", 1),
    (2, 1, "운영체계", 2),
    (2, 2, "기술료의 징수", 3),
    (2, 3, "정부납부기술료", 3),
    (2, 4, "기술료 등의 감면", 4),
    (2, 5, "기술료의 사용", 4),
    (3, 1, "정부납부기술료 납부대상", 5),
    (3, 2, "정부납부기술료 납부 기준", 5),
    (3, 3, "정부납부기술료 납부 기간", 6),
    (3, 4, "정부납부기술료 감면", 6),
    (3, 5, "정부납부기술료 납부 수단", 6),
    (3, 6, "관련 서식", 6),
]

# 본문 헤딩 스냅샷 (본문 원문 verbatim: "운영체제") — 데이터 제목의 canonical (동결 D9)
EXPECTED_BODY_SECTIONS = [
    (1, 1, "정의", 1),
    (1, 2, "목적", 1),
    (1, 3, "근거", 1),
    (2, 1, "운영체제", 2),
    (2, 2, "기술료의 징수", 3),
    (2, 3, "정부납부기술료", 3),
    (2, 4, "기술료 등의 감면", 4),
    (2, 5, "기술료의 사용", 4),
    (3, 1, "정부납부기술료 납부대상", 5),
    (3, 2, "정부납부기술료 납부 기준", 5),
    (3, 3, "정부납부기술료 납부 기간", 6),
    (3, 4, "정부납부기술료 감면", 6),
    (3, 5, "정부납부기술료 납부 수단", 6),
    (3, 6, "관련 서식", 6),
]

# 목차↔본문 승인 불일치 — 정확히 이 1건만 허용 (그 외 diff는 BLOCK — 동결 D9)
KNOWN_TOC_BODY_MISMATCH = {(2, 1): ("운영체계", "운영체제")}

# [부록] 1건 — 비장절 독립자료(chapter_no 0·section_label "[부록]")
EXPECTED_REFS = [
    (1, "연구개발과제협약 시 기술기여도 산정 및 검증 가이드라인", 7),
]

# 부록 소제목 6개 — 본문 실측 verbatim (렌더 대조 2026-08-04). b2-ref-1 검색 제목군으로 등록하고
# 부록 본문 내 실재를 fail-closed 검증(동결 D2 — 별권 2 목차엔 소절 엔트리가 없어 목차 유도 불가).
EXPECTED_APPENDIX_SUBTITLES = [
    "납부 대상",
    "납부 기준(「국가연구개발혁신법 시행령」제39조)",
    "매출액 기준에 따른 기술기여도 산정 방법(예시)",
    "기술기여도 작성",
    "매출액 검증절차",
    "기타",
]

# 목차 표기 known-variant — 검색 제목군에만 추가(데이터 제목은 본문 canonical·동결 D9).
# provenance: 목차 표기(KISTEP 원문 오기)로 검색하는 사용자의 제목 tier 도달 보장.
# ★별도 상수가 아니라 KNOWN_TOC_BODY_MISMATCH에서 유도 — 이중 장부 드리프트 차단(P1 적대검토 채택).
def known_toc_variants() -> dict[str, list[str]]:
    return {
        f"b2-{c}-{n}": [toc_title]
        for (c, n), (toc_title, _body_title) in sorted(KNOWN_TOC_BODY_MISMATCH.items())
    }

# 결속 객체 사실 기재 (동결 D8 — P1 렌더 대조 실측. 값 오결속이 아니라 구조 정보가 텍스트에 없음.
# 경고 부착은 보류 회피 수단이 아님 — 값·본문 보존이 확인된 (ii) 판정 객체에만 부착)
TABLE_STRUCTURE_NOTES = {
    "b2-2-1": [
        "이 절의 [그림 1] 기술료제도 운영체제 도식은 이미지로만 실려 있어 도식 안의 기관 간 흐름·"
        "납부 상한·기술료 사용 항목이 추출 텍스트에 없습니다. 해당 수치·항목은 제2장 3~5절과 "
        "제3장 본문 또는 시행령 제38조~제41조 원문으로 확인하십시오.",
    ],
    "b2-3-2": [
        "이 절의 정부납부기술료 기준표는 '분류' 열(제3자 실시/직접 실시)이 세로 병합 셀이라 추출 "
        "텍스트에서 각 그룹 첫 위치에 한 번만 나타나며, 어느 행까지 적용되는지는 직렬화 순서로만 "
        "구분됩니다. 행별 귀속은 표기된 인쇄쪽 원문 또는 시행령 제38조·제39조 원문으로 확인하십시오.",
    ],
    "b2-ref-1": [
        "이 부록의 기술기여도 산식(분수식)은 분자·분모가 세로로 나뉜 줄로 직렬화되어 나눗셈 관계가 "
        "텍스트에 없습니다(매출액 계층도의 상하 관계도 동일). 산식 구조는 표기된 인쇄쪽 원문으로 "
        "확인하십시오.",
        "인쇄 12쪽 산정기준 표는 '협약 시' 열의 빈 셀이 추출 텍스트에서 사라져 '실사용 적용' 등 값의 "
        "열 귀속이 텍스트에 없습니다. 열 귀속은 인쇄쪽 원문으로 확인하십시오.",
    ],
}

# ── 러닝헤더/마커 제거 규칙 (실측: 헤더 y0 5.4~5.7%·장 표제 밴드 9.2~9.5% → 상단 8% /
#    마커 y0 93.6% → 하단 90%) ─────────────────────────────────────────────────
_TOP_FRAC = 0.08
_BOTTOM_FRAC = 0.90
_DOC_TITLE_HDR = "국가연구개발사업 기술료 제도 매뉴얼"
# 인쇄쪽 마커: 홀수 "/ N /"·짝수 "\ N \" (양끝 동일 문자 — 홀짝 강제)
_PAGE_MARK = re.compile(r"^([\\/])\s*(\d+)\s*([\\/])$")

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


def expected_header_for(printed: int) -> str:
    """쪽별 기대 러닝 헤더(정규화 전 원형 아님 — 정규화 비교용 기준 문자열).

    짝수쪽 = 문서 제목. 홀수쪽 = 그 쪽을 소유한 장 "제N장 <제목>￭￭￭" 또는 부록 "[부록] <제목>￭￭￭".
    """
    if printed % 2 == 0:
        return _DOC_TITLE_HDR
    ref_start = EXPECTED_REFS[0][2]
    if printed >= ref_start:
        return f"[부록] {EXPECTED_REFS[0][1]}￭￭￭"
    owner = None
    for c, t, p in EXPECTED_CHAPTERS:
        if p <= printed:
            owner = (c, t)
    return f"제{owner[0]}장 {owner[1]}￭￭￭"


# ── 목차(TOC) 파싱 — 판 갱신 드리프트 감지기 ─────────────────────────────────

_TOC_SKIP = re.compile(r"^(CONTENTS|목\s*차)$")
# 별권 2 목차 엔트리: 제N장 / "N." 절 / "[부록]" — 전부 점선+쪽번호로 끝남(소절 "(N)" 없음)
_TOC_ENTRY = re.compile(
    r"^(?:제\s*(\d+)\s*장|(\d+)\.|(\[부록\]))\s*(.*?)\s*·{1,}\s*(\d+)\s*$"
)


def parse_printed_toc(doc):
    """별권 2 인쇄 목차를 파싱해 chapters/sections/refs 반환 (2줄 꺾임 제목 대응 — 부록 실측)."""
    toc_lines = []
    for i in range(min(10, doc.page_count)):
        text = doc[i].get_text()
        if "목  차" not in text[:60] and "CONTENTS" not in text[:60]:
            continue
        if not re.search(r"제\s*\d+\s*장.*·{1,}\s*\d+", text):
            continue
        toc_lines.extend(text.split("\n"))

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
    cur_chapter = None
    ref_no = 0
    for line in merged:
        m = _TOC_ENTRY.match(line)
        if not m:
            continue
        title, page = m.group(4).strip(), int(m.group(5))
        if m.group(1):  # 제N장
            cur_chapter = int(m.group(1))
            chapters.append((cur_chapter, title, page))
        elif m.group(2):  # "N." 절
            sections.append((cur_chapter, int(m.group(2)), title, page))
        else:  # [부록]
            ref_no += 1
            refs.append((ref_no, title, page))
    return chapters, sections, refs


def validate_constants(errors: list[str]):
    """상수 자체 정합성: TOC/BODY 스냅샷 diff = 승인 목록·상수 관계식·notes 쪽 참조 (동결 D9)."""
    # 상수 관계식: 본문 끝 = 물리 쪽수 − 오프셋 − 뒤표지 1 (결합 드리프트 차단 — P1 적대검토 채택)
    if EXPECTED_BODY_END != EXPECTED_PHYSICAL_PAGES - EXPECTED_PAGE_OFFSET - 1:
        errors.append(
            f"상수 관계식 위반: BODY_END {EXPECTED_BODY_END} != 물리 {EXPECTED_PHYSICAL_PAGES} - 오프셋 {EXPECTED_PAGE_OFFSET} - 1"
        )
    if sorted(EXPECTED_PAGE_TEXT_SHA256) != list(range(1, EXPECTED_BODY_END + 1)):
        errors.append("EXPECTED_PAGE_TEXT_SHA256 키가 본문 쪽 1~BODY_END와 불일치")
    # notes의 "인쇄 N쪽" 참조가 수록 범위 안인지 (상수-본문 범위 결합 드리프트 차단)
    for sid, notes in TABLE_STRUCTURE_NOTES.items():
        for note in notes:
            for m in re.finditer(r"인쇄\s*(\d+)쪽", note):
                n = int(m.group(1))
                if not (1 <= n <= EXPECTED_BODY_END):
                    errors.append(f"TABLE_STRUCTURE_NOTES[{sid}]의 쪽 참조 {n}이 수록 범위(1~{EXPECTED_BODY_END}) 밖")
    toc_by_key = {(c, n): (t, p) for c, n, t, p in EXPECTED_TOC_SECTIONS}
    body_by_key = {(c, n): (t, p) for c, n, t, p in EXPECTED_BODY_SECTIONS}
    if set(toc_by_key) != set(body_by_key):
        errors.append("TOC/BODY 스냅샷의 (장,절) 키 집합 불일치")
        return
    diffs = {}
    for k in toc_by_key:
        if toc_by_key[k] != body_by_key[k]:
            if toc_by_key[k][1] != body_by_key[k][1]:
                errors.append(f"TOC/BODY 시작쪽 불일치 {k}: {toc_by_key[k][1]} vs {body_by_key[k][1]}")
            diffs[k] = (toc_by_key[k][0], body_by_key[k][0])
    expected_diffs = KNOWN_TOC_BODY_MISMATCH
    if diffs != expected_diffs:
        errors.append(
            f"TOC/BODY 제목 diff가 승인 목록과 다름:\n  승인: {expected_diffs}\n  실제: {diffs}"
        )


def validate_toc(parsed, errors: list[str]):
    chapters, sections, refs = parsed
    exp_ch = [(n, norm_title(t), p) for n, t, p in EXPECTED_CHAPTERS]
    got_ch = [(n, norm_title(t), p) for n, t, p in chapters]
    if got_ch != exp_ch:
        errors.append(f"장 목차 불일치:\n  기대: {exp_ch}\n  파싱: {got_ch}")
    exp_se = [(c, n, norm_title(t), p) for c, n, t, p in EXPECTED_TOC_SECTIONS]
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
        errors.append(f"[부록] 목차 불일치:\n  기대: {exp_rf}\n  파싱: {got_rf}")


# ── 페이지 텍스트 추출 (쪽별 기대 헤더·홀짝 마커 + bbox 이중 조건 제거) ───────

def extract_page_lines(page, printed: int, audit: dict) -> list[str]:
    """fitz dict 순서로 줄 재구성. 쪽별 기대 헤더(상단)·홀짝 마커(하단)만 제거."""
    d = page.get_text("dict")
    height = page.rect.height
    top_limit = height * _TOP_FRAC
    bottom_limit = height * _BOTTOM_FRAC
    exp_header_norm = norm_title(expected_header_for(printed))
    want_slash = "/" if printed % 2 == 1 else "\\"
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
            header_like = norm_title(s) == exp_header_norm
            m = _PAGE_MARK.match(s)
            mark_ok = bool(
                m and int(m.group(2)) == printed
                and m.group(1) == want_slash and m.group(3) == want_slash
            )
            if header_like and y0 <= top_limit:
                audit["removed"] += 1
                audit["removed_by_page"][printed] = audit["removed_by_page"].get(printed, 0) + 1
                continue
            if mark_ok and y0 >= bottom_limit:
                audit["removed"] += 1
                audit["removed_by_page"][printed] = audit["removed_by_page"].get(printed, 0) + 1
                continue
            if (header_like and y0 > top_limit) or (mark_ok and y0 < bottom_limit):
                # 패턴 일치이나 bbox 영역 밖 → 본문으로 보존 + 감사 기록 (과제거 방지 —
                # 짝수 장 시작쪽의 문서 제목 밴드 y≈9.5%가 여기 잡힌다·실측 인쇄 2)
                audit["kept_outside_region"].append((printed, s[:40], round(y0 / height * 100, 1)))
            if norm_title(s) == norm_title(_DOC_TITLE_HDR) and not (header_like and y0 <= top_limit):
                # 문서 제목 밴드 보존 전건 기록 — 홀수쪽(기대 헤더가 장 형)은 kept_outside_region에
                # 잡히지 않아 감사 리포트 공백이 생김(P1 적대검토 채택·실측 인쇄 1·2·5)
                audit["doc_title_band"].append((printed, round(y0 / height * 100, 1)))
            kept.append(text)
    return kept


def find_heading_indices(lines: list[str], sec_no: int, title: str) -> list[int]:
    """절 시작쪽에서 'N. 제목' 헤딩 줄 index 전수 탐색 — 정규화 전체 제목 정확 일치.

    별권 2는 14개 헤딩 전건이 한 줄이라 별권 3의 전방일치·꺾임 보정이 불필요하며,
    정확 일치가 본문 수치("2.5%" 등) 오포착과 상수 동시 변조 주입을 모두 차단한다
    (P1 적대검토 채택 — 4자 anchor는 'N. 제목X' 변조를 통과시켰다).
    """
    tnorm = norm_title(title)
    hits: list[int] = []
    for i, ln in enumerate(lines):
        m = _SEC_HEAD.match(ln.strip())
        if not m or int(m.group(1)) != sec_no:
            continue
        if norm_title(m.group(2)) == tnorm:
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
    ap = argparse.ArgumentParser(description="혁신법 매뉴얼 별권 2 기술료 제도 매뉴얼 추출 (R3-P1)")
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument(
        "--source-url", required=True,
        help="추출한 판의 KISTEP 게시물 URL (필수 — meta.source_url로 기록. https + kistep.re.kr만 허용)",
    )
    args = ap.parse_args()

    parsed_url = urllib.parse.urlparse(args.source_url)
    host = parsed_url.hostname or ""
    if not args.source_url.startswith("https://") or not (
        host == "kistep.re.kr" or host.endswith(".kistep.re.kr")
    ):
        print(f"[오류] --source-url은 https://…kistep.re.kr… 형태여야 합니다: {args.source_url}", file=sys.stderr)
        return 1
    # 승인 게시물 고정 — 다른 게시물 URL이 provenance로 기록되는 것 차단(P1 적대검토 채택)
    list_no = urllib.parse.parse_qs(parsed_url.query).get("list_no", [None])[0]
    if list_no != EXPECTED_SOURCE_LIST_NO:
        print(
            f"[fail-closed BLOCK] source-url의 list_no {list_no!r} != 승인 {EXPECTED_SOURCE_LIST_NO!r} "
            "— 판 갱신이라면 EXPECTED_SOURCE_LIST_NO를 재실측 갱신하십시오.",
            file=sys.stderr,
        )
        return 2

    if not args.pdf.exists():
        print(f"[오류] PDF가 없습니다: {args.pdf}", file=sys.stderr)
        return 1

    pdf_sha = sha256_of(args.pdf)
    if pdf_sha != EXPECTED_PDF_SHA256:
        print("[fail-closed BLOCK] PDF sha256이 승인 스냅샷과 다릅니다 — JSON 미생성.", file=sys.stderr)
        print(f"  기대: {EXPECTED_PDF_SHA256}\n  실제: {pdf_sha}", file=sys.stderr)
        print("새 판(개정판)이라면 docstring의 판 갱신 절차에 따라 EXPECTED_* 상수를 재실측·갱신 후 재실행하십시오.", file=sys.stderr)
        return 2

    doc = fitz.open(args.pdf)
    if doc.page_count != EXPECTED_PHYSICAL_PAGES:
        print(f"[fail-closed BLOCK] 물리 쪽수 {doc.page_count} (기대 {EXPECTED_PHYSICAL_PAGES}) — JSON 미생성.", file=sys.stderr)
        return 2
    off = EXPECTED_PAGE_OFFSET

    # 0) 상수 자체 정합성 + 1) 목차 파싱 + fail-closed 검증
    errors: list[str] = []
    validate_constants(errors)
    parsed = parse_printed_toc(doc)
    validate_toc(parsed, errors)

    # 2) 쪽번호 마커 검증 — 하단 bbox·홀짝 형식·번호 일치·쪽당 정확 1개·전 본문쪽 실재
    marker_count_by_page: dict[int, int] = {}
    offsets: dict[int, int] = {}
    for i in range(doc.page_count):
        printed_guess = (i + 1) - off
        if printed_guess < 1 or printed_guess > EXPECTED_BODY_END:
            continue
        page = doc[i]
        height = page.rect.height
        d = page.get_text("dict")
        want_slash = "/" if printed_guess % 2 == 1 else "\\"
        for block in d["blocks"]:
            if block.get("type") != 0:
                continue
            for ln in block["lines"]:
                s = "".join(sp["text"] for sp in ln["spans"]).strip()
                m = _PAGE_MARK.match(s)
                if not m or ln["bbox"][1] < height * _BOTTOM_FRAC:
                    continue
                if m.group(1) != want_slash or m.group(3) != want_slash:
                    errors.append(f"p.{printed_guess}: 마커 홀짝 형식 위반 {s!r} (기대 {want_slash!r})")
                    continue
                found = int(m.group(2))
                marker_count_by_page[printed_guess] = marker_count_by_page.get(printed_guess, 0) + 1
                o = (i + 1) - found
                offsets[o] = offsets.get(o, 0) + 1
    if list(offsets.keys()) != [off]:
        errors.append(f"쪽번호 오프셋 불균일: {offsets} (기대 단일값 {off})")
    bad_marks = {p: c for p in range(1, EXPECTED_BODY_END + 1)
                 if (c := marker_count_by_page.get(p, 0)) != 1}
    if bad_marks:
        errors.append(f"쪽당 마커 수 이상(기대 정확 1): {bad_marks}")

    if errors:
        print("[fail-closed BLOCK] 상수/목차/마커가 EXPECTED 스냅샷과 다릅니다 — JSON 미생성.", file=sys.stderr)
        print("새 판(개정판)이라면 docstring의 판 갱신 절차에 따라 EXPECTED_* 상수를 갱신 후 재실행하십시오.", file=sys.stderr)
        for e in errors:
            print(" - " + e, file=sys.stderr)
        return 2

    # 3) 본문 페이지 전처리 + ★쪽별 텍스트 sha 잠금(라이브러리 드리프트·추출 회귀 차단)
    audit = {"removed": 0, "removed_by_page": {}, "kept_outside_region": [], "doc_title_band": []}
    page_lines: dict[int, list[str]] = {}
    image_pages: set[int] = set()
    table_pages: set[int] = set()
    table_flag_error = None
    page_sha_errors: list[str] = []
    for printed in range(1, EXPECTED_BODY_END + 1):
        page = doc[printed + off - 1]
        lines = extract_page_lines(page, printed, audit)
        page_lines[printed] = lines
        joined = "\n".join(lines)
        got_sha = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        if got_sha != EXPECTED_PAGE_TEXT_SHA256[printed]:
            page_sha_errors.append(f"p.{printed}: 추출 텍스트 sha 불일치 ({got_sha[:16]}…)")
        if len(joined.strip()) < 100 and page.get_images():
            image_pages.add(printed)
        try:
            if page.find_tables().tables:
                table_pages.add(printed)
        except Exception as exc:  # 표 플래그는 advisory — 실패해도 파이프라인 중단 금지
            table_flag_error = f"{type(exc).__name__}: {exc}"
    if page_sha_errors:
        print("[fail-closed BLOCK] 쪽별 추출 텍스트가 승인 스냅샷과 다릅니다 — JSON 미생성.", file=sys.stderr)
        print("판 갱신 또는 PyMuPDF 버전 변경이라면 원문 대조 후 EXPECTED_PAGE_TEXT_SHA256를 재실측 갱신하십시오.", file=sys.stderr)
        for e in page_sha_errors:
            print(" - " + e, file=sys.stderr)
        return 2

    # 4) 유닛 목록 (장 표제 간지 없음 — 전 장에서 장 시작쪽 = 첫 절 시작쪽 실측)
    first_sec_of_chapter = {}
    for c, n, _t, p in EXPECTED_BODY_SECTIONS:
        first_sec_of_chapter.setdefault(c, p)
    for c, _t, cp in EXPECTED_CHAPTERS:
        if first_sec_of_chapter[c] != cp:
            print(f"[fail-closed BLOCK] 제{c}장 시작쪽 {cp} != 첫 절 시작쪽 {first_sec_of_chapter[c]} — 간지 없음 전제 위반", file=sys.stderr)
            return 2

    units = []
    for c, n, t, p in EXPECTED_BODY_SECTIONS:
        units.append({
            "id": f"b2-{c}-{n}", "chapter_no": c,
            "chapter_title": dict((x[0], x[1]) for x in EXPECTED_CHAPTERS)[c],
            "section_label": f"{n}.", "section_no": n, "section_title": t,
            "start": p, "is_ref": False,
            "first_of_chapter": (p == first_sec_of_chapter[c] and n == min(
                sn for cc, sn, _tt, _pp in EXPECTED_BODY_SECTIONS if cc == c
            )),
        })
    for n, t, p in EXPECTED_REFS:
        units.append({
            "id": f"b2-ref-{n}", "chapter_no": 0, "chapter_title": "[부록]",
            "section_label": "[부록]", "section_no": n, "section_title": t,
            "start": p, "is_ref": True, "first_of_chapter": True,
        })

    # 5) 절 단위 조립 — 같은 쪽 다중 절 분할 지원 (헤딩 미발견·순서 역전 = BLOCK)
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
        # 단 이 경우에도 헤딩/표제 실재는 검증한다.
        if pos == 0 and (u["is_ref"] or u["first_of_chapter"]):
            begin = 0
            if u["is_ref"]:
                # 별권 2 부록 표제는 3줄 꺾임: "[부록]" 줄 실재 + 정규화 제목 포함으로 검증
                has_label = any(ln.strip() == "[부록]" for ln in start_lines)
                page_norm = norm_title("".join(start_lines))
                if not has_label or norm_title(u["section_title"]) not in page_norm:
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
    lines_by_page: dict[int, int] = {}
    for a in assembled:
        for pg in a["pages"]:
            lines_by_page[pg["printed_page"]] = lines_by_page.get(pg["printed_page"], 0) + len(pg["lines"])
    for pp in range(1, EXPECTED_BODY_END + 1):
        if lines_by_page.get(pp, 0) != len(page_lines[pp]):
            print(f"[fail-closed BLOCK] p.{pp} 줄 계수 불일치: 원본 {len(page_lines[pp])} vs 귀속 합 {lines_by_page.get(pp, 0)}", file=sys.stderr)
            return 2
    # 쪽별 헤더+마커 정확 2줄 제거 강제 — 전 본문쪽에 헤더 1+마커 1 실측(12×2=24)
    bad_removed = {pp: audit["removed_by_page"].get(pp, 0) for pp in range(1, EXPECTED_BODY_END + 1) if audit["removed_by_page"].get(pp, 0) != 2}
    if bad_removed:
        print(f"[fail-closed BLOCK] 쪽별 헤더/마커 제거 수 이상(기대 쪽당 2): {bad_removed}", file=sys.stderr)
        return 2

    # 6.5) 부록 소제목 검증 (fail-closed — 동결 D2): 줄 단위 정확 일치·각 1회·문서 순서
    # (부분문자열 포함 검사는 소제목 축소·오타 변조를 통과시킴 — P1 적대검토 적발로 강화)
    ref_unit = next(a for a in assembled if a["unit"]["is_ref"])
    ref_lines_norm = [norm_title(ln) for pg in ref_unit["pages"] for ln in pg["lines"]]
    sub_problems: list[str] = []
    sub_positions: list[int] = []
    for t in EXPECTED_APPENDIX_SUBTITLES:
        tn = norm_title(t)
        occ = [i for i, ln in enumerate(ref_lines_norm) if ln == tn]
        if len(occ) != 1:
            sub_problems.append(f"{t!r}: 전체 줄 일치 {len(occ)}회(기대 정확 1회)")
        else:
            sub_positions.append(occ[0])
    if sub_problems:
        print(f"[fail-closed BLOCK] 부록 소제목 검증 실패: {sub_problems} — JSON 미생성", file=sys.stderr)
        return 2
    if sub_positions != sorted(sub_positions):
        print(f"[fail-closed BLOCK] 부록 소제목 문서 순서 불일치: {sub_positions}", file=sys.stderr)
        return 2
    all_ids = {a["unit"]["id"] for a in assembled}
    variants = known_toc_variants()
    bad_variant_keys = [k for k in variants if k not in all_ids]
    if bad_variant_keys:
        print(f"[fail-closed BLOCK] known-variant의 미존재 id: {bad_variant_keys}", file=sys.stderr)
        return 2
    bad_note_keys = [k for k in TABLE_STRUCTURE_NOTES if k not in all_ids]
    if bad_note_keys:
        print(f"[fail-closed BLOCK] TABLE_STRUCTURE_NOTES의 미존재 id: {bad_note_keys}", file=sys.stderr)
        return 2

    # 7) JSON 구성 (section_index는 파일 내 로컬 값 — 전역 index 저장 금지)
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
        subsection_titles: list[str] = []
        if u["is_ref"]:
            subsection_titles = list(EXPECTED_APPENDIX_SUBTITLES)
        subsection_titles += variants.get(u["id"], [])
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
            "subsection_titles": subsection_titles,
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
        "source_title": "국가연구개발사업 기술료 제도 매뉴얼",
        "series_title": "국가연구개발혁신법 매뉴얼",
        "series_part": "별권 2",
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
        "excluded_note": "표지·간지·목차·뒤표지 미수록 — 인쇄쪽 1~12 전체 수록(장 표제 간지 없음)",
        "pymupdf_version": fitz.__version__ if hasattr(fitz, "__version__") else fitz.VersionBind,
        "extractor": "scripts/extract_manual_b2.py",
        "source_url": args.source_url,
        "id_format": "^b2-(\\d+-\\d+|ref-\\d+)$",
        "section_count": len(sections_json),
        "chapters": [
            {"no": c, "title": t, "page_start": p} for c, t, p in EXPECTED_CHAPTERS
        ],
    }
    payload = {"meta": meta, "sections": sections_json}

    # 8) 자체 정합성 검증 (fail-closed — assert는 -O 실행에서 제거되므로 명시적 검사)
    expected_units = len(EXPECTED_BODY_SECTIONS) + len(EXPECTED_REFS)
    ids = [s["id"] for s in sections_json]
    if not (len(ids) == len(set(ids)) == expected_units):
        print(f"[fail-closed BLOCK] 절 id 수 이상: {len(ids)} (기대 {expected_units})", file=sys.stderr)
        return 2
    if [s["section_index"] for s in sections_json] != list(range(expected_units)):
        print("[fail-closed BLOCK] section_index 연속성 위반", file=sys.stderr)
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
    if total_chars != EXPECTED_TOTAL_CHARS:
        print(f"[fail-closed BLOCK] 총 자수 {total_chars:,} != 승인 스냅샷 {EXPECTED_TOTAL_CHARS:,} — JSON 미생성", file=sys.stderr)
        return 2
    # 배선 검증: 상수 TABLE_STRUCTURE_NOTES가 JSON에 그대로 실렸는지 (조립 회귀 차단)
    notes_in_json = {
        s["id"]: s["table_structure_notes"] for s in sections_json if "table_structure_notes" in s
    }
    if notes_in_json != TABLE_STRUCTURE_NOTES:
        print("[fail-closed BLOCK] table_structure_notes 배선 불일치(상수 vs JSON) — JSON 미생성", file=sys.stderr)
        return 2

    # 원자적 쓰기(산출물 세트 단위): JSON·리포트를 모두 임시 파일에 완성한 뒤 함께 교체 —
    # 리포트 생성 실패 시 새 JSON만 공개되는 반쪽 세트 차단(P1 적대검토 채택)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp_json = args.out_json.with_suffix(".json.tmp")
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    json_sha = sha256_of(tmp_json)

    # 9) 품질 리포트
    today = datetime.date.today().isoformat()
    special_chars = {}
    for ch in ("･", "ㆍ", "·", "｢", "｣", "￭", "•", "∙", "Ⅰ", "Ⅱ", "Ⅲ"):
        cnt = sum(("\n".join(p["text"] for p in s["pages"])).count(ch) for s in sections_json)
        if cnt:
            special_chars[ch] = cnt

    rep = []
    rep.append("# 매뉴얼 별권 2 「기술료 제도 매뉴얼」 추출 품질 리포트 (R3-P1)\n")
    rep.append(f"- 실행일: {today} · PyMuPDF {meta['pymupdf_version']}")
    rep.append(f"- PDF: `{args.pdf.name}` · {doc.page_count}쪽 · sha256 `{pdf_sha[:20]}…` (승인 스냅샷 일치)")
    try:
        json_path_disp = args.out_json.relative_to(REPO_ROOT)
    except ValueError:
        json_path_disp = args.out_json
    rep.append(f"- JSON: `{json_path_disp}` · sha256 `{json_sha[:20]}…`")
    rep.append(
        f"- 목차 검증: PASS (장 {len(EXPECTED_CHAPTERS)}·절 {len(EXPECTED_TOC_SECTIONS)}·부록 {len(EXPECTED_REFS)}"
        f"·승인 불일치 1건[운영체계/운영체제]) · 오프셋 +{off} 균일·마커 홀짝 {EXPECTED_BODY_END}쪽 전건"
    )
    rep.append(f"- 단위 {len(sections_json)}개 · 총 {total_chars:,}자 · 러닝헤더/마커 제거 {audit['removed']}줄")
    rep.append(f"- 부록 소제목 실재 검증: PASS ({len(EXPECTED_APPENDIX_SUBTITLES)}건)")
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

    rep.append("## 결속 객체 사실 기재 (동결 D8 — 렌더 대조 판정 (ii))\n")
    for sid, notes in TABLE_STRUCTURE_NOTES.items():
        for n in notes:
            rep.append(f"- `{sid}`: {n}")
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

    rep.append("## 러닝헤더/마커 제거 감사\n")
    anomalies = {p: c for p, c in audit["removed_by_page"].items() if c >= 4}
    rep.append(f"- 총 제거 {audit['removed']}줄(기대 {EXPECTED_BODY_END * 2}) · 쪽당 4줄 이상 이상치: {anomalies or '없음'}")
    if audit["kept_outside_region"]:
        rep.append("- 패턴 일치했으나 bbox 영역 밖이라 보존한 줄(과제거 방지 확인용 — 장 시작쪽 제목 밴드 기대):")
        for p, s, ypct in audit["kept_outside_region"]:
            rep.append(f"  - p.{p} (y {ypct}%): {s}")
    else:
        rep.append("- 패턴 일치·영역 밖 보존 줄: 없음")
    band = ", ".join(f"p.{p}(y {ypct}%)" for p, ypct in audit["doc_title_band"])
    rep.append(f"- 문서 제목 밴드 본문 보존 전건: {band or '없음'} (장 시작쪽 기대 — 인쇄 1·2·5)")
    rep.append("")

    rep.append("## 특수문자 인벤토리 (verbatim 보존 — 정규화하지 않음)\n")
    for ch, cnt in special_chars.items():
        rep.append(f"- U+{ord(ch):04X} {ch!r}: {cnt:,}회")
    rep.append("")

    tmp_rep = args.out_report.with_suffix(".md.tmp")
    with open(tmp_rep, "w", encoding="utf-8") as f:
        f.write("\n".join(rep))
    # 세트 교체: 두 임시 파일이 모두 완성된 뒤에만 공개
    os.replace(tmp_json, args.out_json)
    os.replace(tmp_rep, args.out_report)

    print(f"[OK] JSON {args.out_json} ({args.out_json.stat().st_size:,} bytes, 단위 {len(sections_json)}개, {total_chars:,}자)")
    print(f"[OK] 리포트 {args.out_report}")
    doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
