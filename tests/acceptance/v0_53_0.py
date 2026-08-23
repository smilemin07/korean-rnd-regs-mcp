"""v0.53.0 배포 전 LIVE acceptance spec — HTTP 클라이언트 의존성 조합 고정(Dockerfile requests·urllib3 핀).

읽는 법(비프로그래머용): 이번 릴리스는 Docker 이미지를 만들 때 설치되는 HTTP 클라이언트 라이브러리
두 종(requests 2.34.2·urllib3 2.7.0)의 버전을 라이브 실측값으로 고정할 뿐, 서버 코드·도구 응답·입력
스키마·검색/랭킹·규정 데이터·매뉴얼 트랙은 전부 무변입니다(contract 0.36.0 유지·재연결 불요).

★본 spec이 검증하는 것 = 도구 경로 무회귀(Level A)뿐입니다. 핀의 효과(이미지 패키지 구성이 라이브와
같은가)는 이 러너로 검증할 수 없습니다(러너는 로컬 venv에서 도구를 in-process로 호출하며 Docker
이미지를 만들지 않음). 핀 검증은 배포 게이트의 별도 단계(운영 실측)로 수행합니다:
  ① pytest `tests/test_dockerfile_pins.py` — Dockerfile 텍스트의 핀 6종이 기대값과 일치.
  ② NAS 후보 이미지 빌드(`docker build --network host`) 후 `pip freeze`를 라이브 컨테이너(v0.52.0)와
     전수 대조 — ★차이 1건이라도 있으면 교체 중단(핀이 no-op임을 증명해야 통과).
     [2026-08-23 실측] 1차 후보에서 cyclopts 4.23.1→4.23.2 드리프트 1건 검출 → 규칙대로 교체 중단하고
     라이브값 `cyclopts==4.23.1` 핀 1건을 추가(서버 런타임 미import·fastmcp CLI 전용)한 뒤 재빌드로 0건 재증명.
     ★규율: 이후 재빌드에서 또 다른 드리프트가 나오면 핀을 늘리지 말고 게이트 중단 → 전체 lock 전환 또는 별도 예외심사.
     기반 이미지 digest·Python patch 버전은 라이브와 동일해야 한다(아래 ★).
  ③ 후보 컨테이너(PORT=18080·FASTMCP_HOST=127.0.0.1·host network) 부팅 406·initialize
     serverInfo.version=0.53.0·cold LIVE 66규정 fan-out(done 66·errors 0)·docker ps STATUS가
     Restarting이 아님.
  ④ 스왑 전 — 롤백 태그 `:0.52.0-rollback`을 현행 라이브 **이미지 ID(091dc91e347d)**에서 생성
     (컨테이너 ID 아님·latest 재지정 전에). 후보 이미지 `pip check` 통과.
  ⑤ 스왑 후 — 외부 URL 정상·무키 406(도달 지표)·로그 `oc=` 0건(키 값 미출력·패턴 개수만).
  ⑥ 24h 관측 판정 기준 4항(로드맵 §2): (1)신규 예외 시그니처 0 (2)parse_failed·timeout·skipped 비율이
     이전 기준 대비 증가 없음 (3)검색 결과 수·지연의 설명되지 않는 회귀 없음 (4)영향 경로(LIVE 조회)가
     실제로 호출된 기록 존재. 하나라도 위반 시 다음 단계 중단 + 롤백 이미지 compose down/up.
  ★기반 이미지 digest 또는 Python patch가 라이브(2026-08-23: sha256:b04b5d72…·3.13.13)와 다르면 이번
     단일 의도 릴리스를 중단한다(pip freeze는 Python·OS 계층 변화를 잡지 못함 — Codex 반영).

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 기록용]
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
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 기록용
        ],
    },
    {
        "name": "무회귀 — 혁신법 문서레벨(283413·v0.51.0 시행일 게이트 유지 — 빌드 층 변경이 도구 경로를 건드리지 않았다는 증거)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283413"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "effective_date", "value": "2026-08-20"},    # WARN
            {"kind": "field_equals", "path": "fetched_detail_effective_date_notice", "value": "<missing>"},  # WARN
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). 이번 릴리스는 도구 응답·호스트 AI 발화에 영향을 주는 변경이 없으므로
# 무회귀 문안 1건만 verbatim 재사용(v0.48.0~v0.52.0 동일 — [[eval-probe-design-standard]]).
LEVEL_B_PROMPTS = [
    {
        "category": "무회귀 — cold 광역 fan-out 경로(v0.48.0 무회귀 B verbatim)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "66규정 fan-out 완주·기존 규정(연구개발비 사용 기준·시행령) 중심 유지 + "
                           "citation·footer 무회귀. 부분 timeout·누락 규정·오류 문면이 새로 보이면 "
                           "회귀 의심.",
    },
]
