"""v0.21.1 배포 전 LIVE acceptance spec — 「근거 법률 인용 원문 단위 보존 프롬프트 정밀화」.

읽는 법(비프로그래머용): 이번 v0.21.1은 코드 로직·응답 schema 변경이 전혀 없는 프롬프트 문자열-only
patch입니다(v0.17.1·v0.19.1·v0.20.1과 동형). 서버가 반환하는 데이터는 v0.21.0과 동일해야 하므로
Level A(자동)는 무회귀 확인만 수행합니다 — ① locate 전문 스캔 블록·기본 경로(oversized_pointer)·
청크 조회·amendment 부착이 그대로인지 ② 검색 fan-out recall이 유지되는지. 개선 자체(개정문 인용 시
근거 법률 인용구의 조문번호 보존)는 호스트 LLM 행동(Level B)이라 배포 후 라이브 커넥터에서 사람이
LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★locate·별표·amendment 관련 항목은 전부 WARN 클래스 — 별표가 개정으로 예산 내 크기로 줄면 기본
  경로가 전문 verbatim으로 바뀌고, amendment_kind는 LIVE 개정에 따라 변하는 것이 정상 거동이라
  hard-BLOCK 부적합(false-block-safe·Andy 최우선 끊김없음). BLOCK 후보는 검색 무회귀에만.
"""

CHECKS = [
    {
        "name": "무회귀 A — locate 전문 스캔 블록 유지(law:285767:BP0002 annex_locate='인건비' → scanned_scope 앵커)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002", "annex_locate": "인건비"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 포인터 유지
            {"kind": "field_equals", "path": "annex_locate_result.scanned_scope", "value": "annex_full_text"},  # WARN — v0.21.0 기능 무회귀
        ],
    },
    {
        "name": "무회귀 B — 기본 경로 무변(law:285767:BP0002 opt-in 미지정 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 포인터 인용 금지 유지
        ],
    },
    {
        "name": "무회귀 C — 청크 조회 유지(law:285767:BP0002 annex_chunk=1 → verbatim 청크·v0.20.0 기능)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002", "annex_chunk": 1},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 청크 원문 유지
            {"kind": "field_equals", "path": "is_complete", "value": False},                  # WARN — 부분성 메타 유지
        ],
    },
    {
        "name": "무회귀 D — law 문서레벨 amendment 부착 유지(중기법 law:281987 amendment_kind=일부개정 — P4 대상 규정)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},            # WARN — 2026-07-22 LIVE 감사 일치 재확인
        ],
    },
    {
        "name": "무회귀 E — admrul 문서레벨 amendment 부착 유지(국토부 운영규정 admrul:2100000282288 amendment_kind=타법개정)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000282288"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "타법개정"},            # WARN — v0.20.1 spec 승계
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

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.21.1 = 조문번호 보존 정밀화가 개선 그 자체.
LEVEL_B_PROMPTS = [
    {
        "category": "★지시 — P4 재현(다중 항목 개정 정리 시 근거 법률 인용 조문번호 보존)",
        "probe_prompt": "중소기업 기술혁신 촉진법이 최근 개정으로 뭐가 바뀌었는지 빠짐없이 알려줘",
        "expect_behavior": "v0.21.0 eval P4 재실행 — 제10조 개정후 대체문 인용에서 '「중소기업진흥에 관한 법률」 "
                           "제68조에 따른'·'「기술보증기금법」 제12조에 따른'의 조문번호('제N조에 따른')를 탈락 없이 "
                           "원문 단위로 보존하는지 + 4개 조문(제10·11·18·27의2) 전수 열거 유지 + ★요약·정리 자체를 "
                           "회피하지 않는지(over-blocking 없음 — 개정문 전체 통짜 복사로 도피하지 않아야 정상).",
    },
    {
        "category": "무회귀 — locate 라우팅·기존 지시와의 상호 간섭 없음",
        "probe_prompt": "산업기술혁신사업 기술개발 평가관리지침 별표들에 RCMS라는 용어가 나오는지 확인해줘.",
        "expect_behavior": "v0.21.0 eval P1 재실행 — 지시 강화 후에도 annex_locate 우선 라우팅(청크 전수 순회 없이 "
                           "1~3호출)·전문 스캔 근거·스캔 한계 고지(줄 단위·HWP 범위 밖)가 유지되는지(기존 지시 희석 없음).",
    },
]
