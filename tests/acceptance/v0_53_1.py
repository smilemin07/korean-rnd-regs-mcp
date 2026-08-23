"""v0.53.1 배포 전 LIVE acceptance spec — NAS 라이브 이미지 의존성 lock(requirements.lock 2단 설치 + 기반 digest 고정).

읽는 법(비프로그래머용): 이번 릴리스는 Docker 이미지를 "어떻게 만드는가"만 바꿉니다(의존성 71종을 lock 파일에서 정확 버전으로
설치하고, 파이썬 기반 이미지를 지문(digest)으로 고정). 서버 코드·도구 응답·입력 스키마·검색/랭킹·규정 데이터·매뉴얼 트랙은
전부 무변입니다(contract 0.36.0 유지·재연결 불요).

★본 spec이 검증하는 것 = 도구 경로 무회귀(Level A)뿐입니다. lock·digest의 효과(이미지가 라이브와 같은 부품으로 만들어졌는가)는
이 러너로 검증할 수 없습니다(러너는 로컬 venv에서 도구를 in-process로 호출하며 Docker 이미지를 만들지 않음).
"행동 무회귀"(이 spec)와 "이미지 재현성"(아래 운영 게이트)은 별개의 증거입니다 — diff 적대검토 Codex 반영.

운영 게이트(배포 전·NAS 실측 — 전건 통과 시에만 배포 승인 요청):
  ① pytest `tests/test_dockerfile_pins.py`(7) — lock 71행 정확 핀·핀 6종 ⊂ lock·pyproject 범위·FROM digest·2단 설치·pip check·COPY 순서.
  ② NAS 후보 빌드(`docker build --network host --progress=plain`) — 로그에 기반 이미지 pull 없음(로컬 동일 digest 사용).
  ③ 후보 `pip freeze` 71/71 라이브(c6cfb3e8c12b) 전수 동일 · `pip check` 통과(빌드 안에서도 실행됨) · 내부 Python 3.13.13·OpenSSL 3.5.6·
     pip 26.0.1 · 기반 RepoDigest 일치 · 기반 이미지 RootFS.Layers 전체가 후보 RootFS.Layers의 정확한 prefix.
  ④ 후보 컨테이너(PORT=18080·FASTMCP_HOST=127.0.0.1·host network) 부팅 406·initialize serverInfo.version=0.53.1·
     cold LIVE 66규정 fan-out(done 66·errors 0)·★hard-fail 스모크 확장(diff 적대검토 Codex MAJOR 3): `get_provision_detail`
     law:283413(effective_date 2026-08-20)·`get_manual_section` 3-4(본권 JSON이 wheel/이미지에 실제 포함됐는지)·`list_rule_sets`
     total 66·응답 텍스트에 키 원문 0 — 하나라도 실패면 후보 폐기. 컨테이너는 STATUS Running + RestartCount == 0.
  ⑤ 롤백 태그 `:0.53.0-rollback`을 현행 라이브 **이미지 ID(7ea3d1762177)**에서 생성하고 가리키는 ID를 확인 · 기반 이미지 로컬 태그 백업
     (`python-base:0.53.1-pinned`) · 검증한 후보 이미지 ID(+git commit·lock sha256)를 기록하고 **그 ID를 그대로** NAS에 승격(재빌드 금지).
     ★롤백 절차(명시·compose는 `image: korean-rnd-regs-mcp:latest`·env는 .env + compose environment에 있어 이미지와 무관):
       발동 = 스왑 후 10분 내 ⑥ 중 하나라도 실패(406 미도달·serverInfo≠0.53.1·검색 errors>0이 실패 캐시 TTL 300s 경과 후에도 지속·Restarting).
       명령 = `sudo /usr/local/bin/docker tag korean-rnd-regs-mcp:0.53.0-rollback korean-rnd-regs-mcp:latest` →
              `cd /volume1/docker/korean-rnd-regs-mcp && sudo /usr/local/bin/docker compose down && sudo /usr/local/bin/docker compose up -d` →
              `curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8080/mcp`(406) + initialize serverInfo 0.53.0 확인.
  ⑥ 스왑 후 — 외부 URL 정상·무키 406(도달 지표)·serverInfo 0.53.1·`list_rule_sets` 66·검색 errors 0·로그 `oc=` 0건(패턴 개수만).
  ⑦ 관측은 시간이 아니라 신호로 — 스왑 후 최소 3회(직후·+1h·+12h 이상) 터널 경유 프로브(검색 fan-out + detail + 매뉴얼 1건씩)가
     전건 정상이고 그 구간의 컨테이너 RestartCount 0·앱 로그 traceback 0·cloudflared 오류 0이면 통과 → P2로 진행.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok / returned_not_below [회귀=BLOCK 후보] · absent_error_code / latency_under / field_equals [WARN]
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

# Level B(배포 후 라이브 확인 + 사람 판정). 도구 응답·호스트 AI 발화에 영향을 주는 변경이 없으므로 무회귀 문안 1건만 verbatim 재사용.
LEVEL_B_PROMPTS = [
    {
        "category": "무회귀 — cold 광역 fan-out 경로(v0.48.0 무회귀 B verbatim)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "66규정 fan-out 완주·기존 규정(연구개발비 사용 기준·시행령) 중심 유지 + "
                           "citation·footer 무회귀. 부분 timeout·누락 규정·오류 문면이 새로 보이면 "
                           "회귀 의심.",
    },
]
