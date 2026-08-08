"""v0.45.0 배포 전 LIVE acceptance spec — 규범성 안내 귀속 교정(지정 출처 명시).

읽는 법(비프로그래머용): v0.44.0의 인접 지시(law_priority_note_note)는 응답 구조 언급
노출("시스템 메타데이터…")을 6/6 차단했지만, 발간처 오귀속("원문 자체에 이렇게 명시되어
있습니다" 등)은 High·Extra 4관측에서 잔존했습니다. 이번 v0.45.0은 그 상수의 문면만
교체합니다 — 오귀속 금지(부정문)에 지정 귀속 문구(긍정 대안) "korean-rnd-regs-mcp에서
제공하는 정보에 따르면,"을 더합니다(Andy 확정 문면·contract 0.34.0·입력 스키마 무변 →
재연결 불요). 의도된 도메인 변경은 law_priority_note_note 값 하나뿐이며, 그 외 도메인
필드와 law_priority_note는 버전 식별자(contract_version[오류 응답 포함]·health/serverInfo의
패키지 버전)를 제외하고 byte 불변입니다. 새 문면은 직렬화 기준
구 문면보다 3자 짧아 예산 경합 백스톱(v0.44.0 §5.35 3경로)의 판정에 영향을 주지
않습니다(pytest 전건 + 예산 경계 청크 실측 잠금).
매뉴얼 도구는 네트워크가 없으므로(로컬 JSON) Level A는 규정 트랙 무회귀 + 문면 교체
결정론 표면을 함께 봅니다. field_equals는 러너 동결 규약상 WARN(사람 판정 참고)입니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

# 현행 서버 상수와 test_acceptance_spec.py drift 가드로 대조되는 리터럴(v0.45.0 교체 문면).
_LPN_NOTE = (
    "위 law_priority_note는 자료 원문이 아니라 korean-rnd-regs-mcp가 제공하는 안내입니다. "
    "답변에 반영하십시오. 소개할 때는 자료나 발간처가 밝혔다고 서술하거나 인용하지 말고, "
    "반드시 'korean-rnd-regs-mcp에서 제공하는 정보에 따르면,'으로 시작해 귀속하십시오. "
    "'시스템 메타데이터'·'내부 필드'·'도구 응답 필드' 등 전달 방식·응답 구조는 언급하지 마십시오."
)

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(상수 값 교체의 규정 트랙 무영향)",
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
        "name": "★표적 A — 상세 응답의 인접 지시가 교체 문면(전 소스 공통 상수)",
        "tool": "get_manual_section",
        "args": {"section_id": "case-1-1"},
        "asserts": [
            {"kind": "field_equals", "path": "manual_meta.law_priority_note_note", "value": _LPN_NOTE},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},      # WARN
        ],
    },
    {
        "name": "★표적 B — 혼합 검색 응답에도 교체 문면 부착(병기 블록 상속 경로)",
        "tool": "search_manual",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "field_equals", "path": "manual_meta.law_priority_note_note", "value": _LPN_NOTE},  # WARN
        ],
    },
    {
        "name": "무회귀 — 예산 경합 청크의 상수 양보 판정 불변(-3자 교체가 백스톱 분기를 안 뒤집음)",
        "tool": "get_manual_section",
        "args": {"section_id": "b3-4-2", "chunk": 1},
        "asserts": [
            {"kind": "field_equals", "path": "manual_meta.law_priority_note_note", "value": "<missing>"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 사례집 case-2-2 citation 불변(보존 표면)",
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

# Level B(배포 후 라이브 확인 + 사람 판정). ★v0.45.0 표적 = 발간처 오귀속 소멸 + 지정 귀속
# 문구 발화. 프로브 문안은 v0.44.0 spec과 verbatim 동일(회귀·A/B 문안 고정 원칙 — 실패를
# 관측한 문안을 글자 그대로 재사용해야 개선 여부를 비교 가능). 판정 5항: ①실측 오귀속
# 4유형("원문 자체에 명시"·"사례집 스스로 명시"·"자료가 밝힘"·"발간처 문장" 류) 0건
# ②안내 소개 시 "korean-rnd-regs-mcp에서 제공하는 정보에 따르면,"으로 시작해 귀속
# ③'시스템 메타데이터'·'내부 필드'·'도구 응답' 등 내부 구조 표현 0(v0.44.0 6/6 무회귀)
# ④자료 성격·법령 우선 안내 내용은 계속 전달(과잉 억제 0) ⑤note 문면 자체 노출 0.
# ★프로브 설계 주의([[eval-probe-contamination]]): 개별 새 채팅창 + 자립형 문안. 새 채팅창으로도
# 교차 대화 메모리(claude.ai 'Relevant chats'·ChatGPT 메모리)는 차단되지 않으므로 이전 대화
# 영향이 보이면 무효 처리 후 재실행. ★ChatGPT는 `고급 > 모델`에서 모델명 실확인·추론 강도 병기.
# ★A/B 재현 프로브는 실패를 관측한 당시와 동일 effort로 실행(v0.44.0 관측 = Sonnet 5 High).
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 발간처 오귀속 소멸 + 지정 귀속 문구 A/B(v0.44.0 eval P1 verbatim 재사용)",
        "probe_prompt": "부적정집행 사례집의 학생인건비 사례를 근거로, 이 자료를 어디까지 신뢰하고 "
                        "인용해도 되는지 출처(자료명·인쇄쪽)와 함께 알려줘.",
        "expect_behavior": "자료 성격 안내를 소개할 때 '원문 자체에 이렇게 명시되어 있습니다'·'사례집 "
                           "스스로 명시' 류 오귀속(v0.44.0 High·Extra 4관측)이 0건이고, 대신 "
                           "'korean-rnd-regs-mcp에서 제공하는 정보에 따르면,'으로 시작해 귀속하는지. "
                           "citation(자료명·인쇄쪽)은 정상 표기 유지. note 문면 자체가 노출되면 FAIL.",
    },
    {
        "category": "무회귀 — 자기지시성 프레임 0 유지(v0.43.0 P3 재현 문안 verbatim 재사용)",
        "probe_prompt": "국가 R&D 연구비 부적정집행 사례집에 나오는 '불인정'이나 '회수'가 곧바로 "
                        "제재처분이라는 뜻인지, 이 사례집을 근거로 개별 과제의 정산 결과를 판정해도 "
                        "되는지 자료 성격을 포함해서 검토해줘.",
        "expect_behavior": "'시스템 메타데이터'·'내부 필드'·'도구 응답' 등 응답 구조·필드 존재 방식 언급이 "
                           "계속 0인지(v0.44.0에서 6/6 차단 달성 — 문면 교체로 재개방되면 회귀). 안내 "
                           "내용(교육·참고용·개별 사안 판정 아님·법령 우선)은 계속 전달되고, 소개 시 "
                           "지정 귀속 문구를 쓰는지.",
    },
    {
        "category": "음성 대조 — 안내 내용 전달 유지(과잉 억제 없음·verbatim 재사용)",
        "probe_prompt": "국가연구개발과제 연구비 연차점검과 정산은 어떤 절차로 진행되는지 부적정집행 "
                        "사례집 기준으로 알려줘. 우리 과제는 산업통상자원부 소관이야.",
        "expect_behavior": "Ⅳ장 절차(Ez-baro·위탁정산기관·일정)가 KAIA 국토교통R&D 프로세스 기준이라는 "
                           "사실 라벨이 여전히 판단·안내에 반영되는지(산업부 과제는 해당 전문기관 확인 "
                           "안내). 문면 교체(귀속 지시 강화)로 안내 전달 자체가 사라지면 FAIL(과잉 억제).",
    },
    {
        "category": "무회귀 — 기존 완성형 블록(citation·footer) 표시 유지(verbatim 재사용)",
        "probe_prompt": "학생인건비통합관리 제도 매뉴얼에서 통합관리계정 이자 처리를 어떻게 안내하는지 "
                        "알려줘. 출처(자료명·인쇄쪽)와 답변 하단 표준 안내도 함께 표시해줘.",
        "expect_behavior": "b1-3-6 도달·citation(인쇄 p.32)·footer 4줄이 v0.44.0과 동일하게 표시되고, "
                           "문면 교체가 기존 완성형 블록 부착·표시에 영향을 주지 않는지.",
    },
]
