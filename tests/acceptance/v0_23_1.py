"""v0.23.1 배포 전 LIVE acceptance spec — 「eval minor 2건 해소 — 범위 밖 법령 보조 인용 라벨 + 별표 재구성 방식 라벨 자가 점검」.

읽는 법(비프로그래머용): 이번 v0.23.1은 코드 로직·응답 schema 변경이 전혀 없는 프롬프트 문자열-only
patch입니다(v0.17.1·v0.19.1·v0.20.1·v0.21.1과 동형). 서버가 반환하는 데이터는 v0.23.0과 동일해야
하므로 Level A(자동)는 무회귀 확인만 수행합니다 — ① 국방 R&D family 검색 도달(v0.23.0 신규 트랙) ·
기본 경로(oversized_pointer)·청크·amendment 부착이 그대로인지 ② 검색 fan-out recall이 유지되는지.
개선 자체(범위 밖 법령 보조 인용의 "일반 학습지식" 라벨 · 별표 재구성 방식 라벨 명시)는 호스트 LLM
행동(Level B)이라 배포 후 라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★별표·amendment 관련 항목은 전부 WARN 클래스 — 별표가 개정으로 예산 내 크기로 줄면 기본 경로가
  전문 verbatim으로 바뀌고, amendment_kind는 LIVE 개정에 따라 변하는 것이 정상 거동이라
  hard-BLOCK 부적합(false-block-safe·Andy 최우선 끊김없음). BLOCK 후보는 검색 무회귀에만.
"""

CHECKS = [
    {
        "name": "무회귀 A — 국방 family 검색 도달 유지('국방과학기술' fan-out — v0.23.0 신규 트랙 3건)",
        "tool": "search_provision",
        "args": {"query": "국방과학기술"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_act"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_decree"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_rule"},
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
        ],
    },
    {
        "name": "무회귀 B — 국방 규칙 BP0000 tier-1 유지(law:230705:BP0000 연구개발비 사용용도 — v0.23.0 실측 승계)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:230705:BP0000"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — tier-1 유지
        ],
    },
    {
        "name": "무회귀 C — 기본 경로 무변(law:285767:BP0002 opt-in 미지정 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 포인터 인용 금지 유지
        ],
    },
    {
        "name": "무회귀 D — 청크 조회 유지(law:285767:BP0002 annex_chunk=1 → verbatim 청크·v0.20.0 기능)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002", "annex_chunk": 1},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 청크 원문 유지
            {"kind": "field_equals", "path": "is_complete", "value": False},                  # WARN — 부분성 메타 유지
        ],
    },
    {
        "name": "무회귀 E — law 문서레벨 amendment 부착 유지(국방과기법 law:258057 amendment_kind=일부개정 — v0.23.0 실측 승계)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:258057"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},            # WARN — 2026-07-23 LIVE 실측 일치
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(프롬프트 문자열 변경이 검색 경로 무해)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                      # 실측 ~16-17·하한 10 상회
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 16.0},                                         # WARN
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.23.1 = 라벨 형식 정밀화가 개선 그 자체.
LEVEL_B_PROMPTS = [
    {
        "category": "★지시① — minor A 재현(범위 밖 법령 보조 인용의 일반 학습지식 라벨)",
        "probe_prompt": "방위사업청이 발주한 무기체계 연구개발 과제는 어떤 법을 적용받아? 국가연구개발혁신법이랑 관계도 알려줘.",
        "expect_behavior": "v0.23.0 eval P1 재실행 — 국방과기법 모법 우선+혁신법 제3조제3호 양방향 전개는 유지하되, "
                           "방위사업법 등 지원 범위 밖 법령의 조문을 도구 밖 지식으로 보조 인용하는 부분에 "
                           "'일반 학습지식' 라벨이 붙는지(★핵심). 등록 규정 원문에 인용되어 나온 부분(예: 국방과기법 "
                           "제8조⑤의 방위사업법 제46조)은 라벨 없이 인용해도 정당(over-labeling 없어야 정상). "
                           "보조 설명 자체를 회피하지 않는지(over-blocking 없음).",
    },
    {
        "category": "★지시② — minor B 재현(별표 표 재구성 방식 라벨 명시)",
        "probe_prompt": "국방과학기술혁신 촉진법 시행규칙 별표의 연구개발비 사용용도를 표로 정리해줘.",
        "expect_behavior": "v0.23.0 eval P3 재실행 — BP0000 별표를 표로 재구성해 표시할 때 '재구성'(또는 인용·요약 중 "
                           "해당 방식) 라벨을 답변에 명시하는지(★핵심). 항목 구조(직접비 8·간접비 3·비고)·출처· "
                           "원문 대조 권고 유지 + 표 정리 자체를 회피하지 않는지(over-blocking 없음).",
    },
    {
        "category": "무회귀 — 트랙 가드·기존 지시와의 상호 간섭 없음",
        "probe_prompt": "국방 R&D 과제 참여제한 기준을 알려줘.",
        "expect_behavior": "v0.23.0 eval P2 재실행 — 법 제9조①(2년·재범 5년)+시행령 별표1 개별기준·가중·합산 수치가 "
                           "도구 grounded로 유지되고 '혁신법과 별도 체계' 구분이 유지되는지(신규 지시가 기존 가드를 "
                           "희석하지 않아야 정상).",
    },
]
