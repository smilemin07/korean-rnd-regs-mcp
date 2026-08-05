"""v0.35.0 배포 전 LIVE acceptance spec — 「R4: 매뉴얼 별권 1 학생인건비통합관리 제도 매뉴얼 수록」.

읽는 법(비프로그래머용): 이번 v0.35.0은 혁신법 매뉴얼 별권 1(96물리쪽·26단위·76,353자)을
기존 매뉴얼 도구 2종에 통합 수록합니다(새 도구 없음·7종 유지·입력 스키마 무변 → 웹 커넥터
재연결 불요·기존 매뉴얼 데이터 3종 byte 불변). Level A(자동)는 규정 트랙·기존 소스 무회귀와
별권 1 신규 표면(조회·청크·structure_notice·검색 도달)을 결정론으로 확인합니다. 개선의 핵심
(호스트가 별권 1 해설을 실제로 활용하고 구판 제75조 안내를 판단에 반영하는가)은 Level B로
배포 후 사람이 확인합니다.

★수동 NO-GO 규칙(v0.33.0 규약 유지): 아래 field_equals는 전부 로컬 결정론 데이터 검증이라
러너에서는 WARN이지만, 매뉴얼 응답(check 3~8)의 field_equals 불일치는 infra 변동이 아니라
코드 회귀이므로 사람 판정에서 BLOCK으로 취급할 것.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN·매뉴얼 check는 사람 판정 BLOCK]
"""

_LAW_LINE = "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 관련 규정 원문을 기준으로 해주시기 바랍니다."
_MANUAL_SOURCE_LINE = (
    "※ 「국가연구개발혁신법 매뉴얼」 등 연구행정 관련 매뉴얼 원문은 "
    "KISTEP 홈페이지(www.kistep.re.kr)에서 확인하시기 바랍니다."
)
_PROVISION_FOOTER = _LAW_LINE + "\n" + _MANUAL_SOURCE_LINE

# structure_notice 기대값(결정론 조립 — manual.py 상수·데이터 note 원문과 동기)
_SN_HEADER = "※ 표·산식 구조 안내(추출 한계):"
_SN_CHUNK_LINE = "- 위 안내는 절 전체 기준이며, 이 청크에 해당 표·산식·도식이 포함되었다는 뜻은 아닙니다."
# 무회귀 신호 — 별권 2 기존 블록(v0.34.0 도입분·글자 단위 불변이어야 함)
_B2_3_2_NOTE = (
    "이 절의 정부납부기술료 기준표는 '분류' 열(제3자 실시/직접 실시)이 세로 병합 셀이라 "
    "추출 텍스트에서 각 그룹 첫 위치에 한 번만 나타나며, 어느 행까지 적용되는지는 직렬화 순서로만 "
    "구분됩니다. 행별 귀속은 표기된 인쇄쪽 원문 또는 시행령 제38조·제39조 원문으로 확인하십시오."
)
_B2_3_2_NOTICE_BLOCK = _SN_HEADER + "\n- " + _B2_3_2_NOTE
# ★신규 — 별권 1 b1-3-4(지급액 책정 및 지급) 전문 부착 블록
_B1_3_4_NOTE = (
    "이 절의 <표 3-1> 지급체계(인쇄 26쪽)의 계정별 지급 구성 막대는 이미지라 추출 텍스트에 "
    "없고, <표 3-2> 지급 개념도(인쇄 27쪽)의 과제→계정→학생연구자 열 대응도 도형 배치로만 "
    "표현됩니다. 지급 구성·흐름은 표기된 인쇄쪽 원문으로 확인하십시오."
)
_B1_3_4_NOTICE_BLOCK = _SN_HEADER + "\n- " + _B1_3_4_NOTE
# ★신규 — 별권 1 b1-ref-3(점검 자료집) 청크 부착 블록(절 전체 기준 주의 줄 포함)
_B1_REF3_NOTE_1 = (
    "이 참고의 점검 체크리스트 표는 '가/부' 판정란(빈 체크박스)이 추출 텍스트에서 항목 사이의 "
    "□ 기호로만 나타나 열 귀속 정보가 없습니다(판정란은 빈 칸이라 값 손실은 아님). 표 구조는 "
    "표기된 인쇄쪽 원문으로 확인하십시오."
)
_B1_REF3_NOTE_2 = (
    "이 참고의 <전산시스템 구축 예시> 화면들은 이미지로만 실려 있어 화면 안의 항목·값이 추출 "
    "텍스트에 없습니다. 구축 예시 상세는 표기된 인쇄쪽 원문으로 확인하십시오."
)
_B1_REF3_NOTICE_CHUNK_BLOCK = (
    _SN_HEADER + "\n- " + _B1_REF3_NOTE_1 + "\n- " + _B1_REF3_NOTE_2 + "\n" + _SN_CHUNK_LINE
)

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(규정 트랙 완전 무변 확인)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                      # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 16.0},                                         # WARN
        ],
    },
    {
        "name": "무회귀 — 규정 상세 footer 2줄(별권 1 수록의 규정 트랙 무영향)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _PROVISION_FOOTER},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 별권 2 b2-3-2 structure_notice 글자 단위 불변(기존 소스 보존 신호)",
        "tool": "get_manual_section",
        "args": {"section_id": "b2-3-2"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "structure_notice", "value": _B2_3_2_NOTICE_BLOCK},  # WARN
        ],
    },
    {
        "name": "★신규 A — b1-3-6(이자 처리) 조회: citation 정확값 + 전문 tier(제75조 안내는 law_priority_note 동반)",
        "tool": "get_manual_section",
        "args": {"section_id": "b1-3-6"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「학생인건비통합관리 제도 매뉴얼」(26.7판) 제3장 6. 학생인건비 이자 처리, 인쇄 p.32"},  # WARN — 신규
            {"kind": "field_equals", "path": "structure_notice", "value": "<missing>"},        # WARN — notes 없는 절 미부착
        ],
    },
    {
        "name": "★신규 B — b1-3-4(지급액 책정) structure_notice 완성형 정확값",
        "tool": "get_manual_section",
        "args": {"section_id": "b1-3-4"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "structure_notice", "value": _B1_3_4_NOTICE_BLOCK},  # WARN — 신규
        ],
    },
    {
        "name": "★신규 C-1 — b1-ref-3(점검 자료집) 포인터: chunk_count 3·structure_notice 미부착(본문 미전달)",
        "tool": "get_manual_section",
        "args": {"section_id": "b1-ref-3"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 신규
            {"kind": "field_equals", "path": "chunk_count", "value": 3},                       # WARN — 신규
            {"kind": "field_equals", "path": "structure_notice", "value": "<missing>"},        # WARN
        ],
    },
    {
        "name": "★신규 C-2 — b1-ref-3 청크 2: structure_notice 완성형 정확값(절 전체 기준 주의 줄 포함)",
        "tool": "get_manual_section",
        "args": {"section_id": "b1-ref-3", "chunk": 2},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "structure_notice", "value": _B1_REF3_NOTICE_CHUNK_BLOCK},  # WARN — 신규
            {"kind": "field_equals", "path": "is_complete", "value": False},                   # WARN
        ],
    },
    {
        "name": "★신규 D — 병합 검색('학생인건비 계상기준 설정'): b1 최상위 도달 + 본권 필수 절 생존",
        "tool": "search_manual",
        "args": {"query": "학생인건비 계상기준 설정"},
        "asserts": [
            {"kind": "field_equals", "path": "matches.0.section_id", "value": "b1-2-3"},       # WARN — 신규
            {"kind": "field_equals", "path": "matches.0.source", "value": "b1"},               # WARN — 신규
            {"kind": "field_equals", "path": "matches.1.section_id", "value": "3-4"},          # WARN — 본권 생존
            {"kind": "field_equals", "path": "matches.1.source", "value": "main"},             # WARN
        ],
    },
    {
        "name": "무회귀 — 3소스 혼합 검색('기술료') 정렬·계측 불변(b1은 cap 밖 body 1건뿐)",
        "tool": "search_manual",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "field_equals", "path": "matches.0.section_id", "value": "2-6"},          # WARN
            {"kind": "field_equals", "path": "matches.0.source", "value": "main"},             # WARN
            {"kind": "field_equals", "path": "returned_by_source.b2", "value": 8},             # WARN
            {"kind": "field_equals", "path": "returned_by_source.b1", "value": 0},             # WARN — 신규(희석 0 신호)
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.35.0 = 별권 1 해설의 실사용 + 구판 제75조
# 안내(law_priority_extra 사실 문장 — v0.33.0 별권 2 구판 용어 패턴의 3번째 적용)의 실효 확인.
# R4-P0 소비 항목 1(제75조 표적 프로브)을 반드시 포함할 것.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 제75조 이자 처리(P0 국소 위험 1건·구판 안내 실효 확인 — 필수 프로브)",
        "probe_prompt": "대학이 학생인건비통합관리 전용계좌에서 발생한 이자를 학생인건비로 쓸 수 있는지, "
                        "현행 규정 기준으로 근거와 함께 알려줘.",
        "expect_behavior": "b1-3-6(이자 처리) 도달 + law_priority_extra의 구판 안내가 판단에 반영되는지 — "
                           "매뉴얼 서술(구판 제1항제4호 선택형)을 그대로 단정하지 않고 현행 제75조(원칙 국고 납입·"
                           "계정 산입은 제2항제1호·중앙행정기관 승인 요건)를 규정 트랙으로 교차 확인하거나 구판 기준 "
                           "서술임을 밝히는지. v0.33.0 별권 2 구판 용어 안내가 eval 2/2 실효한 패턴의 재사용 검증.",
    },
    {
        "category": "★표적 — 계상기준 구체값(석사 월 220만 원) + 규정 트랙 교차 확인",
        "probe_prompt": "석사과정 학생연구자의 학생인건비 계상기준이 월 얼마인지, 대학이 그보다 낮게 "
                        "정할 수 있는지 알려줘.",
        "expect_behavior": "b1-2-3(계상기준 설정) 또는 규정 트랙(제40조·제49조 준용) 도달 — 석사 월 2,200,000원 "
                           "이상·기관 자율 책정(기준 금액 이상)·학과별 별도 기준 불가를 정확 인용. 매뉴얼 트랙 사용 시 "
                           "citation 인쇄쪽 표기와 footer 4줄 표시 여부 관찰(값 자체는 매뉴얼·현행 고시 일치 실측 완료).",
    },
    {
        "category": "★표적 — 지정 현황 다열 표: structure_notice 표시 + 관리유형 단정 회피",
        "probe_prompt": "서강대학교가 학생인건비통합관리기관으로 지정되어 있는지, 지정되어 있다면 "
                        "연구책임자단위인지 연구개발기관단위인지 알려줘.",
        "expect_behavior": "b1-ref-1(지정 현황·2026년 3월 기준) 도달 — 다열 표 직렬화로 관리유형 열 귀속이 텍스트에 "
                           "없다는 structure_notice를 표시하고, 유형을 단정하지 않거나 원문·공고(제2026-0165호) 확인을 "
                           "안내하는지(과대 단정 = 실패 신호). 기준 시점(2026년 3월·이후 지정 건 별도) 고지 여부도 관찰.",
    },
]
