"""v0.47.0 배포 전 LIVE acceptance spec — 과기정통부 심사·검토 고시 2종 수록(지원 규정 64→66).

읽는 법(비프로그래머용): 이번 릴리스는 데이터-only 규정 확대입니다 — rule_sets.yaml에
「대형 연구개발 사업계획검토 운영에 관한 규정」(고시 제2026-15호·admrul 2100000276390)과
「구축형 연구개발사업 심사 운용지침」(고시 제2026-41호·admrul 2100000278982)을 등록하고,
3표면(instructions·review 템플릿·README)의 지원 규정 카운트를 64→66으로 갱신합니다.
코드 실행 경로 변경 0·contract 0.34.0 유지·입력 스키마 무변(재연결 불요 — instructions는
새 대화부터 반영). Level A는 ①신규 2규정이 검색 fan-out에 실제 등록·도달하는지(LIVE)
②별지·서식이 BP 목록에 미노출인지(계획 /disc 조건 ⑤ 실측) ③기존 대표 질의 무회귀
④66규정 fan-out 예산을 봅니다.

★검색 도달 신호의 유효성(사전 실측 2026-08-10): '사업계획검토' 검색 결과 11건 전건이
large_rnd_plan_review 유래, '구축형 심사' 13건 전건이 build_type_rnd_screening 유래 —
두 검색어 토큰은 66규정 코퍼스에서 신규 규정에만 존재하므로 returned_not_below(전체 건수)가
신규 규정 도달의 실질 신호로 성립합니다(타 규정이 이 토큰을 새로 포함하게 되면 이 전제를
재검토할 것). results.0.rule_set_id field_equals는 그 전제의 교차 확인(WARN)입니다.

★사람 판정 승격 규약(러너는 WARN으로 출력하나 배포 게이트에서 BLOCK로 취급할 것):
신규 2규정 관련 check의 실패 — JO 상세 not_found·content_format 불일치·doc-level annex
실측 불일치·results.0.rule_set_id 불일치 — 는 이번 릴리스의 핵심 기능 실패이므로,
infra(상위 API 장애)가 아닌 한 사람 판정에서 배포 보류로 승격합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

CHECKS = [
    {
        "name": "★신규 A — '사업계획검토' 검색이 신규 규정(large_rnd_plan_review)에 도달"
                "(사전 실측: 결과 전건이 신규 규정 유래 — returned가 도달 신호)",
        "tool": "search_provision",
        "args": {"query": "사업계획검토"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "large_rnd_plan_review"},               # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 1},                                   # 회귀=BLOCK 후보(도달 신호)
            {"kind": "field_equals", "path": "results.0.rule_set_id",
             "value": "large_rnd_plan_review"},                                           # WARN — 사람 판정 승격 대상
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 66규정 fan-out 예산
        ],
    },
    {
        "name": "★신규 B — '구축형 심사' 검색이 신규 규정(build_type_rnd_screening)에 도달"
                "(사전 실측: 결과 전건이 신규 규정 유래)",
        "tool": "search_provision",
        "args": {"query": "구축형 심사"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "build_type_rnd_screening"},            # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 1},                                   # 회귀=BLOCK 후보(도달 신호)
            {"kind": "field_equals", "path": "results.0.rule_set_id",
             "value": "build_type_rnd_screening"},                                        # WARN — 사람 판정 승격 대상
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN
        ],
    },
    {
        "name": "★신규 A 문서레벨 — 조문 15·별지 2건 BP 미노출 실측(계획 조건 ⑤)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000276390"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — infra 구분 증거
            {"kind": "field_equals", "path": "articles_count", "value": 15},              # WARN — 사람 판정 승격 대상
            {"kind": "field_equals", "path": "annexes_count", "value": 2},                # WARN — 별표류 전건 집계
            {"kind": "field_equals", "path": "annexes", "value": []},                     # WARN — BP 목록 미노출(별지)
            {"kind": "field_equals", "path": "annexes_count_by_kind.별지", "value": 2},   # WARN
        ],
    },
    {
        "name": "★신규 B 문서레벨 — 조문 42·서식 1건(41,603자) BP 미노출 실측(계획 조건 ⑤)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278982"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — infra 구분 증거
            {"kind": "field_equals", "path": "articles_count", "value": 42},              # WARN — 사람 판정 승격 대상
            {"kind": "field_equals", "path": "annexes_count", "value": 1},                # WARN
            {"kind": "field_equals", "path": "annexes", "value": []},                     # WARN — BP 목록 미노출(서식)
            {"kind": "field_equals", "path": "annexes_count_by_kind.서식", "value": 1},   # WARN
        ],
    },
    {
        "name": "★신규 A 상세 — 제8조(사업계획검토 수행기관) verbatim(평면 schema 조문 분해)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000276390:JO0008"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 사람 판정 승격 대상
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — infra 구분 증거
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 승격 대상
            {"kind": "field_equals", "path": "title", "value": "사업계획검토 수행기관"},   # WARN — 조문 분해 정확성
        ],
    },
    {
        "name": "★신규 B 상세 — 제17조(사업추진심사의 요구·부칙 적용례 대상 조문) verbatim",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278982:JO0017"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 사람 판정 승격 대상
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — infra 구분 증거
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 승격 대상
            {"kind": "field_equals", "path": "title", "value": "사업추진심사의 요구"},     # WARN — 조문 분해 정확성
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall + 66규정 fan-out 예산",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                   # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 10},                                  # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). ★v0.47.0 표적 = 신규 2규정에 대해 호스트가
# ①suggest/search로 신규 규정에 도달하고 ②get_provision_detail로 조문 원문을 확인·인용하며
# ③답변에 실제 활용하는지. ★GO 집계: 표적 A·B 각각 도달(①)·활용(③)을 기록 — 2/2 성공 +
# 음성 대조에서 검색 희석 0이면 GO. 실패 시 단계 분류: 미도달(라우팅) / 도달했으나 미사용
# (응답 소비) / 외부 웹 대체(지시 위반) / 미노출 별지·서식 내용 날조(정직성 위반).
# ★프로브 설계 주의([[eval-probe-contamination]]): 개별 새 채팅창 + 자립형 문안.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 A — 대형 R&D 사업계획검토 질의의 신규 규정 도달 + 별지 정직성",
        "probe_prompt": "대형 연구개발사업의 사업계획검토는 어떤 절차로 진행되고, 검토를 "
                        "수행하는 기관과 점검항목은 무엇인지 규정 근거와 함께 알려줘.",
        "expect_behavior": "suggest_review_sources·search_provision이 large_rnd_plan_review에 "
                           "도달하고 제8조(사업계획검토 수행기관)·제11조(점검항목) 등 조문을 "
                           "get_provision_detail로 확인·인용하는지. ★정직성 기준: 점검항목의 "
                           "세부 목록은 별지 2(BP 미노출)에 있어 본 도구로 본문 조회 불가 — "
                           "제11조 본문 수준을 넘는 별지 세부 내용을 임의 생성하면 FAIL이고, "
                           "미노출 사실과 공식 원문 확인 경로를 안내하면 성공. 외부 웹검색 "
                           "대체·타 규정 오인 없이 신규 규정이 근거의 중심이면 도달 성공.",
    },
    {
        "category": "★표적 B — 구축형 심사 질의의 신규 규정 도달 + 부칙 적용례 정확성",
        "probe_prompt": "구축형 연구개발사업의 사업추진심사는 언제 어떻게 요구해야 하는지 "
                        "알려줘. 이 지침이 지금 시행 중인지도 확인해줘.",
        "expect_behavior": "build_type_rnd_screening 도달 → 제17조(사업추진심사의 요구) 등 조문 "
                           "인용. 시행 상태를 2026-05-11 시행 중으로 정확히 안내하고, 부칙 "
                           "제2조 적용례(제17조제2항제2호 각 목·2026년 11월 이후 요구 사업부터)를 "
                           "규정 전체 미시행으로 오인 서술하면 FAIL. 표적 A·B 2/2 도달·활용이면 "
                           "릴리스 목표 달성(GO).",
    },
    {
        "category": "음성 대조 — 기존 광역 질의 무회귀(검색 희석 검출)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "기존 규정(연구개발비 사용 기준·시행령 등)이 답변의 중심을 유지하고, "
                           "신규 심사·검토 고시 2종이 무관 맥락에서 상위 근거로 부상하지 "
                           "않는지(보조 언급 자체는 허용). 기존 citation·footer 표기 무회귀.",
    },
]
