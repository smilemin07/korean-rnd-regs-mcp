"""v0.62.0 배포 전 LIVE acceptance spec — 원격 서버 의존성 보안 패치(requirements.lock 2행 교체).

읽는 법(비프로그래머용): 이번 릴리스는 앱 코드와 도구 응답을 바꾸지 않습니다(contract 0.38.0 유지·입력 스키마 무변·재연결 불요).
바뀌는 것은 원격 서버 이미지의 의존성 2개(opentelemetry-api 1.44.0→1.45.1, certifi 2026.7.22→2026.10.23)뿐입니다.
그래서 이 spec은 v0.61.0 spec(= v0.60.0 문안)의 문안·기준값을 그대로 다시 보는 무회귀 확인입니다.
새 의존성 자체(tracestate 처리·인증서 목록)는 후보 컨테이너 게이트가 맡습니다. 이 러너는 로컬 venv로 돌므로
lock 버전 확인 용도가 아닙니다.

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
        "category": "무회귀 — 제27조의3 조문 시행일(v0.60.0 재현 게이트 D 문안 verbatim)",
        "probe_prompt": "중소기업 기술혁신 촉진법 제27조의3은 언제부터 시행된 조문인지 도구로 확인해서 알려줘.",
        "expect_behavior": "2026-05-26(법률 제21704호)을 도구 근거로 답함. 2026-07-01을 조문 시행일로 답하면 실패.",
    },
    {
        "category": "무회귀 — 매뉴얼 경로(집계 미들웨어 통과)",
        "probe_prompt": "국가연구개발혁신법 매뉴얼에서 연구개발비 사용 실적 보고에 관한 절을 도구로 찾아 그 절 본문을 확인해서 요약해줘.",
        "expect_behavior": "search_manual·get_manual_section 결과를 근거로 답함. 도구 오류·빈 응답이면 실패.",
    },
]
