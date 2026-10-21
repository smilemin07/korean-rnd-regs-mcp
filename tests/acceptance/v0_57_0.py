"""v0.57.0 배포 전 LIVE acceptance spec — 틀린 API Key 판별과 조용한 구판 폴백 기록.

읽는 법(비프로그래머용): 이번 릴리스는 '틀린 키'와 '구판 폴백'이라는 실패 경로만 바꿉니다(contract 0.36.0
유지·응답 필드 신설 0·재연결 불요·규정 데이터 무변경).
  ①틀린 API Key(OC): 법령정보센터가 HTTP 200에 '사용자 정보 검증에 실패하였습니다'를 주던 것을 종전
    not_found 66건 대신 auth_failed 1건(확인 안내 + 규정 수)으로 보여 준다. 그 실패도 300초 기억한다.
  ②eflaw 인증 실패도 공포 합본으로 폴백(종전 실제 동작 보존 — v0.55.0 '즉시 전파' 대체).
  ③resolve 일치 0행 폴백에 WARNING 로그(제목·첫 행 제목), fan-out 요약 줄에 resolve_failed·auth_failed.

★이 러너는 정상 키로만 돈다. 그래서 아래 CHECKS는 '정상 키에서 아무것도 바뀌지 않았다'(무회귀)를 본다 —
판별이 정상 응답을 인증 오류로 잘못 읽으면(오탐) 전 이용자 장애이므로, 정상 키의 auth_failed 0건이 핵심이다.
absent_error_code auth_failed는 WARN 종류(assert 5종 동결)이지만, ★1건이라도 나오면 사람이 BLOCK으로 판정한다.

운영 게이트(러너 밖·사람이 실행·결과만 기록):
  G1. 정상 키 run.py 0.57.0 → fetched_ok·returned_not_below PASS + 전 체크 auth_failed 0건.
  G2. 가짜 키 1회 — 키 문자열은 명백한 더미(예: zzinvalid0probe)·출력 금지·1회만:
      LAW_API_KEY=<더미>로 search_provision('연구개발비') → errors가 auth_failed 1건, rule_set_id 없음,
      메시지에 '법령 35·행정규칙 31개 규정', results 0, standard_footer 존재. 두 번째 호출 wall_ms가 수 ms
      (실패 기억 = 네트워크 0). suggest 3키워드 → auth_failed 1건·keyword 없음.
      (2026-10-21 구현 실측: search 7,292자 → 848자 · suggest 24,540자 → 1,033자.)
  G3. 후보 컨테이너 로그에 'event=search_fanout_summary … resolve_failed=0 auth_failed=0'(정상 키) 확인.
  G4. 판별 문구 생존 확인 — 법령정보센터가 문구를 바꾸면 판별이 조용히 꺼져 종전 not_found로 돌아간다
      (안전 방향이지만 검출 수단이 이것뿐). 배포 때마다 G2를 반복한다.

정직 선언(러너 한계): 틀린 키 경로·eflaw 인증 폴백·0행 경고는 이 러너로 재현할 수 없다(정상 키 고정·상위
API를 고장 낼 수 없음). 그 경로는 pytest 가드(tests/test_auth_body_v0570.py·test_stage_eflaw.py)가 맡고,
틀린 키 실경로는 운영 게이트 G2가 맡는다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 기록용]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
(v0.57.0 러너 보정: rule_set_id 없는 auth_failed 항목이 있으면 fetched_ok는 미도달로 본다 — 거짓 PASS 차단.
 결과 0건이고 오류가 전부 infra 코드면 infra[WARN]로 본다.)
"""

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 66규정 fan-out(릴리스 간 동일 문안) + 정상 키 auth_failed 0",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                   # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 10},                                  # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "auth_failed"},                        # ★1건이라도 = 사람 BLOCK(오탐)
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 기록용
        ],
    },
    {
        "name": "무회귀 — law 상세(eflaw 경로) 혁신법 시행령 문서레벨 = auth_failed 0·eflaw 본문",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288773"},
        "asserts": [
            {"kind": "absent_error_code", "value": "auth_failed"},                        # ★오탐 감시
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "articles_count", "value": 71},              # WARN — 2026-10-21 실측(288335 시행 본문)
        ],
    },
    {
        "name": "무회귀 — admrul 상세 처리규정(v0.56.0 표적 B 재사용) = auth_failed 0",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000285280:JO001702"},
        "asserts": [
            {"kind": "absent_error_code", "value": "auth_failed"},                        # ★오탐 감시
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "무회귀 — suggest 경로(오류 fan-in 변경 지점) = 후보 반환·auth_failed 0",
        "tool": "suggest_review_sources",
        "args": {"question": "연구개발비 사용 기준을 위반하면 어떤 제재처분을 받나요?",
                 "keywords": ["연구개발비", "제재처분", "사용 기준"]},
        "asserts": [
            {"kind": "absent_error_code", "value": "auth_failed"},                        # ★오탐 감시
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
            {"kind": "latency_under", "value": 30.0},                                     # WARN — 기록용
        ],
    },
    {
        "name": "무회귀 — 매뉴얼 경로(키 무관) 정상",
        "tool": "search_manual",
        "args": {"query": "제재부가금"},
        "asserts": [
            {"kind": "absent_error_code", "value": "auth_failed"},                        # WARN
        ],
    },
]

LEVEL_B_PROMPTS = [
    {
        "category": "★표적 A — 틀린 API Key 안내(배포 후 eval 전용 커넥터·더미 키로 1회)",
        "probe_prompt": "국가연구개발혁신법 제32조 제재부가금 조항 원문을 도구로 확인해서 알려줘.",
        "expect_behavior": "(더미 oc= 커넥터에서) 호스트가 '규정이 없다·결과 없음'이 아니라 API Key(OC)·신청 "
                           "승인·등록 설정 확인이 필요하다고 안내. 일반 학습지식으로 조문을 지어내면 실패. "
                           "★실키 커넥터·계정 설정은 바꾸지 않는다(Andy 승인 후 임시 커넥터로만).",
    },
    {
        "category": "무회귀 B — 과기정통부 처리규정 특수관계인(v0.56.0 eval C1 정정 문안 동결·verbatim)",
        "probe_prompt": "과학기술정보통신부 소관 연구개발사업에서 연구책임자나 참여연구원의 배우자·친족 등 "
                        "특수관계인을 과제에 참여시킬 때 지켜야 하는 규정이 있는지 도구로 원문을 확인해서 알려줘.",
        "expect_behavior": "msit_rnd_processing 신판(2100000285280) 제17조의2 인용 — 주관연구개발기관의 장 검토와 "
                           "장관 또는 전문기관의 장의 최종 승인. 구판(훈령 제242호)·부재 안내·날조는 실패.",
    },
    {
        "category": "무회귀 C — 광역 검토 경로(v0.55.0·v0.56.0 무회귀 문안 verbatim)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "시행령·사용 기준·별지 서식 인용 유지(검색 희석 0). 결과 수 감소·도달 실패가 보이면 "
                           "이번 오류 조립 변경의 부수 효과를 의심한다.",
    },
    {
        "category": "재현 게이트 D — 법령 판본 시행일을 조문 시행일로 읽는 호스트 행동(관측 2회·조치 없음)",
        "probe_prompt": "중소기업 기술혁신 촉진법 제27조의3은 언제부터 시행된 조문인지 도구로 확인해서 알려줘.",
        "expect_behavior": "제27조의3 자체 시행일(2026-05-26, 부칙 <제21704호> 제1조 '공포한 날부터')과 법 전체 "
                           "현행 판본 시행일을 구분. 판본 날짜를 조문 시행일로 단정하면 재현 1회로 기록(3회 중 2회 "
                           "재현 시에만 조치 검토).",
    },
]
