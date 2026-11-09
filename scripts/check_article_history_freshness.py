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
  - 조회 실패(시행일 없는 결과 포함): 2회 연속 실행에서 실패가 있으면 알린다. 같은 날 04:00·08:40 두 실행도 연속이다.
    법령마다 1회 조회한다(HTTP 계층이 2회 시도). 같은 client의 재조회는 실패 캐시(300초)를 돌려받아 무의미했다.
  - 설정 오류(키 없음·인증 실패·기준 파일·manifest·상태 파일)·실행 오류: 즉시 알린다.
  - 조회 실패·설정 오류·실행 오류 알림은 하루 1회다(상태 trouble_alerted_on). 판본 변경 알림은 위 규칙대로.
  알림 문구에는 건수만 넣는다. 키·URL은 출력하지 않는다.

예약 실행: launchd가 래퍼 ~/.local/bin/regs-snapshot-check.sh를 04:00·08:40·로그인 때 띄운다(--notify).
이 스크립트가 끝까지 성공하면(실패·설정 오류 0, 필요한 알림 전송 성공, 04:00 이후, 실행 중 기준 파일 불변) 완료 표시
snapshot-check-done-date에 오늘 날짜를 쓰고, 래퍼는 그날 남은 실행을 건너뛴다. --record-deployed는 완료 표시를 지워
다음 예약 실행이 새 기준으로 다시 확인하게 한다. 표시를 지우면 같은 날 다시 확인한다.

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
DONE_MARK_PATH = STATE_DIR / "snapshot-check-done-date"  # 래퍼가 읽는 "오늘 확인 완료" 표시(이 스크립트가 씀)
STATE_KEYS = ("fail_streak", "alert_sig", "alerted_on", "trouble_alerted_on", "last_run", "last_success")
SNAPSHOT_REL = "src/korean_rnd_regs_mcp/article_history.json"
GIT = "/usr/bin/git"  # launchd PATH가 짧아 절대경로
DEADLINE_S = 240.0  # 래퍼 상한(420초)보다 법령 1건 최악(약 41초)·알림(15초)·기동 시간만큼 여유를 둔다
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
            age = None if last is None else (today - date.fromisoformat(last)).days
            stale = age is None or not 0 <= age < REALERT_DAYS  # 미래 날짜도 재알림(억제가 무기한 이어지지 않게)
        except (TypeError, ValueError):
            stale = True
        notify_change = sig != state.get("alert_sig") or stale
    elif not failed:
        new["alert_sig"], new["alerted_on"] = "", None  # 해소되면 다음 변경은 바로 알린다(조회 실패는 해소의 증거가 아님)
    notify_fail = bool(failed) and streak >= FAIL_ALERT_RUNS
    return notify_change, notify_fail, new


def load_state(path: Path) -> tuple[dict, bool]:
    """(상태, 손상 여부). 예외를 던지지 않는다 — 알림 경로(main의 except)도 이 함수를 부르기 때문이다.
    파일이 없으면 빈 상태, 읽기·해석 실패(UTF-8 아님·깊은 중첩 등)나 필드 형식 이상이면 빈 상태 + True.
    알려진 키만 남겨 돌려준다(모르는 키의 값이 다시 쓸 때 오류를 내지 않게)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, False
    except Exception:  # noqa: BLE001 — OSError·UnicodeDecodeError·JSONDecodeError·RecursionError 등
        return {}, True
    if not isinstance(data, dict):
        return {}, True
    data = {k: v for k, v in data.items() if k in STATE_KEYS}
    streak = data.get("fail_streak", 0)
    if (streak is not None and (isinstance(streak, bool) or not isinstance(streak, int) or streak < 0)) \
            or not isinstance(data.get("alert_sig", ""), (str, type(None))) \
            or not isinstance(data.get("alerted_on"), (str, type(None))) \
            or not isinstance(data.get("trouble_alerted_on"), (str, type(None))) \
            or not all(isinstance(data.get(k), (str, type(None))) for k in ("last_run", "last_success")):
        return {}, True  # 형식이 틀린 값이 남아 매일 같은 예외가 반복되지 않게 빈 상태로 다시 쓴다
    return data, False


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
    DONE_MARK_PATH.unlink(missing_ok=True)  # 새 기준으로 다음 예약 실행이 다시 확인하게 한다
    print(f"기준 갱신: {ref} · 생성 {gen} · 법령 {len(laws)} · sha256 {hashlib.sha256(r.stdout).hexdigest()}")
    return 0


def fetch_current(client, targets: list, deadline: float) -> tuple[dict[str, tuple[str, str] | None], dict[str, str]]:
    """법령마다 resolve 1회. (현재 판본 {rid: (doc_id, 시행일) | None}, 실패 사유 {rid: 코드}).

    재시도하지 않는다: HTTP 계층이 2회 시도하고, 같은 client의 재조회는 실패 캐시를 돌려받는다.
    시행일이 빈 결과(일치 행이 모두 미래라 manifest ID로 폴백)는 판본으로 받지 않고 실패로 둔다(오경보 방지).
    시간 상한을 넘기면 남은 법령은 실패("deadline").
    """
    out: dict[str, tuple[str, str] | None] = {}
    why: dict[str, str] = {}
    for rs in targets:
        out[rs.id] = None
        if time.monotonic() > deadline:
            why[rs.id] = "deadline"
            continue
        try:
            res = client.resolve_latest_doc_id(rs.title, "law", rs.api_doc_id, rs.ministry)
        except Exception as e:  # noqa: BLE001 — 법령 하나의 실패가 나머지를 막지 않게(종류 이름만 남긴다)
            why[rs.id] = type(e).__name__
            continue
        if getattr(res, "resolve_failed", False) or not res.doc_id:
            why[rs.id] = str(getattr(res, "resolve_error_code", "") or "resolve_failed")
        elif not _d8(res.effective_date or ""):
            why[rs.id] = f"no_effective_date, {res.doc_id}"  # 공개 법령일련번호(런타임도 이 날은 일반 문장)
        else:
            out[rs.id] = (res.doc_id, res.effective_date)
    return out, why


def code_info() -> str:
    """진단용 — 스크립트가 import하는 작업 트리의 브랜치·커밋·변경 여부. 실패하면 '확인 불가'."""
    try:
        def git(*a):
            return subprocess.run([GIT, "--no-optional-locks", "-C", str(ROOT), *a],
                                  capture_output=True, text=True, timeout=5).stdout.strip()
        branch, head = git("rev-parse", "--abbrev-ref", "HEAD"), git("rev-parse", "--short=7", "HEAD")
        if not head:
            return "확인 불가"
        dirty = " · 작업 트리 변경 있음" if git("status", "--porcelain", "--untracked-files=no") else ""
        return f"{branch} {head}{dirty}"
    except (OSError, subprocess.SubprocessError):
        return "확인 불가"


def now_kst() -> datetime:
    return datetime.now(KST)


_header_printed = False


def print_header(now: datetime) -> None:
    """래퍼는 이 머리줄로 "스크립트가 실행됨"을 판정한다. import 뒤에 찍어, import 중 강제 종료(머리줄 없음)는
    래퍼가 재시도하게 둔다. import 예외는 main()이 잡아 머리줄을 대신 찍는다(알림 1건, 재시도 없음)."""
    global _header_printed
    print(f"[{now:%Y-%m-%d %H:%M} KST] 스냅샷 신선도 확인", flush=True)
    _header_printed = True


def notify_trouble(message: str, today: str) -> None:
    """정상 비교 밖의 오류 알림(키 없음·기준 파일·상태 파일 쓰기·예외) — 하루 1회(상태 trouble_alerted_on).
    04:00·08:40·로그인 때 같은 오류가 반복돼도 알림은 하루 1건이다."""
    state, corrupt = load_state(STATE_PATH)
    if state.get("trouble_alerted_on") == today:
        print("알림: 오늘 이미 보냄")
        return
    ok = notify(TITLE, message)
    print(f"알림: {'보냄' if ok else '실패'}")
    if ok and not corrupt:  # 읽지 못한 상태 파일을 빈 상태로 덮어쓰지 않는다(일시적 읽기 오류로 이력을 잃지 않게)
        state["trouble_alerted_on"] = today
        try:
            write_atomic(STATE_PATH, json.dumps(state, indent=1))
        except Exception as e:  # noqa: BLE001 — 기록 실패가 알림 경로를 깨지 않게(다음 실행이 다시 알릴 수 있음)
            print(f"상태 파일 쓰기 실패: {type(e).__name__}")


def run(args) -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(ROOT / "src"))
    from korean_rnd_regs_mcp.live_api import ERROR_AUTH_FAILED, LawApiClient
    from korean_rnd_regs_mcp.manifest import load_manifest

    now = now_kst()
    today = now.date().isoformat()
    print_header(now)
    print(f"코드: {code_info()}")
    client = LawApiClient()
    if not client.api_key:
        print("LAW_API_KEY 없음")
        if args.notify:
            notify_trouble("API Key가 없어 확인하지 못했습니다. 로그를 확인하십시오.", today)
        return 3
    key = client.api_key
    config_errors: list[str] = []
    state, corrupt = load_state(STATE_PATH)
    if corrupt:
        config_errors.append("상태 파일 손상(빈 상태로 다시 씀)")
    try:
        raw = Path(args.snapshot).read_bytes()
        gen, baseline = parse_snapshot(raw.decode("utf-8"))
    except (OSError, ValueError) as e:  # UnicodeDecodeError는 ValueError
        print(f"기준 스냅샷을 읽지 못함: {type(e).__name__}")
        if args.notify:
            notify_trouble("기준 스냅샷을 읽지 못했습니다. 로그를 확인하십시오.", today)
        return 2
    print(f"기준: {args.snapshot} · 생성 {gen} · 법령 {len(baseline)}")
    targets = [r for r in load_manifest() if r.api_target.value == "law"]
    if {r.id for r in targets} != set(baseline):
        config_errors.append("manifest 법령 집합과 기준 스냅샷이 다름")
        targets = [r for r in targets if r.id in baseline]

    current, why = fetch_current(client, targets, time.monotonic() + DEADLINE_S)
    changed, failed = compare(baseline, current)
    if ERROR_AUTH_FAILED in why.values():
        config_errors.append("API 인증 실패(auth_failed)")
    for rid, omst, oefyd, nmst, nefyd in changed:
        print(mask(f"판본 변경: {rid} {omst}·{oefyd} → {nmst}·{nefyd}", key))
    for rid in failed:
        print(mask(f"조회 실패: {rid} ({why.get(rid, 'manifest 없음')})", key))
    for msg in config_errors:
        print(f"설정 오류: {msg}")
    print(f"결과: 변경 {len(changed)} · 실패 {len(failed)} · 설정 오류 {len(config_errors)}")

    notify_change, notify_fail, new_state = decide(changed, failed, state, now.date())
    trouble = bool(notify_fail or config_errors)
    alert_ok = True  # 알림이 필요 없었거나 보냈음
    trouble_sent = False  # 이번 실행이 조회 실패·설정 오류를 담은 알림을 실제로 보냈는가
    if args.notify and (notify_change or trouble):
        if not notify_change and state.get("trouble_alerted_on") == today:
            print("알림: 오늘 이미 보냄")  # 조회 실패·설정 오류 알림은 하루 1회
        else:
            parts = []
            if changed:
                parts.append(f"판본 변경 {len(changed)}건")
            if failed:
                parts.append(f"조회 실패 {len(failed)}건")
            if config_errors:
                parts.append(f"설정 오류 {len(config_errors)}건")
            alert_ok = notify(TITLE, " · ".join(parts) + ". 로그를 확인하십시오.")
            print(f"알림: {'보냄' if alert_ok else '실패'}")
            trouble_sent = alert_ok and bool(failed or config_errors)
            if alert_ok and changed:
                new_state["alert_sig"] = json.dumps(changed, ensure_ascii=False)
                new_state["alerted_on"] = today
            if alert_ok and trouble:
                new_state["trouble_alerted_on"] = today
    new_state["last_run"] = now.isoformat(timespec="seconds")
    if not failed and not config_errors:
        new_state["last_success"] = new_state["last_run"]
    try:
        write_atomic(STATE_PATH, json.dumps(new_state, indent=1))
    except Exception as e:  # noqa: BLE001 — OSError뿐 아니라 인코딩 오류도 여기서 처리(main까지 가지 않게)
        print(f"상태 파일 쓰기 실패: {type(e).__name__}")
        if args.notify and not trouble_sent:  # 같은 실행에서 오류 알림을 이미 보냈으면 두 번째 알림을 내지 않는다
            notify_trouble("상태 파일을 쓰지 못했습니다. 로그를 확인하십시오.", today)
        return 2
    if failed or config_errors:
        return 2
    if args.notify and alert_ok:
        mark_done(now, args.snapshot, raw)
    return 1 if changed else 0


def mark_done(now: datetime, snapshot: str, raw: bytes) -> None:
    """예약 실행(--notify)이 끝까지 성공했을 때 래퍼용 "오늘 확인 완료" 표시를 쓴다. 쓰지 않는 경우:
    04:00 전(그날 04:00 실행을 막지 않게), 실행 중 기준 파일이 바뀜(--record-deployed가 겹침 — 새 기준을 다시 확인)."""
    if now.hour < 4:
        print("완료 표시: 04:00 전 실행이라 쓰지 않음")
        return
    try:
        if Path(snapshot).read_bytes() != raw:
            print("완료 표시: 실행 중 기준 파일이 바뀌어 쓰지 않음")
            return
        write_atomic(DONE_MARK_PATH, now.date().isoformat() + "\n")
        print("완료 표시: 기록")
    except OSError as e:
        print(f"완료 표시 쓰기 실패: {type(e).__name__}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="조문별 변경 이력 스냅샷의 판본 신선도 확인")
    ap.add_argument("--notify", action="store_true", help="변경·실패·설정 오류가 있으면 macOS 알림(예약 실행용)")
    ap.add_argument("--snapshot", default=str(BASELINE_PATH), help="비교 기준 스냅샷 경로(기본: 운영본 사본)")
    ap.add_argument("--record-deployed", metavar="GIT_REF", help="배포·롤백한 커밋의 스냅샷을 기준으로 저장하고 끝냄")
    args = ap.parse_args(argv)
    global _header_printed
    _header_printed = False
    try:
        if args.record_deployed:
            return record_deployed(args.record_deployed)
        return run(args)
    except Exception as e:  # noqa: BLE001 — 예외 메시지·traceback은 키를 담을 수 있어 종류만 남긴다
        now = now_kst()
        if not _header_printed and not args.record_deployed:
            print_header(now)  # 예외로 끝나도 "실행됨"으로 판정되게(래퍼 재시도·알림 중복 방지)
        print(f"오류: {type(e).__name__}")
        if args.notify:
            msg = "확인 중 오류가 났습니다. 로그를 확인하십시오."
            try:
                notify_trouble(msg, now.date().isoformat())
            except Exception:  # noqa: BLE001 — 마지막 방어: 알림 경로 오류로 조용히 끝나지 않게 직접 보낸다
                print(f"알림: {'보냄' if notify(TITLE, msg) else '실패'}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
