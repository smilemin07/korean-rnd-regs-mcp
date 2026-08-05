#!/usr/bin/env python3
"""국가연구개발혁신법 매뉴얼 별권 1 「학생인건비통합관리 제도 매뉴얼」 추출 파이프라인 (R4-P1).

사용법:
    /Users/andykim/my_project/venv/bin/python scripts/extract_manual_b1.py \
        --source-url "https://www.kistep.re.kr/board.es?...&list_no=<게시물번호>"
    (옵션) --pdf <경로> --out-json <경로> --out-report <경로>

의존성: PyMuPDF(fitz) — 오프라인 스크립트 전용·패키지 런타임 의존성 아님(본권·별권 2·3 추출기와 동일).

산출물:
    src/korean_rnd_regs_mcp/manual_b1.json     (절 단위 구조화 데이터 — 패키지 데이터 동봉 대상)
    scripts/manual_b1_extract_report.md        (품질 리포트 — 경계 감사·검수용)

별권 2·3 스크립트와의 구조 차이 (R4-P0 설계 동결 D1~D14 근거 — 기존 추출기 3종은 무변 유지):
    - ★장 표제 간지 실재(별권 최초·본권과 동형): 간지 인쇄쪽 {1,9,19,39,47}(표제 verbatim 동결)와
      빈 쪽 {2,8,10,20,38,40,48}(0자 강제)은 미수록. 본문(마커 보유) 79쪽만 절에 귀속하며,
      "96물리쪽 = 선행 4쪽 ∪ 인쇄 1~91 ∪ 뒤표지"·"인쇄 1~91 = 절 귀속 ∪ 간지 ∪ blank"의
      완전 분할(교집합 0·합집합 전체)을 fail-closed 검증(D2·D3). 본권의 "헤딩 미발견 시 쪽 전체
      귀속 warning" fallback은 복제하지 않음(D8 — fail-closed 위반).
    - ★유닛 kind 3종(D1·D8): 일반 절 22(exact-match 헤딩) / 제5장 FAQ 단일 유닛 b1-5-1
      (절 없는 장 — "FAQ" 표제·Q1~Q9 각 정확 1회·문서 순서 검증·Q줄은 subsection_titles로 등재) /
      참고 3건 b1-ref-1~3("참고N" 줄 실재 + 본문 제목 검증. 참고1은 목차 표기와 본문 표기가 달라
      목차 표기를 known-variant로 subsection_titles에 추가 — 검색 제목 tier 도달 보장).
    - 인쇄쪽 마커 "/ N /"(홀)·"\\ N \\"(짝) 교호·러닝헤더 홀수쪽 장형("제N장 …￭￭￭"/"제5장 FAQ ￭￭￭"/
      참고 구간 "참고 ￭￭￭")·짝수쪽 문서 제목 — 별권 2 동형이나 참고 구간 헤더가 장형이 아님(실측).
      장 시작 본문쪽(3·11·21·41·49)의 문서 제목 밴드(y0 9.5~11.4%)는 본문 보존 + 정확 5건 검증.
    - 고시 표기 장부(D7): 본문 내 "제YYYY-N호" 표기의 쪽별 건수를 동결 — 제2026-5호 24건·
      ★제2025-9호 1건(인쇄 22·원문 내부 불일치의 사실 고정 — 변조 아님·후속 판에서 값이 바뀌면
      판 교체 신호)·공고 제2026-0165호 1건(인쇄 51·고시 아님). 제75조 구판 구조 인용(인쇄 32)은
      쪽별 sha 동결에 포함되어 자동 고정(문면이 바뀌면 KISTEP 현행화 → LAW_PRIORITY_EXTRA의
      이자 처리 안내 문장을 제거할 것 — 수명은 수록 판 연동).
    - image_only_pages는 추출 텍스트 0자 쪽만 등재(D4 — 저텍스트·다이미지 쪽을 넣으면
      "텍스트 미추출" 거짓 경고. 별권 1 본문 79쪽은 전건 텍스트 실재라 항상 빈 배열).
    - 승인 PDF sha256·물리 쪽수(96)·쪽별 추출 텍스트 sha 79건·유닛별 자수 26건을 상수 동결.

결정론: 같은 PDF + 같은 --source-url + 같은 스크립트 + 같은 PyMuPDF 버전이면 JSON은 byte-identical.

판 갱신 절차: 본권 extract_manual.py docstring과 동일 — 새 판 게시 시 EXPECTED_* 불일치로
fail-closed 중단되면 목차 대조표를 보고 상수 갱신·구판↔신판 id→제목 전수 대조로 재번호 판정.
산출 JSON은 서버 로더(load_manual_b1)의 강화 검증을 본 추출기가 자동 충족한다 — JSON 수동 편집
금지(위반 시 로드 격리).
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
    "/Users/andykim/mhk/31 - 규정/91-1-1 - 국가연구개발혁신법 매뉴얼(26.7) - 별권 1 - 학생인건비통합관리 제도 매뉴얼.pdf"
)
DEFAULT_JSON = REPO_ROOT / "src" / "korean_rnd_regs_mcp" / "manual_b1.json"
DEFAULT_REPORT = REPO_ROOT / "scripts" / "manual_b1_extract_report.md"

# ── 판(edition) 메타 — 판 갱신 대상 (동결 D6) ────────────────────────────────
EDITION = "26.7"
EDITION_NOTE = (
    "판번은 KISTEP 게시 세트·파일명 기준입니다(별권 PDF 본문·표지에 판번 텍스트 표기 없음). "
    "본권 26.7판과 같은 KISTEP 게시물로 배포되었습니다."
)
BASIS_NOTE = (
    "별권 1 원문에는 본권과 달리 법령 기준일이 명시되어 있지 않습니다. 원문 머리말은 본문 내 "
    "'고시'가 「국가연구개발사업 연구개발비 사용 기준」(과학기술정보통신부고시 제2026-5호)을 "
    "의미한다고 밝히고 있으며, 이 고시 번호는 원문 표기의 사실 기재입니다(발간 후 개정으로 현행 "
    "번호와 다를 수 있음 — 현행 조문은 규정 트랙 rnd_funding_standard로 확인). "
    "본권의 기준일(2026-06)을 별권에 준용하지 않았습니다."
)
# 규범성 확장 문장 (R4-P0 D5 동결 문면 — law_priority_note 말미에 append·데이터 단일 출처)
# ★2문장째(이자 처리)의 수명 = 수록 판 연동: 인쇄 32쪽 문면이 바뀌면(쪽 sha 불일치로 감지)
#   KISTEP이 현행화한 것이므로 이 문장을 제거하고 재추출할 것(P0 게이트 §6-③).
LAW_PRIORITY_EXTRA = [
    "학생인건비 계상기준·지급액·이체 기한 등 구체값을 인용할 때는 get_provision_detail로 국가연구개발사업 연구개발비 사용 기준(rnd_funding_standard) 현행 원문을 교차 확인하십시오.",
    "이 매뉴얼의 학생인건비 이자 처리 서술(제3장 6절)은 구판 고시 제75조 구조(제1항제4호 계정 산입) 기준입니다. 현행 고시는 정부지원금이자의 원칙이 국고 납입으로 변경되고 학생인건비통합관리계정 산입 근거가 제75조제2항제1호로 이동했으므로, 이자 처리는 현행 제75조 원문을 기준으로 확인하십시오.",
]

# ── EXPECTED 스냅샷 (fail-closed 정본 — 별권1 26.7판 실측 2026-08-05) ─────────
EXPECTED_PDF_SHA256 = "7181b447bcb11a67f991df4ade44d103790f289d6ea2bbea01540900d9e4d9a4"
EXPECTED_PHYSICAL_PAGES = 96
EXPECTED_PAGE_OFFSET = 4  # PDF쪽 = 인쇄쪽 + 4 (표지·머리말·목차 2)
EXPECTED_PRINTED_LAST = 91  # 인쇄쪽 최종 (PDF p.95 — p.96은 마커 없는 뒤표지)
EXPECTED_SOURCE_LIST_NO = "94788"  # 승인 KISTEP 게시물 번호 (26.7 세트 — 별권 2와 동일 게시물)
# ★승인 게시물 전체 URL 동결(diff 적대검토 Codex BLOCKING 반영) — list_no만 검사하면 다른
# board 경로(bid·mid)가 provenance로 기록되는 것을 통과시킨다. 본권·별권 2·3 데이터와
# 동일한 canonical URL만 허용(네 파일 source_url 동일성은 테스트로도 잠금).
EXPECTED_SOURCE_URL = "https://www.kistep.re.kr/board.es?mid=a10301000000&bid=0003&act=view&list_no=94788"

# 장 표제 간지(미수록) — raw get_text() verbatim 동결 (D2: 승인 표제 외 텍스트 유입 시 BLOCK)
EXPECTED_GANJI_TEXT = {
    1: "제1 장\n학생인건비통합관리 제도 \n개요\n학생인건비통합관리 제도 매뉴얼\n",
    9: "제2 장\n학생인건비통합관리 제도 \n운영\n학생인건비통합관리 제도 매뉴얼\n",
    19: "제3 장\n학생인건비통합관리\n기관의 학생인건비 관리\n학생인건비통합관리 제도 매뉴얼\n",
    39: "제4 장\n학생인건비통합관리기관 \n지정･변경･점검 및 지정취소\n학생인건비통합관리 제도 매뉴얼\n",
    47: "제5 장\nFAQ\n학생인건비통합관리 제도 매뉴얼\n",
}
EXPECTED_BLANK_PAGES = (2, 8, 10, 20, 38, 40, 48)  # 인쇄 번호 내 빈 쪽(0자 강제·미수록)
EXPECTED_BODY_PAGES = tuple(
    list(range(3, 8)) + list(range(11, 19)) + list(range(21, 38))
    + list(range(41, 47)) + list(range(49, 92))
)  # 마커 보유 본문 79쪽

EXPECTED_CHAPTERS = [
    (1, "학생인건비통합관리 제도 개요", 1),
    (2, "학생인건비통합관리 제도 운영", 9),
    (3, "학생인건비통합관리 기관의 학생인건비 관리", 19),
    (4, "학생인건비통합관리기관 지정･변경･점검 및 지정취소", 39),
    (5, "FAQ", 47),
]

# (chapter_no, section_no, title, start_printed) — 목차 스냅샷 (별권 1은 목차=본문 22/22 일치 실측)
EXPECTED_TOC_SECTIONS = [
    (1, 1, "추진 배경", 3),
    (1, 2, "목적", 3),
    (1, 3, "주요 내용", 3),
    (2, 1, "학생인건비 사용용도", 11),
    (2, 2, "학생연구자 지원규정 마련･운영 및 공개", 12),
    (2, 3, "학생인건비 계상기준 설정", 13),
    (2, 4, "전산시스템 구축 및 연계", 14),
    (2, 5, "통합관리계정 설정", 15),
    (2, 6, "학생인건비부당회수 금지 및 예방 관리", 16),
    (2, 7, "운영현황 자체점검", 17),
    (3, 1, "학생인건비 수입 처리", 21),
    (3, 2, "학생인건비 지급 대상 확인", 23),
    (3, 3, "학생연구자 연구참여확약", 24),
    (3, 4, "학생인건비 지급액 책정 및 지급", 25),
    (3, 5, "계정별 학생인건비 잔액 처리", 30),
    (3, 6, "학생인건비 이자 처리", 32),
    (3, 7, "학생인건비 이관", 33),
    (3, 8, "학생인건비 반납", 36),
    (4, 1, "통합관리기관 지정 및 관리유형 변경", 41),
    (4, 2, "운영결과 점검(과기정통부→통합관리기관)", 43),
    (4, 3, "지정취소 기준", 44),
    (4, 4, "지정취소 시 통합관리기관의 사후조치", 46),
]

# 본문 헤딩 스냅샷 — 별권 1은 TOC와 본문 제목이 전건 일치(실측 22/22·별권 2의 오기류 0)
EXPECTED_BODY_SECTIONS = list(EXPECTED_TOC_SECTIONS)

# 목차↔본문 승인 불일치 — 별권 1은 0건 (그 외 diff는 전부 BLOCK)
KNOWN_TOC_BODY_MISMATCH: dict = {}

# 제5장 FAQ — 절 없는 장의 단일 유닛(D1). Q줄 9건 verbatim 동결(각 정확 1회·문서 순서 검증 후
# subsection_titles로 등재 — 검색 제목 tier 도달 보장)
EXPECTED_FAQ_QLINES = [
    "Q1. 2장 <학생인건비계상률&계상기준>",
    "Q2. 3장 <학생인건비 지급>",
    "Q3. 3장 <학생인건비 지급>",
    "Q4. 3장 <학생인건비 지급>",
    "Q5. 3장 <학생인건비 수입처리>",
    "Q6. 3장 <학생인건비 지급>",
    "Q7. 3장 <학생인건비통합관리계정별 잔액 처리>",
    "Q8. 3장 <학생인건비통합관리계정별 잔액 처리>",
    "Q9. 4장 <학생인건비통합관리기관 지정>",
]

# 참고 3건 — (no, body_title, start, end). 데이터 제목은 본문 canonical(별권 2 D9 동일 원칙)
EXPECTED_REFS = [
    (1, "학생인건비통합관리기관 지정 현황 (2026년 3월 기준)", 51, 51),
    (2, "연구개발기관계정 표준 운영 가이드라인", 52, 52),
    (3, "학생인건비통합관리 점검 자료집", 53, 91),
]
# 목차 표기(참고1만 본문과 다름 — 괄호 연월 없음). known-variant로 subsection_titles에 추가.
EXPECTED_REF_TOC_TITLES = {
    1: "학생인건비통합관리기관 지정 현황",
    2: "연구개발기관계정 표준 운영 가이드라인",
    3: "학생인건비통합관리 점검 자료집",
}

# 쪽별 추출 텍스트(헤더·마커 제거 후) sha256 — 검증 완료 산출물(2026-08-05) 기준 동결.
# ★목적: PyMuPDF 버전 드리프트·추출 로직 회귀로 인한 침묵 텍스트 변화 차단(별권 2 P1 전례).
EXPECTED_PAGE_TEXT_SHA256: dict[int, str] = {
    3: "a182a7fa43a779c20f71fc4c39ccd4e567f5eab1d8bee2cab406cb6fb6e0f723",
    4: "8c566ce84a2fcd3c5d68aafc9e95898eef46a6a51efddd340110c4207ae282c7",
    5: "7747aac3b0412f0c64bd13c45bff7cd6cfc7f3f86368977cfb5dbca6af1460aa",
    6: "08a72a214c4626ddee66541119325a8cdd02cb111049e9b14b33c4657e20f9b8",
    7: "7ac477f4355386ba05f6b66a18a8dca73265658bcb22ee37fd71bd751a1cd183",
    11: "a3f3549e2eafe5807ddca63dee5f8509b067b449e1ea05973e8e93a85a56bd3a",
    12: "fc5e701978e873ed04832bbbfd7b4045fbeea6b49282b4feb35ba5f109a7fe67",
    13: "a512e99a42eebe01ce6012d80be847b0f025849b54cc35ee9f6f014f0040cfa9",
    14: "a1f5d2d8e5561eaa813987a985752a55c51124eb105faf43dc6b765cdcf747f5",
    15: "d4ead711f6714e40f90ce620b67c6ffa024a55e003bad35e8e37de298e4afe42",
    16: "f69533a29a4c09b368a1a540d3e089c69800a70f9d9ab4519db950547b07a9d3",
    17: "b6bcdd425ed418e71e2978117087dc1486cdc31b17c9932e85da76eed519f11e",
    18: "bb02513d75689bfefa617e610d8e20e3f5d71bb0d16bac47edab39de6d162c69",
    21: "9e3467b6bfe3c15c9a7c27c5415e68d063437eaf5733f6bcbda31136dc2f5488",
    22: "8f093a4db54e8e61268c6a9df1fa580ed908a56fc4abc66ec29f3d8131d6f766",
    23: "497b0a8e3b13d55c2866c779f3902fd6216f3267ce1bd27c755edc928e2f6bec",
    24: "f70859eaeee7ef1b37b32b1935e2e19692f097578073c78529003d1c8332c5ec",
    25: "d19ea42fe2cea9a42f70dfe9277463fd2f845336e07218d7e9a9833246eb4bcb",
    26: "3df8f6ef70de693cf4f55cbcd2ce9deb4f44635262bc7cc5e920feeac62b5c6d",
    27: "af280ca90968440c8317b005c8f6d8e10bcdc242630d28333f141d0898c9496a",
    28: "5695db31e3becb70ea51ce46570cc190a36dc34671d08faed8ad11191e8ead7e",
    29: "17702bf2488fc41652617e81c109025e187790afe1277cc1c52ce12bb2c6da5a",
    30: "30ca9f6e7a4758b23c5c175856affde3cf9a78c052467b3fcf94ce7c899a1efe",
    31: "23f8ff09f0e33f869f7ba41646e084eaf0110dac02b45a75ed8da03c7a05079b",
    32: "13adc938150ec3adf4f44102c00dc51a433b2b60baffc276daf4c56a9301fb6c",
    33: "03106a12c88c112ec7eadac038b0aca5948c281f3f9aeadfaec8eea52b8f6d5e",
    34: "0a3e2a5a39e3b10dc1e9c19a1141a3b0284c03e0e58cc52039e40529d8f713c5",
    35: "8c1c6e9bac664478d20208f4a723edc711f2699d1a98168b9e81bbc90adb1a11",
    36: "a01cd660d566f7764d552da86efe1c12760acfdc22238decc45c6f76dcce1768",
    37: "0328e0f3153b9eb5fff04bffca04c127ac09bf3c1a8c3ce33e10396e3a80bfe1",
    41: "6b2b9cae1cd82e98769ed77e279f1d8dbd6d0a0f888ff66bcfcab45a3c9695ff",
    42: "e0431b0454c92abe6b055b79f3c788486954a26b689def085bf496bbd211698e",
    43: "b436ce9c22fd4905f57c6248d2365444487c07b9e7c8aa26c426d1ed15058d1d",
    44: "d2f4e6c1e0ec89e39e1bc1a0abfb61a1fb0f37acb665be4efd9f9d6bff30cc97",
    45: "f72b727b8f9dad60a756d78f56867a5ee5abfb849f4660f4fa4ae56b4049f32b",
    46: "7f02a01e1d78210492ee87d1165a01ea781b4e623b23fdd69fb9c34ae184434a",
    49: "da8179fd84b6185eee845b1ac61f78b6f7537a046a1360ef2b875eee9373c1cd",
    50: "471d2dd73b97b02276f3cbc0dee7a9b28bd2f625f724b6707103065e357723bb",
    51: "b3f86f29e1b90e8ff08c1a7394cbb886c6ba2490adb3e597c9ad17e7d1662b5b",
    52: "42a00e6b4884131e4c14dcad12dd5f9005a2bb1aee6d43c620661924e51b809c",
    53: "3d4fb1ad8d2ffcef77394a02f8912ad275b5b1a38bd806c46a07c38d8682abdc",
    54: "db44c54f17e5975ae44c71bbaf3998b5e22cd6eb3f6e947f41edf829f1782882",
    55: "e6b413a1e31d17a5a00fdc321970842f056ab1e2a23fa38549391a7345d776d3",
    56: "9f17c5379e6e78b8e96909a724c0189a96e2942381da1b1119b91daf596384e7",
    57: "8ca01a997b33f43d82a5867d63d271a13d1164cb386aff1b810fe4be7ea64377",
    58: "ed353554b7f8178645017fc6859408c2365854f4ceaf1c22842550e0fbd78fe4",
    59: "923c18eac0523534198d88b13c7a61d7344f6c44215591b3df0b78dc65be8843",
    60: "b446c7cae33c34d1129f8b0bbc71b1f7203e3a4034adb1b7b14bf69b580829f4",
    61: "2c670838d10dca5a347bd038e9f74b55897562062beec6714b1b1bcc8b2b8cbc",
    62: "901127c655281b9ca48822773a6caedfa1090c80c3272d20a8a6051bcb398f33",
    63: "efae88264bc3e45337c3ad5eb2b964dcea954c2529c1a5aac9a718559e75255a",
    64: "89af06e62dca6919cfd33048578746de008427e29a369e5658fdc52ed746e975",
    65: "35bff06e7accbea7e5bc5d85a7903aa9e69774ef2459eb93c181bc92e2f80fe6",
    66: "b70ed20e97d2ed556f1e68399102b0cffb7ffa1d6ee4b768148369d30b88468c",
    67: "aa359a42a6742c5b32bef8b020f57b678751ad5c33ba884d4b9cfc9030ed90b4",
    68: "3b77f7d404e9b9684f604bcc9e9979c4fd6ae6839bf2d002a122287671312b2e",
    69: "f0b23a05b7966d6ec7855cfe0add3efba24cec3188b7fedf497f06235a72c394",
    70: "7c3e44e88fcc4a21cdbc039450b724c17655ba0f3ff356432780471996b1f00e",
    71: "403c2a906278aeb9e943303facdafd84a8a662f4a2b4204bf5f46431596897e2",
    72: "b7c7cc2ec5d26cf204774b930a81378a3c260e5653cbaba447d0113b356e803e",
    73: "67b35863bfae7e02a5f6c5f15a867abdc64ef703851252ac7f01a05daf26c04d",
    74: "b412a8b55408a454b0e9fd314132159d8b53d28416ccfc766932db65c034ba61",
    75: "e74142d4bb77fd05a176d7b90af6610baab9c4c4e519f38bfef439b885b5f68d",
    76: "86f0a695dc201d76cb420d11cf5edde8d4ee6ca47422f1002ab89147e326b79a",
    77: "8258b425817c7655b04cc4fcc3658a72c3bf990d247e2c270321ef90569a0924",
    78: "b885514d137495670c647bc005338121509c90d7708d4d86000149f281fd9fa8",
    79: "cd444ad9fa1a7306ac67163ac8d179620a55a2893bc1ef812a3fdcf63f5c292e",
    80: "0ddf2d96451db22d4b29246a9ce190946a38939e7601c0818705142aabd403e6",
    81: "0362154557d6534f699bf5550606e81890b2f779cc9b2ffc62278480fc01c8ac",
    82: "82c84f050d8ca9e3cb7ba5a2dc6bf900ef3742faa9668896ce8f0b0b93d0afd7",
    83: "82f7509d0804c2be207602d83359c82c902467b54ad0c12f16285e796c7a4bbd",
    84: "5b2fca744ed2f19eb670e9879f71544c5acb8ed06eb05dca0d51f8185c3473be",
    85: "567f70001bada228db1c485014ce4b3ecfc310a59b9ce094bc350b2bd1c77536",
    86: "2f358e209ebe90cac8c5761c5c141a274526abaf74c0714c88414a86c78779cb",
    87: "c98819426fc09fcd7cb87ead348020e5cce6c66fc11ef05f53b752dc3ba20116",
    88: "e6e1f9d77b0ce2a23d0af03253f3bc85167c5f907f7218475abb7e51eb11bcef",
    89: "8d22238c6ae6556dc4570fe8a2dcfa03dcf46e19564bb6c92564d890ef71d35e",
    90: "f41074275a155cab1c2ba7d5827105f3d9a919eba87468021c0bf1ea9f67e2e0",
    91: "7e530c2c05b6aaaea5736265a052ad4ace52016884bcbbe7a5aa14e078c6ba59",
}

EXPECTED_TOTAL_CHARS = 76353  # 단위 char_count 합계 — 최종 JSON 잠금

# 유닛별 자수 동결(D3-④ 유닛 경계 digest의 경량형) — 쪽별 sha가 같아도 같은 쪽 다중 절
# 사이의 경계 이동은 유닛 자수에 즉시 반영된다.
EXPECTED_UNIT_CHAR_COUNTS: dict[str, int] = {
    "b1-1-1": 269,
    "b1-1-2": 68,
    "b1-1-3": 5644,
    "b1-2-1": 1356,
    "b1-2-2": 1434,
    "b1-2-3": 2404,
    "b1-2-4": 745,
    "b1-2-5": 1707,
    "b1-2-6": 1995,
    "b1-2-7": 1524,
    "b1-3-1": 3251,
    "b1-3-2": 966,
    "b1-3-3": 2565,
    "b1-3-4": 5900,
    "b1-3-5": 2147,
    "b1-3-6": 1037,
    "b1-3-7": 4195,
    "b1-3-8": 1937,
    "b1-4-1": 2349,
    "b1-4-2": 1791,
    "b1-4-3": 2171,
    "b1-4-4": 928,
    "b1-5-1": 2550,
    "b1-ref-1": 856,
    "b1-ref-2": 1180,
    "b1-ref-3": 25384,
}

# 고시 표기 장부(D7) — 본문 내 "제YYYY-N호" 표기의 {표기: {인쇄쪽: 건수}} 동결.
# 제2025-9호@22는 원문 내부 불일치의 사실 고정(변조 아님). 제2026-0165호는 공고 번호(고시 아님).
EXPECTED_GOSI_LEDGER: dict[str, dict[int, int]] = {'제2026-5호': {11: 2, 12: 1, 13: 1, 14: 1, 15: 2, 16: 1, 17: 1, 21: 1, 23: 1, 24: 1, 25: 1, 28: 1, 30: 2, 32: 1, 33: 1, 36: 1, 41: 1, 43: 1, 44: 2, 46: 1}, '제2025-9호': {22: 1}, '제2026-0165호': {51: 1}}

# 결속 객체 사실 기재 (D4 — P1.5 렌더 대조 실측 2026-08-05. 값 오결속이 아니라 구조 정보가
# 텍스트에 없음. 경고 부착은 표 fail-closed QA의 대체 수단이 아님 — 핵심 구체값(계상기준
# 월 130/220/300만 원·제91조의2 잔액 산식·이체 기한)은 텍스트 보존·결속 정상을 렌더로 확인)
TABLE_STRUCTURE_NOTES = {
    "b1-1-3": [
        "이 절의 <표 1-2> 학생인건비 지급 개념도(인쇄 5쪽)는 과제·계정에서 학생연구자로 이어지는 "
        "지급 흐름(화살표·열 대응)이 도형 배치로만 표현되어 추출 텍스트에는 셀 문구만 순서대로 "
        "남습니다. 지급 구조는 제3장 본문 또는 표기된 인쇄쪽 원문으로 확인하십시오.",
    ],
    "b1-3-4": [
        "이 절의 <표 3-1> 지급체계(인쇄 26쪽)의 계정별 지급 구성 막대는 이미지라 추출 텍스트에 "
        "없고, <표 3-2> 지급 개념도(인쇄 27쪽)의 과제→계정→학생연구자 열 대응도 도형 배치로만 "
        "표현됩니다. 지급 구성·흐름은 표기된 인쇄쪽 원문으로 확인하십시오.",
    ],
    "b1-ref-1": [
        "이 참고의 지정 현황 표(인쇄 51쪽)는 다열 표가 열 단위로 직렬화되어 각 기관명이 "
        "연구책임자단위(13개)·연구개발기관단위(59개) 중 어느 유형인지 텍스트에서 구분되지 "
        "않습니다. 기관별 관리유형은 표기된 인쇄쪽 원문 또는 과학기술정보통신부 공고(제2026-0165호)로 "
        "확인하십시오.",
    ],
    "b1-ref-3": [
        "이 참고의 점검 체크리스트 표는 '가/부' 판정란(빈 체크박스)이 추출 텍스트에서 항목 사이의 "
        "□ 기호로만 나타나 열 귀속 정보가 없습니다(판정란은 빈 칸이라 값 손실은 아님). 표 구조는 "
        "표기된 인쇄쪽 원문으로 확인하십시오.",
        "이 참고의 <전산시스템 구축 예시> 화면들은 이미지로만 실려 있어 화면 안의 항목·값이 추출 "
        "텍스트에 없습니다. 구축 예시 상세는 표기된 인쇄쪽 원문으로 확인하십시오.",
    ],
}

# ── 러닝헤더/마커 제거 규칙 (실측: 헤더 y0 5.3~8%·장 시작쪽 문서 제목 밴드 9.5~11.4% →
#    상단 8% / 마커 y0 93.6% → 하단 90% — 별권 2와 동일 상수 재사용 가능 실측) ──────────
_TOP_FRAC = 0.08
_BOTTOM_FRAC = 0.90
_DOC_TITLE_HDR = "학생인건비통합관리 제도 매뉴얼"
# 문서 제목 밴드 보존 기대 쪽(장 시작 본문쪽) — 정확 일치 fail-closed(D8·별권 2는 감사 기록만)
EXPECTED_DOC_TITLE_BAND_PAGES = (3, 11, 21, 41, 49)
# 인쇄쪽 마커: 홀수 "/ N /"·짝수 "\ N \" (양끝 동일 문자 — 홀짝 강제·별권 2 동형)
_PAGE_MARK = re.compile(r"^([\\/])\s*(\d+)\s*([\\/])$")

_SEC_HEAD = re.compile(r"^(\d+)\.\s*(.*)$")
# 연도 4자리 전체 허용 — 미래 판(2030년대 고시 번호) 장부 누락 차단(diff 적대검토 Gemini NIT)
_GOSI_MARK = re.compile(r"제(\d{4})-(\d+)호")


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
    """쪽별 기대 러닝 헤더(정규화 비교용 기준 문자열).

    짝수쪽 = 문서 제목. 홀수쪽 = 참고 구간(참고1 시작 이후)이면 "참고￭￭￭", 그 외에는 그 쪽을
    소유한 장 "제N장 <제목>￭￭￭" (제5장 FAQ 포함 — 실측 "제5장  FAQ ￭￭￭").
    """
    if printed % 2 == 0:
        return _DOC_TITLE_HDR
    ref_start = EXPECTED_REFS[0][2]
    if printed >= ref_start:
        return "참고 ￭￭￭"
    owner = None
    for c, t, p in EXPECTED_CHAPTERS:
        if p <= printed:
            owner = (c, t)
    return f"제{owner[0]}장 {owner[1]}￭￭￭"


# ── 목차(TOC) 파싱 — 판 갱신 드리프트 감지기 ─────────────────────────────────

_TOC_SKIP = re.compile(r"^(CONTENTS|목\s*차)$")
# 별권 1 목차 엔트리: 제N장 / "N." 절 / "참고N" — 전부 점선+쪽번호로 끝남(소절 엔트리 없음)
_TOC_ENTRY = re.compile(
    r"^(?:제\s*(\d+)\s*장|(\d+)\.|참고\s*(\d+))\s*(.*?)\s*·{1,}\s*(\d+)\s*$"
)


def parse_printed_toc(doc):
    """별권 1 인쇄 목차(2쪽)를 파싱해 chapters/sections/refs 반환 (꺾임 제목 병합 — 별권 2 동형)."""
    toc_lines = []
    for i in range(min(10, doc.page_count)):
        text = doc[i].get_text()
        if "목  차" not in text[:60] and "CONTENTS" not in text[:60]:
            continue
        if not re.search(r"(제\s*\d+\s*장|참고\s*\d+).*·{1,}\s*\d+", text):
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
        else:  # 참고N
            refs.append((int(m.group(3)), title, page))
    return chapters, sections, refs


def validate_constants(errors: list[str]):
    """상수 자체 정합성(D3): 분할 집합·관계식·TOC/BODY diff·notes 쪽 참조·FAQ/참고 상수."""
    # 인쇄 1~91 완전 분할: 본문 ∪ 간지 ∪ blank (교집합 0·합집합 전체)
    body = set(EXPECTED_BODY_PAGES)
    ganji = set(EXPECTED_GANJI_TEXT)
    blank = set(EXPECTED_BLANK_PAGES)
    if body & ganji or body & blank or ganji & blank:
        errors.append("분할 집합 교집합 존재(본문/간지/blank)")
    if body | ganji | blank != set(range(1, EXPECTED_PRINTED_LAST + 1)):
        errors.append("분할 집합 합집합이 인쇄 1~91과 불일치")
    # 물리쪽 관계식: 선행 오프셋 + 인쇄쪽 + 뒤표지 1 = 물리 쪽수
    if EXPECTED_PAGE_OFFSET + EXPECTED_PRINTED_LAST + 1 != EXPECTED_PHYSICAL_PAGES:
        errors.append(
            f"물리쪽 관계식 위반: {EXPECTED_PAGE_OFFSET}+{EXPECTED_PRINTED_LAST}+1 != {EXPECTED_PHYSICAL_PAGES}"
        )
    # 장 간지 ↔ 장 시작쪽 관계식: 첫 절 시작쪽 = 간지쪽 + 2 (간지 뒷면 blank 1쪽)
    first_sec_of_chapter: dict[int, int] = {}
    for c, n, _t, p in EXPECTED_BODY_SECTIONS:
        first_sec_of_chapter.setdefault(c, p)
    first_sec_of_chapter.setdefault(5, 49)  # 제5장 FAQ(절 없음)의 본문 시작쪽
    for c, _t, cp in EXPECTED_CHAPTERS:
        if cp not in ganji:
            errors.append(f"제{c}장 시작쪽 {cp}가 간지 집합에 없음")
        if first_sec_of_chapter.get(c) != cp + 2:
            errors.append(f"제{c}장 첫 본문쪽 {first_sec_of_chapter.get(c)} != 간지 {cp}+2")
    if EXPECTED_PAGE_TEXT_SHA256 and sorted(EXPECTED_PAGE_TEXT_SHA256) != list(EXPECTED_BODY_PAGES):
        errors.append("EXPECTED_PAGE_TEXT_SHA256 키가 본문 79쪽과 불일치")
    if not EXPECTED_PAGE_TEXT_SHA256:
        errors.append("EXPECTED_PAGE_TEXT_SHA256 미동결(빈 dict) — freeze 절차 미완")
    # notes의 "인쇄 N쪽" 참조가 수록 범위 안인지
    for sid, notes in TABLE_STRUCTURE_NOTES.items():
        for note in notes:
            for m in re.finditer(r"인쇄\s*(\d+)쪽", note):
                n = int(m.group(1))
                if n not in body:
                    errors.append(f"TABLE_STRUCTURE_NOTES[{sid}]의 쪽 참조 {n}이 본문쪽 밖")
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
    if diffs != KNOWN_TOC_BODY_MISMATCH:
        errors.append(
            f"TOC/BODY 제목 diff가 승인 목록과 다름:\n  승인: {KNOWN_TOC_BODY_MISMATCH}\n  실제: {diffs}"
        )
    # FAQ 상수: Q1~Q9 연속 번호
    qnos = [int(re.match(r"^Q(\d+)\.", q).group(1)) for q in EXPECTED_FAQ_QLINES]
    if qnos != list(range(1, len(EXPECTED_FAQ_QLINES) + 1)):
        errors.append(f"FAQ Q줄 번호 불연속: {qnos}")
    # 참고 상수: 시작·끝 쪽 단조 + 본문쪽 소속
    prev_end = 0
    for n, _t, s, e in EXPECTED_REFS:
        if not (prev_end < s <= e):
            errors.append(f"참고{n} 쪽 범위 이상: {s}~{e}")
        if s not in body or e not in body:
            errors.append(f"참고{n} 시작/끝쪽이 본문쪽 밖: {s}~{e}")
        prev_end = e
    if EXPECTED_REFS[-1][3] != EXPECTED_PRINTED_LAST:
        errors.append("마지막 참고의 끝쪽이 인쇄 최종쪽과 불일치")


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
    exp_rf = [(n, norm_title(t), p) for n, t, p in
              ((n, EXPECTED_REF_TOC_TITLES[n], s) for n, _bt, s, _e in EXPECTED_REFS)]
    got_rf = [(n, norm_title(t), p) for n, t, p in refs]
    if got_rf != exp_rf:
        errors.append(f"참고 목차 불일치:\n  기대: {exp_rf}\n  파싱: {got_rf}")


# ── 페이지 텍스트 추출 (쪽별 기대 헤더·홀짝 마커 + bbox 이중 조건 제거) ───────

def extract_page_lines(page, printed: int, audit: dict) -> list[str]:
    """fitz dict 순서로 줄 재구성. 쪽별 기대 헤더(상단)·홀짝 마커(하단)만 제거 (별권 2 동형)."""
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
                audit["kept_outside_region"].append((printed, s[:40], round(y0 / height * 100, 1)))
            if printed % 2 == 1 and norm_title(s) == norm_title(_DOC_TITLE_HDR) \
                    and not (header_like and y0 <= top_limit):
                # 장 시작 본문쪽(홀수쪽)의 문서 제목 밴드(y0 9.5~11.4%) 보존 기록 — D8에서 정확
                # 5건 검증. 홀수쪽 한정: 짝수쪽은 기대 헤더 자체가 문서 제목이라, 본문에 제목과
                # 동일한 독립 줄이 유입되는 판 갱신 케이스에서 밴드 검증이 거짓 BLOCK되는 것을
                # 차단(diff 적대검토 Gemini 지적 — 그 경우에도 kept_outside_region 감사에는 남음).
                audit["doc_title_band"].append((printed, round(y0 / height * 100, 1)))
            kept.append(text)
    return kept


def find_heading_indices(lines: list[str], sec_no: int, title: str) -> list[int]:
    """절 시작쪽에서 'N. 제목' 헤딩 줄 index 전수 탐색 — 정규화 전체 제목 정확 일치.

    별권 1 본문에는 인용 고시 조문의 호 번호("1. 학생인건비…")가 동형으로 다수 실재하므로
    (실측), 절 번호+정규화 전체 제목 정확 일치가 필수다(별권 2 P1 적대검토 전례와 동일 근거).
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
    ap = argparse.ArgumentParser(description="혁신법 매뉴얼 별권 1 학생인건비통합관리 제도 매뉴얼 추출 (R4-P1)")
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
    list_no = urllib.parse.parse_qs(parsed_url.query).get("list_no", [None])[0]
    if list_no != EXPECTED_SOURCE_LIST_NO:
        print(
            f"[fail-closed BLOCK] source-url의 list_no {list_no!r} != 승인 {EXPECTED_SOURCE_LIST_NO!r} "
            "— 판 갱신이라면 EXPECTED_SOURCE_LIST_NO를 재실측 갱신하십시오.",
            file=sys.stderr,
        )
        return 2
    if args.source_url != EXPECTED_SOURCE_URL:
        print(
            f"[fail-closed BLOCK] source-url이 승인 전체 URL과 다릅니다(bid·mid 등 경로 상이).\n"
            f"  승인: {EXPECTED_SOURCE_URL}\n  입력: {args.source_url}\n"
            "판 갱신이라면 EXPECTED_SOURCE_URL을 재실측 갱신하십시오.",
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

    # 1.5) 선행 물리쪽·간지·blank·뒤표지 검증 (D2·D3 — 96물리쪽 완전 분할)
    if doc[0].get_text().strip() != "":
        errors.append("물리 p.1(표지)에 예상 밖 텍스트 실재")
    if "본 매뉴얼은" not in doc[1].get_text():
        errors.append("물리 p.2(머리말) 기대 문면 미발견")
    for i in (2, 3):
        if "목  차" not in doc[i].get_text()[:60]:
            errors.append(f"물리 p.{i + 1}(목차) 기대 문면 미발견")
    if doc[EXPECTED_PHYSICAL_PAGES - 1].get_text().strip() != "":
        errors.append(f"물리 p.{EXPECTED_PHYSICAL_PAGES}(뒤표지)에 예상 밖 텍스트 실재")
    for pr, exp_text in EXPECTED_GANJI_TEXT.items():
        got = doc[pr + off - 1].get_text()
        if got != exp_text:
            errors.append(f"간지 인쇄 {pr} 표제 verbatim 불일치(승인 표제 외 텍스트 유입 의심)")
    for pr in EXPECTED_BLANK_PAGES:
        if doc[pr + off - 1].get_text().strip() != "":
            errors.append(f"blank 인쇄 {pr}에 텍스트 실재(0자 전제 위반)")

    # 2) 쪽번호 마커 검증 — 본문 79쪽 전건 정확 1개·홀짝·번호·하단 bbox / 비본문쪽 마커 후보 0
    marker_count_by_page: dict[int, int] = {}
    offsets: dict[int, int] = {}
    body_set = set(EXPECTED_BODY_PAGES)
    for i in range(doc.page_count):
        printed_guess = (i + 1) - off
        page = doc[i]
        height = page.rect.height
        d = page.get_text("dict")
        for block in d["blocks"]:
            if block.get("type") != 0:
                continue
            for ln in block["lines"]:
                s = "".join(sp["text"] for sp in ln["spans"]).strip()
                m = _PAGE_MARK.match(s)
                if not m:
                    continue
                if printed_guess not in body_set:
                    errors.append(f"비본문 물리 p.{i + 1}에 마커 후보 {s!r} 실재")
                    continue
                if ln["bbox"][1] < height * _BOTTOM_FRAC:
                    continue
                want_slash = "/" if printed_guess % 2 == 1 else "\\"
                if m.group(1) != want_slash or m.group(3) != want_slash:
                    errors.append(f"p.{printed_guess}: 마커 홀짝 형식 위반 {s!r} (기대 {want_slash!r})")
                    continue
                found = int(m.group(2))
                marker_count_by_page[printed_guess] = marker_count_by_page.get(printed_guess, 0) + 1
                o = (i + 1) - found
                offsets[o] = offsets.get(o, 0) + 1
    if list(offsets.keys()) != [off]:
        errors.append(f"쪽번호 오프셋 불균일: {offsets} (기대 단일값 {off})")
    bad_marks = {p: c for p in EXPECTED_BODY_PAGES
                 if (c := marker_count_by_page.get(p, 0)) != 1}
    if bad_marks:
        errors.append(f"쪽당 마커 수 이상(기대 정확 1): {bad_marks}")

    if errors:
        print("[fail-closed BLOCK] 상수/목차/분할/마커가 EXPECTED 스냅샷과 다릅니다 — JSON 미생성.", file=sys.stderr)
        print("새 판(개정판)이라면 docstring의 판 갱신 절차에 따라 EXPECTED_* 상수를 갱신 후 재실행하십시오.", file=sys.stderr)
        for e in errors:
            print(" - " + e, file=sys.stderr)
        return 2

    # 3) 본문 페이지 전처리 + ★쪽별 텍스트 sha 잠금 + 고시 표기 장부(D7)
    audit = {"removed": 0, "removed_by_page": {}, "kept_outside_region": [], "doc_title_band": []}
    page_lines: dict[int, list[str]] = {}
    image_only_pages: set[int] = set()
    table_pages: set[int] = set()
    table_flag_error = None
    page_sha_errors: list[str] = []
    gosi_ledger: dict[str, dict[int, int]] = {}
    for printed in EXPECTED_BODY_PAGES:
        page = doc[printed + off - 1]
        lines = extract_page_lines(page, printed, audit)
        page_lines[printed] = lines
        joined = "\n".join(lines)
        got_sha = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        if got_sha != EXPECTED_PAGE_TEXT_SHA256[printed]:
            page_sha_errors.append(f"p.{printed}: 추출 텍스트 sha 불일치 ({got_sha[:16]}…)")
        for m in _GOSI_MARK.finditer(joined):
            key = m.group(0)
            gosi_ledger.setdefault(key, {})
            gosi_ledger[key][printed] = gosi_ledger[key].get(printed, 0) + 1
        if len(joined.strip()) == 0:
            image_only_pages.add(printed)  # D4: 추출 0자 쪽만(저텍스트·다이미지 쪽 오등재 금지)
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
    if gosi_ledger != EXPECTED_GOSI_LEDGER:
        print("[fail-closed BLOCK] 고시 표기 장부가 승인 스냅샷과 다릅니다 — JSON 미생성.", file=sys.stderr)
        print(f"  기대: {EXPECTED_GOSI_LEDGER}\n  실제: {gosi_ledger}", file=sys.stderr)
        return 2

    # 4) 유닛 목록 26건 (D1: 일반 절 22 + FAQ 1 + 참고 3)
    first_sec_of_chapter: dict[int, int] = {}
    for c, n, _t, p in EXPECTED_BODY_SECTIONS:
        first_sec_of_chapter.setdefault(c, p)
    chapter_titles = {c: t for c, t, _p in EXPECTED_CHAPTERS}

    units = []
    for c, n, t, p in EXPECTED_BODY_SECTIONS:
        units.append({
            "id": f"b1-{c}-{n}", "kind": "section", "chapter_no": c,
            "chapter_title": chapter_titles[c],
            "section_label": f"{n}.", "section_no": n, "section_title": t,
            "start": p,
            "first_of_chapter": (p == first_sec_of_chapter[c] and n == min(
                sn for cc, sn, _tt, _pp in EXPECTED_BODY_SECTIONS if cc == c
            )),
        })
    # FAQ 단일 유닛 — section_label은 빈 문자열(D1·계획 /disc Codex 권고): citation이
    # "제5장 FAQ FAQ" 중복 없이 "제5장 FAQ"로 조립되게 한다(build_citation 결측 마디 생략).
    units.append({
        "id": "b1-5-1", "kind": "faq", "chapter_no": 5,
        "chapter_title": chapter_titles[5],
        "section_label": "", "section_no": 1, "section_title": "FAQ",
        "start": 49, "first_of_chapter": True,
    })
    for n, t, s, _e in EXPECTED_REFS:
        units.append({
            "id": f"b1-ref-{n}", "kind": "ref", "chapter_no": 0, "chapter_title": "참고",
            "section_label": f"참고{n}", "section_no": n, "section_title": t,
            "start": s, "first_of_chapter": True,
        })
    units.sort(key=lambda u: (u["start"], 0 if u["kind"] == "section" else 1, u["section_no"]))

    # 5) 절 단위 조립 — 같은 쪽 다중 절 분할 지원(인쇄 3 실측 3절)·중간쪽은 본문쪽만 귀속(D8)
    units_by_start: dict[int, list[dict]] = {}
    for u in units:
        units_by_start.setdefault(u["start"], []).append(u)

    assembled = []
    boundary_notes = []
    for k, u in enumerate(units):
        next_start = units[k + 1]["start"] if k + 1 < len(units) else EXPECTED_PRINTED_LAST + 1
        group = units_by_start[u["start"]]
        pos = group.index(u)
        start_lines = page_lines[u["start"]]

        if u["kind"] == "faq":
            # FAQ 표제 검증: "FAQ" 줄 + 장번호 "5" 줄 실재 (헤딩 "N. 제목" 부재 — D1)
            has_faq = any(norm_title(ln) == "FAQ" for ln in start_lines)
            has_no5 = any(ln.strip() == "5" for ln in start_lines)
            if not has_faq or not has_no5:
                print(f"[fail-closed BLOCK] {u['id']}: p.{u['start']}에서 FAQ 장 표제 미발견 — JSON 미생성", file=sys.stderr)
                return 2
            begin = 0
        elif u["kind"] == "ref":
            has_label = any(ln.strip() == u["section_label"] for ln in start_lines)
            page_norm = norm_title("".join(start_lines))
            if not has_label or norm_title(u["section_title"]) not in page_norm:
                print(f"[fail-closed BLOCK] {u['id']}: p.{u['start']}에서 참고 표제 미발견 — JSON 미생성", file=sys.stderr)
                return 2
            begin = 0
        elif pos == 0 and u["first_of_chapter"]:
            begin = 0
            _idx, err = unique_heading_index(start_lines, u)
            if err:
                print(f"[fail-closed BLOCK] {err} — JSON 미생성", file=sys.stderr)
                return 2
        else:
            begin, err = unique_heading_index(start_lines, u)
            if err:
                print(f"[fail-closed BLOCK] {err} — JSON 미생성", file=sys.stderr)
                return 2

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

        # 이후 전체 쪽은 같은 쪽 그룹의 마지막 유닛만 소유 — ★본문쪽만(간지·blank 자동 제외·D8)
        if pos == len(group) - 1:
            for pp in range(u["start"] + 1, next_start):
                if pp in body_set:
                    pages.append({"printed_page": pp, "partial": False, "lines": page_lines[pp]})
        assembled.append({"unit": u, "pages": pages})

    # 6) 커버리지 검증: 본문 79쪽 전건 정확 귀속 + 분할쪽 줄 손실 0 (D3-②·③)
    covered = set()
    for a in assembled:
        for pg in a["pages"]:
            covered.add(pg["printed_page"])
    missing = [p for p in EXPECTED_BODY_PAGES if p not in covered]
    extra = sorted(covered - body_set)
    if missing or extra:
        print(f"[fail-closed BLOCK] 커버리지 누락 쪽: {missing} / 비본문 유입 쪽: {extra}", file=sys.stderr)
        return 2
    lines_by_page: dict[int, int] = {}
    for a in assembled:
        for pg in a["pages"]:
            lines_by_page[pg["printed_page"]] = lines_by_page.get(pg["printed_page"], 0) + len(pg["lines"])
    for pp in EXPECTED_BODY_PAGES:
        if lines_by_page.get(pp, 0) != len(page_lines[pp]):
            print(f"[fail-closed BLOCK] p.{pp} 줄 계수 불일치: 원본 {len(page_lines[pp])} vs 귀속 합 {lines_by_page.get(pp, 0)}", file=sys.stderr)
            return 2
    # 쪽별 헤더+마커 정확 2줄 제거 강제 (본문 79쪽 전건 헤더 1+마커 1 실측)
    bad_removed = {pp: audit["removed_by_page"].get(pp, 0) for pp in EXPECTED_BODY_PAGES
                   if audit["removed_by_page"].get(pp, 0) != 2}
    if bad_removed:
        print(f"[fail-closed BLOCK] 쪽별 헤더/마커 제거 수 이상(기대 쪽당 2): {bad_removed}", file=sys.stderr)
        return 2
    # 문서 제목 밴드 보존: 장 시작 본문쪽 5건 정확 일치 (D8 — 별권 2는 감사 기록만·b1은 fail-closed)
    band_pages = sorted({p for p, _y in audit["doc_title_band"]})
    if band_pages != sorted(EXPECTED_DOC_TITLE_BAND_PAGES):
        print(f"[fail-closed BLOCK] 문서 제목 밴드 보존 쪽 불일치: {band_pages} (기대 {sorted(EXPECTED_DOC_TITLE_BAND_PAGES)})", file=sys.stderr)
        return 2

    # 6.5) FAQ Q줄 검증 (D1): 각 정확 1회·문서 순서
    faq_unit = next(a for a in assembled if a["unit"]["kind"] == "faq")
    faq_lines_norm = [norm_title(ln) for pg in faq_unit["pages"] for ln in pg["lines"]]
    q_problems: list[str] = []
    q_positions: list[int] = []
    for q in EXPECTED_FAQ_QLINES:
        qn = norm_title(q)
        occ = [i for i, ln in enumerate(faq_lines_norm) if ln == qn]
        if len(occ) != 1:
            q_problems.append(f"{q!r}: 전체 줄 일치 {len(occ)}회(기대 정확 1회)")
        else:
            q_positions.append(occ[0])
    if q_problems:
        print(f"[fail-closed BLOCK] FAQ Q줄 검증 실패: {q_problems} — JSON 미생성", file=sys.stderr)
        return 2
    if q_positions != sorted(q_positions):
        print(f"[fail-closed BLOCK] FAQ Q줄 문서 순서 불일치: {q_positions}", file=sys.stderr)
        return 2
    all_ids = {a["unit"]["id"] for a in assembled}
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
        if u["kind"] == "faq":
            subsection_titles = list(EXPECTED_FAQ_QLINES)
        elif u["kind"] == "ref":
            toc_t = EXPECTED_REF_TOC_TITLES[u["section_no"]]
            if norm_title(toc_t) != norm_title(u["section_title"]):
                subsection_titles.append(toc_t)  # known-variant(참고1 목차 표기 — 검색 도달 보장)
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
            "image_only_pages": sorted(p["printed_page"] for p in pages_json if p["printed_page"] in image_only_pages),
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
        "source_title": "학생인건비통합관리 제도 매뉴얼",
        "series_title": "국가연구개발혁신법 매뉴얼",
        "series_part": "별권 1",
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
        "body_pages_printed": [1, EXPECTED_PRINTED_LAST],
        "excluded_note": (
            "표지·머리말·목차·장 표제 간지(인쇄 1·9·19·39·47)·빈 쪽(인쇄 2·8·10·20·38·40·48)·"
            "뒤표지 미수록 — 본문 마커 79쪽(인쇄 3~91) 전체 수록"
        ),
        "pymupdf_version": fitz.__version__ if hasattr(fitz, "__version__") else fitz.VersionBind,
        "extractor": "scripts/extract_manual_b1.py",
        "source_url": args.source_url,
        "id_format": "^b1-(\\d+-\\d+|ref-\\d+)$",
        "section_count": len(sections_json),
        "chapters": [
            {"no": c, "title": t, "page_start": p} for c, t, p in EXPECTED_CHAPTERS
        ],
    }
    payload = {"meta": meta, "sections": sections_json}

    # 8) 자체 정합성 검증 (fail-closed — assert는 -O 실행에서 제거되므로 명시적 검사)
    expected_units = len(EXPECTED_BODY_SECTIONS) + 1 + len(EXPECTED_REFS)
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
    got_unit_chars = {s["id"]: s["char_count"] for s in sections_json}
    if got_unit_chars != EXPECTED_UNIT_CHAR_COUNTS:
        diff = {k: (EXPECTED_UNIT_CHAR_COUNTS.get(k), got_unit_chars.get(k))
                for k in set(EXPECTED_UNIT_CHAR_COUNTS) | set(got_unit_chars)
                if EXPECTED_UNIT_CHAR_COUNTS.get(k) != got_unit_chars.get(k)}
        print(f"[fail-closed BLOCK] 유닛별 자수가 승인 스냅샷과 다름(경계 이동 의심): {diff}", file=sys.stderr)
        return 2
    total_chars = sum(s["char_count"] for s in sections_json)
    if total_chars != EXPECTED_TOTAL_CHARS:
        print(f"[fail-closed BLOCK] 총 자수 {total_chars:,} != 승인 스냅샷 {EXPECTED_TOTAL_CHARS:,} — JSON 미생성", file=sys.stderr)
        return 2
    notes_in_json = {
        s["id"]: s["table_structure_notes"] for s in sections_json if "table_structure_notes" in s
    }
    if notes_in_json != TABLE_STRUCTURE_NOTES:
        print("[fail-closed BLOCK] table_structure_notes 배선 불일치(상수 vs JSON) — JSON 미생성", file=sys.stderr)
        return 2

    # 원자적 쓰기(산출물 세트 단위) — 별권 2 P1 전례
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp_json = args.out_json.with_suffix(".json.tmp")
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    json_sha = sha256_of(tmp_json)

    # 9) 품질 리포트
    today = datetime.date.today().isoformat()
    special_chars = {}
    for ch in ("･", "ㆍ", "·", "｢", "｣", "￭", "•", "∙", "□", "⇓", "☞", "※"):
        cnt = sum(("\n".join(p["text"] for p in s["pages"])).count(ch) for s in sections_json)
        if cnt:
            special_chars[ch] = cnt

    rep = []
    rep.append("# 매뉴얼 별권 1 「학생인건비통합관리 제도 매뉴얼」 추출 품질 리포트 (R4-P1)\n")
    rep.append(f"- 실행일: {today} · PyMuPDF {meta['pymupdf_version']}")
    rep.append(f"- PDF: `{args.pdf.name}` · {doc.page_count}쪽 · sha256 `{pdf_sha[:20]}…` (승인 스냅샷 일치)")
    try:
        json_path_disp = args.out_json.relative_to(REPO_ROOT)
    except ValueError:
        json_path_disp = args.out_json
    rep.append(f"- JSON: `{json_path_disp}` · sha256 `{json_sha[:20]}…`")
    rep.append(
        f"- 목차 검증: PASS (장 {len(EXPECTED_CHAPTERS)}·절 {len(EXPECTED_TOC_SECTIONS)}·참고 {len(EXPECTED_REFS)}"
        f"·목차↔본문 제목 불일치 0건) · 오프셋 +{off} 균일·마커 79쪽 전건 홀짝 일치"
    )
    rep.append(
        f"- 96물리쪽 완전 분할: 선행 4쪽(표지·머리말·목차 2) ∪ 인쇄 1~{EXPECTED_PRINTED_LAST}"
        f"(본문 {len(EXPECTED_BODY_PAGES)} ∪ 간지 {len(EXPECTED_GANJI_TEXT)} ∪ blank {len(EXPECTED_BLANK_PAGES)}) ∪ 뒤표지 1 — 전건 검증 PASS"
    )
    rep.append(f"- 단위 {len(sections_json)}개 · 총 {total_chars:,}자 · 러닝헤더/마커 제거 {audit['removed']}줄")
    rep.append(f"- FAQ Q줄 검증: PASS ({len(EXPECTED_FAQ_QLINES)}건·각 정확 1회·문서 순서)")
    if table_flag_error:
        rep.append(f"- ⚠ 표 플래그 일부 실패(advisory): {table_flag_error}")
    rep.append("")

    rep.append("## 고시 표기 장부 (D7 — 원문 사실 고정)\n")
    rep.append("- 본문 내 고시 번호 표기(머리말 제외·머리말에 제2026-5호 1건 별도 실재):")
    for key in sorted(gosi_ledger):
        pages_disp = ", ".join(f"p.{p}×{c}" if c > 1 else f"p.{p}" for p, c in sorted(gosi_ledger[key].items()))
        rep.append(f"  - {key}: 총 {sum(gosi_ledger[key].values())}건 — {pages_disp}")
    rep.append(
        "- ★제2025-9호(인쇄 22) 1건은 원문 내부 불일치의 사실 기록(변조 아님 — 본권 구판 상호참조에 "
        "이은 KISTEP 미갱신 잔존 2례째). 후속 판에서 값이 바뀌면 판 교체 신호."
    )
    rep.append(
        "- ★제2026-0165호(인쇄 51)는 통합관리기관 지정 공고 번호(고시 아님)."
    )
    rep.append(
        "- ★제75조 구판 구조 인용(인쇄 32)은 쪽별 sha 동결로 고정 — 문면 변경 시 "
        "LAW_PRIORITY_EXTRA 2문장째(이자 처리 안내)를 제거하고 재추출할 것(수명 = 수록 판 연동)."
    )
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

    rep.append("## 결속 객체 사실 기재 (D4 — 렌더 대조 판정: 값 결속 정상·구조 정보 부재만 고지)\n")
    rep.append(
        "- 핵심 구체값 렌더 대조 PASS: 계상기준(월 1,300,000/2,200,000/3,000,000원·인쇄 13)·"
        "제91조의2 잔액 산식(× 0.2·인쇄 30)·체크리스트 항목↔내용 행 결속(인쇄 53) 전건 텍스트 보존."
    )
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
    rep.append(f"- 총 제거 {audit['removed']}줄(기대 {len(EXPECTED_BODY_PAGES) * 2}) · 쪽당 4줄 이상 이상치: {anomalies or '없음'}")
    if audit["kept_outside_region"]:
        rep.append("- 패턴 일치했으나 bbox 영역 밖이라 보존한 줄(과제거 방지 확인용):")
        for p, s, ypct in audit["kept_outside_region"]:
            rep.append(f"  - p.{p} (y {ypct}%): {s}")
    else:
        rep.append("- 패턴 일치·영역 밖 보존 줄: 없음")
    band = ", ".join(f"p.{p}(y {ypct}%)" for p, ypct in audit["doc_title_band"])
    rep.append(f"- 문서 제목 밴드 본문 보존(기대 5쪽 정확 일치 검증 PASS): {band}")
    rep.append("")

    rep.append("## 특수문자 인벤토리 (verbatim 보존 — 정규화하지 않음)\n")
    for ch, cnt in special_chars.items():
        rep.append(f"- U+{ord(ch):04X} {ch!r}: {cnt:,}회")
    rep.append("")

    tmp_rep = args.out_report.with_suffix(".md.tmp")
    with open(tmp_rep, "w", encoding="utf-8") as f:
        f.write("\n".join(rep))
    os.replace(tmp_json, args.out_json)
    os.replace(tmp_rep, args.out_report)

    print(f"[OK] JSON {args.out_json} ({args.out_json.stat().st_size:,} bytes, 단위 {len(sections_json)}개, {total_chars:,}자)")
    print(f"[OK] 리포트 {args.out_report}")
    doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
