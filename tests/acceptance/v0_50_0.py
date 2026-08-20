"""v0.50.0 배포 전 LIVE acceptance spec — 규정 탐색·조회 실패 복구 안내 정비(§5.41).

읽는 법(비프로그래머용): 이번 릴리스는 문면·프롬프트-only입니다 — 런타임 분기·데이터·응답
필드 구조·오류 코드·검색/랭킹 알고리즘이 전부 무변이고, 바뀌는 것은 ①upcoming_revision
문면 후반부 ②규정 상세 not_found 문면 ③용어 드리프트 재검색 힌트(프롬프트 2표면)뿐입니다
(contract 0.34.0 → 0.35.0·입력 스키마 무변·재연결 불요).

Level A 표적 3가지:
  ①광역 fan-out 무회귀(릴리스 간 동일 문안)
  ②not_found 신 문면 LIVE 결정론 확인 — 구 ID(admrul:2100000195842·v0.49.0에서 신 ID로
    교체된 「국가연구개발정보처리기준」 구판)를 직접 조회하면 not_found와 함께 재검색
    복구 지시가 담긴 신 문면이 그대로 반환되어야 합니다(문면은 결정론 문자열 —
    field_equals 전체 일치 잠금).
  ③S1 힌트가 안내하는 목적지 실재 확인 — 현행 용어 '재검토 요청' 검색이 혁신법
    (innovation_act)에 실제 도달하는지(힌트 문구가 가리키는 재검색 경로의 LIVE 실효성).
    구 용어 '제재처분 이의신청'의 미도달 자체는 서버 무변이라 검증하지 않습니다.

★S3-①(upcoming_revision 신 문면)의 LIVE 검증은 확인 불가 — v0.49.0 manifest 현행화로
현재 66규정에 시행일 미래인 새 판본(pending) 표적이 없습니다(2026-08-20 실측). 발화
경로·신 문면은 pytest(test_tools.py의 _resolve_status_fields equality 잠금)가 전담하며,
본 spec에서 PASS로 기록하지 않습니다(Codex 계획 검토 반영 — 표적 부재를 PASS로 오기록
금지). 다음에 어떤 규정이든 개정 예정 행이 lawSearch에 노출되면 그때 라이브로 관측됩니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 66규정 fan-out 대형 규정 도달 + recall(릴리스 간 동일 문안)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                   # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 10},                                  # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — 대량이면 infra 여부 사람 판정
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 기록용
        ],
    },
    {
        "name": "표적 — 구 ID not_found 신 문면(§5.41 — 내부 용어 제거 + 재검색 복구 지시·결정론 잠금)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000195842"},
        "asserts": [
            {"kind": "field_equals", "path": "errors.0.code", "value": "not_found"},      # WARN — 구 ID는 지원 목록 밖(v0.49.0 기지 성질)
            {"kind": "field_equals", "path": "errors.0.message", "value": (
                "지원 규정 목록에 admrul:2100000195842 항목 없음 — 규정 개정으로 "
                "문서 ID가 바뀐 구 ID이거나 미지원 규정일 수 있으니, 질문 핵심 용어로 "
                "search_provision을 재호출해 현행 provision_id를 확인하십시오"
            )},                                                                            # WARN — ★신 문면 전체 일치(구 문면 'manifest에 …'가 나오면 신 코드 미배포 신호)
            {"kind": "latency_under", "value": 16.0},                                     # WARN — resolve fallback 순회 포함 기록용
        ],
    },
    {
        "name": "표적 — S1 힌트 목적지 실재: 현행 용어 '재검토 요청' 검색이 혁신법 도달(전건 WARN — v0.50.0 코드 무변·LIVE 코퍼스 의존이라 BLOCK 후보 부적격[false-block-safe])",
        "tool": "search_provision",
        "args": {"query": "재검토 요청"},
        "asserts": [
            {"kind": "field_equals", "path": "results.0.rule_set_id", "value": "innovation_act"},  # WARN — 도달 검증(fetched_ok는 '오류 부재'만 검사·v0.47.0 학습)
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). 표적 = 호스트가 신 문면·힌트를 실제로 소비해
# 복구 행동으로 잇는가. S1 문안은 2026-08-19 intensive test C13 verbatim(A/B 비교 기준),
# 무회귀 문안은 v0.48.0 spec verbatim 재사용([[eval-probe-design-standard]]).
LEVEL_B_PROMPTS = [
    {
        "category": "표적 A — S1 용어 드리프트(intensive test C13 문안 verbatim·A/B 비교)",
        "probe_prompt": "국가연구개발사업에서 제재처분을 받았을 때 이의신청은 며칠 안에 해야 하나요? "
                        "근거 조문과 함께 알려줘.",
        "expect_behavior": "혁신법 제33조③(사전통지 후 20일 이내 재검토 요청) 도달 + '정식 명칭은 "
                           "재검토 요청' 구분. A/B 관측 포인트 = v0.48.0(힌트 부재)에서는 검색 3회 "
                           "재구성으로 도달 — 이번에는 더 적은 검색 횟수로 도달하는지. "
                           "제14조⑥ 10일을 제재처분 기한으로 제시하면 실패.",
    },
    {
        "category": "표적 B — S3-② 구 ID not_found 회복(v0.49.0 eval P3 문안 계열·신 문면 소비)",
        "probe_prompt": "get_provision_detail 도구를 admrul:2100000195842 로 호출해서 그 규정 내용을 "
                        "보여줘. 조회가 안 되면 왜 안 되는지 오류 내용을 그대로 알려주고, 현행 판을 "
                        "찾아서 무엇이 언제부터 시행 중인지 알려줘.",
        "expect_behavior": "신 문면('지원 규정 목록에 … search_provision을 재호출해 …') 인용 + "
                           "재검색으로 신 ID 2100000283100(2026-08-20 시행) 도달. 내부 용어 "
                           "'manifest'가 답변에 나오면 구 문면 잔존(실패). 구판 내용 날조 금지.",
    },
    {
        "category": "무회귀 C — cold 광역 fan-out 경로(v0.48.0 무회귀 B verbatim)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "66규정 fan-out 완주·기존 규정(연구개발비 사용 기준·시행령) 중심 유지 + "
                           "citation·footer 무회귀. 부분 timeout·누락 규정·오류 문면이 새로 보이면 "
                           "회귀 의심.",
    },
]
