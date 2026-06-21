"""v0.6.0 배포 전 LIVE acceptance spec — 「get_provision_detail 조문(JO) 응답 크기 계층화」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류는 5가지로 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로(path) 값이 value와 같음.                        [WARN — 차단 안 함]

★v0.6.0의 특수성 — 조문 size-tier 3-tier 분기·백스톱은 pytest가 결정론으로 하드게이트
  (test_build_article_detail_*_v060, test_get_provision_detail_small_article_unchanged_v060,
   test_article_demotes_to_oversized_when_injection_exceeds_budget_v060). 그리고 ★배포 전 증거 게이트
   실측(36규정 1,125 조문)에서 어떤 조문도 임계(15,700자)를 넘지 않아 현행 LIVE는 전건 tier-1
   (최대 직렬화 12,180자=산업기술 시행령 제57조) — 즉 이 변경은 현재 거동을 바꾸지 않는 예방 가드다.
  아래 LIVE CHECKS는 (a) 가장 큰 실조문이 size-tier 도입 후에도 여전히 plain_text_verbatim(=가드가
   실데이터를 잘못 강등하지 않음, field_equals=WARN)과 (b) 기존 검색 무회귀(fetched_ok/returned_not_below
   =BLOCK 후보)를 확인한다.
  - get_provision_detail("admrul:2100000251982:JO0002") = 산업기술혁신사업 공통 운영요령 제2조(용어의 정의)
    = content 단독 최대(9,253자, 평면 schema). 임계(15,700) 미달이라 plain_text_verbatim 유지여야 한다.
  - get_provision_detail("law:285891:JO0057") = 산업기술혁신 촉진법 시행령 제57조(권한의 위임·위탁)
    = 직렬화 envelope 최대(12,180자, structured 8,234). 임계 미달이라 plain_text_verbatim + article_structure 유지여야 한다.

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "size-tier 무회귀 LIVE — content 최대 실조문(산업기술 운영요령 제2조 9,253자)이 여전히 plain_text_verbatim",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000251982:JO0002"},   # industry_tech_operating 제2조(용어의 정의)
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 가드가 실데이터 미강등
        ],
    },
    {
        "name": "size-tier 무회귀 LIVE — 직렬화 최대 실조문(산업기술 시행령 제57조 envelope 12,180자) 전문+structure 유지",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285891:JO0057"},   # industry_tech_decree 제57조(권한의 위임·위탁)
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — structure-heavy도 tier-1
        ],
    },
    {
        "name": "무회귀 — 광역 '연구개발비' 도달·recall(조문 size-tier 추가가 기존 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 5}]                       # recall net (block 후보)
        ),
    },
    {
        "name": "skip·latency 모니터 — N=36 cold tail 허용(WARN only). 조문 분기 변경이 평소 경로를 안 깼는지",
        "tool": "search_provision",
        "args": {"query": "협약 변경"},
        "asserts": [
            {"kind": "absent_error_code", "value": "timeout"},   # WARN — 비결정 skip 허용(정상 cold tail)
            {"kind": "latency_under", "value": 16.0},            # WARN — cold tail 변동 허용
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인) — 호스트 LLM 행동(비결정). 게이트 판정은 사람.
# ★v0.6.0은 예방 가드(현행 36규정 조문 중 overflow 0건)라 'oversized 강등'은 실데이터로 트리거되지 않는다.
#   따라서 Level B의 초점은 '개선이 작동했나'가 아니라 '대형 조문이 size-tier 도입 후에도 무회귀로
#   끝까지 정확히 전달되나'(truncation·누락 없이 전문 인용)다.
LEVEL_B_PROMPTS = [
    {
        "category": "largest-flat-article no-regression (content 최대)",
        "probe_prompt": "산업기술혁신사업 공통 운영요령 제2조(용어의 정의)의 정의 항목들을 가능한 한 빠짐없이 정리해줘",
        "expect_behavior": "get_provision_detail로 제2조를 조회해 9,000자대 본문(다수 호의 정의)을 전문(plain_text_verbatim)으로 받아 "
                           "정확히 인용/정리함. 조문이 잘리거나 article_structure 누락으로 항·호가 깨지지 않음(size-tier 도입 무회귀 확인). "
                           "content_format은 plain_text_verbatim(oversized_pointer 아님).",
    },
    {
        "category": "structure-heavy-article no-regression (직렬화 최대)",
        "probe_prompt": "산업기술혁신 촉진법 시행령 제57조(권한의 위임·위탁)의 위임·위탁 사항을 항·호 구조 그대로 정리해줘",
        "expect_behavior": "제57조를 조회해 중첩 항/호(structured 8,234자)를 article_structure로 받아 구조 그대로 전달. "
                           "content_format=plain_text_verbatim 유지(직렬화 12,180자로 임계 미달이라 강등 없음). 본문·구조 무손실.",
    },
]
