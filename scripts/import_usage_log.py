"""서버 로그의 일별 이용 현황 줄(event=daily_usage)을 볼트 노트로 옮긴다 — v0.61.0 운영 도구.

wheel에 포함되지 않는 운영자용 스크립트다(서버 실행과 무관). 표준 라이브러리만 쓴다.

사용 예(Mac 터미널):
  ssh <NAS> 'sudo -n /usr/local/bin/docker logs korean-rnd-regs-mcp 2>&1' \\
    | grep -F 'event=daily_usage' \\
    | /Users/andykim/my_project/venv/bin/python scripts/import_usage_log.py --note "<볼트 노트 경로>"

배포(컨테이너 재생성) 직전에는 반드시 실행한다. 재생성하면 컨테이너 로그가 사라진다.
로그에 찍힌 줄만 옮길 수 있다 — 마지막 줄 이후 아직 줄로 남지 않은 숫자는 옮길 수 없다.
그래서 배포 때는 다음 10분 구간이 시작된 뒤 서버에 요청 1회(무키 GET /mcp)를 보내 줄을 남기고 나서 실행한다.

동작:
  - 앱 로그 형식 전체가 맞는 줄(날짜·숫자·고정 이름)만 받는다. 다른 줄은 세기만 하고 내용은 출력하지 않는다.
    그래서 키·검색어 같은 다른 로그 내용은 노트에 들어갈 수 없다.
  - 같은 (날짜, boot)의 줄은 누적값이라 줄 번호(seq)가 가장 큰 줄 하나만 남긴다.
  - 노트의 원자료 표가 해석되지 않으면 아무것도 쓰지 않고 멈춘다(fail-closed).
  - 동시에 두 번 실행되지 않게 잠금 파일을 쓴다. 읽은 뒤 노트가 바뀌었으면 쓰지 않고 멈춘다.
  - 쓰기는 임시 파일에 쓴 뒤 교체한다. 기존 노트는 시스템 임시 폴더에 백업한다.
  - 출력은 건수 요약뿐이다.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

INT_FIELDS = ("seq", "users", "http_requests", "tool_calls")
RAW_COLUMNS = ("date", "boot", "seq", "final", "users", "http_requests", "tool_calls", "saturated")
_MAX_LINE = 400
_MAX_LINES = 1_000_000

_LINE_RE = re.compile(
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} - rnd-regs-mcp - INFO - event=daily_usage"
    r" date=(?P<date>\d{4}-\d{2}-\d{2})"
    r" final=(?P<final>[01])"
    r" boot=(?P<boot>[0-9a-f]{8})"
    r" seq=(?P<seq>\d{1,9})"
    r" users=(?P<users>\d{1,9})"
    r" http_requests=(?P<http_requests>\d{1,12})"
    r" tool_calls=(?P<tool_calls>\d{1,12})"
    r" saturated=(?P<saturated>[01])"
)
BEGIN = "<!-- usage-raw-begin -->"
END = "<!-- usage-raw-end -->"
_KST = timezone(timedelta(hours=9))
TITLE = "SP1 - rnd-regs-mcp - 2026-10-27 - 기록 - 일별 이용 현황"


class NoteFormatError(Exception):
    pass


def _row(rec: dict) -> dict:
    """문자열 칸 → 검증된 행. 틀리면 ValueError."""
    date.fromisoformat(rec["date"])
    if not re.fullmatch(r"[0-9a-f]{8}", rec["boot"]):
        raise ValueError("boot")
    if rec["final"] not in ("0", "1") or rec["saturated"] not in ("0", "1"):
        raise ValueError("flag")
    row = {"date": rec["date"], "boot": rec["boot"], "final": int(rec["final"]),
           "saturated": int(rec["saturated"])}
    for f in INT_FIELDS:
        if not re.fullmatch(r"\d{1,12}", rec[f]):
            raise ValueError(f)
        row[f] = int(rec[f])
    return row


def parse_log_lines(lines):
    """daily_usage 줄 → (행 목록, 버린 줄 수)."""
    rows, rejected = [], 0
    for i, line in enumerate(lines):
        if i >= _MAX_LINES:
            rejected += 1
            continue
        line = line.rstrip("\r\n")
        m = _LINE_RE.fullmatch(line) if len(line) <= _MAX_LINE else None
        if not m:
            rejected += 1
            continue
        try:
            rows.append(_row(m.groupdict()))
        except ValueError:
            rejected += 1
    return rows, rejected


class SeqConflictError(Exception):
    pass


def merge(existing, new):
    """(date, boot)마다 seq가 가장 큰 행 하나. 카운터가 줄어든 행 수를 함께 돌려준다.

    같은 (date, boot, seq)에 값이 다른 두 행이 있으면 SeqConflictError(정상 서버에서는 생기지 않음).
    """
    groups: dict[tuple[str, str], dict[int, dict]] = {}
    for row in list(existing) + list(new):
        g = groups.setdefault((row["date"], row["boot"]), {})
        if row["seq"] in g and g[row["seq"]] != row:
            raise SeqConflictError(f"{row['date']} boot {row['boot']} seq {row['seq']}")
        g[row["seq"]] = row
    merged, decreases = [], 0
    for key in sorted(groups):
        by_seq = groups[key]
        prev = None
        for s in sorted(by_seq):
            cur = by_seq[s]
            if prev and any(cur[f] < prev[f] for f in ("users", "http_requests", "tool_calls")):
                decreases += 1
            prev = cur
        merged.append(by_seq[max(by_seq)])
    return merged, decreases


def read_raw_rows(text):
    """노트의 원자료 표를 읽는다. 표식이 없으면 None, 해석 불가면 NoteFormatError."""
    if BEGIN not in text and END not in text:
        return None
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) > text.index(END):
        raise NoteFormatError("원자료 표식이 하나씩 순서대로 있어야 합니다")
    body = text[text.index(BEGIN) + len(BEGIN):text.index(END)].strip().splitlines()
    if len(body) < 2:
        raise NoteFormatError("원자료 표 머리가 없습니다")
    header = tuple(c.strip() for c in body[0].strip().strip("|").split("|"))
    if header != RAW_COLUMNS:
        raise NoteFormatError("원자료 표 머리가 예상과 다릅니다")
    sep = [c.strip() for c in body[1].strip().strip("|").split("|")]
    if len(sep) != len(RAW_COLUMNS) or not all(re.fullmatch(r":?-{3,}:?", c) for c in sep):
        raise NoteFormatError("원자료 표 구분선이 예상과 다릅니다")
    rows = []
    for line in body[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != len(RAW_COLUMNS):
            raise NoteFormatError("원자료 행의 칸 수가 다릅니다")
        try:
            rows.append(_row(dict(zip(RAW_COLUMNS, cells))))
        except ValueError as exc:
            raise NoteFormatError("원자료 행을 해석할 수 없습니다") from exc
    return rows


def _table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def render(rows, created, revised):
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)
    summary = []
    for d in sorted(by_date, reverse=True):
        rs = by_date[d]
        lo = max(r["users"] for r in rs)
        hi = sum(r["users"] for r in rs)
        users = str(lo) if len(rs) == 1 else f"{lo}~{hi}"
        if any(r["saturated"] for r in rs):
            users += "+"
        state = "자정 뒤 기록" if all(r["final"] for r in rs) else "중간값"
        summary.append([d, users, sum(r["tool_calls"] for r in rs),
                        sum(r["http_requests"] for r in rs), len(rs), state])
    lines = [
        "---", f"created: {created}", f"revised: {revised}", "aliases:", "tags:", "---", "",
        f"# {TITLE}", "",
        "- 원격 서버(mcp.rndmanagers.org)가 KST 하루마다 로그에 남긴 숫자를 옮긴 노트다. v0.61.0(2026-10-27 배포)부터 기록한다.",
        "- `scripts/import_usage_log.py`(korean-rnd-regs-mcp 저장소)가 이 노트를 고쳐 쓴다. 표를 손으로 고치지 않는다.",
        "- 이용자 수 = 그날 도구를 써서 결과를 받은 서로 다른 API Key 수다. 사람 수가 아니다(한 키를 여럿이 쓰거나 한 사람이 키 여럿을 쓸 수 있다).",
        "  - 빠지는 것: 연결만 하고 도구를 부르지 않은 경우, health만 부른 경우, 결과가 없는 호출, 그날 인증 실패가 난 키.",
        "- 숫자는 로그에 찍힌 마지막 줄 기준이다. 그 줄 이후 서버가 꺼질 때까지의 요청은 빠진다(줄은 10분 구간이 바뀐 뒤 첫 요청 때 찍힘).",
        "- 그날 서버가 다시 시작되면(배포 포함) 부팅마다 따로 센다. 이용자 수는 부팅별 값의 최댓값~합계로 적는다(관측된 구간 기준). `+`는 집계 상한(1만)에 닿았다는 뜻이다.",
        "- HTTP 요청에는 연결 유지 요청이 섞여 있다. 이용량은 도구 호출로 본다.",
        "- 상태 \"중간값\"은 그날 부팅 가운데 자정 뒤 줄이 없는 것이 있다는 뜻이다(배포로 끝난 부팅은 늘 그렇다). \"자정 뒤 기록\"이어도 위 빠지는 구간은 있을 수 있다.",
        "- 2026-10-27은 배포·시험 호출이 섞여 있다.",
        "",
        "## 날짜별 요약", "",
        *_table(["날짜", "이용자 수", "도구 호출", "HTTP 요청", "부팅 수", "상태"], summary),
        "", "## 원자료", "", BEGIN,
        *_table(list(RAW_COLUMNS), [[r[c] for c in RAW_COLUMNS] for r in rows]),
        END, "",
    ]
    return "\n".join(lines)


def _revised_of(text):
    m = re.search(r"^revised: (\d{4}-\d{2}-\d{2})$", text, re.M)
    return m.group(1) if m else None


def _created_of(text, default):
    m = re.search(r"^created: (\d{4}-\d{2}-\d{2})$", text, re.M)
    return m.group(1) if m else default


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(note: str, stdin) -> int:
    if not note.endswith(".md"):
        print("오류: --note는 .md 파일이어야 합니다", file=sys.stderr)
        return 2
    # 잠금·백업 파일은 볼트 밖(시스템 임시 폴더)에 둔다 — 동기화 폴더에 흔적을 남기지 않게.
    tag = _sha(os.path.realpath(note))[:12]
    lock = os.path.join(tempfile.gettempdir(), f"usage-note-{tag}.lock")
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print(f"중단: 다른 가져오기가 실행 중입니다(남은 잠금이면 지우고 다시 실행: {lock})", file=sys.stderr)
        return 4
    try:
        new_rows, rejected = parse_log_lines(stdin)
        text = ""
        existed = os.path.exists(note)
        if existed:
            with open(note, encoding="utf-8") as f:
                text = f.read()
        try:
            old_rows = read_raw_rows(text)
        except NoteFormatError as exc:
            print(f"중단: 노트를 고치지 않았습니다 — {exc}", file=sys.stderr)
            return 3
        if text and old_rows is None:
            print("중단: 노트에 원자료 표가 없습니다(다른 노트일 수 있음)", file=sys.stderr)
            return 3
        try:
            merged, decreases = merge(old_rows or [], new_rows)
        except SeqConflictError as exc:
            print(f"중단: 노트를 고치지 않았습니다 — 같은 줄 번호에 다른 값이 있습니다({exc})", file=sys.stderr)
            return 3
        today = datetime.now(_KST).date().isoformat()
        unchanged = old_rows is not None and merged == sorted(old_rows, key=lambda r: (r["date"], r["boot"]))
        if unchanged and _revised_of(text) and render(merged, _created_of(text, today), _revised_of(text)) == text:
            print(f"변경 없음 · 읽은 줄 {len(new_rows)} · 버린 줄 {rejected} · 행 {len(merged)}")
            return 0
        out = render(merged, _created_of(text, today), today)
        if text:
            shutil.copyfile(note, os.path.join(tempfile.gettempdir(), f"usage-note-{tag}.backup.md"))
        d = os.path.dirname(os.path.abspath(note))
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".usage-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(out)
            # 교체 직전에 노트가 읽은 때와 같은지 다시 본다(없던 노트가 생긴 경우 포함).
            # 이 확인과 교체 사이의 아주 짧은 틈은 막지 못한다 — 노트를 손으로 고치지 않는 규칙으로 보완.
            exists_now = os.path.exists(note)
            changed = exists_now != existed
            if exists_now and not changed:
                with open(note, encoding="utf-8") as f:
                    changed = f.read() != text
            if changed:
                os.unlink(tmp)
                print("중단: 읽는 동안 노트가 바뀌었습니다. 다시 실행하십시오", file=sys.stderr)
                return 5
            os.replace(tmp, note)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        msg = f"읽은 줄 {len(new_rows)} · 버린 줄 {rejected} · 기존 행 {len(old_rows or [])} · 결과 행 {len(merged)}"
        if decreases:
            msg += f" · 경고: 카운터가 줄어든 줄 {decreases}개(시계 보정 등)"
        print(msg)
        return 0
    finally:
        os.close(lock_fd)
        os.unlink(lock)


def main(argv=None):
    ap = argparse.ArgumentParser(description="서버 로그의 daily_usage 줄을 볼트 노트로 옮긴다")
    ap.add_argument("--note", required=True, help="볼트 노트(.md) 경로")
    args = ap.parse_args(argv)
    # 비UTF-8 바이트가 섞여도 멈추지 않게 — 그런 줄은 형식 검사에서 버려진다.
    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    return run(args.note, stdin)


if __name__ == "__main__":
    sys.exit(main())
