"""v0.65.0 배포 전 LIVE acceptance spec — 원격 서버 세션 누적 해소(requirements.lock mcp 1.29.0 → 1.30.0 1행).

읽는 법(비프로그래머용): 이번 릴리스는 앱 코드와 도구 응답을 바꾸지 않습니다(contract 0.40.0 유지·입력 스키마 무변·재연결 불요).
바뀌는 것은 원격 서버 이미지의 mcp 1행뿐이고, 그 효과(세션 30분 유휴 만료 기본 적용·동시 1만 개 상한)는 원격(HTTP) 전송 계층에서만
나타납니다. 이 러너는 로컬 stdio·env 키로 도구를 직접 부르므로 세션 한도와 무관합니다. 그래서 아래 CHECKS는 v0.64.0 spec의
무회귀 체크를 문안·기준값 그대로 다시 보는 것입니다. 세션 한도는 단위 테스트(tests/test_v0650_session_limits.py)·로컬 세션
스모크·호스트 사전 시험·후보 컨테이너 게이트가 맡습니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 기록용]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

_N_27_3 = '국가법령정보 조문별 변경 이력(2026-10-28 확인)상 조회된 판본까지 이 조문의 최근 변경 기록은 법률 제21704호(2026-05-26 공포)이고, 그 판본은 2026-05-26에 시행되었습니다. 그 부칙에서 조문별 시행일을 따로 정했다면 그에 따릅니다. effective_date(2026-07-01)는 조회된 법령 판본 전체의 시행일입니다.'
_N_INNO_2 = "국가법령정보 조문별 변경 이력(2026-10-28 확인)상 조회된 판본까지 이 조문의 최근 변경 기록은 법률 제21421호(2026-03-10 공포)입니다. 그 판본의 시행일은 2026-06-11·2026-09-11로 나뉘어 있습니다. 그 개정의 부칙 시행일 조항 원문은 다음과 같습니다.\n제1조(시행일) 이 법은 공포 후 6개월이 경과한 날부터 시행한다. 다만, 제2조ㆍ제17조제1항ㆍ제18조ㆍ제32조의 개정규정 및 부칙 제3조는 공포 후 3개월이 경과한 날부터 시행한다.\n이 원문은 위 최근 개정으로 바뀐 부분의 시행일을 정합니다. 단서가 항·호나 '…에 관한 부분'처럼 조문 일부에만 걸리면 부분별로 나누어 답하십시오. 단서가 이 조문이 아닌 다른 조문만 들면 이 조문에는 본문의 시행일이 적용됩니다. 조문 번호는 가지 번호(예: 제17조의2)까지 같을 때만 해당합니다. '공포 후 N개월' 같은 기간은 위 시행일 목록에서 대응하는 날짜를 고르고, 목록에 없는 날짜를 계산해 만들지 마십시오. 목록 중 아직 오지 않은 날짜는 시행 예정일입니다. 위 원문만으로 정할 수 없으면 한 날짜로 단정하지 마십시오. effective_date(2026-10-02)는 조회된 법령 판본 전체의 시행일입니다."
_N_INNO_1 = '국가법령정보 조문별 변경 이력(2026-10-28 확인)상 조회된 판본까지 이 조문의 최근 변경 기록은 법률 제17343호(2020-06-09 공포)이고, 그 판본은 2021-01-01에 시행되었습니다. 그 부칙에서 조문별 시행일을 따로 정했다면 그에 따릅니다. effective_date(2026-10-02)는 조회된 법령 판본 전체의 시행일입니다.'
_N_IND_6 = '국가법령정보 조문별 변경 이력(2026-10-28 확인)상 조회된 판본까지 이 조문의 최근 변경 기록은 법률 제21065호(2025-10-01 공포)입니다. 그 판본의 시행일이 2025-10-01·2026-01-02로 나뉘어 있어, 이 조문의 시행일은 이 응답으로 정할 수 없으니 그 부칙에서 확인하십시오. effective_date(2026-09-18)는 조회된 법령 판본 전체의 시행일입니다.'

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
        "name": "★표적 — 혁신법 제2조(분리 시행 판본 + 부칙 시행일 조항 원문)",
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
        "name": "★표적 — 산업기술혁신 촉진법 제6조(타법개정 분리 시행 = v0.60.0 문장 그대로)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:284363:JO0006"},
        "asserts": [
            {"kind": "field_equals", "path": "article_effective_notice", "value": _N_IND_6},  # WARN
        ],
    },
    {
        "name": "★표적 — 검색어 201자는 invalid_query(조회 0건)",
        "tool": "search_provision",
        "args": {"query": "연" * 201},
        "asserts": [
            {"kind": "field_equals", "path": "errors.0.code", "value": "invalid_query"},  # WARN
            {"kind": "field_equals", "path": "total", "value": 0},                         # WARN
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
        "category": "★표적 — claude.ai·ChatGPT 웹 커넥터에서 30분 이상 유휴 뒤 같은 대화 재질의(보안 강화 시리즈 C단계 게이트 ③)",
        "probe_prompt": "(1) 국가연구개발혁신법 제2조 정의를 도구로 확인해서 알려줘. → 35분 이상 아무 입력 없이 기다린 뒤 같은 대화에서 → (2) 같은 법 제32조의 요지를 도구로 확인해서 알려줘.",
        "expect_behavior": "(2)에서 수작업 재연결 없이 도구를 다시 호출해 원문 근거로 답함. 커넥터 오류·연결 끊김 안내·도구 없이 학습지식으로 답하면 실패.",
    },
    {
        "category": "무회귀 — 혁신법 제2조 조문 시행일(v0.60.0 eval P4 문안)",
        "probe_prompt": "국가연구개발혁신법 제2조는 언제부터 시행된 조문인지 도구로 확인해서 알려줘.",
        "expect_behavior": "2026-06-11을 부칙 단서 근거와 함께 답함. 2026-06-10·2026-09-11 단정이나 사용자에게 확인을 미루면 실패.",
    },
]
