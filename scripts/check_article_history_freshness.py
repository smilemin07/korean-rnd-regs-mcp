"""조문별 변경 이력 스냅샷 신선도 매일 확인 — 운영 도구(서버 런타임·wheel과 무관).

무엇을 하는가(비프로그래머용): 서버는 배포 전에 만든 스냅샷(article_history.json)으로 조문 시행일 안내를 만든다.
법령이 새로 시행되어 서빙 판본이 바뀌면 서버는 그 법령에 일반 문장을 낸다(틀린 정보는 내지 않는다). 이 도구는
매일 35개 법령의 현재 판본(법령일련번호·시행일)을 운영 중인 스냅샷과 비교해, 바뀌었으면 macOS 알림으로
알린다. 알림이 오면 스냅샷을 다시 만들어 릴리스한다.

기준(운영본): `~/Library/Application Support/korean-rnd-regs-mcp/deployed_article_history.json`.
배포·롤백으로 서버를 교체할 때 그 커밋의 스냅샷으로 갱신한다:
  /Users/andykim/my_project/venv/bin/python scripts/check_article_history_freshness.py --record-deployed <git-ref>

보증 범위: 서빙 판본 식별자(법령일련번호·시행일) 변경만 감지한다. 본문 정상성, 같은 판본 안의 부칙 정정은
보증하지 않는다.

알림 규칙(--notify):
  - 판본 변경: 바뀐 목록이 지난 알림과 다르거나 마지막 알림 뒤 7일이 지나면 알린다. 알림이 성공한 뒤에만 기록한다.
  - 조회 실패(법령마다 1회 재시도 뒤): 2회 연속 실행에서 실패가 있으면 알린다.
  - 설정 오류(키 없음·기준 파일·manifest·상태 파일): 즉시 알린다.
  알림 문구에는 건수만 넣는다. 키·URL은 출력하지 않는다.

사용:
  /Users/andykim/my_project/venv/bin/python scripts/check_article_history_freshness.py --notify
종료 코드: 0 = 변화 없음 / 1 = 판본 변경 있음 / 2 = 조회 실패·설정 오류 있음(변경보다 우선) / 3 = 키 없음
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path.home() / "Library" / "Application Support" / "korean-rnd-regs-mcp"
BASELINE_PATH = STATE_DIR / "deployed_article_history.json"
STATE_PATH = STATE_DIR / "snapshot-check-state.json"
SNAPSHOT_REL = "src/korean_rnd_regs_mcp/article_history.json"
GIT = "/usr/bin/git"  # launchd PATH가 짧아 절대경로
DEADLINE_S = 300.0
RETRY_WAIT_S = 2.0
REALERT_DAYS = 7
FAIL_ALERT_RUNS = 2
TITLE = "규정 MCP 스냅샷 확인"
KST = timezone(timedelta(hours=9))


def _d8(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def mask(text: str, key: str = "") -> str:
    """출력 직전 정화 — 키 원문과 `OC=` 뒤 값을 지운다."""
    if key:
        text = text.replace(key, "***")
    return re.sub(r"OC=[^&\s]*", "OC=***", text)


def parse_snapshot(raw: str) -> tuple[str, dict[str, tuple[str, str]]]:
    """스냅샷 JSON → (generated_at, {rule_set_id: (mst, 시행일 8자리)}). 형식 이상이면 ValueError."""
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("laws"), dict):
        raise ValueError("snapshot_format")
    out = {}
    for rid, law in data["laws"].items():
        if not (isinstance(law, dict) and isinstance(law.get("mst"), str) and isinstance(law.get("efyd"), str)):
            raise ValueError("snapshot_law_format")
        out[rid] = (law["mst"], _d8(law["efyd"]))
    if not out:
        raise ValueError("snapshot_empty")
    return str(data.get("generated_at") or ""), out


def compare(baseline: dict[str, tuple[str, str]], current: dict[str, tuple[str, str] | None]) -> tuple[list, list]:
    """(바뀐 법령 [(rid, 기준 mst, 기준 시행일, 현재 doc_id, 현재 시행일)], 조회 실패 [rid]). 순수 함수."""
    changed, failed = [], []
    for rid in sorted(baseline):
        cur = current.get(rid)
        if cur is None:
            failed.append(rid)
        elif (cur[0], _d8(cur[1])) != baseline[rid]:
            changed.append((rid, baseline[rid][0], baseline[rid][1], cur[0], _d8(cur[1])))
    return changed, failed


def decide(changed: list, failed: list, state: dict, today: date) -> tuple[bool, bool, dict]:
    """(변경 알림 여부, 실패 알림 여부, 알림 전 상태). 변경 알림 기록은 알림 성공 뒤 호출부가 한다. 순수 함수."""
    sig = json.dumps(changed, ensure_ascii=False) if changed else ""
    new = dict(state)
    streak = int(state.get("fail_streak") or 0) + 1 if failed else 0
    new["fail_streak"] = streak
    notify_change = False
    if changed:
        last = state.get("alerted_on")
        try:
            stale = last is None or (today - date.fromisoformat(last)).days >= REALERT_DAYS
        except (TypeError, ValueError):
            stale = True
        notify_change = sig != state.get("alert_sig") or stale
    else:
        new["alert_sig"], new["alerted_on"] = "", None  # 해소되면 다음 변경은 바로 알린다
    notify_fail = bool(failed) and streak >= FAIL_ALERT_RUNS
    return notify_change, notify_fail, new


def load_state(path: Path) -> tuple[dict, bool]:
    """(상태, 손상 여부). 파일이 없으면 빈 상태, 손상이면 빈 상태 + True."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, False
    except OSError:
        return {}, True
    try:
        data = json.loads(raw)
        return (data, False) if isinstance(data, dict) else ({}, True)
    except ValueError:
        return {}, True


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def notify(title: str, message: str) -> bool:
    """macOS 알림. 문구는 내부에서 만든 건수 문장뿐이다. 성공(반환 코드 0)이면 True."""
    safe = lambda s: s.replace("\\", "").replace('"', "")
    try:
        r = subprocess.run(["osascript", "-e", f'display notification "{safe(message)}" with title "{safe(title)}"'],
                           check=False, timeout=15, capture_output=True)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def record_deployed(ref: str) -> int:
    """배포(또는 롤백)한 커밋의 스냅샷을 기준 파일로 저장한다."""
    if not ref or ref.startswith("-"):
        print("git ref 형식 이상")
        return 2
    r = subprocess.run([GIT, "-C", str(ROOT), "show", f"{ref}:{SNAPSHOT_REL}"], capture_output=True, timeout=30)
    if r.returncode != 0:
        print(f"git show 실패: {ref}")
        return 2
    raw = r.stdout.decode("utf-8")
    gen, laws = parse_snapshot(raw)
    write_atomic(BASELINE_PATH, raw)
    print(f"기준 갱신: {ref} · 생성 {gen} · 법령 {len(laws)} · sha256 {hashlib.sha256(r.stdout).hexdigest()}")
    return 0


def fetch_current(client, targets: list, deadline: float) -> dict[str, tuple[str, str] | None]:
    """법령마다 resolve 1회(실패·resolve_failed면 1회 재시도). 시간 상한을 넘기면 남은 법령은 실패(None)."""
    out: dict[str, tuple[str, str] | None] = {}
    for rs in targets:
        got = None
        for attempt in range(2):
            if time.monotonic() > deadline:
                break
            try:
                res = client.resolve_latest_doc_id(rs.title, "law", rs.api_doc_id, rs.ministry)
                if not getattr(res, "resolve_failed", False) and res.doc_id:
                    got = (res.doc_id, res.effective_date or "")
                    break
            except Exception:  # noqa: BLE001 — 법령 하나의 실패가 나머지를 막지 않게(종류는 출력 안 함)
                pass
            if attempt == 0:
                time.sleep(RETRY_WAIT_S)
        out[rs.id] = got
    return out


def run(args) -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(ROOT / "src"))
    from korean_rnd_regs_mcp.live_api import LawApiClient
    from korean_rnd_regs_mcp.manifest import load_manifest

    now = datetime.now(KST)
    print(f"[{now:%Y-%m-%d %H:%M} KST] 스냅샷 신선도 확인")
    client = LawApiClient()
    if not client.api_key:
        print("LAW_API_KEY 없음")
        if args.notify:
            notify(TITLE, "API Key가 없어 확인하지 못했습니다. 로그를 확인하십시오.")
        return 3
    key = client.api_key
    config_errors: list[str] = []
    state, corrupt = load_state(STATE_PATH)
    if corrupt:
        config_errors.append("상태 파일 손상(빈 상태로 다시 씀)")
    try:
        gen, baseline = parse_snapshot(Path(args.snapshot).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"기준 스냅샷을 읽지 못함: {type(e).__name__}")
        if args.notify:
            notify(TITLE, "기준 스냅샷을 읽지 못했습니다. 로그를 확인하십시오.")
        return 2
    print(f"기준: {args.snapshot} · 생성 {gen} · 법령 {len(baseline)}")
    targets = [r for r in load_manifest() if r.api_target.value == "law"]
    if {r.id for r in targets} != set(baseline):
        config_errors.append("manifest 법령 집합과 기준 스냅샷이 다름")
        targets = [r for r in targets if r.id in baseline]

    current = fetch_current(client, targets, time.monotonic() + DEADLINE_S)
    changed, failed = compare(baseline, current)
    for rid, omst, oefyd, nmst, nefyd in changed:
        print(mask(f"판본 변경: {rid} {omst}·{oefyd} → {nmst}·{nefyd}", key))
    for rid in failed:
        print(f"조회 실패: {rid}")
    for msg in config_errors:
        print(f"설정 오류: {msg}")
    print(f"결과: 변경 {len(changed)} · 실패 {len(failed)} · 설정 오류 {len(config_errors)}")

    notify_change, notify_fail, new_state = decide(changed, failed, state, now.date())
    if args.notify and (notify_change or notify_fail or config_errors):
        parts = []
        if changed:
            parts.append(f"판본 변경 {len(changed)}건")
        if failed:
            parts.append(f"조회 실패 {len(failed)}건")
        if config_errors:
            parts.append(f"설정 오류 {len(config_errors)}건")
        ok = notify(TITLE, " · ".join(parts) + ". 로그를 확인하십시오.")
        print(f"알림: {'보냄' if ok else '실패'}")
        if ok and changed:
            new_state["alert_sig"] = json.dumps(changed, ensure_ascii=False)
            new_state["alerted_on"] = now.date().isoformat()
    new_state["last_run"] = now.isoformat(timespec="seconds")
    if not failed and not config_errors:
        new_state["last_success"] = new_state["last_run"]
    try:
        write_atomic(STATE_PATH, json.dumps(new_state, ensure_ascii=False, indent=1))
    except OSError as e:
        print(f"상태 파일 쓰기 실패: {type(e).__name__}")
        if args.notify:
            notify(TITLE, "상태 파일을 쓰지 못했습니다. 로그를 확인하십시오.")
        return 2
    if failed or config_errors:
        return 2
    return 1 if changed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="조문별 변경 이력 스냅샷의 판본 신선도 확인")
    ap.add_argument("--notify", action="store_true", help="변경·실패·설정 오류가 있으면 macOS 알림")
    ap.add_argument("--snapshot", default=str(BASELINE_PATH), help="비교 기준 스냅샷 경로(기본: 운영본 사본)")
    ap.add_argument("--record-deployed", metavar="GIT_REF", help="배포·롤백한 커밋의 스냅샷을 기준으로 저장하고 끝냄")
    args = ap.parse_args(argv)
    try:
        if args.record_deployed:
            return record_deployed(args.record_deployed)
        return run(args)
    except Exception as e:  # noqa: BLE001 — 예외 메시지·traceback은 키를 담을 수 있어 종류만 남긴다
        print(f"오류: {type(e).__name__}")
        if args.notify:
            notify(TITLE, "확인 중 오류가 났습니다. 로그를 확인하십시오.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
