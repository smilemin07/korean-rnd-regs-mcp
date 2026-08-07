#!/usr/bin/env python3
"""「국가 R&D 연구비 부적정집행 사례집」(KAIA·25.5) 추출 파이프라인 (v0.43.0).

사용법:
    /Users/andykim/my_project/venv/bin/python scripts/extract_manual_case.py \
        --source-url "https://www.kaia.re.kr/portal/bbs/view/B0000061/12547.do?menuNo=200858"
    (옵션) --pdf <경로> --out-json <경로> --out-report <경로> --accept-sha256 <실측값>

의존성: PyMuPDF(fitz) — 오프라인 스크립트 전용·패키지 런타임 의존성 아님(기존 추출기 6종과 동일).

산출물:
    src/korean_rnd_regs_mcp/manual_case.json   (절 단위 구조화 데이터 — 패키지 데이터 동봉 대상)
    scripts/manual_case_extract_report.md      (품질 리포트 — 경계·장부 감사·검수용)

문서 특성 (2026-08-07 실측):
    - ★기존 추출기 6종과 달리 물리 1쪽 = 좌우 2인쇄쪽 스프레드(1191×842pt·물리 2~50).
      인쇄쪽 = 좌: 2×물리−4 · 우: 2×물리−3. 반쪽 clip으로 인쇄쪽 단위 추출
      (midline 교차 단어 0개 전 쪽 실측 — 반분할 무손실).
    - ★FAQ·일부 사례 쪽은 반쪽(=인쇄쪽) 내부가 2열 박스 배치이고 열 gutter 위치가 쪽마다
      다름(인쇄 86 ≈ x280 · 인쇄 89 ≈ x330). 단순 y정렬은 Q13/Q14처럼 좌·우 박스를 섞고,
      PDF 스트림 순서도 논리 순서가 아님(인쇄 86 실측 Q1→Q4→Q2→Q3). → 줄 내부 큰 x-간격
      분리 + 런(수직 박스 군집) 내부 최대 x-간격 동적 감지로 좌열 전체 → 우열 전체 정렬.
      정합성은 FAQ Q1~Q18 연속·비목별 사례 번호 1~N 연속의 전수 fail-closed로 잠근다
      (계획 /disc Codex 지적 반영 — 2026-08-07 전 쪽 통과 + 인쇄 89 렌더 시각 대조 일치).
    - 러닝 헤더 = 각 반쪽 상단 y≤80(문서 제목·장 배너·비목명). 인쇄쪽 번호 마커 = 하단
      y≥790 독립 숫자. 좌표 기반 제거 + 헤더 문면 허용 목록 대조 fail-closed(본문 오제거 방지).
    - 편제 = Ⅰ 들어가기전에(인쇄 6~9) · Ⅱ 부적정집행 사례 비목 10절(12~82) · Ⅲ 자주 묻는
      질문(86~90) · Ⅳ 상시·연차점검/정산 절차(94~95). 사례 번호는 비목별 리셋(총 105건).
    - 수록 제외 = 표지(물리 1)·속표지(인쇄 2)·인사말(인쇄 1)·목차(인쇄 3)·장 표지·간지
      (인쇄 4·5·10·11·84·85·92·93)·마커만 있는 빈 쪽(인쇄 83·91·96)·뒤표지(물리 50 우반).
      전체 장부(수록+제거+제외 = 원본 전체·비공백 문자 기준)를 fail-closed로 검증.
    - Ⅳ장(인쇄 94~95)은 절차 도식 텍스트라 상자·화살표 배치가 보존되지 않음 —
      table_structure_notes로 완성형 안내(structure_notice 경로·v0.34.0)를 공급.
    - 발간 주체 = 국토교통과학기술진흥원(KAIA)·표지 발행연월 2025.05. 판권지·공공누리
      표시 없음(전문 검색 0건 실측) — meta에 사실 기재.

결정론: 같은 PDF + 같은 --source-url + 같은 스크립트 + 같은 PyMuPDF 버전이면 JSON은
extracted_at(실행일)을 제외하고 byte-identical.

판 갱신 절차: 새 판 게시 시 EXPECTED_* 불일치로 fail-closed 중단되면 목차 대조표를 보고
상수 갱신·구판↔신판 id→제목 전수 대조로 재번호 판정. 산출 JSON은 서버 로더
(load_manual_case)의 강화 검증을 본 추출기가 자동 충족한다 — JSON 수동 편집 금지.
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
    "91-B - 국가 R&D 연구비 부적정집행 사례집(25.5).pdf"
)
DEFAULT_JSON = REPO_ROOT / "src" / "korean_rnd_regs_mcp" / "manual_case.json"
DEFAULT_REPORT = REPO_ROOT / "scripts" / "manual_case_extract_report.md"

# ── 승인 원본 고정 (fail-closed — 파일 교체 시 BLOCK) ────────────────────────
EXPECTED_PDF_SHA256 = "ee27fecd62fa6f7eefe93a5e2915debf2c0c07de18894edfd139c15bd0d2116a"  # 2026-08-07 실측
EXPECTED_PHYS_PAGES = 50
DOC_TITLE = "국가 R&D 연구비 부적정집행 사례집"

# 스프레드 매핑: 인쇄쪽 → (물리쪽, 반). 좌 = 짝수 인쇄쪽.
def printed_to_half(printed: int) -> tuple[int, str]:
    if printed % 2 == 0:
        return (printed + 4) // 2, "L"
    return (printed + 3) // 2, "R"

# 본문 인쇄쪽 범위(비연속 — 장 표지·간지 제외)
BODY_RANGES = [(6, 9), (12, 82), (86, 90), (94, 95)]
# 제외 인쇄쪽(텍스트 실재하나 본문 아님): 인사말 1·속표지 2·목차 3·장 표지/간지 4·5·10·11·
# 84·85·92·93·마커만 있는 빈 쪽 96. 인쇄 0(물리 2 좌반)·물리 1(표지)·물리 50 우반(뒤표지)은
# 인쇄쪽 밖 물리 영역으로 별도 계상.
EXCLUDED_PRINTED = (1, 2, 3, 4, 5, 10, 11, 83, 84, 85, 91, 92, 93, 96)

# ── 레이아웃 상수 (2026-08-07 실측) ─────────────────────────────────────────
HEADER_Y1_MAX = 80.0     # 이하 = 러닝 헤더·배너 (본문 최상단 실측 y≈105)
MARKER_Y0_MIN = 790.0    # 이상 = 인쇄쪽 번호 마커
LINE_SPLIT_GAP = 18.0    # 같은 y줄 내부 스팬 간격 초과 → 별도 조각(2열 병합 줄 분리)
                         # 전 문서 실측: 정상 줄 내 간격 ≤16.2pt·열 경계 병합 ≥20.2pt(인쇄 79)
RUN_SPLIT_GAP = 20.0     # 수직 간격 초과(겹침 없음) → 런 분리(박스 경계)
COL_MIN_GAP = 18.0       # 런 내부 좌/우 열 최소 간격(동적 gutter) — 인쇄 79 열 간격 20.2pt 포괄
LINE_OVERLAP = 0.5       # y-range 겹침 비율 → 같은 줄
SPAN_JOIN_GAP = 1.5      # 스팬 사이 이 간격 초과면 공백 삽입

# 러닝 헤더 허용 문면(부분 문자열·정규화 비교) — 이 목록 밖 텍스트가 헤더 영역에 있으면 BLOCK
# (본문 오제거 방지 fail-closed). 장 배너는 장제목·비목명·문서제목·부제의 조합으로 나타난다.
HEADER_ALLOWED_SUBSTRINGS = (
    "국가R&D연구비부적정집행사례집",
    "국토교통R&D올바른연구비사용을위한길잡이",
    "들어가기전에",
    "부적정집행사례",
    "자주묻는질문",
    "상시·연차점검/정산절차",
    "연구비사용전꼭!기억해야하는사항",
    "인건비",          # 비목명(학생인건비·연구시설·장비비 등은 아래 항목이 포괄)
    "학생인건비",
    "연구시설·장비비",
    "연구재료비",
    "연구활동비",
    "연구수당",
    "위탁연구개발비",
    "국제공동연구개발비",
    "간접비",
    "기타",
    "Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "/",
)

# ── 편제 동결 (fail-closed) — (id, chapter_title, section_label, section_title, start, end)
EXPECTED_UNITS = [
    ("case-1-1", "들어가기전에", "Ⅰ.", "연구비 사용전 꼭! 기억해야하는 사항", 6, 9),
    ("case-2-1", "부적정집행 사례", "Ⅱ. 부적정집행 사례 01", "인건비", 12, 23),
    ("case-2-2", "부적정집행 사례", "Ⅱ. 부적정집행 사례 02", "학생인건비", 24, 28),
    ("case-2-3", "부적정집행 사례", "Ⅱ. 부적정집행 사례 03", "연구시설·장비비", 29, 37),
    ("case-2-4", "부적정집행 사례", "Ⅱ. 부적정집행 사례 04", "연구재료비", 38, 41),
    ("case-2-5", "부적정집행 사례", "Ⅱ. 부적정집행 사례 05", "연구활동비", 42, 57),
    ("case-2-6", "부적정집행 사례", "Ⅱ. 부적정집행 사례 06", "연구수당", 58, 63),
    ("case-2-7", "부적정집행 사례", "Ⅱ. 부적정집행 사례 07", "위탁연구개발비", 64, 67),
    ("case-2-8", "부적정집행 사례", "Ⅱ. 부적정집행 사례 08", "국제공동연구개발비", 68, 70),
    ("case-2-9", "부적정집행 사례", "Ⅱ. 부적정집행 사례 09", "간접비", 71, 78),
    ("case-2-10", "부적정집행 사례", "Ⅱ. 부적정집행 사례 10", "기타 사례", 79, 82),
    ("case-3-1", "자주 묻는 질문", "Ⅲ.", "자주 묻는 질문", 86, 90),
    ("case-4-1", "상시·연차점검 / 정산 절차", "Ⅳ.", "상시·연차점검 / 정산 절차", 94, 95),
]
# 비목별 사례 수 동결 (독립 표제 "사례 N." 기준·2026-08-07 전수 실측 — 합계 105)
EXPECTED_CASE_COUNTS = {
    "case-2-1": 19, "case-2-2": 6, "case-2-3": 11, "case-2-4": 5, "case-2-5": 28,
    "case-2-6": 8, "case-2-7": 5, "case-2-8": 4, "case-2-9": 13, "case-2-10": 6,
}
EXPECTED_FAQ_MAX = 18   # FAQ Q1~Q18 연속(2026-08-07 실측)

# 절 제목이 러닝 헤더(제거 대상)에만 있는 단위의 시작 실재 검증용 본문 첫 문구(실측)
START_HINT_OVERRIDES = {
    "case-4-1": "연구비 점검은 이렇게 진행됩니다.",
}

STRUCTURE_NOTES_BY_UNIT = {
    "case-1-1": [
        "인쇄 8쪽 11번 항목의 불인정 기준표(연구수당 불인정·간접비 불인정 라벨과 각 기준)는 "
        "좌우 배치가 텍스트 추출에서 라벨 2줄 → 기준 2줄 순서로 평탄화되어 행 대응이 인접하지 "
        "않습니다 — 각 기준의 괄호 근거 조문(연구수당=연구개발비 사용 기준 제26조제7항·간접비="
        "혁신법 시행령 제26조제5항제3호)으로 대응을 확인하거나 원문 PDF를 대조하십시오.",
    ],
    "case-4-1": [
        "인쇄 94~95쪽의 <국토교통R&D 연구비 관리 주요 프로세스>·<연차점검 절차 및 일정>·"
        "<정산 진행 일정> 도식은 상자·화살표 배치가 텍스트 추출에 보존되지 않아 단계 사이 "
        "연결·순서가 원문과 다르게 읽힐 수 있습니다 — 절차 흐름은 원문 PDF 도식으로 확인하십시오.",
    ],
}

# ── 메타 문면 ────────────────────────────────────────────────────────────────
EDITION = "25.5"
EDITION_NOTE = (
    "판번은 표지의 발행 연월 표기(2025. 05) 기준입니다. 이 사례집에는 판권지·발간등록번호가 "
    "없어 표지 표기 외의 판 식별 정보는 확인 불가입니다."
)
PUBLISHER = "국토교통과학기술진흥원(KAIA)"
PUBLISHER_NOTE = (
    "발간 주체는 표지(www.kaia.re.kr)·인사말의 국토교통과학기술진흥원(KAIA) 표기 기준입니다. "
    "국토교통 연구개발사업 관점의 안내('국토교통R&D 올바른 연구비 사용을 위한 길잡이')를 "
    "포함하며, 인사말 기준으로 사례는 국가 R&D 전반에서 수집되었습니다."
)
BASIS_NOTE = (
    "이 사례집 원문에는 법령 기준일이 명시되어 있지 않습니다(발간 2025.05 표지 기준·확인 불가). "
    "사례·FAQ가 인용하는 「국가연구개발사업 연구개발비 사용 기준」 등의 조문 번호·수치·한도는 "
    "발간 시점 스냅샷이므로, 구체값은 규정 트랙(rnd_funding_standard 등) 현행 원문으로 "
    "확인하십시오."
)
BASIS_LAWS = [
    "국가연구개발사업 연구개발비 사용 기준(과학기술정보통신부고시)",
    "국가연구개발혁신법 제32조·같은 법 시행령 제59조(제재처분 관련 인용)",
]
LAW_PRIORITY_EXTRA = [
    "이 자료는 KAIA(국토교통과학기술진흥원)가 발간한 교육·참고용 사례집이며, 법령·행정규칙이 "
    "아니고 개별 사안에 대한 정산 판정·제재처분 결정도 아닙니다. 사례의 결론은 기관 유형"
    "(영리/비영리·대학·출연연), 협약 내용, 증빙, 소관 전문기관 기준에 따라 달라질 수 있으므로 "
    "개별 사안은 소관 전문기관에 확인하십시오.",
    "사례집의 '부적정집행'·'불인정'·'회수'는 곧바로 연구부정행위나 제재처분을 뜻하지 않습니다 — "
    "제재처분 사유·절차는 국가연구개발혁신법 제32조·같은 법 시행령 원문과 제재처분 가이드라인"
    "(별권 3)으로 별도 확인하십시오.",
    "조문 번호·금액·비율·한도 등 구체값을 인용할 때는 get_provision_detail로 "
    "「국가연구개발사업 연구개발비 사용 기준」(rnd_funding_standard) 등 현행 원문을 교차 "
    "확인하십시오(사례집은 발간 시점 스냅샷).",
    "Ⅳ장(상시·연차점검/정산 절차)의 연구비통합관리시스템(Ez-baro)·위탁정산기관·점검 일정은 "
    "KAIA 국토교통R&D 프로세스 기준입니다 — 타 부처·타 전문기관 과제는 해당 기관의 절차를 "
    "확인하십시오.",
    "사례집이 인용하는 고용보험법 등 이 서버가 수록하지 않은 법령의 내용은 이 서버로 확인된 "
    "것이 아니므로, 국가법령정보센터(law.go.kr) 등 1차 출처에서 확인하십시오.",
]
FOOTER_MANUAL_LINE = (
    "※ 사례·해설 부분은 「국가 R&D 연구비 부적정집행 사례집」(국토교통과학기술진흥원 발간)을 "
    "참고한 설명입니다. 이 사례집은 법령·행정규칙이나 개별 사안에 대한 처분·정산 판정이 아니며, "
    "내용이 다를 때는 법령·행정규칙 원문이 우선합니다."
)
# footer 2번째 줄(원문 확인처) — 기본 문면은 KISTEP 홈페이지라 KAIA 발간물에 오귀속됨
# (diff 적대검토 Codex MAJOR 채택 — 단독 응답에서 교체·혼합 응답에서 병기)
FOOTER_SOURCE_LINE = (
    "※ 「국가 R&D 연구비 부적정집행 사례집」 원문은 "
    "KAIA 홈페이지(www.kaia.re.kr)에서 확인하시기 바랍니다."
)


def norm(s: str) -> str:
    return re.sub(r"[\s･·ㆍ]+", "", s or "")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def nonws_len(s: str) -> int:
    """비공백 문자 수 — 줄 조립의 공백 정규화와 무관한 장부 불변량."""
    return len("".join(s.split()))


def clean_invisibles(t: str) -> str:
    """비가시 아티팩트 제거 — BEL(U+0007·불릿 뒤 제어문자)·ZWNJ(U+200C).

    91-B 텍스트 레이어 고유 아티팩트(기존 6소스 데이터 전례 0)로, 렌더링·복사·토큰 검색에
    불가시 잡음만 남긴다(diff 적대검토 Codex MINOR 채택). 가시 문장부호(·‘’“”•※–)는 유지.
    수록·헤더·마커·제외 전 구간에 균일 적용해 장부 정합을 보존한다."""
    return t.replace("\x07", "").replace("\u200c", "")


# ── 반쪽 스팬 수집·컬럼 인지 정렬 (레이아웃 실측 §문서 특성 참조) ────────────
def half_rect(page, half: str) -> fitz.Rect:
    mid = page.rect.width / 2
    if half == "L":
        return fitz.Rect(0, 0, mid, page.rect.height)
    return fitz.Rect(mid, 0, page.rect.width, page.rect.height)


def collect_spans(page, half: str):
    clip = half_rect(page, half)
    d = page.get_text("dict", clip=clip, sort=False)
    body, header, marker = [], [], []
    for b in d["blocks"]:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                t = clean_invisibles(s["text"])
                if not t.strip():
                    continue
                x0, y0, x1, y1 = s["bbox"]
                rec = {"x0": x0 - clip.x0, "x1": x1 - clip.x0, "y0": y0, "y1": y1, "text": t}
                if y1 <= HEADER_Y1_MAX:
                    header.append(rec)
                elif y0 >= MARKER_Y0_MIN:
                    marker.append(rec)
                else:
                    body.append(rec)
    return body, header, marker


def group_lines(spans):
    """y-range 겹침 기반 줄 묶기 → 큰 x-간격으로 줄 내부 분리 → 조각(part) 목록."""
    spans = sorted(spans, key=lambda s: (s["y0"], s["x0"]))
    lines: list[list[dict]] = []
    for s in spans:
        placed = False
        for ln in reversed(lines[-8:]):
            ly0 = min(t["y0"] for t in ln)
            ly1 = max(t["y1"] for t in ln)
            ov = min(ly1, s["y1"]) - max(ly0, s["y0"])
            if ov > LINE_OVERLAP * min(ly1 - ly0, s["y1"] - s["y0"]):
                ln.append(s)
                placed = True
                break
        if not placed:
            lines.append([s])
    parts = []
    for ln in lines:
        ln.sort(key=lambda s: s["x0"])
        cur = [ln[0]]
        for s in ln[1:]:
            if s["x0"] - cur[-1]["x1"] > LINE_SPLIT_GAP:
                parts.append(cur)
                cur = [s]
            else:
                cur.append(s)
        parts.append(cur)
    out = []
    for p in parts:
        text = p[0]["text"]
        for prev, s in zip(p, p[1:]):
            text += (" " if s["x0"] - prev["x1"] > SPAN_JOIN_GAP else "") + s["text"]
        out.append({
            "x0": min(s["x0"] for s in p),
            "x1": max(s["x1"] for s in p),
            "y0": min(s["y0"] for s in p),
            "y1": max(s["y1"] for s in p),
            "text": " ".join(text.split()),
        })
    return out


def _split_runs(parts):
    parts = sorted(parts, key=lambda p: (p["y0"], p["x0"]))
    runs, run, run_y0, run_y1 = [], [], None, None
    for p in parts:
        if run and p["y0"] - run_y1 > RUN_SPLIT_GAP and not (p["y0"] < run_y1 and p["y1"] > run_y0):
            runs.append(run)
            run, run_y0, run_y1 = [], None, None
        run.append(p)
        run_y0 = p["y0"] if run_y0 is None else min(run_y0, p["y0"])
        run_y1 = p["y1"] if run_y1 is None else max(run_y1, p["y1"])
    if run:
        runs.append(run)
    return runs


def _order_run(run):
    """런 내부: 최대 x-간격으로 2열 감지 — 좌열 전체 → 우열 전체. 아니면 y 순."""
    if len(run) < 2:
        return run
    by_x = sorted(run, key=lambda p: p["x0"])
    left_max = by_x[0]["x1"]
    best_gap, best_t = 0.0, None
    for p in by_x[1:]:
        gap = p["x0"] - left_max
        if gap > best_gap:
            best_gap, best_t = gap, (left_max + p["x0"]) / 2
        left_max = max(left_max, p["x1"])
    if best_gap < COL_MIN_GAP or best_t is None:
        return sorted(run, key=lambda p: (p["y0"], p["x0"]))
    left = [p for p in run if p["x1"] <= best_t]
    right = [p for p in run if p["x0"] >= best_t]
    if not left or not right:
        return sorted(run, key=lambda p: (p["y0"], p["x0"]))
    ly0, ly1 = min(p["y0"] for p in left), max(p["y1"] for p in left)
    ry0, ry1 = min(p["y0"] for p in right), max(p["y1"] for p in right)
    if min(ly1, ry1) - max(ly0, ry0) <= 0:
        return sorted(run, key=lambda p: (p["y0"], p["x0"]))
    return sorted(left, key=lambda p: p["y0"]) + sorted(right, key=lambda p: p["y0"])


def order_half(page, half: str):
    """반쪽 본문을 읽기 순서 줄 목록으로. 반환: (줄 목록, 헤더 스팬, 마커 스팬, 2열 감지 여부)"""
    body, header, marker = collect_spans(page, half)
    if not body:
        return [], header, marker, False
    parts = group_lines(body)
    out, two_col = [], False
    for run in _split_runs(parts):
        ordered = _order_run(run)
        if len(ordered) >= 2 and ordered != sorted(run, key=lambda p: (p["y0"], p["x0"])):
            two_col = True
        out.extend(p["text"] for p in ordered)
    return out, header, marker, two_col


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--source-url", required=True,
                    help="공식 게시물 URL(https·kaia.re.kr)")
    ap.add_argument("--accept-sha256", default=None,
                    help="최초 실행/판 교체 시 실측 sha256 승인값(EXPECTED_PDF_SHA256 갱신 전 임시 통과)")
    args = ap.parse_args()

    u = urllib.parse.urlparse(args.source_url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not (host == "kaia.re.kr" or host.endswith(".kaia.re.kr")):
        print("[fail-closed BLOCK] --source-url은 https + kaia.re.kr 게시물이어야 합니다", file=sys.stderr)
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

    body_pages = [p for s, e in BODY_RANGES for p in range(s, e + 1)]

    # 0) 전수 반쪽 스캔 — 장부 원천 + 마커·헤더 fail-closed
    ledger = {"included": 0, "header": 0, "marker": 0, "excluded": 0}
    page_lines: dict[int, list[str]] = {}
    two_col_pages: list[int] = []
    all_printed = list(range(0, 98))  # 인쇄 0(물리 2 좌반·빈)~96 + 97(물리 50 우반=뒤표지)
    for printed in all_printed:
        phys, half = printed_to_half(printed)
        if not (1 <= phys <= EXPECTED_PHYS_PAGES):
            continue
        page = doc[phys - 1]
        lines, header, marker, two_col = order_half(page, half)
        body_chars = sum(nonws_len(l) for l in lines)
        header_chars = sum(nonws_len(s["text"]) for s in header)
        marker_chars = sum(nonws_len(s["text"]) for s in marker)
        # 마커 검증: 실재하면 값이 인쇄쪽 번호와 정확 일치해야 함(한 자리 쪽은 '06' zero-pad 표기)
        for s in marker:
            mv = s["text"].strip()
            if not re.fullmatch(r"\d{1,3}", mv) or int(mv) != printed:
                print(f"[fail-closed BLOCK] 인쇄 {printed} 마커 값 불일치: {s['text']!r}", file=sys.stderr)
                return 2
        if printed in body_pages:
            if not marker:
                print(f"[fail-closed BLOCK] 본문 인쇄 {printed} 마커 부재", file=sys.stderr)
                return 2
            if not lines:
                print(f"[fail-closed BLOCK] 본문 인쇄 {printed} 본문 0줄", file=sys.stderr)
                return 2
            # 헤더 문면 허용 목록 fail-closed(본문 오제거 방지) — 단방향 포함만(a in hn):
            # 역방향(hn in a)을 허용하면 헤더 영역에 우연히 걸린 본문 파편(허용 문면의
            # 부분 문자열)이 검증을 통과해 침묵 삭제될 수 있다(diff 적대검토 Gemini MINOR).
            for s in header:
                hn = norm(s["text"])
                if hn and not any(a in hn for a in map(norm, HEADER_ALLOWED_SUBSTRINGS)):
                    print(f"[fail-closed BLOCK] 인쇄 {printed} 헤더 영역에 미허용 텍스트: {s['text']!r}", file=sys.stderr)
                    return 2
            page_lines[printed] = lines
            ledger["included"] += body_chars
            ledger["header"] += header_chars
            ledger["marker"] += marker_chars
            if two_col:
                two_col_pages.append(printed)
        else:
            # 미분류 쪽 fail-closed: 본문도 승인 제외 목록도 아닌 인쇄쪽에 텍스트가 실재하면
            # BLOCK — 신판이 간지 등에 새 실질 내용을 넣어도 침묵 제외되지 않게 한다
            # (diff 적대검토 Codex 채택 — EXCLUDED_PRINTED를 선언에서 검증 상수로 승격).
            if printed not in EXCLUDED_PRINTED and printed not in (0, 97) and (lines or header or marker):
                print(f"[fail-closed BLOCK] 미분류 인쇄쪽 {printed}에 텍스트 실재 — 편제/제외 목록 재검토", file=sys.stderr)
                return 2
            # 제외 쪽: 인쇄 83·91·96(마커만·본문 0)만 마커 허용, 그 외 마커 실재 시 분류 재검토
            if marker and printed not in (83, 91, 96):
                print(f"[fail-closed BLOCK] 제외 인쇄 {printed}에 마커 실재 — 분류 재검토", file=sys.stderr)
                return 2
            if printed in (83, 91, 96) and lines:
                print(f"[fail-closed BLOCK] 인쇄 {printed}은 빈 쪽이어야 함(본문 {len(lines)}줄)", file=sys.stderr)
                return 2
            ledger["excluded"] += body_chars + header_chars + marker_chars

    # 물리 1(표지)·물리 50 우반(뒤표지)은 위 인쇄 0~96 루프의 매핑에 포함되지 않는 영역이
    # 없도록 설계됨: 물리 1은 인쇄 매핑 밖 — 별도 계상.
    cover_chars = sum(nonws_len(l) for l in clean_invisibles(doc[0].get_text()).split("\n"))
    ledger["excluded"] += cover_chars

    # 전체 장부: 수록 + 헤더 + 마커 + 제외 = 문서 전체(비공백 문자)
    total_raw = 0
    for i in range(EXPECTED_PHYS_PAGES):
        total_raw += nonws_len(clean_invisibles(doc[i].get_text()))
    lhs = ledger["included"] + ledger["header"] + ledger["marker"] + ledger["excluded"]
    if lhs != total_raw:
        print(f"[fail-closed BLOCK] 전체 장부 불일치: 수록 {ledger['included']} + 헤더 {ledger['header']} "
              f"+ 마커 {ledger['marker']} + 제외 {ledger['excluded']} = {lhs} != 원본 {total_raw}", file=sys.stderr)
        return 2

    # 1) 편제 경계 무결성(동결 상수 자체) — 본문 범위 정확 커버
    covered = [p for _u in EXPECTED_UNITS for p in range(_u[4], _u[5] + 1)]
    if sorted(covered) != sorted(body_pages) or len(covered) != len(set(covered)):
        print("[fail-closed BLOCK] 동결 편제가 본문 쪽을 정확히 커버하지 않음", file=sys.stderr)
        return 2

    # 2) 절 시작 헤딩 실재 검증 — 배너 제목이 2줄 분할('국제공동연구'+'개발비')·축약('기타')될 수
    #    있어 첫 6줄 결합 정규화 문자열 포함으로 판정(순서 정합의 실질 가드는 3의 번호 연속성).
    for uid, _ch, _label, title, start, _end in EXPECTED_UNITS:
        lines = page_lines[start]
        head = norm("".join(lines[:6]))
        if uid.startswith("case-2-"):
            no = uid.split("-")[-1].zfill(2)
            if not any(l.strip() == no for l in lines[:6]) or norm(title) not in head:
                print(f"[fail-closed BLOCK] {uid}: p.{start} 비목 배너('{no}'·'{title}') 미확정", file=sys.stderr)
                return 2
        else:
            want = START_HINT_OVERRIDES.get(uid, title)
            if norm(want) not in head:
                print(f"[fail-closed BLOCK] {uid}: p.{start} 표제 '{want}' 미확정", file=sys.stderr)
                return 2

    # 3) 순서 정합 fail-closed — 비목별 사례 번호 연속·FAQ Q 연속(컬럼 정렬 정합의 전수 증명)
    case_re = re.compile(r"^사례 (\d+)\.\s*$")
    for uid, cnt in EXPECTED_CASE_COUNTS.items():
        _u = next(u for u in EXPECTED_UNITS if u[0] == uid)
        seq = []
        for pp in range(_u[4], _u[5] + 1):
            seq += [int(m.group(1)) for l in page_lines[pp] if (m := case_re.match(l.strip()))]
        if seq != list(range(1, cnt + 1)):
            print(f"[fail-closed BLOCK] {uid} 사례 번호 이상: {seq} (기대 1~{cnt})", file=sys.stderr)
            return 2
    faq = next(u for u in EXPECTED_UNITS if u[0] == "case-3-1")
    q_re = re.compile(r"^Q(\d+)$")
    qseq = []
    for pp in range(faq[4], faq[5] + 1):
        qseq += [int(m.group(1)) for l in page_lines[pp] if (m := q_re.match(l.strip()))]
    if qseq != list(range(1, EXPECTED_FAQ_MAX + 1)):
        print(f"[fail-closed BLOCK] FAQ Q 번호 이상: {qseq} (기대 1~{EXPECTED_FAQ_MAX})", file=sys.stderr)
        return 2

    # 4) 표 실재 쪽 자동 산출(find_tables·행≥2 AND 열≥2 — 기존 추출기 동형·반쪽 clip)
    table_pages_all: set[int] = set()
    for printed in body_pages:
        phys, half = printed_to_half(printed)
        page = doc[phys - 1]
        try:
            for tb in page.find_tables(clip=half_rect(page, half)).tables:
                ext = tb.extract()
                if len(ext) >= 2 and max((len(r) for r in ext), default=0) >= 2:
                    table_pages_all.add(printed)
                    break
        except Exception:
            table_pages_all.add(printed)  # 실패는 보수적으로 표 있음 처리(경고 과소 방지)

    # 5) JSON 조립
    sections = []
    for idx, (uid, chapter_title, label, title, start, end) in enumerate(EXPECTED_UNITS):
        pages_out = [{
            "printed_page": pp,
            "partial": False,
            "text": "\n".join(page_lines[pp]),
        } for pp in range(start, end + 1)]
        full = "\n".join(p["text"] for p in pages_out)
        sec = {
            "id": uid,
            "section_index": idx,
            "chapter_no": 0,   # 원문이 로마숫자 장(Ⅰ.~Ⅳ.)이라 '제N장' 발명 대신 citation 장 생략
            "chapter_title": chapter_title,
            "section_label": label,
            "section_title": title,
            "page_start": start,
            "page_end": end,
            "pdf_page_start": printed_to_half(start)[0],
            "pdf_page_end": printed_to_half(end)[0],
            "char_count": len(full),
            "subsection_titles": [],  # 사례 105건 표제는 본문 검색으로 도달(응답 팽창 방지 — 계획 /disc)
            "image_only_pages": [],   # 전 본문 쪽 텍스트 실재(0줄 fail-closed 통과)
            "table_pages": sorted(p for p in range(start, end + 1) if p in table_pages_all),
            "warnings": [],
            "pages": pages_out,
        }
        if uid in STRUCTURE_NOTES_BY_UNIT:
            sec["table_structure_notes"] = STRUCTURE_NOTES_BY_UNIT[uid]
        sections.append(sec)

    meta = {
        "schema_version": "1.0",
        "source_title": DOC_TITLE,
        "edition": EDITION,
        "edition_provenance": "판번은 표지의 발행 연월(2025. 05) 표기 기준",
        "edition_note": EDITION_NOTE,
        "manual_basis_date": None,
        "basis_note": BASIS_NOTE,
        "basis_laws": BASIS_LAWS,
        "law_priority_extra": LAW_PRIORITY_EXTRA,
        "footer_manual_line": FOOTER_MANUAL_LINE,
        "footer_source_line": FOOTER_SOURCE_LINE,
        "source_type": "agency_case_reference",
        "legal_effect": "not_binding",
        "publisher": PUBLISHER,
        "publisher_note": PUBLISHER_NOTE,
        "pdf_sha256": digest,
        "source_url": args.source_url,
        "extracted_at": datetime.date.today().isoformat(),
        "physical_pages": EXPECTED_PHYS_PAGES,
        "spread_mapping": "물리 2~50쪽 = 좌우 2인쇄쪽 스프레드 — 인쇄쪽 좌 = 2×물리−4, 우 = 2×물리−3",
        "id_format": "^case-\\d+-\\d+$",
        "section_count": len(sections),
        "excluded_note": (
            "표지(물리 p1)·속표지(인쇄 2)·인사말(인쇄 1)·목차(인쇄 3)·장 표지·간지(인쇄 4·5·10·11·"
            "84·85·92·93)·빈 쪽(인쇄 83·91·96·마커만 실재)·뒤표지 미수록 — 본문 인쇄 6~9·12~82·86~90·"
            "94~95쪽 전체 수록"
        ),
    }
    payload = {"meta": meta, "sections": sections}
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    total_chars = sum(s["char_count"] for s in sections)
    report = ["# manual_case.json 추출 리포트", "",
              f"- 생성일: {meta['extracted_at']} · PDF sha256: {digest}",
              f"- 단위 {len(sections)}개 · 본문 인쇄 {body_pages[0]}~{body_pages[-1]}쪽(비연속 4구간) · 총 {total_chars:,}자",
              f"- 전체 장부(비공백 문자): 원본 {total_raw:,} = 수록 {ledger['included']:,} + 헤더 "
              f"{ledger['header']:,} + 마커 {ledger['marker']:,} + 제외 {ledger['excluded']:,} (일치 검증 통과)",
              f"- 순서 정합: 비목별 사례 번호 1~N 연속 전건(합계 "
              f"{sum(EXPECTED_CASE_COUNTS.values())}건) + FAQ Q1~Q{EXPECTED_FAQ_MAX} 연속 (fail-closed 통과)",
              f"- 반쪽 내 2열 감지 쪽: {two_col_pages}",
              f"- 표 실재 쪽(find_tables): {sorted(table_pages_all)}",
              "", "## 단위별", ""]
    for s in sections:
        report.append(f"- {s['id']}: {s['section_label']} {s['section_title']} — "
                      f"인쇄 {s['page_start']}~{s['page_end']} · {s['char_count']:,}자")
    args.out_report.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"OK: {len(sections)}단위 · {total_chars:,}자 → {args.out_json}")
    print(f"리포트: {args.out_report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
