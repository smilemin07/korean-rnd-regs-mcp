"""v0.23.0 배포 전 LIVE acceptance spec — 「국방 R&D family 3건 확대(55→58) — 방위사업청 트랙 1차」.

읽는 법(비프로그래머용): 이번 v0.23.0은 순수 data+prompt+test 확대(코드 로직 0줄)입니다.
Level A(자동)는 ① 신규 3건(국방과학기술혁신 촉진법·시행령·시행규칙)이 검색 fan-out에서 LIVE
도달하는지(검색어 '국방과학기술' — 2026-07-23 재프로브에서 3건 모두 조문 본문 실존 확인:
38/24/9회) ② 시행령 별표(제재 기준)가 본문 전문 tier-1로, 시행규칙 별표(연구개발비 사용용도·
★채번 BP0000)가 도달하는지 ③ 기존 경로 무회귀 + N=58 cold fan-out을 확인합니다. 트랙 정체성
가드(혁신법 오적용 방지)는 호스트 LLM 행동(Level B)이라 배포 후 사람이 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★별표 tier·amendment_kind 항목은 전부 WARN 클래스 — 시행규칙 BP0000의 tier-1은 추정(11,040자·
  escaped 11,585 < 예산 15,700 — 직렬화 오버헤드 포함 실판정은 이 spec 실행이 곧 실측)이고,
  별표 크기·제개정구분은 LIVE 개정으로 변하는 것이 정상 거동이라 hard-BLOCK 부적합
  (false-block-safe·Andy 최우선 끊김없음). BLOCK 후보는 도달·검색 무회귀에만.
"""

CHECKS = [
    {
        "name": "신규 A — 국방 R&D family 3건 검색 fan-out LIVE 도달('국방과학기술' — N=58 첫 실측)",
        "tool": "search_provision",
        "args": {"query": "국방과학기술"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_act"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_decree"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_rule"},
            {"kind": "returned_not_below", "value": 3},                                   # 신규 family 본문 매치 하한
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN — graceful skip 0
            {"kind": "latency_under", "value": 16.0},                                     # WARN — N=58 cold 예산 내
        ],
    },
    {
        "name": "신규 B — 법 문서레벨 도달(law:258057 amendment_kind=일부개정·LIVE 2026-07-23)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:258057"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — LIVE 개정 시 변동 정상
        ],
    },
    {
        "name": "신규 C — 시행령 별표 1 본문 전문 tier-1(law:287549:BP0001 — 제재 기준·최대 4,360자<예산)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:287549:BP0001"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — BP 채번 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — tier-1 전문
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": True},    # WARN — 인용 허용
        ],
    },
    {
        "name": "신규 D — 시행규칙 별표 BP0000 도달(law:230705:BP0000 — 연구개발비 사용용도·채번 '0000' 코너케이스·tier-1 추정 실측)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:230705:BP0000"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — BP0000 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — tier-1 추정 검증
        ],
    },
    {
        "name": "신규 E — 시행규칙 문서레벨 제정 kind(law:230705 amendment_kind=제정 — amendment_text skip 정상 거동)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:230705"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "제정"},            # WARN — 제정 skip 정상
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(N=58 확대가 기존 검색 경로 무해) + oversized 기본 경로",
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
    {
        "name": "무회귀 A — oversized 별표 기본 경로 무변(law:285767:BP0002 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.23.0 = 국방 트랙 신설 + 정체성 가드가 개선 그 자체.
LEVEL_B_PROMPTS = [
    {
        "category": "★가드 — 국방 R&D 적용 법체계(혁신법 오적용 방지 실효)",
        "probe_prompt": "방위사업청에서 발주한 국방 연구개발 과제를 수행 중인데, 어떤 법령이 적용되는지 규정 근거와 함께 알려줘",
        "expect_behavior": "국가연구개발혁신법으로 단정하지 않고 국방과학기술혁신 촉진법 family를 우선 조회·인용하는지 + "
                           "혁신법 제3조제3호(보안과제 국방사업에 제9~18조 비적용)를 전면 배제로 과확대하지 않는지(반대 오류 0).",
    },
    {
        "category": "★개선 — 제재 기준 별표 grounded(신규 트랙 end-to-end)",
        "probe_prompt": "국방 연구개발에서 부정행위를 하면 참여제한이 몇 년까지 가능한지 규정 검토해줘",
        "expect_behavior": "국방과기혁신법 시행령 별표(참여제한 기간 기준 — tier-1 전문)를 도구로 조회해 근거 인용하는지 + "
                           "날조 0 + 도구 응답에 없는 수치 임의 단정 없음.",
    },
    {
        "category": "무회귀 — 제정 규칙 정직 소비 + 기존 지시 간섭 없음",
        "probe_prompt": "국방과학기술혁신 촉진법 시행규칙의 연구개발비 사용용도 별표 내용과 최근 개정 여부를 알려줘",
        "expect_behavior": "BP0000 별표 본문(tier-1)을 조회·인용하고, 개정 이력이 없음(2021 제정 이래 무개정·amendment 미제공)을 "
                           "날조 없이 정직하게 표시하는지 + 서식 1건 미노출 caveat 처리.",
    },
]
