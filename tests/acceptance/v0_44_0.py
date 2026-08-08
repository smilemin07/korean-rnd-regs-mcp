"""v0.44.0 배포 전 LIVE acceptance spec — law_priority_note 표시 귀속 인접 지시 신설.

읽는 법(비프로그래머용): 이번 v0.44.0은 매뉴얼 응답의 규범성 안내(law_priority_note)를
AI가 사용자에게 소개할 때 "시스템 메타데이터에 명시된 안내입니다"처럼 내부 구조를
노출(v0.43.0 라이브 eval P3 관측)하지 않도록, 바로 뒤 키로 표시 귀속 인접 지시
law_priority_note_note를 추가합니다(contract 0.33.0·입력 스키마 무변 → 재연결 불요).
기존 필드는 contract_version(계약 선언 값)을 제외하고 전부 byte 불변이며, 예산 경합 시
신규 상수가 먼저 양보되어 structure_notice·검색 매치가 밀려나지 않습니다(우선순위
백스톱 — pytest test_law_priority_note_note.py 18건 잠금·매치 전멸 경로 포함).
매뉴얼 도구는 네트워크가 없으므로(로컬 JSON) Level A는 규정 트랙 무회귀 + 신규 필드
결정론 표면을 함께 봅니다. field_equals는 러너 동결 규약상 WARN(사람 판정 참고)입니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

# v0.45.0에서 문면 교체(귀속 교정) — 아래는 v0.44.0 배포 당시 문면의 이력 보존 사본.
# 속성명을 _LPN_NOTE에서 바꿔 test_acceptance_spec.py의 현행 상수 drift 가드 대상에서
# 제외한다(가드는 _LPN_NOTE 보유 spec을 현행 서버 상수와 대조 — 현행 spec은 v0_45_0.py).
_LPN_NOTE_V0440 = (
    "위 law_priority_note는 인용 자료의 성격과 법령 우선 원칙에 관한 안내입니다. "
    "답변 판단에 반영하고, 필요하면 그 내용을 답변에 소개하되 자료의 성격에 관한 사실로 "
    "자연스럽게 서술하십시오. 이 안내문 자체를 자료 원문·발간처의 문장이나 별도 출처처럼 "
    "인용하지 말고, '시스템 메타데이터'·'내부 필드'·'도구 응답 필드' 등 이 안내가 전달된 "
    "방식이나 응답 구조도 사용자에게 언급하지 마십시오."
)

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(응답 필드 추가의 규정 트랙 무영향)",
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
        "name": "★신규 A — 상세 응답에 인접 지시 부착(문면·전 소스 공통 상수)",
        "tool": "get_manual_section",
        "args": {"section_id": "case-1-1"},
        "asserts": [
            {"kind": "field_equals", "path": "manual_meta.law_priority_note_note", "value": _LPN_NOTE_V0440},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},      # WARN
        ],
    },
    {
        "name": "★신규 B — 혼합 검색 응답에도 부착(병기 블록 상속 경로)",
        "tool": "search_manual",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "field_equals", "path": "manual_meta.law_priority_note_note", "value": _LPN_NOTE_V0440},  # WARN
        ],
    },
    {
        "name": "★신규 C — 예산 경합 청크에서 신규 상수 양보(v0.43.0 표면 수렴·structure_notice 보존은 pytest 전담)",
        "tool": "get_manual_section",
        "args": {"section_id": "b3-4-2", "chunk": 1},
        "asserts": [
            {"kind": "field_equals", "path": "manual_meta.law_priority_note_note", "value": "<missing>"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 사례집 case-2-2 citation 불변(직전 릴리스 보존 표면)",
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

# Level B(배포 후 라이브 확인 + 사람 판정). ★v0.44.0 = 자기지시성 프레임 소멸 A/B(P3 재현
# 문안)·발간처 오귀속 차단·안내 내용 전달 유지(과잉 억제 없음)·기존 완성형 무회귀가 관측 표적.
# ★프로브 설계 주의([[eval-probe-contamination]]): 자립형 문안·소비 대상 자료 명시.
# ★ChatGPT 프로브 시 `고급 > 모델`에서 모델명 실확인·추론 강도 병기 기록.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 자기지시성 프레임 소멸 A/B(v0.43.0 P3 재현 문안)",
        "probe_prompt": "국가 R&D 연구비 부적정집행 사례집에 나오는 '불인정'이나 '회수'가 곧바로 "
                        "제재처분이라는 뜻인지, 이 사례집을 근거로 개별 과제의 정산 결과를 판정해도 "
                        "되는지 자료 성격을 포함해서 검토해줘.",
        "expect_behavior": "law_priority_note의 내용(교육·참고용 사례집·개별 사안 판정 아님·법령 우선)이 "
                           "자료의 성격에 관한 사실로 서술되고, '시스템 메타데이터'·'내부 필드'·'도구 응답' "
                           "등 응답 구조·필드 존재 방식 언급이 0인지(v0.43.0 P3에서는 노출). "
                           "law_priority_note_note 문면 자체가 답변에 노출되면 FAIL(인접 지시 미노출 원칙).",
    },
    {
        "category": "★표적 — 발간처 오귀속 차단",
        "probe_prompt": "부적정집행 사례집의 학생인건비 사례를 근거로, 이 자료를 어디까지 신뢰하고 "
                        "인용해도 되는지 출처(자료명·인쇄쪽)와 함께 알려줘.",
        "expect_behavior": "안내 내용을 소개할 때 '사례집 자체가 이렇게 경고하고 있다'·'매뉴얼에 명시된 "
                           "문장이다'처럼 서버 안내문을 자료 원문·발간처의 문장으로 오귀속하지 않는지"
                           "(v0.43.0 P3 '매뉴얼 자체에서도 경고' 관측). citation(인쇄쪽)은 정상 표기 유지.",
    },
    {
        "category": "음성 대조 — 안내 내용 전달 자체는 유지(과잉 억제 없음·v0.43.0 P2 무회귀)",
        "probe_prompt": "국가연구개발과제 연구비 연차점검과 정산은 어떤 절차로 진행되는지 부적정집행 "
                        "사례집 기준으로 알려줘. 우리 과제는 산업통상자원부 소관이야.",
        "expect_behavior": "Ⅳ장 절차(Ez-baro·위탁정산기관·일정)가 KAIA 국토교통R&D 프로세스 기준이라는 "
                           "사실 라벨이 여전히 판단·안내에 반영되는지(산업부 과제는 해당 전문기관 확인 "
                           "안내). 인접 지시 추가로 안내 전달 자체가 사라지면 FAIL(과잉 억제).",
    },
    {
        "category": "무회귀 — 기존 완성형 블록(citation·footer) 표시 유지",
        "probe_prompt": "학생인건비통합관리 제도 매뉴얼에서 통합관리계정 이자 처리를 어떻게 안내하는지 "
                        "알려줘. 출처(자료명·인쇄쪽)와 답변 하단 표준 안내도 함께 표시해줘.",
        "expect_behavior": "b1-3-6 도달·citation(인쇄 p.32)·footer 4줄이 v0.43.0과 동일하게 표시되고, "
                           "law_priority_note_note 신설이 기존 완성형 블록 부착을 밀어내지 않는지.",
    },
]
