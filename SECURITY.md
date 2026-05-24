# Security Policy

## Supported Versions

본 프로젝트는 0.1.0 (첫 publish) 단계입니다. 최신 minor 버전만 보안 패치 대상입니다.

| Version | Supported |
|---|---|
| 0.1.x | ✅ |
| < 0.1 | ❌ (pre-publish 내부 버전, 노출된 적 없음) |

---

## 취약점 신고

보안 취약점 발견 시 다음 절차를 따라주십시오.

### 1. 공개 GitHub Issue로 보고하지 말 것

Public issue tracker에 보고하면 patch 전에 취약점이 노출되어 악용될 위험이 있습니다.

### 2. 다음 이메일로 비공개 보고

```
smilemin07 [at] gmail [dot] com
```

(spam 차단을 위해 `[at]`·`[dot]` 표기 사용. 실제 보고 시 일반 이메일 주소로 변환)

### 3. 보고 시 포함 사항

- **취약점 종류** (예: API key 누설, 잘못된 권한 처리, XML 파싱 취약점, injection)
- **재현 방법** (코드·명령·입력 sequence)
- **영향 범위** (사용자 환경·데이터·권한)
- **가능하면 patch 제안**

### 4. 응답 일정

- 보고 접수 후 **7일 이내** 회신
- patch release 목표: **30일 이내**
- critical 등급: 가능한 한 빠르게 (24-72시간)

---

## LAW_API_KEY 노출 시 대처

본 프로젝트는 LAW_API_KEY를 도구 응답·로그·error message에 절대 포함하지 않도록 다중 layer 방어를 적용합니다 (defense-in-depth):

- `_request_with_retry`: `requests.exceptions.RequestException` 포괄 catch + `type(e).__name__`만 사용 (URL·query string·key 미노출)
- `_sanitize_error_message`: 도구 응답 직전 second-layer redact
- 회귀 테스트: `test_*_no_key_leak`, `test_live_api_handles_sslerror_without_url_leak`

단, 사용자가 직접 키를 `.env` 또는 MCP 클라이언트 config에 저장하므로 다음 사항 주의:

### 키 노출 가능 경로

| 경로 | 대처 |
|---|---|
| `.env` 파일을 git commit | `.gitignore`에 등록되어 있으나 `git add -A` 등 강제 추가 시 누설 가능. 매 commit 전 `git diff --cached`로 확인 |
| 채팅·screenshot에 키 노출 | 채팅 LLM이 키 값을 그대로 화면에 출력하지 않도록 prompt에 "키는 출력하지 마" 명시 |
| log 파일 직접 노출 | log handler 설정 시 환경변수 자동 redact 미적용 — 본 프로젝트는 stderr handler에 key 미포함, 외부 도구 사용 시 검토 필요 |
| shell history | `LAW_API_KEY=xxx korean-rnd-regs-mcp` 형태로 직접 export 시 history에 남음. 항상 `.env` 파일 사용 권장 |

### 키 노출 발견 시 즉시 폐기·재발급

1. https://open.law.go.kr → 로그인 → 마이페이지 → API 신청 내역
2. 해당 키 **삭제** → 새 키 발급
3. `.env` 또는 MCP config의 키 값 업데이트
4. 노출된 곳(git history, log, screenshot 등) 완전 제거 — git history에 들어간 키는 BFG Repo-Cleaner 등으로 history rewrite 필요

---

## 알려진 보안 한계

### LAW_API_URL 환경변수 override

`LAW_API_URL` 환경변수로 base URL을 변경하면 `OC=<LAW_API_KEY>`가 그 host로 전송됩니다. 개발·테스트 외 운영 환경에서는 **기본값(`https://www.law.go.kr/DRF`) 그대로 사용 권장**합니다. 임의 host 사용 시 키가 해당 host 운영자에게 전송될 위험.

### TLS / HTTPS 의존

통신은 HTTPS이나 국가법령정보 OpenAPI 자체의 TLS 인증서 정책에 의존합니다. requests 라이브러리 기본 verify=True 사용.

### LLM 응답에서의 키 누설 risk

본 서버는 도구 응답에 키를 포함하지 않으나, 사용자가 prompt에 키를 직접 입력하면 LLM이 응답·로그에 그대로 출력할 수 있습니다. 키를 LLM prompt에 노출하지 마십시오.

---

## PyPI Token 보안 (개발자용)

본 프로젝트를 fork·재배포하는 개발자는 PyPI token도 동일한 원칙으로 관리해야 합니다:

- `~/.pypirc` 외부에 노출 금지
- 채팅·README·`.env`·shell history에 남기지 말 것
- 가능한 한 GitHub Actions **Trusted Publishers** 사용 (token 자체 불요)

---

## 참고

- [국가법령정보 OpenAPI 이용 약관](https://open.law.go.kr)
- [Apache License 2.0](LICENSE) — 본 프로젝트 라이선스
- 본 프로젝트의 보안 layer 구현: `src/korean_rnd_regs_mcp/live_api.py`의 `_request_with_retry`, `src/korean_rnd_regs_mcp/main.py`의 `_sanitize_error_message`
