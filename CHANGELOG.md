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

#### MCP Prompts (1종 — v0.2 plan 1·3 보강을 v0.1.0에 미리 포함)
- `review_regulation` — 다층적 규정 검토 워크플로 자동 적용. Claude Desktop의 prompts 메뉴에서 선택 시, 본 server의 13개 규정을 위계 순서로 cross-reference하여 근거 조항 verbatim 인용과 함께 답변. 본 프로젝트 저자의 표준 규정 검토 워크플로 패턴(Tier 1 → Tier 2 → Supplementary, provision_id verbatim 인용)을 본 server 도구 호출 형태로 자동화 — 외부 사용자도 별도 skill 설치 없이 표준 워크플로 기반의 1차 검토 가능. 단, 매뉴얼·부처별 운영규정·관리지침은 본 server 미커버 (별도 자료 확인 필요)

#### Manifest (13개 rule set — 4개 MVP + 9개 v0.2 보강을 v0.1.0에 미리 포함)

Tier 1 — 핵심 법률·시행령·시행규칙 (혁신법 family):
- `innovation_act` — 국가연구개발혁신법 (법률, MST 260807, 2025-02-28 시행)
- `innovation_decree` — 동 시행령 (대통령령, MST 285767, 2026-05-06 시행)
- `innovation_rule` — 동 시행규칙 (과기정통부령, MST 285043, 2026-03-25 시행)

Tier 2 — 핵심 행정규칙 (review-regulations 표준 Tier 2 전체):
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

### 9차 AI review 추가 fix (publish 직전)

 +  합의 발견 사항 반영:

- live_api.py `_FLAT_ARTICLE_PATTERN`: 제목 내부 괄호 대응을 위해 lazy match로 변경 (`r'제(\d+)조(?:의(\d+))?\s*\((.+?)\)\s*(.*)'`). 괄호 자체는 필수 유지 → 장/절/관 wrapper("제1장 총칙" 등) 자동 제외 효과 유지
- live_api.py 가지조문 collision 방지: 표준 schema + 평면 schema 양쪽에서 가지조문(제15조의2 등) skip. contract 0.1.0의 provision_id가 JO + 숫자만 지원하므로 가지조문은 본 조문과 조문번호 충돌 (예: rnd_funding_standard에 제10조의2/제11조의2/제15조의2 등 8건 LIVE 발견). v0.2 prefix 확장 시 자동 활성화 예정
- rule_sets.yaml unit_types 정정: rnd_funding_standard·facility_equipment_standard 둘 다 평면 schema fallback으로 조문 본문도 풍부함이 확인되어 annex → both 변경. 조문 117개/46개 본문이 search 대상에 포함됨
- rule_sets.yaml + manifest.py HierarchyRank Enum 확장: Supplementary 법률 rank 1→5, Supplementary 시행령 rank 2→6. 직전엔 부패방지법(rank 1)이 혁신법 시행령(rank 2)보다 먼저 추천되던 정렬 오염을 해결 — 표준 위계 순서(혁신법 family → 행정규칙 → Supplementary) 보장
- pyproject.toml sdist 정리: CLAUDE.md(Andy 내부 노트) + .claude/(redirect notice + project-local skill) public sdist에서 명시적 exclude. README/CHANGELOG/SECURITY/LICENSE만 노출
- README.md 정리: 내부 절대 경로 제거 + 일반 설명으로 대체, "동일한 깊이" → "표준 워크플로 기반 1차 검토"로 표현 약화 (매뉴얼·운영규정·관리지침 미커버 명시), stale "4개 rule set"·"63 passed" 정정

### Known Limitations (v0.2 / v0.3 deferred)
- 가지조문(예: 제15조의2): 현재 provision_id 포맷이 `JO` + 숫자만 지원 — 검색·상세조회에서 누락. v0.2 prefix 확장 예정
- 법령 시행령 별표(혁신법 시행령 별표 1~7 등): 현재 `unit_types: article`로 설정되어 별표 미검색. v0.3에서 `get_law_detail`에 annexes 파싱 추가 예정
- PDF 색인·OCR·SQLite FTS5 (기관별 운영규정·매뉴얼): v0.3 이후

---

### Pre-publish 내부 이력 (참고용)

publish 전 개발 중 사용한 임시 contract_version 1.0.x 시리즈는 외부 사용자에게 노출된 적이 없습니다. 본 0.1.0 publish 시점에 0.x.x 대역으로 reset. 내부 변경 사항은 [docs/api_contract.md §6](docs/api_contract.md) "Pre-publish 내부 이력" 표에 보존되어 있습니다.

[0.1.0]: https://github.com/smilemin07/korean-rnd-regs-mcp/releases/tag/v0.1.0
