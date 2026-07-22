"""v0.22.0 배포 전 LIVE acceptance spec — 「연구실안전법 family 3건 확대(52→55)」.

읽는 법(비프로그래머용): 이번 v0.22.0은 순수 data+prompt+test 확대(코드 로직 0줄)입니다.
Level A(자동)는 ① 신규 3건(연구실 안전환경 조성에 관한 법률·시행령·시행규칙)이 검색 fan-out에서
실제 LIVE 도달하는지 ② 시행령 별표가 예상대로 본문 전문 tier-1로 반환되는지 ③ 기존 경로가
무회귀인지(검색 recall·oversized 기본 경로)를 확인합니다. N 52→55 확대 후의 cold fan-out
지연도 latency_under로 함께 관측합니다(WARN — 차단 안 함). 소비 품질(연구실 안전 질의를
호스트가 도구 근거로 검토하는지)은 Level B라 배포 후 라이브 커넥터에서 사람이 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★별표 tier·amendment_kind 관련 항목은 전부 WARN 클래스 — 별표가 개정으로 커지면 tier-1이
  oversized_pointer로 바뀌고 amendment_kind는 LIVE 개정에 따라 변하는 것이 정상 거동이라
  hard-BLOCK 부적합(false-block-safe·Andy 최우선 끊김없음). BLOCK 후보는 도달·검색 무회귀에만.
"""

CHECKS = [
    {
        "name": "신규 A — 연구실안전법 family 3건 검색 fan-out LIVE 도달('연구실 안전' — N=55 첫 실측)",
        "tool": "search_provision",
        "args": {"query": "연구실 안전"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "lab_safety_act"},
            {"kind": "fetched_ok", "rule_set_id": "lab_safety_decree"},
            {"kind": "fetched_ok", "rule_set_id": "lab_safety_rule"},
            {"kind": "returned_not_below", "value": 5},                                   # 신규 family 본문 매치 하한
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN — graceful skip 0
            {"kind": "latency_under", "value": 16.0},                                     # WARN — N=55 cold 예산 내
        ],
    },
    {
        "name": "신규 B — 시행령 문서레벨 도달 + amendment 부착(law:286181 amendment_kind=일부개정·LIVE 2026-07-22)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:286181"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — LIVE 개정 시 변동 정상
        ],
    },
    {
        "name": "신규 C — 시행령 별표 1 본문 전문 tier-1(law:286181:BP0001 — LIVE 11,590자<예산·oversized 0)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:286181:BP0001"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — BP 채번 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — tier-1 전문
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": True},    # WARN — 인용 허용
        ],
    },
    {
        "name": "신규 D — 법률 문서레벨 도달(law:283355 amendment_kind=일부개정·조문 46 corpus 진입)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283355"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN
        ],
    },
    {
        "name": "무회귀 A — oversized 별표 기본 경로 무변(law:285767:BP0002 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},   # WARN — 포인터 인용 금지 유지
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(N=55 확대가 기존 검색 경로 무해)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                  # 실측 ~16-17·하한 10 상회
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.22.0 = 연구실 안전 트랙 신설이 개선 그 자체.
LEVEL_B_PROMPTS = [
    {
        "category": "★개선 — 연구실 안전 질의 grounded(신규 트랙 end-to-end)",
        "probe_prompt": "대학 연구실의 연구활동종사자가 받아야 하는 안전교육 시간이 어떻게 되는지 규정 근거와 함께 알려줘",
        "expect_behavior": "종전에는 미지원(외부 웹 폴백·stale 위험)이던 질의 — 호스트가 연구실안전법 시행령·시행규칙"
                           "(교육시간 별표 tier-1 전문)을 도구로 조회해 근거 조문·별표를 인용하는지 + 날조 0 + "
                           "도구 응답에 없는 수치를 임의 단정하지 않는지.",
    },
    {
        "category": "★개선 — 연구실 사고 보고 절차(법·령 조문 라우팅)",
        "probe_prompt": "연구실에서 사고가 발생했을 때 보고 절차와 기한이 어떻게 되는지 규정 검토해줘",
        "expect_behavior": "연구실안전법(법률)·시행령·시행규칙을 위계 순서로 조회(cross-check 라우팅 실효)하고 "
                           "보고 주체·기한을 조문 근거로 답하는지 — 미확인 값은 확인 불가 표시.",
    },
    {
        "category": "무회귀 — 기존 locate 라우팅·기존 지시와의 상호 간섭 없음",
        "probe_prompt": "산업기술혁신사업 기술개발 평가관리지침 별표들에 RCMS라는 용어가 나오는지 확인해줘.",
        "expect_behavior": "N=55 확대 후에도 annex_locate 우선 라우팅(청크 전수 순회 없이 1~3호출)·전문 스캔 근거·"
                           "스캔 한계 고지(줄 단위·HWP 범위 밖)가 유지되는지(기존 지시 희석 없음).",
    },
]
