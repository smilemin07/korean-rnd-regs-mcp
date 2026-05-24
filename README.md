# korean-rnd-regs-mcp

[![PyPI version](https://img.shields.io/pypi/v/korean-rnd-regs-mcp.svg)](https://pypi.org/project/korean-rnd-regs-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/korean-rnd-regs-mcp.svg)](https://pypi.org/project/korean-rnd-regs-mcp/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

국가연구개발 규정 검토용 Python MCP server. Claude Desktop·Claude Code 등 MCP 클라이언트에서 자연어 질의로 **국가연구개발혁신법**·동 시행령·시행규칙·핵심 행정규칙을 검색·검토하는 도구입니다.

**대상 사용자**:
- 연구자 — 연구개발비 사용·증빙 기준 사전 확인
- 대학·기관 행정직원 — 협약 체결·실적 보고 시 규정 인용
- R&D 전문기관 직원 — 사업 운영·평가 시 규정 근거 확인

비프로그래머도 Claude Desktop에 한 번 등록하면 자연어 질문으로 즉시 사용 가능합니다.

> 본 도구는 **법률 판단을 하지 않습니다**. 검토 후보 제시만 수행하며, 최종 판단은 사용자 책임입니다. [Disclaimer](#disclaimer) 참조.

---

## 기능

**5개 MCP tool**:

| Tool | 용도 |
|---|---|
| `health` | 서비스 상태·API 키 설정 여부 확인 |
| `list_rule_sets` | 등록된 13개 규정 목록·hierarchy rank·문서 ID 조회 |
| `search_provision` | 조문·별표 본문에서 키워드 검색 → snippet + provision_id 후보 list |
| `get_provision_detail` | provision_id로 단일 조문/별표 본문 verbatim 조회 (LLM 임의 부제 발명 방어 metadata 포함) |
| `suggest_review_sources` | 자연어 질문 → 키워드 추출 → 검토할 규정·조문 후보 + 추천 검토 순서 (법률 → 시행령 → 시행규칙 → 행정규칙) |

**1개 MCP prompt** (Claude Desktop의 prompts 메뉴에서 선택 가능):

| Prompt | 용도 |
|---|---|
| `review_regulation` | **다층적 규정 검토 워크플로 자동 적용** — 13개 규정을 위계 순서로 cross-reference하여 근거 조항 verbatim 인용과 함께 답변. 상황만 입력하면 도구 호출·우선순위·출력 형식이 자동 진행 |

**지원 규정 (v0.1.0, 총 13개)**:

Tier 1 — 핵심 법률·시행령·시행규칙 (혁신법 family):

| ID | 명칭 | 종류 | MST/ID |
|---|---|---|---|
| `innovation_act` | 국가연구개발혁신법 | 법률 (2025-02-28) | MST 260807 |
| `innovation_decree` | 국가연구개발혁신법 시행령 | 대통령령 (2026-05-06) | MST 285767 |
| `innovation_rule` | 국가연구개발혁신법 시행규칙 | 과기정통부령 (2026-03-25) | MST 285043 |

Tier 2 — 핵심 행정규칙 (4개 — review-regulations 표준 Tier 2 전체):

| ID | 명칭 | 시행일 | admrul ID |
|---|---|---|---|
| `rnd_funding_standard` | 국가연구개발사업 연구개발비 사용 기준 | 2024-06-13 | 2100000278740 |
| `simultaneous_research_limit` | 국가연구개발사업 동시수행 연구개발과제 수 제한 기준 | 2021-01-01 | 2100000196149 |
| `facility_equipment_standard` | 국가연구개발 시설·장비의 관리 등에 관한 표준지침 | 2026-04-23 | 2100000278230 |
| `research_note_guideline` | 국가연구개발사업 연구노트 지침 | 2022-01-01 | 2100000207982 |

Supplementary — 신고·포상금·부패행위·청탁금지·공익신고자보호 검토용 cross-reference:

| ID | 명칭 | 종류 | MST |
|---|---|---|---|
| `anti_corruption_act` | 부패방지 및 국민권익위원회의 설치와 운영에 관한 법률 | 법률 (2025-01-21) | 268657 |
| `anti_corruption_decree` | 동 시행령 | 대통령령 (2026-03-03) | 283781 |
| `improper_solicitation_act` | 부정청탁 및 금품등 수수의 금지에 관한 법률 (청탁금지법/김영란법) | 법률 (2025-01-21) | 268655 |
| `improper_solicitation_decree` | 동 시행령 | 대통령령 (2025-12-30) | 281817 |
| `public_interest_whistleblower_act` | 공익신고자 보호법 | 법률 (2026-02-01) | 268861 |
| `public_interest_whistleblower_decree` | 동 시행령 | 대통령령 (2024-08-07) | 264451 |

---

## 사전 준비: LAW_API_KEY 발급

본 서버는 [국가법령정보 OpenAPI](https://open.law.go.kr) 를 호출합니다. 무료이며 가입·신청 후 즉시 발급됩니다.

### 이미 키를 보유하고 있는 경우

설치 후 환경변수 또는 MCP 클라이언트 config에 다음 한 줄을 추가하시면 됩니다:

```
LAW_API_KEY=발급받은_OC_인증값
```

### 처음 발급받는 경우 (5분 소요)

1. https://open.law.go.kr 접속 → 회원가입
2. 로그인 → [마이페이지] → [API 신청] → "법령" 카테고리 신청 → 승인 즉시 (자동)
3. 발급된 **OC 인증값**을 LAW_API_KEY로 설정

> 보안: 키는 `.env` 파일이나 MCP 클라이언트 config에만 보관하시고, 절대 git commit하거나 채팅·screenshot에 노출하지 마십시오. 노출 시 즉시 폐기·재발급 ([SECURITY.md](SECURITY.md) 참조).

---

## 설치 + 등록

### Option 1: Claude Desktop 사용자 (가장 일반적)

```bash
pip install korean-rnd-regs-mcp
```

Claude Desktop config 파일 편집:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "korean-rnd-regs": {
      "command": "korean-rnd-regs-mcp",
      "env": {
        "LAW_API_KEY": "발급받은_OC_인증값"
      }
    }
  }
}
```

Claude Desktop 재시작 → 우측 하단 MCP 아이콘 확인.

### Option 2: Claude Code 사용자

```bash
pip install korean-rnd-regs-mcp
claude mcp add korean-rnd-regs korean-rnd-regs-mcp -e LAW_API_KEY=발급받은_OC_인증값
```

### Option 3: 다른 MCP 클라이언트

stdio mode로 다음 명령 실행:

```bash
korean-rnd-regs-mcp
```

표준 MCP protocol (JSON-RPC over stdio). FastMCP 3.3 기반.

### 설치 확인

```bash
korean-rnd-regs-mcp --version
# korean-rnd-regs-mcp 0.1.0
```

---

## 사용 예시

### 예시 0 (권장): MCP prompt — 다층적 규정 검토 자동 워크플로

Claude Desktop의 좌하단 `+` 또는 `/` 메뉴에서 **review_regulation** prompt를 선택하면, situation 입력칸이 표시됩니다. 상황을 자연어로 입력하면 본 server의 도구가 자동으로 호출되어 13개 규정을 위계 순서대로 cross-reference한 결과가 출력됩니다.

예시 입력 (situation):
```
연구기관이 공문으로 정식 절차를 밟아 공동연구기관 추가를 요청했으나 전문기관이 접수 후 무응답으로 방치한 상태에서, 최종평가가 진행됐으며 '극히 불량' 등급을 받음. 현장실태조사 결과도 좋지 않아 제재조치평가위원회에서 '참여제한 2년 처분'을 받게 됨. 위 상황에서 적용 가능한 규정과 검토 포인트는?
```

자동으로 적용되는 워크플로:
1. `suggest_review_sources` 호출 → 키워드 추출 + 13개 규정 cross-search
2. recommended_review_order에 따라 법률 → 시행령 → 시행규칙 → 행정규칙 순서로 `get_provision_detail` 호출
3. Tier 2 키워드 cross-check (참여제한 → rnd_funding_standard, 동시수행 등)
4. Supplementary cross-check (해당 시)
5. 출력 format: 검토 규정 · 핵심 답변 · 근거 조항(verbatim) · 모호한 부분 · 권고 조치

본 prompt는 본 프로젝트 저자가 자체 유지하던 규정 검토 워크플로(Tier 1 → Tier 2 → Supplementary 순서, provision_id verbatim 인용, 출력 형식 표준화)를 본 MCP server 도구 호출 형태로 자동화한 것입니다. 외부 사용자도 별도 skill 설치 없이 표준 워크플로 기반의 1차 검토를 받을 수 있습니다. 단, 매뉴얼·부처별 운영규정·관리지침은 본 server 미커버 — 별도 자료 확인 필요.

### 예시 1: 자연어 질문 → 검토 시작점 찾기 (저수준 도구 직접 사용)

질문: "특별평가를 받으려면 어떤 절차가 필요한가요?"

Claude가 호출하는 도구: `suggest_review_sources("특별평가를 받으려면 어떤 절차가 필요한가요?")`

응답 (요약):
- `extracted_keywords`: `["특별평가", "절차"]`
- `recommended_review_order`: 법률 → 시행령 → 시행규칙 순으로 검토 우선순위
- `candidates`: 매칭 조문 list (각각 `provision_id` + `snippet`)

Claude가 이어서 가장 관련 높은 조문의 `get_provision_detail`로 본문 verbatim 조회.

### 예시 2: 특정 조문 본문 그대로 조회

```
korean-rnd-regs-mcp 도구로 국가연구개발혁신법 제15조 본문(항·호 모두) 편집하지 말고 그대로 보여줘.
```

**중요 (verbatim hint)**:

"**편집하지 말고 그대로**" 또는 "**원문 그대로**", "**verbatim**" 같은 prompt 추가가 필요합니다. Claude는 기본적으로 가독성을 위해 임의 부제 추가나 paraphrase를 하는 경향이 있습니다. 본 서버는 응답에 `content_format: "plain_text_verbatim"` marker와 `format_instructions` metadata를 포함하지만, 사용자 prompt가 더 강한 신호가 되어야 정확한 인용이 보장됩니다.

응답에 함께 포함되는 정보:
- `content`: 조문 본문 (조문내용 + 항 + 호 합쳐서 verbatim)
- `article_structure`: machine-readable nested hierarchy (`title` / `paragraphs[].number` / `text` / `source_text` / `subparagraphs`)
- `effective_date`, `document_source_url`, `disclaimer`

### 예시 3: 별표 본문 조회

질문: "연구개발비 사용 기준의 기본사업연구개발비 계상 기준 별표를 보여줘"

처리 흐름:
1. `search_provision("기본사업연구개발비")` → `provision_id: "admrul:2100000278740:BP0001"` 발견
2. `get_provision_detail("admrul:2100000278740:BP0001")` → 별표 본문 + `attached_file_url` (있을 경우)

### 예시 4: 등록된 규정 목록 조회

```
korean-rnd-regs-mcp가 지원하는 규정 목록을 보여줘.
```

→ `list_rule_sets()` 호출 → 13개 rule set의 id·title·hierarchy_rank·api_doc_id·effective_date·source_url 반환.

---

## API Contract

contract_version: **0.1.0** (첫 publish)

> 0.x.x 대역은 **unstable signal** — minor bump(0.1.0 → 0.2.0)도 breaking change 허용. 외부 사용자 코드는 contract_version을 응답에서 확인하여 호환성 체크 권장.

### provision_id 포맷

```
{doc_type}:{doc_id}[:{unit_id}]
```

| 필드 | 허용 값 |
|---|---|
| `doc_type` | `law` 또는 `admrul` |
| `doc_id` | MST (법령) 또는 행정규칙일련번호 |
| `unit_id` (선택) | `JO` + 4자리 이상 숫자 (조문) 또는 `BP` + 4자리 이상 숫자 (별표). 생략 시 document-level |

### 예시

| provision_id | 의미 |
|---|---|
| `law:260807` | 국가연구개발혁신법 전체 |
| `law:260807:JO0015` | 동 법 제15조 |
| `admrul:2100000278740` | 연구개발비 사용 기준 전체 |
| `admrul:2100000278740:BP0001` | 동 행정규칙 별표 1 |

### 표준 오류 코드

| code | 의미 |
|---|---|
| `auth_failed` | OpenAPI 인증 실패 (401/403 또는 잘못된 OC) |
| `rate_limited` | 429 또는 일일 호출 제한 |
| `parse_failed` | XML 파싱 실패, HTML 에러 페이지, 기타 4xx/5xx |
| `not_found` | 검색 결과 0건 또는 상세 대상 없음 |
| `invalid_provision_id` | provision_id 포맷 위반 |
| `invalid_query` | search query가 공백 제외 2자 미만 |

자세한 응답 schema·변경 이력은 [docs/api_contract.md](docs/api_contract.md) 참조.

---

## v0.2 / v0.3 예정 (현재 미지원)

다음 항목은 **silent skip 또는 false negative** 가능하니 주의:

- **가지조문** (예: 제15조의2, 제5조의3): 현재 provision_id 포맷이 `JO` + 숫자만 지원. 가지조문은 검색·상세조회에서 누락됨. v0.2에서 prefix 확장 예정.
- **법령 시행령 별표** (혁신법 시행령 별표 1~7 등): 현재 `unit_types: article`로 설정되어 별표 미검색. v0.3에서 `get_law_detail`에 annexes 파싱 추가 예정.
- **PDF 색인·OCR·SQLite FTS5**: 기관별 운영규정(예: 국토교통부소관 연구개발사업 운영규정), 부처별 관리지침(예: 국토교통 연구개발사업 관리지침), 매뉴얼(국가연구개발혁신법 매뉴얼 등) OpenAPI 미공개 자료의 검색은 v0.3 이후. 본 자료들이 필요한 검토는 본 MCP server cover 범위 밖이므로 별도 확인 필요.
- **다관점 분석** (해석이 갈리는 모호한 규정, 제재 비례성 판단, 감사 리스크 평가 등): 본 MCP server는 자료 layer만 제공하며 다관점 분석은 LLM의 reasoning에 의존. `review_regulation` prompt는 단일 패스 분석에 최적화되어 있으며, 다관점이 필요한 사안은 변호사 자문을 권고드립니다.

검토 결과가 의심스러우면 항상 응답의 `source_url`을 직접 확인하시기 바랍니다.

---

## Troubleshooting

### Q. Claude가 "관련 조문을 찾을 수 없습니다"라고 답합니다

1. Claude에게 도구 응답의 `errors` field 확인 요청 — API 인증 실패 등은 errors로 전달됨
2. `health` 도구로 `api_key_configured: true` 확인
3. LAW_API_KEY가 정확한지 [국가법령정보 OpenAPI 마이페이지](https://open.law.go.kr/LSO/mypage.do)에서 확인
4. 키 문자열 앞뒤 공백 제거

### Q. Claude가 조문 본문에 없는 부제나 요약을 만들어냅니다

- prompt에 "**편집하지 말고 그대로**" 또는 "**verbatim**" 추가 (위 예시 2 참조)
- 서버 응답의 `format_instructions` field가 Claude에 verbatim 정책을 전달하지만, 기본 rendering을 override하려면 사용자 prompt가 더 강한 신호 필요

### Q. 특정 조문이 검색되지 않습니다

- 가지조문(제N조의M)이면 v0.2까지 미지원 (위 v0.2 섹션 참조)
- 시행령 별표면 v0.3까지 미지원
- 그 외엔 `search_provision` keyword를 다양화 시도 (띄어쓰기·약칭). 예: "연구개발비 사용 기준" → "연구개발비사용기준"

### Q. "auth_failed" 오류

- LAW_API_KEY가 비어있거나 잘못됨. open.law.go.kr 마이페이지 → API 키 재발급

### Q. "rate_limited" 오류

- 일일 호출 제한 도달. 24시간 대기 후 재시도. 캐시(24h)가 동일 query 반복 호출을 줄여줍니다

### Q. Claude Desktop에서 MCP 아이콘이 안 보입니다

- config 파일 JSON 문법 오류 가능. `python -m json.tool < claude_desktop_config.json` 검사
- Claude Desktop 완전 종료 후 재시작 (Cmd+Q → 재실행)
- 로그 확인: `~/Library/Logs/Claude/mcp-server-korean-rnd-regs.log`

---

## 개발자용

### 로컬 개발 환경

```bash
git clone https://github.com/smilemin07/korean-rnd-regs-mcp.git
cd korean-rnd-regs-mcp
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### 테스트 실행

```bash
pytest
# 67 passed (mock 기반, 네트워크 미사용)
```

### 빌드

```bash
python -m build
twine check dist/*
```

---

## 보안

LAW_API_KEY는 다중 layer 방어로 도구 응답·로그·error message에 절대 노출되지 않습니다:
- `_request_with_retry`에서 `requests.exceptions.RequestException` 포괄 catch + type 이름만 사용 (URL/key 미노출)
- `_sanitize_error_message` defense-in-depth layer
- 키 누설 회귀 테스트 다수 포함

자세한 보안 정책·취약점 보고: [SECURITY.md](SECURITY.md)

---

## Disclaimer

본 도구는 **법률 판단을 하지 않으며**, 검토 후보 제시만 수행합니다. 실제 법령 판단·적용은 사용자 책임이며, 다음을 직접 확인해야 합니다:

- 최신 시행일·개정 상황 ([국가법령정보센터](https://www.law.go.kr))
- 기관별 운영규정·매뉴얼 (각 R&D 전문기관 — 별도 자료)
- 별표·서식 첨부파일 (도구 응답의 `attached_file_url` 또는 `source_url`)
- 가지조문 누락 가능성 (v0.2 deferred)

---

## License

[Apache License 2.0](LICENSE)

## Contributing

이슈·PR 환영합니다: https://github.com/smilemin07/korean-rnd-regs-mcp/issues

## Changelog

[CHANGELOG.md](CHANGELOG.md)
