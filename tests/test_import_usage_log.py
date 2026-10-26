"""scripts/import_usage_log.py 가드 (네트워크 0) — v0.61.0."""
import importlib.util
import io
import os
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "import_usage_log.py"
if not _SCRIPT.exists():  # pragma: no cover - sdist 배포본 경로
    pytest.skip("scripts/import_usage_log.py 미포함 배포본", allow_module_level=True)

_SPEC = importlib.util.spec_from_file_location("import_usage_log", _SCRIPT)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)

P = "2026-10-27 10:00:00,123 - rnd-regs-mcp - INFO - "


def L(date="2026-10-27", final=0, boot="aaaaaaaa", seq=1, users=1, http=10, tools=2, sat=0):
    return (f"{P}event=daily_usage date={date} final={final} boot={boot} seq={seq} users={users} "
            f"http_requests={http} tool_calls={tools} saturated={sat}\n")


def _run(note, text):
    return _MOD.run(str(note), io.StringIO(text))


def test_server_line_format_matches_importer():
    """서버가 실제로 찍는 줄을 importer가 받는다(형식 결박)."""
    import logging
    from datetime import datetime, timedelta, timezone

    from korean_rnd_regs_mcp.usage_stats import _UsageStats

    s = _UsageStats(now=datetime(2026, 10, 27, 9, 0, tzinfo=timezone(timedelta(hours=9))))
    s.enable()
    s._seq = 0
    line = s._line(final=False)
    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    rec = logging.LogRecord("rnd-regs-mcp", logging.INFO, __file__, 1, line, None, None)
    rows, rejected = _MOD.parse_log_lines([fmt.format(rec)])
    assert rejected == 0 and len(rows) == 1


def test_new_note_and_merge_by_seq(tmp_path):
    note = tmp_path / "n.md"
    assert _run(note, L(seq=1, http=5) + L(seq=3, http=9, tools=4) + L(seq=2, http=7)) == 0
    rows = _MOD.read_raw_rows(note.read_text(encoding="utf-8"))
    assert len(rows) == 1 and rows[0]["seq"] == 3 and rows[0]["tool_calls"] == 4
    # 다시 가져와도 같은 결과(멱등)
    assert _run(note, L(seq=1, http=5)) == 0
    assert _MOD.read_raw_rows(note.read_text(encoding="utf-8"))[0]["seq"] == 3


def test_multi_boot_day_shows_range(tmp_path):
    note = tmp_path / "n.md"
    _run(note, L(boot="aaaaaaaa", users=3, seq=2) + L(boot="bbbbbbbb", users=2, seq=1))
    text = note.read_text(encoding="utf-8")
    assert "| 2026-10-27 | 3~5 |" in text


def test_rejects_foreign_and_injected_lines(tmp_path):
    note = tmp_path / "n.md"
    secret = "SECRETKEY123"
    bad = (
        f"{P}lawSearch 상세링크 OC={secret} event=daily_usage date=2026-10-27\n"
        f"{P}Invalid arguments for tool 'x\\nevent=daily_usage date=2026-10-27 final=0 boot=aaaaaaaa seq=9 "
        f"users=999 http_requests=1 tool_calls=1 saturated=0'\n"
        + L().rstrip("\n") + f" extra={secret}\n"
        + "x" * 1000 + "\n"
    )
    assert _run(note, bad + L(users=1)) == 0
    text = note.read_text(encoding="utf-8")
    assert secret not in text and "999" not in text


def test_fail_closed_on_unparseable_note(tmp_path):
    note = tmp_path / "n.md"
    _run(note, L())
    broken = note.read_text(encoding="utf-8").replace("| aaaaaaaa |", "| 손으로 고침 |")
    note.write_text(broken, encoding="utf-8")
    assert _run(note, L(seq=5)) == 3
    assert note.read_text(encoding="utf-8") == broken


def test_refuses_note_without_raw_table(tmp_path):
    note = tmp_path / "other.md"
    note.write_text("# 다른 노트\n", encoding="utf-8")
    assert _run(note, L()) == 3
    assert note.read_text(encoding="utf-8") == "# 다른 노트\n"


def test_refuses_non_md_and_concurrent_run(tmp_path):
    assert _run(tmp_path / "n.csv", L()) == 2
    note = tmp_path / "n.md"
    lock = os.path.join(_MOD.tempfile.gettempdir(),
                        f"usage-note-{_MOD._sha(os.path.realpath(str(note)))[:12]}.lock")
    open(lock, "w").close()
    try:
        assert _run(note, L()) == 4
        assert not note.exists()
    finally:
        os.unlink(lock)


def test_decrease_warning(tmp_path, capsys):
    note = tmp_path / "n.md"
    assert _run(note, L(seq=1, http=10) + L(seq=2, http=8)) == 0
    assert "줄어든 줄 1개" in capsys.readouterr().out


def test_fail_closed_on_broken_separator(tmp_path):
    """구분선이 사라지면 첫 데이터 행을 머리 다음 줄로 오인하지 않고 멈춘다(diff 적대검토 Codex)."""
    note = tmp_path / "n.md"
    _run(note, L())
    text = note.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    i = next(k for k, x in enumerate(lines) if x.startswith("| date | boot |"))
    broken = "".join(lines[: i + 1] + lines[i + 2:])
    note.write_text(broken, encoding="utf-8")
    assert _run(note, L(seq=2)) == 3
    assert note.read_text(encoding="utf-8") == broken


def test_seq_conflict_stops(tmp_path):
    note = tmp_path / "n.md"
    assert _run(note, L(seq=1, http=5) + L(seq=1, http=6)) == 3
    assert not note.exists()


def test_note_changed_before_replace_stops(tmp_path, monkeypatch):
    note = tmp_path / "n.md"
    _run(note, L())
    original_render = _MOD.render

    def render_and_touch(*a, **k):
        out = original_render(*a, **k)
        note.write_text(note.read_text(encoding="utf-8") + "\n손으로 추가\n", encoding="utf-8")
        return out

    monkeypatch.setattr(_MOD, "render", render_and_touch)
    assert _run(note, L(seq=2)) == 5
    assert "손으로 추가" in note.read_text(encoding="utf-8")


def test_backup_written_outside_vault(tmp_path):
    note = tmp_path / "n.md"
    _run(note, L())
    before = note.read_text(encoding="utf-8")
    _run(note, L(seq=2))
    tag = _MOD._sha(os.path.realpath(str(note)))[:12]
    backup = os.path.join(_MOD.tempfile.gettempdir(), f"usage-note-{tag}.backup.md")
    with open(backup, encoding="utf-8") as f:
        assert f.read() == before
    assert sorted(x.name for x in tmp_path.iterdir()) == ["n.md"]


def test_no_rewrite_when_nothing_new(tmp_path, capsys):
    note = tmp_path / "n.md"
    _run(note, L())
    text = note.read_text(encoding="utf-8")
    mtime = note.stat().st_mtime_ns
    assert _run(note, L()) == 0
    assert "변경 없음" in capsys.readouterr().out
    assert note.stat().st_mtime_ns == mtime and note.read_text(encoding="utf-8") == text


def test_client_text_with_newline_cannot_forge_a_line(capfd):
    """클라이언트가 도구 이름·인자에 줄바꿈 + 완전한 가짜 줄을 넣어도, 서버가 쓰는 어떤 로그 줄도
    importer 형식에 맞지 않는다(diff 적대검토 Codex·Grok — FastMCP는 이름·인자를 repr로 찍어 줄바꿈이 이스케이프됨)."""
    import asyncio

    from fastmcp import Client

    from korean_rnd_regs_mcp import main

    forged = ("\n2026-10-27 10:00:00,123 - rnd-regs-mcp - INFO - event=daily_usage date=2026-10-27 final=0 "
              "boot=ffffffff seq=9 users=999 http_requests=1 tool_calls=1 saturated=0\n")

    async def run():
        async with Client(main.mcp) as c:
            await c.call_tool("no_such_tool" + forged, {}, raise_on_error=False)
            await c.call_tool("get_manual_section", {"section_id": forged, "bogus": forged}, raise_on_error=False)
            await c.call_tool("search_manual", {"query": forged}, raise_on_error=False)

    asyncio.run(run())
    out, err = capfd.readouterr()
    rows, _ = _MOD.parse_log_lines((out + err).splitlines())
    assert rows == []
