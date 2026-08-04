"""v0.34.0 — 표·산식 구조 안내 완성형 승격(structure_notice) + 오류 self-echo 마스킹 잠금 테스트.

동기 = v0.33.0 배포 후 라이브 eval: warnings 배열 원소(table_structure_notes)는 호스트 답변에
전이되지 않고, 같은 응답의 citation·standard_footer(완성형 블록)는 복사됨 — 완성형 승격.
보안 = 사용자가 실수로 자신의 OC 키를 도구 인자에 붙여넣었을 때의 오류 self-echo 3경로 마스킹.
네트워크 호출 없음(마스킹 테스트의 resolve 폴백은 monkeypatch로 차단).
"""

import asyncio
import json

import pytest

import korean_rnd_regs_mcp.main as main_mod
import korean_rnd_regs_mcp.manual as manual_mod
from korean_rnd_regs_mcp.main import _attach_structure_notice, get_manual_section, get_provision_detail
from korean_rnd_regs_mcp.manual import (
    MANUAL_DETAIL_CHAR_BUDGET,
    STRUCTURE_NOTICE_CHUNK_LINE,
    STRUCTURE_NOTICE_HEADER,
    STRUCTURE_NOTICE_NOTE,
    build_structure_notice,
    load_manual_b2,
    load_manual_b3,
)

FAKE_KEY = "FAKEKEY_TEST_ONLY_1234"


@pytest.fixture()
def fresh_cache():
    manual_mod._reset_cache_for_tests()
    yield
    manual_mod._reset_cache_for_tests()


# ── structure_notice 부착(전문 절 3) ─────────────────────────────────────────

@pytest.mark.parametrize("sid", ["b2-2-1", "b2-3-2", "b2-ref-1"])
def test_notice_attached_on_full_sections(fresh_cache, sid):
    r = asyncio.run(get_manual_section(sid))
    assert r.get("content_format") == "plain_text_verbatim"
    sn = r.get("structure_notice")
    assert isinstance(sn, str) and sn.startswith(STRUCTURE_NOTICE_HEADER)
    # 데이터 notes 원문이 전부 결정론 조립됨(generic 요약 아님)
    data = load_manual_b2()
    sec = data.by_id[sid]
    for note in sec["table_structure_notes"]:
        assert note in sn, (sid, note[:30])
    # 전문 응답에는 청크 주의 줄 없음
    assert STRUCTURE_NOTICE_CHUNK_LINE not in sn
    assert r.get("structure_notice_note") == STRUCTURE_NOTICE_NOTE
    # 기존 warnings 표면 병존(보존 — warnings에서 제거하지 않음)
    joined = "\n".join(r["warnings"])
    for note in sec["table_structure_notes"]:
        assert note in joined


# ── structure_notice 부착(청크·b3-4-2) + 크기 잠금 ──────────────────────────

@pytest.mark.parametrize("chunk", [1, 2])
def test_notice_attached_on_chunks_within_budget(fresh_cache, chunk):
    r = asyncio.run(get_manual_section("b3-4-2", chunk=chunk))
    assert r.get("is_complete") is False
    sn = r.get("structure_notice")
    assert isinstance(sn, str) and sn.startswith(STRUCTURE_NOTICE_HEADER)
    assert STRUCTURE_NOTICE_CHUNK_LINE in sn  # 절 전체 기준 주의(over-claim 차단)
    data = load_manual_b3()
    for note in data.by_id["b3-4-2"]["table_structure_notes"]:
        assert note in sn
        # 청크 응답에서도 기존 warnings 표면 병존(보존)
        assert any(note in w for w in r["warnings"])
    # ★크기 게이트: 부착 후에도 응답 예산(16,000자) 이내 — b3-4-2 청크 1이 최대 케이스
    size = len(json.dumps(r, ensure_ascii=False))
    assert size <= MANUAL_DETAIL_CHAR_BUDGET
    if chunk == 1:
        # 실측 정확값 잠금(15,799자) — 조립 문면·데이터·직렬화가 바뀌면 여기서 신호가 난다
        assert size == 15799, size


# ── 미부착 분기(포인터·notes 없는 절) ────────────────────────────────────────

@pytest.mark.parametrize("sid", ["b3-4-2", "1-1"])
def test_notice_absent_on_pointer(fresh_cache, sid):
    r = asyncio.run(get_manual_section(sid))
    assert r.get("content_format") == "oversized_pointer"
    assert "structure_notice" not in r
    assert "structure_notice_note" not in r


@pytest.mark.parametrize("sid", ["b3-1-1", "b2-1-1"])
def test_notice_absent_on_sections_without_notes(fresh_cache, sid):
    r = asyncio.run(get_manual_section(sid))
    assert r.get("content_format") == "plain_text_verbatim"
    assert "structure_notice" not in r
    assert "structure_notice_note" not in r


# ── 예산 백스톱·fail-safe(헬퍼 단위) ─────────────────────────────────────────

def test_budget_backstop_omits_without_mutation():
    sec = {"table_structure_notes": ["x" * 200]}
    resp = {"content": "y" * (MANUAL_DETAIL_CHAR_BUDGET - 50)}
    before = dict(resp)
    out = _attach_structure_notice(resp, sec, is_chunk=False)
    assert out == before  # 초과 시 원본 무변경 생략(v0.29.0 footer 백스톱과 동일 규약)


def test_attach_helper_adds_fields_when_within_budget():
    sec = {"table_structure_notes": ["구조 손실 안내 문장"]}
    resp = {"content": "본문"}
    out = _attach_structure_notice(resp, sec, is_chunk=True)
    assert out["structure_notice"].startswith(STRUCTURE_NOTICE_HEADER)
    assert "구조 손실 안내 문장" in out["structure_notice"]
    assert STRUCTURE_NOTICE_CHUNK_LINE in out["structure_notice"]
    assert out["structure_notice_note"] == STRUCTURE_NOTICE_NOTE


@pytest.mark.parametrize("bad", [None, "문자열", [], [1, 2], ["", None], ["유효 문장", 1], ["유효 문장", None], ["유효 문장", ""]])
def test_build_structure_notice_fail_safe(bad):
    """비정형 원소가 하나라도 있으면 전체 생략(fail-closed) — 일부만 조립된 불완전 안내가
    완전한 안내처럼 보이는 것 차단(diff 적대검토 MINOR 반영). warnings 표면은 별도 유지."""
    assert build_structure_notice({"table_structure_notes": bad}) is None


# ── 오류 self-echo 마스킹 3경로 ──────────────────────────────────────────────

def test_masking_invalid_section_id(fresh_cache, monkeypatch):
    monkeypatch.setenv("LAW_API_KEY", FAKE_KEY)
    r = asyncio.run(get_manual_section(FAKE_KEY))
    s = json.dumps(r, ensure_ascii=False)
    assert r["errors"][0]["code"] == "invalid_section_id"
    assert FAKE_KEY not in s
    assert "<KEY-REDACTED>" in r["errors"][0]["message"]


def test_masking_invalid_provision_id(monkeypatch):
    monkeypatch.setenv("LAW_API_KEY", FAKE_KEY)
    r = asyncio.run(get_provision_detail(FAKE_KEY))  # 콜론 없음 — part 수 위반 echo 경로
    s = json.dumps(r, ensure_ascii=False)
    assert r["errors"][0]["code"] == "invalid_provision_id"
    assert FAKE_KEY not in s
    assert "<KEY-REDACTED>" in r["errors"][0]["message"]


def test_masking_manifest_miss_not_found(monkeypatch):
    """doc_id는 형식 제약 없는 사용자 입력 — manifest 불일치 not_found 문면도 마스킹.
    resolve 폴백은 monkeypatch로 차단(네트워크 0)."""
    monkeypatch.setenv("LAW_API_KEY", FAKE_KEY)

    async def _no_resolve(*args, **kwargs):
        raise RuntimeError("blocked in test")

    monkeypatch.setattr(main_mod, "_resolve_doc_id", _no_resolve)
    r = asyncio.run(get_provision_detail(f"law:{FAKE_KEY}"))
    s = json.dumps(r, ensure_ascii=False)
    assert r["errors"][0]["code"] == "not_found"
    assert FAKE_KEY not in s
    assert "<KEY-REDACTED>" in r["errors"][0]["message"]


def test_masking_http_contextvar_key_three_paths(fresh_cache, monkeypatch):
    """HTTP 모드 per-user OC 키(contextvar)도 신규 마스킹 3경로에서 차단되는지 —
    _sanitize_error_message는 환경변수 키와 contextvar 키를 모두 검사(diff 적대검토 반영)."""
    monkeypatch.delenv("LAW_API_KEY", raising=False)
    token = main_mod._request_api_key.set(FAKE_KEY)
    try:
        r1 = asyncio.run(get_manual_section(FAKE_KEY))
        r2 = asyncio.run(get_provision_detail(FAKE_KEY))

        async def _no_resolve(*args, **kwargs):
            raise RuntimeError("blocked in test")

        monkeypatch.setattr(main_mod, "_resolve_doc_id", _no_resolve)
        r3 = asyncio.run(get_provision_detail(f"law:{FAKE_KEY}"))
    finally:
        main_mod._request_api_key.reset(token)
    for r in (r1, r2, r3):
        s = json.dumps(r, ensure_ascii=False)
        assert FAKE_KEY not in s
        assert "<KEY-REDACTED>" in r["errors"][0]["message"]


# ── 키 미포함 일반 오류 문면 byte 불변 ───────────────────────────────────────

def test_error_messages_unchanged_without_key(fresh_cache, monkeypatch):
    monkeypatch.delenv("LAW_API_KEY", raising=False)
    r = asyncio.run(get_manual_section("x-y-z"))
    assert r["errors"][0]["message"].startswith("section_id 형식 위반: 'x-y-z' — 허용 형식은 본권")
    r2 = asyncio.run(get_provision_detail("nocolon"))
    assert "2개 또는 3개 part" in r2["errors"][0]["message"]
    assert "받은 값: 'nocolon'" in r2["errors"][0]["message"]
