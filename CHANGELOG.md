# Changelog

본 파일은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 1.1.0 형식을 따릅니다.
버전 번호는 [Semantic Versioning](https://semver.org/lang/ko/) 2.0.0을 따르되, 0.x.x 대역은 unstable signal이며 minor bump도 breaking change 허용입니다.

## [0.1.1] - 2026-05-25

### Fixed — search-first 패턴 (규정 개정 자동 반영)

- 규정 개정 시 최신 버전을 자동으로 조회하는 search-first 패턴 추가 (`resolve_latest_doc_id`)
  - 도구 호출 시 manifest의 규정명으로 검색 API를 먼저 호출하여 최신 문서 ID 확인
  - 개정이 감지되면 최신 ID로 상세 조회 + 응답에 `revision_notice` 필드 포함
  - 검색 실패 시 manifest ID로 fallback (기존 동작 유지)
  - 24시간 캐시로 반복 호출 시 추가 API 비용 없음, 실패는 5분 캐시로 빠르게 복구
- `get_provision_detail`: resolved doc_id로 provision_id가 전달될 때 manifest lookup fallback 추가
- title matching에 Unicode 중간점 정규화 추가 (`ㆍ` U+318D → `·` U+00B7)
- `suggest_review_sources`: search-first로 doc_id가 변경되어도 정상 동작하도록 `rule_set_id` 기반 lookup으로 변경

### Tests
- 14개 신규 테스트 추가 (67 → 81개): resolve 동작·fallback·캐시·중간점·최신 날짜 선택·보안 회귀

[0.1.1]: https://github.com/smilemin07/korean-rnd-regs-mcp/releases/tag/v0.1.1

## [0.1.0] - 2026-05-24

### Added — 첫 publish

#### MCP Tools (5종)
- `health` — 서비스 상태·API 키 설정 여부 확인
- `list_rule_sets` — 등록된 규정 목록 조회
- `search_provision` — 조문·별표 본문 키워드 검색 → snippet + provision_id list
- `get_provision_detail` — provision_id로 단일 조문/별표 본문 verbatim 조회
- `suggest_review_sources` — 자연어 질문 → 키워드 추출 → 검토 후보 + 추천 순서

#### MCP Prompts (1종 — v0.2 plan 1·3 보강을 v0.1.0에 미리 포함)
- `review_regulation` — 다층적 규정 검토 워크플로 자동 적용. Claude Desktop의 prompts 메뉴에서 선택 시, 본 server의 13개 규정을 위계 순서로 cross-reference하여 근거 조항 verbatim 인용과 함께 답변. 본 프로젝트 저자의 표준 규정 검토 워크플로 패턴(Tier 1 → Tier 2 → Supplementary, provision_id verbatim 인용)을 본 server 도구 호출 형태로 자동화 — 외부 사용자도 별도 skill 설치 없이 표준 워크플로 기반의 1차 검토 가능. 단, 매뉴얼·부처별 운영규정·관리지침은 본 server 미커버 (별도 자료 확인 필요)

#### Manifest (13개 rule set — 4개 MVP + 9개 v0.2 보강을 v0.1.0에 미리 포함)

Tier 1 — 핵심 법률·시행령·시행규칙 (혁신법 family):
- `innovation_act` — 국가연구개발혁신법 (법률, MST 260807, 2025-02-28 시행)
- `innovation_decree` — 동 시행령 (대통령령, MST 285767, 2026-05-06 시행)
- `innovation_rule` — 동 시행규칙 (과기정통부령, MST 285043, 2026-03-25 시행)

Tier 2 — 핵심 행정규칙 (핵심 행정규칙):
- `rnd_funding_standard` — 국가연구개발사업 연구개발비 사용 기준 (admrul ID 2100000278740, 2024-06-13)
- `simultaneous_research_limit` — 국가연구개발사업 동시수행 연구개발과제 수 제한 기준 (2100000196149, 2021-01-01)
- `facility_equipment_standard` — 국가연구개발 시설·장비의 관리 등에 관한 표준지침 (2100000278230, 2026-04-23)
- `research_note_guideline` — 국가연구개발사업 연구노트 지침 (2100000207982, 2022-01-01)

Supplementary — 신고·포상금·부패행위·청탁금지·공익신고자보호 cross-reference:
- `anti_corruption_act` / `anti_corruption_decree` — 부패방지 및 국민권익위원회의 설치와 운영에 관한 법률 (+ 시행령) (MST 268657 / 283781)
- `improper_solicitation_act` / `improper_solicitation_decree` — 부정청탁 및 금품등 수수의 금지에 관한 법률 (청탁금지법/김영란법) (+ 시행령) (MST 268655 / 281817)
- `public_interest_whistleblower_act` / `public_interest_whistleblower_decree` — 공익신고자 보호법 (+ 시행령) (MST 268861 / 264451)

#### Infrastructure
- live_api 트랙: 국가법령정보 OpenAPI(lawSearch.do, lawService.do) 기반 검색·상세조회
- provision_id 포맷 `{doc_type}:{doc_id}[:{unit_id}]` — JO(조문) / BP(별표) prefix 지원
- API contract v0.1.0 ([docs/api_contract.md](docs/api_contract.md))
- LawApiClient + TTLCache (24h success, 5min failure)
- Pydantic RuleSet schema (14 fields, extra="forbid")
- FastMCP 3.3 stdio mode + prompts 지원
- 행정규칙 schema 2종 모두 지원: 표준 `<조문단위>` 구조 + 평면 `<조문내용>` (root 직속) fallback (LIVE 검증: 동시수행 과제 수 제한·연구노트 지침 등)

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
- 67 unit tests (mock 기반, 네트워크 미사용) — manifest 13건 검증, prompt template substitution, schema B fallback 등 포함
- LIVE API 통합 테스트는 v0.2에서 @pytest.mark.network 마커로 분리 예정

### Known Limitations (현재 미지원)
- 가지조문(예: 제15조의2): 현재 provision_id 포맷이 `JO` + 숫자만 지원 — 검색·상세조회에서 누락
- 법령 시행령 별표(혁신법 시행령 별표 1~7 등): 현재 `unit_types: article`로 설정되어 별표 미검색
- PDF 색인·OCR·SQLite FTS5 (기관별 운영규정·매뉴얼): 향후 확장 예정

[0.1.0]: https://github.com/smilemin07/korean-rnd-regs-mcp/releases/tag/v0.1.0
