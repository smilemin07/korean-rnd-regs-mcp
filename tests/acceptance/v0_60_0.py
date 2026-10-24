"""v0.60.0 배포 전 LIVE acceptance spec — 조문별 변경 이력 안내(판본 시행일과 조문 변경 시점 구분).

읽는 법(비프로그래머용): 이번 릴리스는 law 조문 상세(get_provision_detail JO)에 article_effective_notice 1문장을
붙입니다(contract 0.37.0 → 0.38.0·입력 스키마 무변·재연결 불요·런타임 네트워크 호출 추가 0). 문장은 배포 전
스냅샷(article_history.json)과 서빙 판본이 같을 때 조문별 기록을, 아니면 일반 안내를 냅니다. 검색은 바뀌지 않으므로
v0.59.0 회귀 3건을 같은 문안·같은 기준값으로 다시 봅니다.

문장 기대값의 "(2026-10-25 확인)"은 스냅샷 생성일이다. 스냅샷을 다시 만들면 날짜만 바뀌므로 field_equals(WARN)로 둔다.
결정론 잠금은 pytest(test_v0600_article_history.py)가 맡는다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 기록용]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

_N_27_3 = (
    "국가법령정보 조문별 변경 이력(2026-10-25 확인)상 조회된 판본까지 이 조문의 최근 변경 기록은 법률 제21704호(2026-05-26 공포)이고, "
    "그 판본은 2026-05-26에 시행되었습니다. 그 부칙에서 조문별 시행일을 따로 정했다면 그에 따릅니다. "
    "effective_date(2026-07-01)는 조회된 법령 판본 전체의 시행일입니다."
)
_N_INNO_2 = (
    "국가법령정보 조문별 변경 이력(2026-10-25 확인)상 조회된 판본까지 이 조문의 최근 변경 기록은 법률 제21421호(2026-03-10 공포)입니다. "
    "그 판본의 시행일이 2026-06-11·2026-09-11로 나뉘어 있어, 이 조문의 시행일은 이 응답으로 정할 수 없으니 그 부칙에서 확인하십시오. "
    "effective_date(2026-10-02)는 조회된 법령 판본 전체의 시행일입니다."
)
_N_INNO_1 = (
    "국가법령정보 조문별 변경 이력(2026-10-25 확인)상 조회된 판본까지 이 조문의 최근 변경 기록은 법률 제17343호(2020-06-09 공포)이고, "
    "그 판본은 2021-01-01에 시행되었습니다. 그 부칙에서 조문별 시행일을 따로 정했다면 그에 따릅니다. "
    "effective_date(2026-10-02)는 조회된 법령 판본 전체의 시행일입니다."
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
        "name": "★표적 — 제27조의3 조문 상세(단일 시행·수기 고지와 같은 날짜)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987:JO002703"},
        "asserts": [
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
            {"kind": "field_equals", "path": "article_effective_notice", "value": _N_27_3},  # WARN — eflaw 정상 경로
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — tier 무변
        ],
    },
    {
        "name": "★표적 — 혁신법 제2조(분리 시행 판본 = 조문 날짜 미제시)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:290757:JO0002"},
        "asserts": [
            {"kind": "field_equals", "path": "article_effective_notice", "value": _N_INNO_2},  # WARN
        ],
    },
    {
        "name": "★표적 — 혁신법 제1조(제정 이후 무변경 = 2021-01-01)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:290757:JO0001"},
        "asserts": [
            {"kind": "field_equals", "path": "article_effective_notice", "value": _N_INNO_1},  # WARN
        ],
    },
    {
        "name": "무회귀 — 행정규칙 조문 상세에는 안내 없음",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278740:JO0086"},
        "asserts": [
            {"kind": "field_equals", "path": "article_effective_notice", "value": "<missing>"},  # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
        ],
    },
]

LEVEL_B_PROMPTS = [
    {
        "category": "재현 게이트 D — 제27조의3 조문 시행일(v0.57.0 문안 verbatim)",
        "probe_prompt": "중소기업 기술혁신 촉진법 제27조의3은 언제부터 시행된 조문인지 도구로 확인해서 알려줘.",
        "expect_behavior": "2026-05-26(법률 제21704호)을 도구 근거로 답함. 2026-07-01을 조문 시행일로 답하면 실패.",
    },
    {
        "category": "일반화 — 수기 고지 없는 무변경 조문",
        "probe_prompt": "국가연구개발혁신법 제1조는 언제부터 시행된 조문인지 도구로 확인해서 알려줘.",
        "expect_behavior": "2021-01-01(법률 제17343호 제정 판본)을 근거로 답함. 2026-10-02를 조문 시행일로 답하면 실패.",
    },
    {
        "category": "분리 시행 — 날짜 단정 금지",
        "probe_prompt": "국가연구개발혁신법 제2조는 언제부터 시행된 조문인지 도구로 확인해서 알려줘.",
        "expect_behavior": "법률 제21421호가 2026-06-11·2026-09-11 분리 시행이라 부칙 확인이 필요하다고 답함. "
                           "한 날짜를 조문 시행일로 단정하면 실패.",
    },
]
