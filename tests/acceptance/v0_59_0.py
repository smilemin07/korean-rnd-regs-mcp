"""v0.59.0 배포 전 LIVE acceptance spec — 법령명·조문 번호로 찾는 질문의 도달성 개선.

읽는 법(비프로그래머용): 이번 릴리스는 search_provision에서
  ①법령 이름(정식 명칭·공식 약칭·혁신법 같은 통용명) 바로 뒤의 '제N조(의M)'·'별표N(의M)' 단위를 결과 맨 앞에 두고
  ②그때·0건일 때 search_note(조건부 1필드)로 안내합니다(contract 0.36.0 → 0.37.0·입력 스키마 무변·재연결 불요).
법령 이름이 없는 검색은 결과가 그대로여야 합니다.

returned_not_below 값은 v0.58.0 코드로 같은 날(2026-10-24 03시) 측정한 값이다(같은 세션 A/B에서 이름 없는
30질의 중 결과가 있는 29건 응답이 v0.59.0과 byte 동일 — contract_version 제외). 줄면 데이터 변동인지 provision_id
집합으로 먼저 가린다. 법령명+번호 질의의 1위는 field_equals(WARN)로 보고, 결정론 잠금은 pytest(test_v0590_pin.py)가 맡는다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 기록용]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

_NOTE_ZERO = (
    "검색 결과 0건은 수록 범위 밖이라는 뜻이 아닙니다. 검색은 조문·별표의 제목과 본문에 낱말이 모두 있는지 "
    "비교합니다(별지·서식 제외). 법령 이름은 바로 뒤에 조문·별표 번호(예: 제27조의3, 별표 2)가 올 때만 "
    "알아보며, 이름만으로는 검색되지 않습니다. 이름을 빼고 본문 용어로 다시 검색하거나 이름 뒤에 번호를 붙여 "
    "검색하십시오. 수록 규정은 list_rule_sets로 확인할 수 있습니다."
)

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 66규정 fan-out(릴리스 간 동일 문안·이름 없음 = 안내 없음)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                   # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 18},                                  # 회귀=BLOCK 후보 — v0.58.0 코드 2026-10-24 실측
            {"kind": "field_equals", "path": "search_note", "value": "<missing>"},       # WARN
            {"kind": "absent_error_code", "value": "auth_failed"},                        # WARN
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 기록용
        ],
    },
    {
        "name": "무회귀 — 절단 질의 '기술료' returned 비감소",
        "tool": "search_provision",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "returned_not_below", "value": 17},                                  # 회귀=BLOCK 후보 — v0.58.0 실측
            {"kind": "field_equals", "path": "search_note", "value": "<missing>"},       # WARN
        ],
    },
    {
        "name": "무회귀 — 절단 질의 '제재부가금' returned 비감소",
        "tool": "search_provision",
        "args": {"query": "제재부가금"},
        "asserts": [
            {"kind": "returned_not_below", "value": 15},                                  # 회귀=BLOCK 후보 — v0.58.0 실측
        ],
    },
    {
        "name": "무회귀 — 번호 단독 '제27조의3'(이름 없음 = 종전 1위 유지)",
        "tool": "search_provision",
        "args": {"query": "제27조의3"},
        "asserts": [
            {"kind": "returned_not_below", "value": 8},                                   # 회귀=BLOCK 후보 — v0.58.0 실측
            {"kind": "field_equals", "path": "results.0.provision_id", "value": "law:281987:JO002703"},  # WARN
            {"kind": "field_equals", "path": "search_note", "value": "<missing>"},       # WARN
        ],
    },
    {
        "name": "★표적 — 게이트 D 질의(v0.58.0 0건) → 중기법 제27조의3 고정·사업화 금융지원·부칙 문장",
        "tool": "search_provision",
        "args": {"query": "중소기업 기술혁신 촉진법 제27조의3"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "sme_tech_act"},                        # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 1},                                   # 회귀=BLOCK 후보 — v0.58.0은 0
            {"kind": "field_equals", "path": "results.0.provision_id", "value": "law:281987:JO002703"},  # WARN
            {"kind": "field_equals", "path": "results.0.title", "value": "사업화 금융지원"},  # WARN — 폴백 판본이면 다름
            {"kind": "field_equals", "path": "results.0.warnings.0", "value": "제27조의3(사업화 금융지원)은 법률 제21704호 부칙 제1조(공포한 날부터 시행)에 따라 2026-05-26부터 시행되었습니다. effective_date는 법령 판본의 시행일입니다. 종전 제27조의3은 제27조의4로 이동."},  # WARN — eflaw 정상 경로
            {"kind": "field_equals", "path": "search_note", "value": "질의의 「중소기업 기술혁신 촉진법」 제27조의3에 해당하는 단위를 앞쪽 결과에 두었습니다."},  # WARN
        ],
    },
    {
        "name": "★표적 — 통용명 '혁신법 제32조'(v0.58.0은 인용 조문만) → 혁신법 제32조 1위",
        "tool": "search_provision",
        "args": {"query": "혁신법 제32조"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "innovation_act"},                      # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 7},                                   # 회귀=BLOCK 후보 — v0.58.0 실측 8. 고정 결과가 꼬리 1건과 바뀔 수 있어 여유 1
            {"kind": "field_equals", "path": "results.0.rule_set_id", "value": "innovation_act"},  # WARN
            {"kind": "field_equals", "path": "results.0.unit_id", "value": "JO0032"},     # WARN
        ],
    },
    {
        "name": "★표적 — 다른 법 같은 번호 혼입 '산업기술혁신 촉진법 제11조의2' → 대상 1위",
        "tool": "search_provision",
        "args": {"query": "산업기술혁신 촉진법 제11조의2"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "industry_tech_act"},                   # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 4},                                   # 회귀=BLOCK 후보 — v0.58.0 실측
            {"kind": "field_equals", "path": "results.0.rule_set_id", "value": "industry_tech_act"},  # WARN
            {"kind": "field_equals", "path": "results.0.unit_id", "value": "JO001102"},   # WARN
        ],
    },
    {
        "name": "★표적 — 별표 정답 '연구개발비 사용 기준 별표 2' → BP0002 1위",
        "tool": "search_provision",
        "args": {"query": "연구개발비 사용 기준 별표 2"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 8},                                   # 회귀=BLOCK 후보 — v0.58.0 실측
            {"kind": "field_equals", "path": "results.0.unit_id", "value": "BP0002"},     # WARN
        ],
    },
    {
        "name": "★표적 — 0건 복구 안내 '촉진법 제27조의3'(비공식 약칭 = 미탐지)",
        "tool": "search_provision",
        "args": {"query": "촉진법 제27조의3"},
        "asserts": [
            {"kind": "field_equals", "path": "search_note", "value": _NOTE_ZERO},         # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
        ],
    },
    {
        "name": "무회귀 — suggest 경로 정상(이름 없는 키워드)",
        "tool": "suggest_review_sources",
        "args": {"question": "연구책임자를 변경하려고 하는데 어떤 규정을 봐야 하나요?", "keywords": ["연구책임자", "변경"]},
        "asserts": [
            {"kind": "field_equals", "path": "search_note", "value": "<missing>"},       # WARN — suggest에는 전달 안 됨
            {"kind": "absent_error_code", "value": "auth_failed"},                        # WARN
            {"kind": "latency_under", "value": 30.0},                                     # WARN — 기록용
        ],
    },
]

LEVEL_B_PROMPTS = [
    {
        "category": "재현 게이트 D — 제27조의3 조문 시행일(v0.57.0 문안 verbatim·검색 경로)",
        "probe_prompt": "중소기업 기술혁신 촉진법 제27조의3은 언제부터 시행된 조문인지 도구로 확인해서 알려줘.",
        "expect_behavior": "2026-05-26(법률 제21704호 부칙 제1조 '공포한 날부터')을 도구 응답 근거로 답함. "
                           "'수록 범위 밖'으로 판단하거나 웹의 옛 날짜(2021-10-21)를 답하면 실패(Claude 3회·ChatGPT 1회, "
                           "ChatGPT는 커넥터 Refresh 뒤 새 대화).",
    },
    {
        "category": "법령명+번호 — 통용명",
        "probe_prompt": "국가연구개발혁신법 제32조 내용을 도구로 확인해서 알려줘.",
        "expect_behavior": "혁신법 제32조(부정행위 등에 대한 제재처분) 원문을 근거로 답함. 시행령 별표만 인용하면 실패.",
    },
    {
        "category": "법령명+번호 — 다른 법 같은 번호 혼입",
        "probe_prompt": "산업기술혁신 촉진법 제11조의2를 도구로 확인해서 요약해줘.",
        "expect_behavior": "산업기술혁신 촉진법 제11조의2를 근거로 답함. 다른 법(중소기업 기술혁신 촉진법 제11조의2)을 "
                           "인용하면 실패.",
    },
    {
        "category": "관찰 — 비공식 약칭 0건 뒤 회복",
        "probe_prompt": "중기법 제27조의3 시행일을 도구로 확인해서 알려줘.",
        "expect_behavior": "0건 안내(search_note) 뒤 정식 명칭·번호로 재검색해 회복하는지 관찰(판정 아님).",
    },
]
