"""v0.36.0 tool annotations 잠금 — 7도구 전건 readOnlyHint/destructiveHint/openWorldHint.

metadata-only 표면이므로 registry(ToolAnnotations 객체)와 wire(to_mcp_tool 직렬화) 양면을 잠근다.
idempotentHint·title은 의도적 미지정 — MCP 스펙상 두 필드 모두 readOnlyHint == false일 때만
의미가 있거나(idempotent) 표시명 우선순위를 바꾸는 사용자 노출 변경(title)이라 제외. None 잠금.
openWorldHint 배정 근거: 외부 law.go.kr OpenAPI를 호출하는 도구(키 필요 3종 = C4 무키 차단
적용 3곳과 동일)만 true, 패키지 데이터·환경만 읽는 도구는 false.
"""
import asyncio

import pytest

from korean_rnd_regs_mcp.main import mcp

_OPEN_WORLD = {
    # 외부 law.go.kr OpenAPI 호출 3종
    "search_provision": True,
    "get_provision_detail": True,
    "suggest_review_sources": True,
    # 로컬 전용 4종
    "health": False,
    "list_rule_sets": False,
    "search_manual": False,
    "get_manual_section": False,
}


@pytest.fixture(scope="module")
def tools_by_name():
    tools = asyncio.run(mcp.list_tools(run_middleware=False))
    return {t.name: t for t in tools}


def test_tool_names_exactly_seven(tools_by_name):
    assert set(tools_by_name) == set(_OPEN_WORLD)


@pytest.mark.parametrize("name", sorted(_OPEN_WORLD))
def test_registry_annotations(tools_by_name, name):
    ann = tools_by_name[name].annotations
    assert ann is not None
    assert ann.readOnlyHint is True
    assert ann.destructiveHint is False
    assert ann.openWorldHint is _OPEN_WORLD[name]
    assert ann.idempotentHint is None
    assert ann.title is None


@pytest.mark.parametrize("name", sorted(_OPEN_WORLD))
def test_wire_annotations(tools_by_name, name):
    ann = tools_by_name[name].to_mcp_tool().annotations
    assert ann is not None
    assert ann.readOnlyHint is True
    assert ann.destructiveHint is False
    assert ann.openWorldHint is _OPEN_WORLD[name]
