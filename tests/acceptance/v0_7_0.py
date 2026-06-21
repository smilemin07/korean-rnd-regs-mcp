"""v0.7.0 배포 전 LIVE acceptance spec — 「조문(JO) 발견성 갭 해소 — 문서 레벨 조문 목록」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류는 5가지로 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로(path) 값이 value와 같음(점표기+리스트 인덱스).  [WARN — 차단 안 함]

★v0.7.0의 특수성 — 문서 레벨 articles 목록 조립·dedup·숫자필터·size 백스톱은 pytest가 결정론으로 하드게이트
  (test_doc_level_articles_listing_v070, *_skips_nondigit_and_dedups_v070, *_truncation_backstop_v070,
   *_listing_admrul_flat_v070). 아래 LIVE CHECKS는 (a) 실제 OpenAPI 응답에서 문서 레벨 articles 목록이
   나타나고, v0.6.0 eval에서 외부 우회를 유발했던 admrul 평면 schema의 특정 조문(제2조)이 이제 JO
   provision_id로 발견 가능한지(field_equals=WARN), (b) 조문 수 최대 규정(117조문)에서도 목록이 나오는지,
   (c) 기존 검색 무회귀(fetched_ok/returned_not_below=BLOCK 후보)를 확인한다.
  - get_provision_detail("admrul:2100000251982") = 산업기술혁신사업 공통 운영요령 문서 레벨
    = v0.6.0 라이브 eval에서 호스트가 제2조(JO0002)를 못 찾아 외부 우회한 바로 그 규정(평면 schema).
      이제 articles 목록에 제1조·제2조가 JO provision_id로 노출되어야 한다.
  - get_provision_detail("admrul:2100000278740") = 연구개발비 사용 기준 문서 레벨
    = 조문 수 최대(117조문)·size 백스톱 경계. articles 목록 첫 항목이 JO0001로 노출되어야 한다(절단은 미발동).

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "발견성 갭 해소 LIVE — 평면 admrul 문서 레벨 articles 목록에 제2조(JO0002)가 발견 가능(v0.6.0 eval 외부우회 규정)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000251982"},   # 산업기술혁신사업 공통 운영요령 doc-level
        "asserts": [
            {"kind": "field_equals", "path": "articles.0.provision_id", "value": "admrul:2100000251982:JO0001"},  # WARN
            {"kind": "field_equals", "path": "articles.1.provision_id", "value": "admrul:2100000251982:JO0002"},  # WARN — 제2조 발견 가능
            {"kind": "field_equals", "path": "articles.1.label", "value": "제2조"},                               # WARN
        ],
    },
    {
        "name": "size 백스톱 경계 LIVE — 조문 수 최대(117조문) 규정도 문서 레벨 articles 목록 노출(절단 미발동)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278740"},   # 연구개발비 사용 기준 doc-level(117조문)
        "asserts": [
            {"kind": "field_equals", "path": "articles.0.provision_id", "value": "admrul:2100000278740:JO0001"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 광역 '연구개발비' 도달·recall(문서 레벨 articles 추가가 기존 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 5}]                       # recall net (block 후보)
        ),
    },
    {
        "name": "skip·latency 모니터 — N=36 cold tail 허용(WARN only). doc-level 조립 변경이 평소 경로를 안 깼는지",
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
# ★v0.7.0의 초점 = '호스트가 특정 조문을 찾을 때 문서 레벨 articles 목록을 써서 JO를 발견하고
#   외부(law.go.kr)로 우회하지 않는가'. v0.6.0 eval에서 외부 우회가 실관측된 바로 그 시나리오(평면 admrul 특정조문).
LEVEL_B_PROMPTS = [
    {
        "category": "flat-admrul specific-article discoverability (v0.6.0 eval 외부우회 재현 케이스)",
        "probe_prompt": "산업기술혁신사업 공통 운영요령 제2조(용어의 정의)의 정의 항목들을 빠짐없이 정리해줘",
        "expect_behavior": "호스트가 (1) 문서 레벨 get_provision_detail(unit_id 없이)로 articles 목록을 받아 제2조의 "
                           "provision_id(admrul:…:JO0002)를 확인한 뒤 (2) 그 provision_id로 본문을 조회해 전문 인용. "
                           "외부 law.go.kr·웹검색으로 우회하지 않음(v0.6.0 eval에서 관측된 외부 우회가 사라져야 함).",
    },
    {
        "category": "law nested-schema specific-article (대조군 — search도 매칭되던 경로 무회귀)",
        "probe_prompt": "국가연구개발혁신법 제13조(연구개발과제의 보안과제 지정)의 요건을 조문 근거와 함께 정리해줘",
        "expect_behavior": "법령(중첩 schema)은 종전처럼 search 또는 문서 레벨 articles 목록 어느 경로로도 제13조 JO를 찾아 "
                           "get_provision_detail로 전문 인용. 외부 우회 없음(무회귀).",
    },
]
