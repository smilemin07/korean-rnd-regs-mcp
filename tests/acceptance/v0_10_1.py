"""v0.10.1 배포 전 LIVE acceptance spec — 「law 호(號) 아래 목(目) 본문 파싱 — 조문 content 완전성 보강」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.10.1의 특수성 — content-only 정확도 수정(live_api.py `_build_article_content`가 호 순회 내부에서 `<목내용>`을
  4-space indent로 content에 append). 응답 schema·필드·provision_id·검색/랭킹/fallback/fan-out/transport·공유파서 인터페이스 불변
  (목 텍스트를 기존 content 문자열에 포함시키는 완전성 수정 → contract_version 0.9.0 유지).
  - 따라서 LIVE acceptance(Level-A)의 본질 = (1)목 보유 조문이 목 append 후에도 size-tier 예산(15,700) 내에서 plain_text_verbatim 유지
    (size 무회귀) + (2)검색 fan-out 무회귀(목 추가가 latency/recall을 깨지 않음).
  - ★목 텍스트가 실제로 content에 수록되는지(소기업 3명 등) + 목 텍스트 검색 도달은 **5종 고정 assert로 substring 확인 불가** →
    배포 전 '측정 battery'(메인 스레드 직접 LIVE 프로브)가 검증: ① 목 보유 최대 조문 content 길이 vs 예산(tier 전환 목록)
    ② corp_lab_decree JO0006 content에 소기업/3명/연구개발부서/1명 포함 ③ "소기업 연구전담요원" 검색이 corp_lab_decree 매칭(목 보강 전엔 미매칭).
  - N=46 cold fan-out wall(예산 20s)은 이 로컬 하니스가 아니라 **배포 시 NAS 신이미지 cold 스모크**가 검증. latency_under는 WARN advisory.

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

CHECKS = [
    {
        "name": "목 보유 조문 size 무회귀 — corp_lab_decree 시행령 제6조(JO0006)가 목 append 후에도 plain_text_verbatim 유지",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:282915:JO0006"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # ★핵심 — 목 추가 후 budget 내 전문 유지(WARN advisory)
            {"kind": "absent_error_code", "value": "invalid_provision_id"},                       # WARN — JO0006 유효
            {"kind": "absent_error_code", "value": "parse_failed"},                               # WARN — 상위 API 장애 신호
            {"kind": "absent_error_code", "value": "not_found"},                                  # WARN — resolve·도달 정상
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(목 append가 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},   # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},      # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 10},                     # 실측 14(회귀=BLOCK 후보)
            {"kind": "absent_error_code", "value": "timeout"},               # WARN — fan-out skip 0 기대
            {"kind": "latency_under", "value": 16.0},                        # WARN — cold tail 변동 허용
        ],
    },
    {
        "name": "무회귀 — '기업부설연구소' corp_lab family 전건 도달(v0.10.0 회귀 가드)",
        "tool": "search_provision",
        "args": {"query": "기업부설연구소"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "corp_lab_act"},
            {"kind": "fetched_ok", "rule_set_id": "corp_lab_decree"},
            {"kind": "fetched_ok", "rule_set_id": "corp_lab_rule"},
            {"kind": "returned_not_below", "value": 3},                      # recall(회귀=BLOCK 후보)
            {"kind": "absent_error_code", "value": "timeout"},               # WARN
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.10.1은 목 content 완전성 — v0.10.0 eval에서 미수록이던 '기업유형별 연구전담요원 수'가
# 이제 도구 content로 grounded 인용되는지(개선 end-to-end) + 다른 규정 무회귀.
LEVEL_B_PROMPTS = [
    {
        "category": "★v0.10.1 개선 end-to-end — 목 수치 grounding",
        "probe_prompt": "기업부설연구소 인정 요건 중 기업유형별(소기업·중기업·중견기업·국외 등) 연구전담요원 최소 인원 수를 규정 근거(조문)와 함께 알려줘",
        "expect_behavior": "MCP get_provision_detail(law:282915:JO0006=시행령 제6조)의 content에 각 목(가.~사.)의 기업유형별 인원 수(소기업 3명 등)가 "
                           "이제 수록됨 → 호스트가 그 수치를 외부 웹 우회 없이 grounded 인용. ★v0.10.0 eval에서 호스트가 '각 목 미수록'으로 정직 고지했던 "
                           "바로 그 정보가 채워졌는지 = 본 수정의 핵심 목표. content_format=plain_text_verbatim(oversized 아님).",
    },
    {
        "category": "무회귀 — 다른 규정 grounding 정상",
        "probe_prompt": "국가연구개발혁신법상 연구개발비 사용 원칙을 조문 근거와 함께 알려줘",
        "expect_behavior": "혁신법/사용기준 관련 조문을 MCP로 검색·인용(외부 우회·stale 없음). 목 파싱 변경이 목 없는 조문의 기존 content를 회귀시키지 않았는지 확인.",
    },
]
