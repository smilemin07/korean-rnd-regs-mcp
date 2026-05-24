# Changelog

본 파일은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 1.1.0 형식을 따릅니다.
버전 번호는 [Semantic Versioning](https://semver.org/lang/ko/) 2.0.0을 따르되, 0.x.x 대역은 unstable signal이며 minor bump도 breaking change 허용입니다.

## [0.1.0] - 2026-05-24

### Added — 첫 publish

#### MCP Tools (5종)
- `health` — 서비스 상태·API 키 설정 여부 확인
- `list_rule_sets` — 등록된 규정 목록 조회
- `search_provision` — 조문·별표 본문 키워드 검색 → snippet + provision_id list
- `get_provision_detail` — provision_id로 단일 조문/별표 본문 verbatim 조회
- `suggest_review_sources` — 자연어 질문 → 키워드 추출 → 검토 후보 + 추천 순서

#### Manifest (4개 MVP rule set)
- `innovation_act` — 국가연구개발혁신법 (법률, MST 260807, 2025-02-28 시행)
- `innovation_decree` — 동 시행령 (대통령령, MST 285767, 2026-05-06 시행)
- `innovation_rule` — 동 시행규칙 (과기정통부령, MST 285043, 2026-03-25 시행)
- `rnd_funding_standard` — 국가연구개발사업 연구개발비 사용 기준 (행정규칙, admrul ID 2100000278740, 2024-06-13 시행)

#### Infrastructure
- live_api 트랙: 국가법령정보 OpenAPI(lawSearch.do, lawService.do) 기반 검색·상세조회
- provision_id 포맷 `{doc_type}:{doc_id}[:{unit_id}]` — JO(조문) / BP(별표) prefix 지원
- API contract v0.1.0 ([docs/api_contract.md](docs/api_contract.md))
- LawApiClient + TTLCache (24h success, 5min failure)
- Pydantic RuleSet schema (14 fields, extra="forbid")
- FastMCP 3.3 stdio mode

#### LLM 환각 방어 (additive metadata)
- `get_provision_detail` 응답에 `content_format: "plain_text_verbatim"` marker
- `format_instructions` field (LLM 표시 정책 명시)
- `article_structure` (machine-readable nested hierarchy: title / paragraphs[].number / text / source_text / subparagraphs)

### Security
- LAW_API_KEY 누설 차단 다중 layer:
  - `_request_with_retry`: `requests.exceptions.RequestException` 포괄 catch + type 이름만 사용 (URL/key 미노출)
  - `_sanitize_error_message`: 도구 응답 직전 second-layer redact
  - 응답·로그·error message 어느 곳에도 키 원문·앞자리·hash 미포함
- 회귀 테스트 다수 포함 (test_*_no_key_leak, test_live_api_handles_sslerror_without_url_leak)

### Tests
- 63 unit tests (mock 기반, 네트워크 미사용)
- LIVE API 통합 테스트는 v0.2에서 @pytest.mark.network 마커로 분리 예정

### Known Limitations (v0.2 / v0.3 deferred)
- 가지조문(예: 제15조의2): 현재 provision_id 포맷이 `JO` + 숫자만 지원 — 검색·상세조회에서 누락. v0.2 prefix 확장 예정
- 법령 시행령 별표(혁신법 시행령 별표 1~7 등): 현재 `unit_types: article`로 설정되어 별표 미검색. v0.3에서 `get_law_detail`에 annexes 파싱 추가 예정
- PDF 색인·OCR·SQLite FTS5 (기관별 운영규정·매뉴얼): v0.3 이후

---

### Pre-publish 내부 이력 (참고용)

publish 전 개발 중 사용한 임시 contract_version 1.0.x 시리즈는 외부 사용자에게 노출된 적이 없습니다. 본 0.1.0 publish 시점에 0.x.x 대역으로 reset. 내부 변경 사항은 [docs/api_contract.md §6](docs/api_contract.md) "Pre-publish 내부 이력" 표에 보존되어 있습니다.

[0.1.0]: https://github.com/smilemin07/korean-rnd-regs-mcp/releases/tag/v0.1.0
