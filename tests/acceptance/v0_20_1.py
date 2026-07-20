"""v0.20.1 배포 전 LIVE acceptance spec — 「청크·이력 소비 표시 정밀화 프롬프트 보강」.

읽는 법(비프로그래머용): 이번 v0.20.1은 코드 로직·응답 schema 변경이 전혀 없는 프롬프트 문자열-only
patch입니다(v0.17.1·v0.19.1과 동형). 서버가 반환하는 데이터는 v0.20.0과 동일해야 하므로 Level A(자동)는
무회귀 확인만 수행합니다 — ① 청크 조회·기본 경로(oversized_pointer)·amendment 부착이 그대로인지
② 검색 fan-out recall이 유지되는지. 개선 자체(별표 인용 방식 표시·전수 확인 범위 표시·latest_history
마커 라벨 보존)는 호스트 LLM 행동(Level B)이라 배포 후 라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로
수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★청크·별표 관련 항목은 전부 WARN 클래스 — 별표가 개정으로 예산 내 크기로 줄면 기본 경로가 전문
  verbatim으로 바뀌는 것이 정상 거동이라 hard-BLOCK 부적합(false-block-safe·Andy 최우선 끊김없음).
  BLOCK 후보는 검색 무회귀에만.
"""

CHECKS = [
    {
        "name": "무회귀 A — law 대용량 별표 청크 조회 유지(law:285767:BP0002 annex_chunk=1 → verbatim 청크)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002", "annex_chunk": 1},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 청크 원문 유지
            {"kind": "field_equals", "path": "is_complete", "value": False},                  # WARN — 부분성 메타 유지
        ],
    },
    {
        "name": "무회귀 B — 기본 경로 무변(law:285767:BP0002 annex_chunk 미지정 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 포인터 인용 금지 유지
        ],
    },
    {
        "name": "무회귀 C — 문서레벨 amendment 부착 유지(국토부 운영규정 admrul:2100000282288 amendment_kind=타법개정)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000282288"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — fallback id 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "타법개정"},            # WARN — 2026-07-21 LIVE 일치 재확인
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

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.20.1 = 소비 표시 정밀화가 개선 그 자체.
LEVEL_B_PROMPTS = [
    {
        "category": "★지시 ① — 별표 인용 방식 표시(인용/재구성/요약) + over-blocking 확인",
        "probe_prompt": "국가연구개발혁신법 시행령 별표 2(연구개발비 사용 용도)의 세부 항목을 표로 보기 좋게 "
                        "정리해줘. 원문 근거도 함께.",
        "expect_behavior": "청크로 전문을 확보해 정리하면서, 답변이 원문 줄 배열 유지 인용인지 내용 보존 "
                           "재구성인지 일부 요약인지 방식을 명시하는지 확인. ★동시에 재구성 자체를 회피·거부"
                           "하지 않는지(over-blocking 없음 — 표 정리는 여전히 수행되어야 정상).",
    },
    {
        "category": "★지시 ① — 별표 전체 결론의 전수/일부 확인 범위 표시",
        "probe_prompt": "산업기술혁신사업 기술개발 평가관리지침 별표들에 RCMS라는 용어가 나오는지 확인해줘.",
        "expect_behavior": "v0.20.0 eval P2 재실행 — 부재/존재 결론을 낼 때 전체 청크를 모두 확인했는지 "
                           "일부만 확인했는지 확인 범위를 답변에 명시하는지 확인(예: '별표1 전체 5개 청크 확인').",
    },
    {
        "category": "★지시 ② — latest_history 마커 유형 라벨 보존",
        "probe_prompt": "중소기업 기술혁신 촉진법 시행령에서 최근 개정된 조문이 뭐야? 조문별로 어떤 변경인지 알려줘.",
        "expect_behavior": "v0.20.0 eval P3 후속 — articles의 latest_history를 소비할 때 '신설'·'개정' 등 마커 "
                           "유형 라벨을 '손질'류의 다른 표현으로 뭉뚱그리지 않고 원문 라벨 그대로 표기하는지 + "
                           "라벨에서 개정 범위·중요도를 추론하지 않는지 확인.",
    },
    {
        "category": "무회귀 — 기존 amendment·청크 지시와의 상호 간섭 없음",
        "probe_prompt": "중소기업 기술혁신 촉진법이 최근 개정으로 뭐가 바뀌었는지 빠짐없이 알려줘",
        "expect_behavior": "v0.17.1~v0.20.0 검증 시나리오 재실행 — 신규 지시 삽입 후에도 amendment_text 개정 지시 "
                           "항목을 가지조문 포함 전수 열거하고 근거 법률 인용을 보존하는지(기존 지시 희석 없음).",
    },
]
