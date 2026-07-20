"""v0.20.0 배포 전 LIVE acceptance spec — 「대용량 별표 본문 청크 조회(opt-in) — oversized 별표 접근성 해소」.

읽는 법(비프로그래머용): 이번 v0.20.0은 get_provision_detail에 optional 입력 annex_chunk를 추가해,
대용량 별표(oversized_pointer·본문 미수록)를 줄 경계 청크로 나눠 원문 그대로 조회할 수 있게 합니다.
Level A(자동)는 ① 신규 청크 경로가 LIVE 대용량 별표(law·admrul 각 1건)에서 실제로 verbatim 청크를
반환하는지 ② 기본 경로(annex_chunk 미지정)·검색 fan-out이 회귀하지 않았는지를 봅니다. 청크의
소비 품질(호스트가 부분 본문임을 인지하는지·발췌/청크에 없는 문구를 확인 불가로 표시하는지)은
호스트 LLM 행동(Level B)이라 배포 후 라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★청크 관련 항목은 전부 WARN 클래스(field_equals·absent_error_code) — 별표가 개정으로 예산 내
  크기로 줄면 기본 경로가 전문 verbatim으로 바뀌고 청크는 '무시+정직 경고'가 정상 거동이라
  hard-BLOCK 부적합(false-block-safe·Andy 최우선 끊김없음). BLOCK 후보는 검색 무회귀에만.
  별표 크기 전제(2026-06 실측): 혁신법 시행령 별표2 17,480자·평가관리지침 별표1 oversized(v0.12.0 spec).
"""

CHECKS = [
    {
        "name": "개선 A — law 대용량 별표 청크 조회(혁신법 시행령 law:285767:BP0002 annex_chunk=1 → verbatim 청크)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002", "annex_chunk": 1},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 청크 원문 반환
            {"kind": "field_equals", "path": "is_complete", "value": False},                  # WARN — 부분성 메타
            {"kind": "field_equals", "path": "chunk_index", "value": 1},                      # WARN — 요청 청크 번호 일치
        ],
    },
    {
        "name": "무회귀 A — 기본 경로 무변(law:285767:BP0002 annex_chunk 미지정 → oversized_pointer 유지 + chunk_count 발견성)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 포인터 인용 금지 유지
        ],
    },
    {
        "name": "개선 B — admrul 대용량 별표 청크 조회(평가관리지침 admrul:2100000252016:BP0001 annex_chunk=1)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000252016:BP0001", "annex_chunk": 1},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 양 트랙 커버
            {"kind": "field_equals", "path": "is_complete", "value": False},                  # WARN
        ],
    },
    {
        "name": "무회귀 B — manifest rider 정합(국토부 운영규정 신 doc_id 2100000282288 문서레벨 도달·amendment_kind=타법개정)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000282288"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 신 fallback id 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "타법개정"},            # WARN — 2026-07-20 LIVE 실측
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(annex_chunk 추가가 검색 fan-out 무해)",
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

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.20.0 = 청크 소비 품질이 개선 그 자체.
LEVEL_B_PROMPTS = [
    {
        "category": "★청크 소비 — 대용량 별표 세부 수치를 도구로 확인",
        "probe_prompt": "국가연구개발혁신법 시행령 별표 2(연구개발비 사용 용도)의 세부 항목을 원문 근거와 함께 "
                        "정리해줘. 표에 있는 기준을 정확히 인용해줘.",
        "expect_behavior": "oversized_pointer의 chunk_count를 보고 annex_chunk로 청크를 조회해(외부 웹 우회 없이) "
                           "원문을 인용하는지 + 청크가 부분 본문임을 인지하고(전체를 다 봤다고 과장하지 않고) "
                           "필요 시 다른 청크를 추가 조회하거나 남은 범위를 밝히는지 확인.",
    },
    {
        "category": "★발췌 한계 라벨 — 발췌·청크에 없는 문구는 확인 불가 표시",
        "probe_prompt": "산업기술혁신사업 기술개발 평가관리지침 별표에서 RCMS 관련 처리 기준이 정확히 어떻게 "
                        "적혀 있는지 알려줘.",
        "expect_behavior": "v0.19.1 eval P3에서 PLAUSIBLE로 남았던 시나리오. 검색 발췌·청크에서 정확 문구를 "
                           "찾으면 verbatim 인용하고, 못 찾은 문구·수치는 단정하지 않고 'MCP 응답에서 확인되지 "
                           "않음'으로 표시하거나 다른 청크·공식 원문 확인을 안내하는지 확인.",
    },
    {
        "category": "무회귀 — 기존 amendment·검색 소비와의 상호 간섭 없음",
        "probe_prompt": "중소기업 기술혁신 촉진법이 최근 개정으로 뭐가 바뀌었는지 빠짐없이 알려줘",
        "expect_behavior": "v0.17.1~v0.19.1 검증 시나리오 재실행 — 청크 지시 삽입 후에도 amendment_text 개정 지시 "
                           "항목을 가지조문 포함 전수 열거하고 근거 법률 인용을 보존하는지(기존 지시 희석 없음).",
    },
]
