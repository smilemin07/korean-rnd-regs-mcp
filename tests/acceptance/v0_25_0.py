"""v0.25.0 배포 전 LIVE acceptance spec — 「국방 트랙 3차 확대(60→63) — 미래도전 지침·시설장비 규정·표준협약서 등록」.

읽는 법(비프로그래머용): 이번 v0.25.0은 rule_sets.yaml 데이터 3건 추가 + 프롬프트 라우팅 문자열이며
코드 알고리즘·응답 schema·캐시 상수 변경이 없습니다(순수 data 확대 13번째·캐시 96은 N=63에서
headroom 33). Level A(자동)는 ① 신규 3건이 LIVE에서 실제 도달·조회되는지(정확 제목 resolve —
축약명 함정 2건 검증 겸함) ② 시설장비 규정의 대용량 별표 8이 oversized_pointer로 정직 안내되고
annex_chunk로 전문 조회되는지 ③ 기존 경로가 그대로인지(무회귀) ④ N=63 cold fan-out이 예산 내인지
확인합니다. 소비 품질(미래도전 절차 질의·협약 조문 grounded·별지 정직 고지)은 호스트 LLM 행동
(Level B)이라 배포 후 라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★별표·amendment 관련 항목은 전부 WARN 클래스 — 별표 크기·제개정구분은 LIVE 개정에 따라 변하는
  것이 정상 거동이라 hard-BLOCK 부적합(false-block-safe·Andy 최우선 끊김없음). BLOCK 후보는
  검색 도달·recall에만. ★미래도전 지침의 별표 4건은 활성 2+삭제 2로 개별 BP 번호의 활성 여부가
  LIVE 종속이라 특정 BP 단정 체크는 두지 않음(문서레벨 도달로 갈음).
"""

CHECKS = [
    {
        "name": "신규 A — 국방 8건 fan-out 도달('국방과학기술' — N=63 첫 cold fan-out·신규 3건 포함 전건 무오류)",
        "tool": "search_provision",
        "args": {"query": "국방과학기술"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_act"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_decree"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_rule"},
            {"kind": "fetched_ok", "rule_set_id": "defense_rnd_guideline"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_fee_notice"},
            {"kind": "fetched_ok", "rule_set_id": "defense_future_challenge_guideline"},  # ★v0.25.0 신규
            {"kind": "fetched_ok", "rule_set_id": "defense_facility_equipment"},          # ★v0.25.0 신규
            {"kind": "fetched_ok", "rule_set_id": "defense_standard_agreement"},          # ★v0.25.0 신규
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 18.0},                                         # WARN — cold N=63(v0.24.1 실측 6.04s@60)
        ],
    },
    {
        "name": "신규 B — 미래도전 지침 문서레벨 도달+amendment_kind(admrul:2100000274618 — 정식 제목 '연구개발' 포함 resolve·일부개정)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000274618"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 정확 제목 resolve 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},            # WARN — 2026-07-24 프로브 실측
        ],
    },
    {
        "name": "신규 C — 시설장비 규정 대용량 별표 8 포인터 정직(admrul:2100000274594:BP0008 — escaped 16,695>15,700)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000274594:BP0008"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — U+00B7 제목 resolve+별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 본문 미수록 정직 안내
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 포인터 인용 금지
        ],
    },
    {
        "name": "신규 D — 시설장비 규정 별표 8 청크 조회(annex_chunk=1 → verbatim 청크 — 신규 규정에서 청크 경로 실효)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000274594:BP0008", "annex_chunk": 1},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 청크 원문 반환
            {"kind": "field_equals", "path": "is_complete", "value": False},                  # WARN — 부분성 메타
            {"kind": "field_equals", "path": "chunk_index", "value": 1},                      # WARN — 요청 청크 번호 일치
        ],
    },
    {
        "name": "신규 E — 표준협약서 문서레벨 도달+amendment_kind(admrul:2100000272176 — 별표 0=article·별지 5건 BP 미노출)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000272176"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 정확 제목 resolve 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},            # WARN — 프로브 실측(2026-01-02)
        ],
    },
    {
        "name": "무회귀 A — 기본 경로 무변(law:285767:BP0002 opt-in 미지정 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 포인터 인용 금지 유지
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(N=63이 검색 경로 무해)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                      # 실측 ~16-17·하한 10 상회
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 16.0},                                         # WARN — warm 경로
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.25.0 = 신규 3건 소비 품질 + 국방 트랙 가드 무회귀.
LEVEL_B_PROMPTS = [
    {
        "category": "★신규 — 미래도전 지침 소비(미래도전국방기술 실무 절차 grounded + 자매 지침 구분)",
        "probe_prompt": "미래도전국방기술 연구개발사업은 어떤 절차로 진행돼? 근거 규정 조문과 함께 알려줘.",
        "expect_behavior": "미래도전국방기술 연구개발 업무처리지침(예규 제1040호)이 검색·상세 조회로 grounded되는지"
                           "(★핵심 — v0.24.0까지는 미지원이라 기등록 국방기술 업무처리지침으로 대답이 쏠렸음). "
                           "기등록 국방기술 연구개발 업무처리지침(예규 1045)과 혼동 없이 별개 문서로 구분·인용하는지. "
                           "지침 조문 번호·원문 인용이 도구 응답 기반인지(외부 웹 폴백 없음).",
    },
    {
        "category": "★신규 — 시설장비 규정 소비(대용량 별표 8 청크 경로 + 병존 규정 구분)",
        "probe_prompt": "국방연구개발 과제에서 연구시설·장비는 어떻게 등록·관리해야 해? 등록할 때 필요한 정보 항목도 구체적으로 알려줘.",
        "expect_behavior": "국방연구개발 시설·장비의 관리 등에 관한 규정(훈령 제945호)이 grounded되는지(★핵심). "
                           "등록 정보항목(별표 8)은 oversized라 포인터 응답 시 chunk_count를 확인해 annex_chunk로 "
                           "재호출하여 원문 확인하는지·확인 못한 부분은 확인 불가로 표시하는지. 과기정통부 시설·장비 "
                           "표준지침(범부처)과 부처·적용범위 구분이 유지되는지.",
    },
    {
        "category": "★신규 — 표준협약서 소비(협약 조문 grounded + 별지 정직 고지)",
        "probe_prompt": "무기체계 연구개발 협약을 체결할 때 표준협약서상 협약 당사자의 의무와 지식재산권 귀속은 어떻게 정해져 있어?",
        "expect_behavior": "무기체계 연구개발 표준협약서(예규 제1019호)가 grounded되는지(★핵심). 조문 45개 본문 기반으로 "
                           "인용하는지. 부속 별지 5건은 BP 미노출인데 별지 서식 내용을 본문으로 날조하지 않고 미수록을 "
                           "정직 고지하는지. 국방과기법 제8조(협약·계약 원칙)와의 위계 연결이 정확한지.",
    },
]
