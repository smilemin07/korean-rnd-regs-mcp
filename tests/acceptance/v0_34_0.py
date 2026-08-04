"""v0.34.0 배포 전 LIVE acceptance spec — 「구조 안내 완성형 승격 + 오류 self-echo 마스킹」.

읽는 법(비프로그래머용): 이번 v0.34.0은 v0.33.0 배포 후 확인된 응답 안전성 결함 2건의 최소
보강입니다. ①표·산식 구조 손실 안내를 warnings 배열에서 완성형 블록(structure_notice)으로
승격(구조 손실 확인 4절 한정·본문 전달 응답 전용) ②오류 self-echo 마스킹 3경로. 새 도구
없음(7종 유지)·입력 스키마 무변 → 웹 커넥터 재연결 불요. 매뉴얼 데이터 3종 byte 불변.
Level A(자동)는 규정 트랙·본권·별권 무회귀와 structure_notice 부착/미부착 분기를 결정론으로
확인합니다. 마스킹 3경로는 LIVE 러너 대상이 아니라 pytest(test_structure_notice.py)에서
잠급니다(오류 유도 입력은 러너 assert 5종 범위 밖). 개선의 핵심(호스트가 structure_notice를
답변에 실제로 표시하는가)은 Level B로 배포 후 사람이 확인합니다.

★수동 NO-GO 규칙(v0.33.0 규약 유지): 아래 field_equals는 전부 로컬 결정론 데이터 검증이라
러너에서는 WARN이지만, 매뉴얼 응답(check 3~7)의 field_equals 불일치는 infra 변동이 아니라
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
_MAIN_NOTICE = "인용 매뉴얼: 26.7판 · 법령 시행일 2026-06 기준"

# structure_notice 기대값(결정론 조립 — manual.py 상수·데이터 note 원문과 동기)
_SN_HEADER = "※ 표·산식 구조 안내(추출 한계):"
_SN_CHUNK_LINE = "- 위 안내는 절 전체 기준이며, 이 청크에 해당 표·산식·도식이 포함되었다는 뜻은 아닙니다."
_B2_3_2_NOTE = (
    "이 절의 정부납부기술료 기준표는 '분류' 열(제3자 실시/직접 실시)이 세로 병합 셀이라 "
    "추출 텍스트에서 각 그룹 첫 위치에 한 번만 나타나며, 어느 행까지 적용되는지는 직렬화 순서로만 "
    "구분됩니다. 행별 귀속은 표기된 인쇄쪽 원문 또는 시행령 제38조·제39조 원문으로 확인하십시오."
)
_B2_3_2_NOTICE_BLOCK = _SN_HEADER + "\n- " + _B2_3_2_NOTE
_B3_4_2_NOTE_1 = (
    "이 절의 처분 기준표 중 세로 병합 셀(예: 감경·가중 '2분의 1의 범위')은 추출 텍스트에서 "
    "첫 행 그룹에만 나타나며 병합 범위(어느 행까지 적용되는지) 정보가 소실되어 있습니다. "
    "행별 적용 여부는 표기된 인쇄쪽 원문 또는 시행령 별표 6·별표 7 원문으로 확인하십시오."
)
_B3_4_2_NOTE_2 = (
    "각 기준표 하단의 감경요소/가중요소 예시표(2열 목록)는 열 단위로 직렬화되어 두 목록의 "
    "경계 구분이 텍스트에 없습니다. 어느 항목이 감경/가중인지는 인쇄쪽 원문으로 확인하십시오."
)
_B3_4_2_NOTICE_CHUNK_BLOCK = (
    _SN_HEADER + "\n- " + _B3_4_2_NOTE_1 + "\n- " + _B3_4_2_NOTE_2 + "\n" + _SN_CHUNK_LINE
)
_SN_NOTE = (
    "위 structure_notice는 이 절의 표·산식·도식 구조가 추출 텍스트에 보존되지 않은 부분에 대한 "
    "완성형 안내입니다. 이 절의 수치·산식·표 내용을 답변에 인용했다면 이 블록을 답변에 그대로"
    "(요약·윤문 없이) 1회 표시하십시오. 같은 내용이 warnings에도 있으니 warnings 쪽을 중복 "
    "표시하지 마십시오."
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
        "name": "무회귀 — 규정 상세 footer 2줄 + 소형 조문 형태(마스킹 변경의 정상 경로 무영향)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _PROVISION_FOOTER},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 본권 절 문면·notes 없는 절 structure_notice 미부착(기존 응답 불변)",
        "tool": "get_manual_section",
        "args": {"section_id": "3-13"},
        "asserts": [
            {"kind": "field_equals", "path": "manual_meta.notice", "value": _MAIN_NOTICE},     # WARN
            {"kind": "field_equals", "path": "structure_notice", "value": "<missing>"},        # WARN — 신규(미부착 잠금)
            {"kind": "field_equals", "path": "structure_notice_note", "value": "<missing>"},   # WARN — 신규
        ],
    },
    {
        "name": "★신규 A — b2-3-2(요율표 절) structure_notice 완성형 정확값 + 인접 지시",
        "tool": "get_manual_section",
        "args": {"section_id": "b2-3-2"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "structure_notice", "value": _B2_3_2_NOTICE_BLOCK},  # WARN — 신규
            {"kind": "field_equals", "path": "structure_notice_note", "value": _SN_NOTE},      # WARN — 신규
        ],
    },
    {
        "name": "★신규 B — b3-4-2 청크 1: structure_notice 완성형 정확값(절 전체 기준 주의 줄 포함)",
        "tool": "get_manual_section",
        "args": {"section_id": "b3-4-2", "chunk": 1},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "structure_notice", "value": _B3_4_2_NOTICE_CHUNK_BLOCK},  # WARN — 신규
            {"kind": "field_equals", "path": "structure_notice_note", "value": _SN_NOTE},      # WARN — 신규(부착 신호)
            {"kind": "field_equals", "path": "is_complete", "value": False},                   # WARN
        ],
    },
    {
        "name": "★신규 C — b3-4-2 포인터(본문 미전달): structure_notice 미부착",
        "tool": "get_manual_section",
        "args": {"section_id": "b3-4-2"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN
            {"kind": "field_equals", "path": "structure_notice", "value": "<missing>"},        # WARN — 신규
        ],
    },
    {
        "name": "무회귀 — 3소스 혼합 검색('기술료') 정렬·계측 불변(structure_notice는 검색 미표면)",
        "tool": "search_manual",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "field_equals", "path": "matches.0.section_id", "value": "2-6"},          # WARN
            {"kind": "field_equals", "path": "matches.0.source", "value": "main"},             # WARN
            {"kind": "field_equals", "path": "returned_by_source.b2", "value": 8},             # WARN
            {"kind": "field_equals", "path": "structure_notice", "value": "<missing>"},        # WARN — 검색 미표면 유지
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.34.0 = structure_notice가 호스트 답변에
# 실제로 표시되는가(v0.33.0 eval의 미소비 관측에 대한 개선 실측). 미소비 재관측 시에도
# 서비스·정확도 회귀가 없으면 롤백 사유 아님 — 효과 없음으로 기록하고 추가 churn 중단(계획 /disc 합의).
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 부록 분수식: structure_notice 표시 여부(v0.33.0 프로브 ③ 재사용·직접 대조)",
        "probe_prompt": "제품 단위 매출액을 산정하기 어려울 때 기술기여도를 어떻게 계산하는지 산식을 정확히 알려줘.",
        "expect_behavior": "별권 2 부록(b2-ref-1)에 도달하고, 이번에 신설된 structure_notice(분수식 분자·분모 관계 "
                           "소실·인쇄 12쪽 열 귀속) 블록을 답변에 그대로 표시하는지 — v0.33.0에서는 같은 내용이 "
                           "warnings에만 있어 0/1 미표시였음(직접 대조 축). 산식 값 자체의 정확성도 함께 확인.",
    },
    {
        "category": "★표적 — 요율표 병합 셀: structure_notice 표시 + 행 귀속 정확성",
        "probe_prompt": "중견기업이 연구개발성과를 직접 실시해서 수익이 났을 때 정부납부기술료를 얼마나 내야 하는지, "
                        "근거와 함께 알려줘.",
        "expect_behavior": "b2-3-2(직접 실시·중견 5%·상한 정부지원연구개발비의 20%) 도달 + structure_notice(분류 "
                           "병합 셀 행 귀속) 블록 표시 여부 + 시행령 제38조·제39조 교차 확인(v0.33.0 프로브 ① 대조). "
                           "표시 위치가 표·수치 인용 부근 또는 답변 하단 1회인지도 관찰.",
    },
]
