"""Unit tests for health and list_rule_sets — no network, no live API."""
import asyncio
import json

from korean_rnd_regs_mcp import __version__
from korean_rnd_regs_mcp.main import health, list_rule_sets, mcp, review_regulation_prompt


def test_health_returns_required_fields():
    result = asyncio.run(health())
    assert result["status"] == "ok"
    assert result["service"] == "korean-rnd-regs-mcp"
    assert result["version"] == __version__
    assert isinstance(result["api_key_configured"], bool)


def test_health_no_key_leak(monkeypatch):
    test_key = "fake_secret_test_key_12345abc"
    monkeypatch.setenv("LAW_API_KEY", test_key)
    result = asyncio.run(health())
    response_str = json.dumps(result, ensure_ascii=False)
    assert test_key not in response_str
    assert test_key[:6] not in response_str
    assert result["api_key_configured"] is True


def test_health_reports_unset_key(monkeypatch):
    monkeypatch.delenv("LAW_API_KEY", raising=False)
    result = asyncio.run(health())
    assert result["api_key_configured"] is False


def test_health_no_per_user_oc_key_leak():
    """회귀(작업1 gap a·b): per-user OC key(contextvar)가 health 응답에 미포함."""
    from korean_rnd_regs_mcp.main import _request_api_key
    per_user_oc = "PER_USER_OC_FAKE_7788"
    token = _request_api_key.set(per_user_oc)
    try:
        result = asyncio.run(health())
        response_str = json.dumps(result, ensure_ascii=False)
        assert per_user_oc not in response_str
        assert per_user_oc[:6] not in response_str
        assert result["api_key_configured"] is True
    finally:
        _request_api_key.reset(token)


# === MCP prompt: review_regulation (v0.1.0 보강 — 다층적 검토 워크플로 자동 적용) ===
def test_review_regulation_prompt_substitutes_situation():
    """prompt template이 situation argument를 정확히 substitute."""
    situation = "연구기관이 공동연구기관 추가를 요청했으나 무응답 방치된 사례"
    body = review_regulation_prompt(situation)
    assert isinstance(body, str)
    assert situation in body, "situation argument substitution 실패"
    # 본 server의 핵심 도구 명시
    assert "suggest_review_sources" in body
    assert "get_provision_detail" in body
    # 위계 순서 안내
    assert "법률 → 시행령 → 시행규칙" in body
    # verbatim 정책 명시 — 의도: 원문 인용 충실성 보장. 표현은 시간에 따라 변할 수 있음
    assert "verbatim" in body
    assert "paraphrase" in body  # 핵심 키워드 (요약/paraphrase 금지)
    assert "원문" in body and ("그대로 사용" in body or "verbatim 인용" in body)


def test_review_regulation_prompt_handles_quotes_in_situation():
    """회귀(작업2): situation에 큰따옴표가 있어도 도구 호출 안내가 깨지지 않음."""
    situation = '연구자가 "특별평가" 대상인지 문의'
    body = review_regulation_prompt(situation)
    assert isinstance(body, str)
    assert situation in body  # 큰따옴표 포함 situation이 검토 상황 블록에 그대로 포함
    # question="{situation}" 리터럴 삽입 제거 → 중첩 따옴표로 깨지는 패턴 부재
    assert 'suggest_review_sources(question="' not in body


def test_review_regulation_prompt_includes_tier2_routing():
    """Tier 2 키워드 routing + v0.2.6 공통/사업 행정규칙 cross-check 안내 포함, 제거된 보조 법령 부재."""
    body = review_regulation_prompt("X")
    # Tier 2 routing
    assert "rnd_funding_standard" in body
    assert "simultaneous_research_limit" in body
    assert "facility_equipment_standard" in body
    assert "research_note_guideline" in body
    # v0.2.6 공통/사업 행정규칙 cross-check (보조 법령 routing 대체)
    assert "rnd_info_processing" in body
    assert "rnd_security_measures" in body
    assert "performance_eval_act" in body
    assert "tech_fee_integrated" in body
    # 제거된 보조 법령 routing은 더 이상 프롬프트에 없어야 함
    assert "anti_corruption_act" not in body
    assert "improper_solicitation_act" not in body
    assert "public_interest_whistleblower_act" not in body


def test_review_regulation_prompt_includes_limitation_notice():
    """본 server cover 범위 밖 자료 + 가지조문/별표 한계 명시 (false negative 방지)."""
    body = review_regulation_prompt("X")
    assert "매뉴얼" in body  # 매뉴얼·운영규정·관리지침
    assert "가지조문" in body  # v0.2 deferred
    assert "별표" in body  # v0.3 deferred
    assert "변호사 자문" in body  # 법률 판단 disclaimer


def test_review_regulation_prompt_includes_procedure_flow_section():
    """v0.1.10: 절차형 답변 시각화 — 조건부 8절 '절차 흐름' + fabrication 가드 + literal 백틱3개 부재."""
    body = review_regulation_prompt("X")
    assert "### 8. 절차 흐름" in body  # 조건부 절 신설
    assert "코드블록" in body  # 텍스트 흐름(모든 클라이언트 렌더)
    assert "임의로 추가하지 말 것" in body  # 규정에 없는 단계 fabrication 가드
    assert "mermaid" not in body.lower()  # mermaid 미언급(미렌더 커넥터 raw 노출 방지)
    assert "```" not in body  # README 단일 펜스·동기화 회귀 보호(literal triple-backtick 금지)


def test_readme_embedded_prompt_matches_template():
    """회귀: README에 임베드된 review_regulation 프롬프트가 main.py _REVIEW_PROMPT_TEMPLATE와
    정확히 일치하는지 검증 (문서-코드 drift 방지 — 단일 출처 가드)."""
    import re
    from pathlib import Path
    from korean_rnd_regs_mcp.main import _REVIEW_PROMPT_TEMPLATE
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    m = re.search(r"규정 검토용 프롬프트</summary>\s*\n+```\n(.*?)\n```", readme, re.DOTALL)
    assert m, "README에서 '규정 검토용 프롬프트' 코드블록을 찾지 못함"
    assert m.group(1).strip() == _REVIEW_PROMPT_TEMPLATE.strip(), (
        "README 임베드 프롬프트가 main.py _REVIEW_PROMPT_TEMPLATE와 불일치 — 동기화 필요"
    )


def test_suggest_review_sources_keywords_param_is_optional():
    """회귀(additive): suggest_review_sources에 keywords 선택 파라미터가 default None으로 존재 — 기존 question-only 호출 무영향."""
    import inspect
    from korean_rnd_regs_mcp.main import suggest_review_sources
    sig = inspect.signature(suggest_review_sources)
    assert "question" in sig.parameters
    assert "keywords" in sig.parameters
    assert sig.parameters["keywords"].default is None


def test_review_prompt_instructs_keyword_array_to_suggest():
    """프롬프트가 LLM에게 검색 키워드 배열을 suggest_review_sources의 keywords로 전달하도록 지시."""
    prompt = review_regulation_prompt("테스트 상황")
    assert "keywords" in prompt
    assert "검색 키워드 배열" in prompt


def test_list_rule_sets_returns_live_api_items():
    """v0.12.0: 산업기술혁신사업 운영 지침 2건(보안관리요령·평가관리지침) 추가 = 51건."""
    result = asyncio.run(list_rule_sets())
    assert "rule_sets" in result
    assert isinstance(result["rule_sets"], list)
    assert result["total"] == 51
    assert len(result["rule_sets"]) == 51
    ids = {rs["id"] for rs in result["rule_sets"]}
    expected = {
        # Tier 1 + 기존 Tier 2 (혁신법 family + 연구개발비 사용 기준)
        "innovation_act", "innovation_decree", "innovation_rule", "rnd_funding_standard",
        # Tier 2 신규 (review-regulations SKILL.md Tier 2 완성)
        "simultaneous_research_limit", "facility_equipment_standard", "research_note_guideline",
        # v0.1.3 — 국토교통 R&D family (혁신법과 함께 적용)
        "sector_kt_act", "sector_kt_decree", "sector_kt_rule", "kt_rnd_operations",
        # v0.2.5 — 산업기술 R&D family (산업통상부)
        "industry_tech_act", "industry_tech_decree", "industry_tech_rule", "industry_tech_operating",
        # v0.12.0 — 산업기술혁신사업 운영 지침 2건 (연구보안·성과평가)
        "industry_tech_security", "industry_tech_evaluation",
        # v0.2.5 — 중소기업 R&D family (중소벤처기업부)
        "sme_tech_act", "sme_tech_decree", "sme_tech_rule", "sme_rnd_operating",
        # v0.2.6 — 성과평가 family
        "performance_eval_act", "performance_eval_decree",
        # v0.2.6 — 공통 행정규칙 (과기정통부)
        "rnd_info_processing", "rnd_security_measures", "msit_rnd_processing",
        "ict_rnd_management", "ict_research_ethics",
        # v0.2.6 — 기술료 family (산업부·중기부, 소관부처 필터)
        "tech_fee_integrated", "sme_tech_fee",
        # v0.3.0 — 보건복지부 보건의료기술 R&D family
        "health_tech_act", "health_tech_decree", "health_tech_rule", "health_rnd_operating",
        # v0.4.0 — 질병관리청 R&D family
        "kdca_rnd_management", "kdca_agency_designation", "kdca_facility_equipment", "kdca_relay_operating",
        # v0.8.0 — 교육부 학술진흥법 family
        "hakjin_act", "hakjin_decree", "hakjin_rule",
        # v0.9.0 — 교육부 산학협력 family + 연구윤리 지침
        "sanhak_act", "sanhak_decree", "sanhak_rule", "research_ethics_guideline",
        # v0.10.0 — 과기정통부 기업부설연구소 family
        "corp_lab_act", "corp_lab_decree", "corp_lab_rule",
        # v0.11.0 — 과기정통부 연구산업진흥법 family
        "research_industry_act", "research_industry_decree", "research_industry_rule",
    }
    assert ids == expected, f"id 불일치: 누락={expected - ids}, 추가={ids - expected}"
    # 모든 항목이 필수 field + v0.2.6 ministry 필드(additive) 노출
    by_id = {rs["id"]: rs for rs in result["rule_sets"]}
    for rs in result["rule_sets"]:
        assert rs["api_target"] in ("law", "admrul")
        assert rs["hierarchy_rank"] in (1, 2, 3, 4, 5, 6)
        assert rs["unit_types"] in ("article", "annex", "both")
        assert "ministry" in rs  # additive 필드 — None 또는 부처명
    assert by_id["tech_fee_integrated"]["ministry"] == "산업통상부"
    assert by_id["innovation_act"]["ministry"] is None
    # v0.3.0 — 보건복지부 family ministry 노출
    assert by_id["health_tech_act"]["ministry"] == "보건복지부"
    assert by_id["health_rnd_operating"]["ministry"] == "보건복지부"
    # v0.4.0 — 질병관리청 family ministry 노출
    assert by_id["kdca_rnd_management"]["ministry"] == "질병관리청"
    assert by_id["kdca_relay_operating"]["ministry"] == "질병관리청"
    # v0.8.0 — 교육부 학술진흥법 family (law target·중첩 schema·ministry=교육부)
    assert by_id["hakjin_act"]["ministry"] == "교육부"
    assert by_id["hakjin_decree"]["ministry"] == "교육부"
    assert by_id["hakjin_rule"]["ministry"] == "교육부"
    assert by_id["hakjin_act"]["api_target"] == "law"
    assert by_id["hakjin_decree"]["unit_types"] == "both"
    # v0.9.0 — 교육부 산학협력 family + 연구윤리 (ministry=교육부)
    assert by_id["sanhak_act"]["ministry"] == "교육부"
    assert by_id["sanhak_decree"]["unit_types"] == "both"
    assert by_id["sanhak_rule"]["unit_types"] == "article"
    assert by_id["research_ethics_guideline"]["ministry"] == "교육부"
    assert by_id["research_ethics_guideline"]["api_target"] == "admrul"
    # v0.10.0 — 과기정통부 기업부설연구소 family (law target·ministry=과학기술정보통신부)
    assert by_id["corp_lab_act"]["ministry"] == "과학기술정보통신부"
    assert by_id["corp_lab_act"]["api_target"] == "law"
    assert by_id["corp_lab_act"]["unit_types"] == "article"
    assert by_id["corp_lab_decree"]["unit_types"] == "both"
    assert by_id["corp_lab_rule"]["unit_types"] == "both"


def test_review_regulation_prompt_includes_annex_discovery_guides():
    """v0.2.1: 별표 의존조문 동반조회(dependent_article_hints·1단계 한정) +
    문서레벨 annexes 목록으로 BP 선택(추측 금지) 지시가 프롬프트에 포함."""
    body = review_regulation_prompt("테스트 상황")
    assert "dependent_article_hints" in body
    assert "annexes 목록" in body
    assert "1단계까지만" in body
    assert "추측해 호출하지 말 것" in body


# === v0.2.9: 도구 호출 유도 메타데이터 가드 (Level A — '문구 탑재'만 결정적 검증) ===
# 주의: 아래는 짧고 안정적인 핵심 구절만 단언한다(긴 문장 verbatim 단언은 사소한 리워딩에도
# 깨져 비프로그래머 유지보수에 churn). 실제 '호스트가 도구를 부르는가'(behavior)는 비결정·
# 호스트 의존(Level B)이라 여기서 검증하지 않으며 배포 후 수동 eval(acceptance LEVEL_B_PROMPTS)의 몫.

def test_server_instructions_nudges_tool_call():
    """v0.2.9 #1: FastMCP 서버 instructions가 탑재되고 호출 유도/금지 핵심 구절을 포함."""
    instr = mcp.instructions
    assert instr, "서버 instructions가 비어 있음 — initialize payload 호출 유도 신호 누락"
    assert "일반 학습지식으로 답하지 말고" in instr  # WHEN TO USE (호출 유도)
    assert "호출하지 마십시오" in instr               # WHEN NOT (과호출 차단)


def test_tool_docstrings_include_usage_timing_stanza():
    """v0.2.9 #2: 3개 도구 docstring 첫 문단에 '사용 시점/호출 금지' 스탠자 탑재(도구별 핵심 구절)."""
    import inspect
    from korean_rnd_regs_mcp.main import (
        search_provision,
        suggest_review_sources,
        get_provision_detail,
    )
    sp = inspect.getdoc(search_provision) or ""
    assert "사용 시점" in sp
    assert "일반 학습지식" in sp

    srs = inspect.getdoc(suggest_review_sources) or ""
    assert "사용 시점" in srs
    assert "알려줘" in srs  # 광역 '알려줘' 표현도 호출 대상임을 명시

    gpd = inspect.getdoc(get_provision_detail) or ""
    assert "사용 시점" in gpd
    assert "추측하지 마십시오" in gpd  # provision_id 없이 추측 금지(삭제 여부·현행 내용은 호출로 확인)


def test_contract_version_is_0_9_0():
    """v0.7.0: get_provision_detail document-level articles 목록 additive → contract 0.8.0→0.9.0."""
    from korean_rnd_regs_mcp.provision_id import CONTRACT_VERSION
    assert CONTRACT_VERSION == "0.9.0"


# === v0.2.11: MCP Registry 등록 마커 + server.json ===
def test_readme_has_mcp_name_marker():
    """README에 MCP Registry 소유권 마커 1줄 존재(PyPI description 검증용)."""
    from pathlib import Path
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    assert "<!-- mcp-name: io.github.smilemin07/korean-rnd-regs-mcp -->" in readme


def test_server_json_valid_for_registry():
    """repo 루트 server.json — name·버전(릴리스 일치)·remotes 제외·description ≤100자."""
    import json
    from pathlib import Path
    from korean_rnd_regs_mcp import __version__
    sj = json.loads(
        (Path(__file__).resolve().parent.parent / "server.json").read_text(encoding="utf-8")
    )
    assert sj["name"] == "io.github.smilemin07/korean-rnd-regs-mcp"
    assert sj["version"] == __version__                       # server.json = 릴리스 버전
    assert sj["packages"][0]["version"] == __version__         # 3자 일치(등록 소유권 검증)
    assert sj["packages"][0]["identifier"] == "korean-rnd-regs-mcp"
    assert "remotes" not in sj                                 # 호스팅 endpoint 미노출(키 안전)
    assert len(sj["description"]) <= 100                       # 스키마 maxLength


# === v0.2.12: 도구 미가용 시 fail-closed 안내 + 범위 외 정직성 ===
def test_server_instructions_fail_closed_and_scope_honesty():
    """v0.2.12: instructions에 fail-closed(도구 미가용 시 단정 금지) + 범위 외 정직성('도구 호출 결과' 기준) 탑재."""
    instr = mcp.instructions
    # fail-closed: 도구를 못 부르면 훈련지식 단정 금지·stdio 재시도 안내
    assert "도구가 보이지 않거나 호출에 실패" in instr
    assert "단정하지" in instr
    assert "stdio 클라이언트" in instr
    # 범위 외 정직성: '도구 호출 결과' 기준(호출 전 추측으로 미지원 단정 방지 — Codex blocking 반영)
    assert "도구 호출 결과" in instr
    assert "1차 출처" in instr
    # 기존 도구 호출 유도 구절 보존(회귀 — append-only)
    assert "일반 학습지식으로 답하지 말고" in instr


# === v0.3.0: 보건복지부 확대 + 미지원 규정 현행성 정직 가드 ===
def test_server_instructions_stale_guard_v030():
    """v0.3.0: 범위 외 정직성 절이 미지원 규정의 변동 구체값 현행 단정 자제 + 43 카운트 동기화."""
    instr = mcp.instructions
    assert "지원 51개 규정 밖이면" in instr               # 미지원 한정(in-scope 인용 비억제) + 카운트
    assert "변동 가능한 구체값을 현행 사실로 단정하지" in instr  # stale 식별자 단정 자제
    assert "1차 출처" in instr                            # 1차 출처 안내 보존
    # 미지원 한정 조건이 유지돼 in-scope 인용을 억제하지 않음(과억제 방지 회귀)
    assert "단정하지 말며" in instr


def test_review_prompt_mentions_health_family_and_count():
    """v0.3.0: review 템플릿에 보건의료 R&D family 행 + 43 카운트(host가 범위 밖 오분류 방지)."""
    body = review_regulation_prompt("테스트 상황")
    assert "보건의료 R&D family" in body                  # Tier 1 family 행
    assert "보건의료기술 진흥법" in body                  # family 규정명
    assert "(51개 규정)" in body                          # 카운트 동기화
    assert "health_tech_act" in body                      # cross-check 라우팅


# === v0.4.0: 질병관리청 R&D 확대 ===
def test_kdca_family_registered_and_relay_prefixed():
    """v0.4.0: 질병관리청 4건 등록(ministry·admrul) + 이어달리기는 부처 접두 제목(resolve 정확성 불변식)."""
    from korean_rnd_regs_mcp.manifest import load_manifest
    items = {rs.id: rs for rs in load_manifest()}
    for rid in ("kdca_rnd_management", "kdca_agency_designation",
                "kdca_facility_equipment", "kdca_relay_operating"):
        assert rid in items, f"질병관리청 규정 누락: {rid}"
        assert items[rid].ministry == "질병관리청"
        assert items[rid].api_target == "admrul"
    # 이어달리기: 부처 접두 포함 정식 제목 — 접두 없으면 resolve 정확일치 0 → manifest fallback(현행성 추적 死)
    assert items["kdca_relay_operating"].title.startswith("(질병관리청)")


def test_review_prompt_mentions_kdca_family_and_count():
    """v0.4.0: review 템플릿에 질병관리청 R&D family 행 + cross-check 라우팅 + 43 카운트."""
    body = review_regulation_prompt("테스트 상황")
    assert "질병관리청 R&D 행정규칙" in body              # Tier 2 family 행
    assert "(51개 규정)" in body                          # 카운트 동기화
    assert "kdca_rnd_management" in body                   # cross-check 라우팅


# === v0.8.0: 교육부 학술진흥법 확대 (순수 data — 코드 무변경, law target·중첩 schema) ===
def test_hakjin_family_registered_v080():
    """v0.8.0: 학술진흥법 3건 등록(ministry=교육부·law target). LIVE 게이트(2026-06-23): 트랙 충돌 0·정확 title+ministry 단건 resolve."""
    from korean_rnd_regs_mcp.manifest import load_manifest
    items = {rs.id: rs for rs in load_manifest()}
    for rid in ("hakjin_act", "hakjin_decree", "hakjin_rule"):
        assert rid in items, f"학술진흥법 규정 누락: {rid}"
        assert items[rid].ministry == "교육부"
        assert items[rid].api_target == "law"          # 평면 admrul 아님(중첩 schema)
    # hierarchy: 법1·시행령2·시행규칙3 (기존 law family 패턴)
    assert items["hakjin_act"].hierarchy_rank == 1
    assert items["hakjin_decree"].hierarchy_rank == 2
    assert items["hakjin_rule"].hierarchy_rank == 3


def test_review_prompt_mentions_hakjin_family_v080():
    """v0.8.0: review 템플릿 적용 범위에 학술진흥 R&D family 행 추가(host가 교육부 규정을 범위 밖 오분류 방지)."""
    body = review_regulation_prompt("테스트 상황")
    assert "학술진흥 R&D family" in body
    assert "학술진흥법" in body


def test_sanhak_family_registered_v090():
    """v0.9.0: 교육부 산학협력 family 3건 + 연구윤리 지침 등록. LIVE 게이트(2026-06-24): 트랙 충돌 0·정확 title+ministry 단건 resolve."""
    from korean_rnd_regs_mcp.manifest import load_manifest
    items = {rs.id: rs for rs in load_manifest()}
    for rid in ("sanhak_act", "sanhak_decree", "sanhak_rule"):
        assert rid in items, f"산학협력 규정 누락: {rid}"
        assert items[rid].ministry == "교육부"
        assert items[rid].api_target == "law"          # 중첩 schema(평면 admrul 아님)
    # hierarchy: 법1·시행령2·시행규칙3 (기존 law family 패턴)
    assert items["sanhak_act"].hierarchy_rank == 1
    assert items["sanhak_decree"].hierarchy_rank == 2
    assert items["sanhak_rule"].hierarchy_rank == 3
    # 연구윤리 확보를 위한 지침 (교육부 훈령·admrul)
    assert "research_ethics_guideline" in items, "연구윤리 지침 누락"
    assert items["research_ethics_guideline"].ministry == "교육부"
    assert items["research_ethics_guideline"].api_target == "admrul"
    assert items["research_ethics_guideline"].hierarchy_rank == 4
    # doc_id 결정론 고정 (yaml drift 방어 — LIVE 게이트 2026-06-24 값)
    assert items["sanhak_act"].api_doc_id == "267351"
    assert items["sanhak_decree"].api_doc_id == "284767"
    assert items["sanhak_rule"].api_doc_id == "285257"
    assert items["research_ethics_guideline"].api_doc_id == "2100000226306"


def test_review_prompt_mentions_sanhak_family_v090():
    """v0.9.0: review 템플릿 적용 범위에 산학협력 R&D family 행 + 연구윤리 라우팅 추가."""
    body = review_regulation_prompt("테스트 상황")
    assert "산학협력 R&D family" in body
    assert "research_ethics_guideline" in body


def test_corp_lab_family_registered_v0100():
    """v0.10.0: 과기정통부 기업부설연구소 family 3건 등록. LIVE 게이트(2026-06-29): 정확 title+ministry=과기정통부 단건 resolve·동명충돌 0."""
    from korean_rnd_regs_mcp.manifest import load_manifest
    items = {rs.id: rs for rs in load_manifest()}
    for rid in ("corp_lab_act", "corp_lab_decree", "corp_lab_rule"):
        assert rid in items, f"기업부설연구소 규정 누락: {rid}"
        assert items[rid].ministry == "과학기술정보통신부"
        assert items[rid].api_target == "law"          # 중첩 schema(평면 admrul 아님)
    # hierarchy: 법1·시행령2·시행규칙3 (기존 law family 패턴)
    assert items["corp_lab_act"].hierarchy_rank == 1
    assert items["corp_lab_decree"].hierarchy_rank == 2
    assert items["corp_lab_rule"].hierarchy_rank == 3
    # 별표 노출: 법률 article·시행령/시행규칙 both(시행규칙 별표0000은 oversized→oversized_pointer)
    assert items["corp_lab_act"].unit_types == "article"
    assert items["corp_lab_decree"].unit_types == "both"
    assert items["corp_lab_rule"].unit_types == "both"
    # doc_id 결정론 고정 (yaml drift 방어 — LIVE 게이트 2026-06-29 값)
    assert items["corp_lab_act"].api_doc_id == "282553"
    assert items["corp_lab_decree"].api_doc_id == "282915"
    assert items["corp_lab_rule"].api_doc_id == "283223"


def test_review_prompt_mentions_corp_lab_family_v0100():
    """v0.10.0: review 템플릿 적용 범위에 기업부설연구소 R&D family 행 + cross-check 라우팅."""
    body = review_regulation_prompt("테스트 상황")
    assert "기업부설연구소 R&D family" in body
    assert "corp_lab_act" in body


def test_research_industry_family_registered_v0110():
    """v0.11.0: 과기정통부 연구산업진흥법 family 3건 등록. LIVE 게이트(2026-06-30): 정확 title+ministry=과기정통부 단건 resolve·동명충돌 0."""
    from korean_rnd_regs_mcp.manifest import load_manifest
    items = {rs.id: rs for rs in load_manifest()}
    for rid in ("research_industry_act", "research_industry_decree", "research_industry_rule"):
        assert rid in items, f"연구산업진흥법 규정 누락: {rid}"
        assert items[rid].ministry == "과학기술정보통신부"
        assert items[rid].api_target == "law"          # 중첩 schema(평면 admrul 아님)
    # hierarchy: 법1·시행령2·시행규칙3 (기존 law family 패턴)
    assert items["research_industry_act"].hierarchy_rank == 1
    assert items["research_industry_decree"].hierarchy_rank == 2
    assert items["research_industry_rule"].hierarchy_rank == 3
    # 별표 노출: 법률·시행규칙 article(시행규칙 별표0·서식만→BP 미노출)·시행령 both(별표2 tier-1)
    assert items["research_industry_act"].unit_types == "article"
    assert items["research_industry_decree"].unit_types == "both"
    assert items["research_industry_rule"].unit_types == "article"
    # doc_id 결정론 고정 (yaml drift 방어 — LIVE 게이트 2026-06-30 값)
    assert items["research_industry_act"].api_doc_id == "231603"
    assert items["research_industry_decree"].api_doc_id == "261923"
    assert items["research_industry_rule"].api_doc_id == "262117"


def test_review_prompt_mentions_research_industry_family_v0110():
    """v0.11.0: review 템플릿 적용 범위에 연구산업 R&D family 행 + cross-check 라우팅."""
    body = review_regulation_prompt("테스트 상황")
    assert "연구산업 R&D family" in body
    assert "research_industry_act" in body


def test_industry_tech_guidelines_registered_v0120():
    """v0.12.0: 산업기술혁신사업 운영 지침 2건 등록(ministry=산업통상부·admrul 평면). LIVE 게이트(2026-07-01): 정확 title+ministry 단건 resolve·동명 타부처 사본 0."""
    from korean_rnd_regs_mcp.manifest import load_manifest
    items = {rs.id: rs for rs in load_manifest()}
    for rid in ("industry_tech_security", "industry_tech_evaluation"):
        assert rid in items, f"산업기술 지침 누락: {rid}"
        assert items[rid].ministry == "산업통상부"
        assert items[rid].api_target == "admrul"        # 평면 schema admrul(기존 공통 운영요령과 동형)
        assert items[rid].hierarchy_rank == 4            # 운영요령과 병렬 admrul(Tier 2)
        assert items[rid].unit_types == "both"           # 둘 다 별표 노출(BP)
    # doc_id 결정론 고정 (yaml drift 방어 — LIVE 게이트 2026-07-01 값)
    assert items["industry_tech_security"].api_doc_id == "2100000122711"
    assert items["industry_tech_evaluation"].api_doc_id == "2100000252016"


def test_review_prompt_mentions_industry_tech_guidelines_v0120():
    """v0.12.0: review 템플릿 적용 범위(사업 운영규정·요령)에 산업기술혁신사업 보안관리요령·평가관리지침 노출."""
    body = review_regulation_prompt("테스트 상황")
    assert "산업기술혁신사업 보안관리요령" in body
    assert "산업기술혁신사업 기술개발 평가관리지침" in body


def test_readme_has_stable_usage_guidance():
    """v0.2.12: README '안정적으로 사용하기' 섹션 — 섹션 범위로 가드(다른 섹션/Changelog 우연 통과 방지)."""
    import re
    from pathlib import Path
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    m = re.search(r"## 안정적으로 사용하기\n(.*?)(?=\n## )", readme, re.DOTALL)
    assert m, "README '안정적으로 사용하기' 섹션을 찾지 못함"
    section = m.group(1)
    assert "사용하지 않는 커넥터" in section
    assert "provision_id" in section
    assert "새 대화" in section
    assert "stdio" in section


def test_version_consistency_across_manifests():
    """v0.2.12(Codex 권고): 버전 5개소(__version__·pyproject·plugin·marketplace·server.json 2필드) 일치."""
    import json
    import re
    from pathlib import Path
    from korean_rnd_regs_mcp import __version__
    root = Path(__file__).resolve().parent.parent
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert m and m.group(1) == __version__, "pyproject.toml version 불일치"
    plugin = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin["version"] == __version__, "plugin.json version 불일치"
    mkt = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert mkt["plugins"][0]["version"] == __version__, "marketplace.json version 불일치"
    sj = json.loads((root / "server.json").read_text(encoding="utf-8"))
    assert sj["version"] == __version__, "server.json version 불일치"
    assert sj["packages"][0]["version"] == __version__, "server.json packages version 불일치"


# === v0.4.1: 외부 웹 본문 폴백 차단 (규정 본문은 도구로) ===
def test_review_prompt_forbids_external_body_fallback_v041():
    """v0.4.1: review 템플릿 4단계에 외부 웹 본문 폴백 금지·미제공 식별자 정직 처리·비교 조회 종료조건 + oversized 예외 보존."""
    body = review_regulation_prompt("테스트 상황")
    assert "본문을 외부에서 채우지 말 것" in body                                    # 외부 웹 본문 폴백 금지
    assert "MCP 응답에서 확인되지 않음" in body                                     # 미제공 식별자(고시번호) 정직 처리
    assert "같은 provision_id는 이미 받은 결과를 재사용하여 중복 호출하지 말 것" in body  # 비교 조회 종료조건(B3)
    assert "공식 원문을 확인할 것" in body                                          # plain_text_verbatim 아닌 경우 공식 원문 예외 보존(과억제 회귀 방지)


def test_server_instructions_external_fallback_guard_v041():
    """v0.4.1: instructions에 지원 범위 내 본문 외부 폴백 금지 1문장 append + 기존 가드 구절 전부 보존."""
    instr = mcp.instructions
    assert "지원 범위 내 규정의 조문·별표 본문은" in instr                  # in-scope 외부 폴백 금지(신규)
    assert "응답에 없는 고시·예규 번호는 현행으로 단정하지 마십시오" in instr
    # append-only 회귀: 기존 도구 호출 유도·범위 외 정직성 가드 보존
    assert "일반 학습지식으로 답하지 말고" in instr
    assert "지원 51개 규정 밖이면" in instr


def test_get_provision_detail_docstring_external_fallback_v041():
    """v0.4.1: get_provision_detail docstring에 content=본문 권위 출처·외부 폴백 금지 + 기존 구절 보존."""
    import inspect
    from korean_rnd_regs_mcp.main import get_provision_detail
    doc = inspect.getdoc(get_provision_detail) or ""
    assert "규정 조문·별표 본문의 권위 출처" in doc       # content=본문 권위(B1 — 현행 식별자 overclaim 회피 framing)
    assert "외부 웹" in doc                                # 외부 본문 폴백 금지 언급
    assert "추측하지 마십시오" in doc                      # v0.2.9 기존 구절 보존(회귀)


def test_server_instructions_false_negative_guard_v050():
    """v0.5.0: instructions에 false-negative 가드(등록 규정 외부 미발견≠존재 안 함, B3) + version 필드 안내 append + 기존 구절 보존."""
    instr = mcp.instructions
    assert "존재하지 않는다고 단정하지 말고" in instr                       # B3 false-negative 가드(프롬프트3 직접 겨냥)
    assert "issuance_number·regulation_kind·version_label" in instr        # version 필드 안내
    # append-only 회귀: v0.4.1·이전 가드 구절 전부 보존
    assert "응답에 없는 고시·예규 번호는 현행으로 단정하지 마십시오" in instr
    assert "지원 범위 내 규정의 조문·별표 본문은" in instr
    assert "일반 학습지식으로 답하지 말고" in instr
    assert "지원 51개 규정 밖이면" in instr


def test_get_provision_detail_docstring_mentions_version_fields_v050():
    """v0.5.0: get_provision_detail docstring에 admrul version 필드 안내(issuance_number 등) + 기존 구절 보존."""
    import inspect
    from korean_rnd_regs_mcp.main import get_provision_detail
    doc = inspect.getdoc(get_provision_detail) or ""
    assert "issuance_number" in doc and "version_label" in doc   # 신규 version 필드 안내
    assert "규정 조문·별표 본문의 권위 출처" in doc                # v0.4.1 구절 보존(회귀)
    assert "추측하지 마십시오" in doc                             # v0.2.9 구절 보존(회귀)
