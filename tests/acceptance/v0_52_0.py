"""v0.52.0 배포 전 LIVE acceptance spec — HTTP 수신 인터페이스 노출면 축소(FASTMCP_HOST 존중).

읽는 법(비프로그래머용): 이번 릴리스는 --http 모드의 바인딩 주소 결정만 바꿉니다(main.py
_resolve_http_bind_host — FASTMCP_HOST strip·빈값/공백은 호환 기본 0.0.0.0). 도구 응답·입력 스키마·
검색/랭킹·규정 데이터·매뉴얼 트랙은 전부 무변(contract 0.36.0 유지·재연결 불요).

★본 spec이 검증하는 것 = 도구 경로 무회귀(Level A)뿐입니다. 바인딩 축소 자체는 이 러너로 검증할 수
없습니다(러너는 도구를 in-process로 호출하며 HTTP 소켓을 열지 않음). 바인딩 검증은 배포 게이트의
별도 단계(운영 실측)로 수행합니다:
  ① 로컬 부팅 스모크 — FASTMCP_HOST=127.0.0.1 PORT=<free> --http 기동 후 127.0.0.1:<port>/mcp 406 +
     외부 인터페이스 IP:<port> 연결 거부.
  ② NAS 후보 컨테이너(PORT=18080·FASTMCP_HOST=127.0.0.1·host network) — docker ps STATUS가
     Restarting이 아님 · NAS 내부 127.0.0.1:18080 406 · ★NAS 외부 LAN 클라이언트(Andy Mac)에서
     NAS LAN IP 192.168.0.14:18080이 406이 아니라 연결 거부/타임아웃(406이면 BLOCK) · netstat에
     127.0.0.1:18080 LISTEN만(0.0.0.0:18080 없음).
     ★Tailscale IP(100.90.114.76) 경유 호출은 판정 지표가 아님 — Synology Tailscale은
     --tun=userspace-networking로 동작해 tailnet 요청을 127.0.0.1로 프록시하므로 loopback 바인딩 후에도 406이
     정상이다(2026-08-22 실측·사전 게이트의 전제 오류로 교체). tailnet 도달은 별도 잔여 노출로 기록.
  ③ 스왑 후 — 0.0.0.0:8080 LISTEN 소멸 + 127.0.0.1:8080 단독 · 외부 URL 정상 · 무키 406 유지.
  바인딩 결정 로직 자체는 pytest(test_tools.py *_v0520 5종 — main() 배선 잠금 포함)가 잠급니다.

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
        "name": "무회귀 — 혁신법 신판 문서레벨(283413·v0.51.0 시행일 게이트 유지 — transport 변경이 도구 경로를 건드리지 않았다는 증거)",
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
# 무회귀 문안 1건만 verbatim 재사용(v0.48.0~v0.51.0 동일 — [[eval-probe-design-standard]]).
LEVEL_B_PROMPTS = [
    {
        "category": "무회귀 — cold 광역 fan-out 경로(v0.48.0 무회귀 B verbatim)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "66규정 fan-out 완주·기존 규정(연구개발비 사용 기준·시행령) 중심 유지 + "
                           "citation·footer 무회귀. 부분 timeout·누락 규정·오류 문면이 새로 보이면 "
                           "회귀 의심.",
    },
]
