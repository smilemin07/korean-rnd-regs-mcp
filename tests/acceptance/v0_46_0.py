"""v0.46.0 배포 전 LIVE acceptance spec — 국토교통 R&D 맥락 사례집 라우팅 보강(프롬프트-only).

읽는 법(비프로그래머용): "국토부 R&D 연구비 집행" 같은 부처명 질의는 사례집(case) 본문에
부처명 표기가 없거나 드물어('국토교통부'·'국토부' 0건·'국토교통' 1건 실측) 토큰 AND 검색이
0건이 됩니다. v0.46.0은 코드·데이터를 바꾸지 않고 프롬프트 표면 3곳(_SERVER_INSTRUCTIONS·
search_manual docstring·review_regulation 템플릿)에 ①사례집 우선 확인 라우팅 ②검색어 구성
지시(부처명 대신 '부적정집행'·비목명·'정산' 주제어) ③범위 사실(사례는 국가 R&D 전반 수집 —
국토부 전용 아님·Ⅳ장 절차만 KAIA 기준 유지)을 추가합니다. contract 0.34.0 유지·입력 스키마
무변 → 커넥터 삭제·재등록 불요(변경 지시문은 새 대화[새 MCP 초기화]부터 자동 반영).
규정·매뉴얼 도구의 도메인 응답은 패키지 버전 표면(health.version·serverInfo·instructions·
tools/list의 설명문)을 제외하고 byte 불변이어야 하므로, Level A는 무회귀 + 결손·우회 경로의
결정론 전제 확인이 중심이고, 라우팅 지시의 실효(호스트가 주제어로 검색을 구성하는지)는
Level B(배포 후 사람 판정) 전담입니다. field_equals는 러너 동결 규약상 WARN(사람 판정 참고)
입니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
(search_manual 응답에는 results 키가 없으므로 returned_not_below를 쓰지 않고 field_equals로
소스별 계수를 확인합니다 — 러너 동결 규약 준수.)
"""

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(프롬프트-only의 규정 트랙 무영향)",
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
        "name": "★전제 A — 부처명 토큰 질의는 여전히 case 0건(코드·데이터 무변 확인 — 결손은 지시로 우회)",
        "tool": "search_manual",
        "args": {"query": "국토교통부 부적정집행"},
        "asserts": [
            {"kind": "field_equals", "path": "total_matched_by_source.case", "value": 0},     # WARN
        ],
    },
    {
        "name": "★전제 B — 지시가 안내하는 주제어 우회 경로가 case에 도달(9건·로컬 데이터 결정론)",
        "tool": "search_manual",
        "args": {"query": "연구비 부적정집행"},
        "asserts": [
            {"kind": "field_equals", "path": "total_matched_by_source.case", "value": 9},     # WARN
        ],
    },
    {
        "name": "무회귀 — 사례집 case-2-2 citation 불변(보존 표면·응답 byte 무변)",
        "tool": "get_manual_section",
        "args": {"section_id": "case-2-2"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「국가 R&D 연구비 부적정집행 사례집」(25.5판) "
                      "Ⅱ. 부적정집행 사례 02 학생인건비, 인쇄 p.24~28"},                        # WARN
        ],
    },
    {
        "name": "무회귀 — 규정 상세 verbatim(규정 트랙 무접촉 확인)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). ★v0.46.0 표적 = 부처명 질의에서 호스트가
# ①search_manual을 호출하고 ②query를 부처명 없이 주제어로 구성해 ③case 소스에 도달한 뒤
# ④get_manual_section으로 절 본문을 조회하고 ⑤citation을 표기하며 ⑥답변에 실제 활용하는지.
# ★GO 집계표: 표적 A·B·C 3프로브 각각에 대해 위 ①~⑥ 중 case 도달(③)·활용(⑥)을 성공으로
# 기록하고, 3회 중 2회 이상 성공 + 전 프로브 범위 오판 0(Ⅰ~Ⅲ장 국토부 전용 오인 0·Ⅳ장
# 범부처 오인 0)이면 GO. 실패 시 단계 분류: 미호출(salience) / 부처명 query 0건(검색어 구성
# 지시 미준수) / 도달했으나 미사용(응답 소비) — 도구 호출·전달 query 문자열을 호스트 UI의
# 도구 로그에서 확인·기록할 것.
# ★프로브 설계 주의([[eval-probe-contamination]]): 개별 새 채팅창 + 자립형 문안. 새 채팅창으로도
# 교차 대화 메모리는 차단되지 않으므로 이전 대화 영향이 보이면 무효 처리 후 재실행.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 A — 국토부 표현 질의의 사례집 도달(신규 라우팅·검색어 구성)",
        "probe_prompt": "국토부 R&D 과제의 연구비 집행에서 자주 문제가 되는 부적정집행 사례를 "
                        "비목별로 알려줘. 출처(자료명·인쇄쪽)도 함께 표시해줘.",
        "expect_behavior": "search_manual 호출 시 query에 '국토부'·'국토교통부'를 넣지 않고 "
                           "'부적정집행'·비목명 등 주제어로 검색하여 case 소스 도달"
                           "(returned_by_source.case ≥1) → get_manual_section으로 절 본문 조회 → "
                           "citation 표기·답변 활용까지 이어지는지(발췌만 인용하면 부분 성공으로 "
                           "기록). 사례집을 국토교통부 전용 자료로 오인 서술하면 범위 오판 FAIL.",
    },
    {
        "category": "★표적 B — 국토교통부 표현·비목 특정 질의의 사례집 도달",
        "probe_prompt": "국토교통부 소관 연구개발과제에서 학생인건비를 잘못 집행해 문제가 된 "
                        "사례와 유의사항을 알려줘. 근거 규정도 함께 확인해줘.",
        "expect_behavior": "search_manual query가 주제어(부적정집행·학생인건비 등)로 구성돼 case "
                           "도달(case-2-2 등) → 절 조회·citation·활용. 근거 규정은 규정 도구로 교차 "
                           "확인하는지. 부처명 토큰 query로 0건을 받은 뒤 사례집 없이 답하면 "
                           "FAIL(단계 분류 기록).",
    },
    {
        "category": "★표적 C — 국토부 정산 맥락 질의의 사례집 도달(집계 3회분·표현 변형)",
        "probe_prompt": "국토부 연구개발사업 정산 과정에서 연구비 사용이 불인정되기 쉬운 유형과 "
                        "예방 방법을 알려줘. 참고한 자료의 출처도 표시해줘.",
        "expect_behavior": "표적 A·B와 동일 판정(주제어 query 구성 → case 도달 → 절 조회·citation·"
                           "활용). 표적 A·B·C 3회 중 2회 이상 도달·활용이면 릴리스 목표 달성(GO).",
    },
    {
        "category": "음성 대조 1 — 일반 산업부 정산 질의(사례집 미지정)의 과잉 라우팅 검출",
        "probe_prompt": "산업통상자원부 소관 R&D 과제의 연구비 정산 절차와 유의사항을 알려줘.",
        "expect_behavior": "사례집을 명시하지 않은 타 부처 일반 질의에서 ①산업부 소관 규정"
                           "(공통 운영요령 등)·규정 트랙이 답변의 중심을 유지하고 ②신규 라우팅 "
                           "지시가 과잉 적용돼 사례집이 최우선 근거로 부상하거나 Ⅳ장 KAIA 절차가 "
                           "산업부 과제에 그대로 적용되지 않는지. 사례집을 보조 참고로 언급하는 "
                           "것 자체는 허용(사례는 국가 R&D 전반 수집).",
    },
    {
        "category": "음성 대조 2 — 타 부처(산업부) Ⅳ장 구분 무회귀(v0.45.0 verbatim 재사용)",
        "probe_prompt": "국가연구개발과제 연구비 연차점검과 정산은 어떤 절차로 진행되는지 부적정집행 "
                        "사례집 기준으로 알려줘. 우리 과제는 산업통상자원부 소관이야.",
        "expect_behavior": "v0.45.0과 동일 문안(회귀 A/B 고정). 사례집 참조는 유지하되 Ⅳ장 절차는 "
                           "KAIA 국토교통R&D 프로세스 기준이라는 구분과 산업부 전문기관 확인 안내가 "
                           "유지되는지. 신규 라우팅 지시로 '사례집은 국토부 전용이라 참조 불가' 류 "
                           "과잉 축소가 생기면 FAIL.",
    },
    {
        "category": "무회귀 — 지정 귀속 문구·오귀속 0 유지(v0.45.0 P1 verbatim 재사용)",
        "probe_prompt": "부적정집행 사례집의 학생인건비 사례를 근거로, 이 자료를 어디까지 신뢰하고 "
                        "인용해도 되는지 출처(자료명·인쇄쪽)와 함께 알려줘.",
        "expect_behavior": "자료 성격 안내 소개 시 'korean-rnd-regs-mcp에서 제공하는 정보에 따르면,' "
                           "귀속이 유지되고(v0.45.0 누적 8/8), 발간처 오귀속·응답 구조 언급이 계속 "
                           "0인지. citation(자료명·인쇄쪽) 정상 표기 유지.",
    },
]
