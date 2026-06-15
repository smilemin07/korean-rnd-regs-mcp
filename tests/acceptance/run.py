#!/usr/bin/env python
"""배포 전 LIVE acceptance 러너 (고정 엔진 — 버전 무관, 거의 안 바뀜).

목적: 배포 직전, 신코드를 로컬 shared venv에서 실행해 LIVE 상위 API(law.go.kr) 대상으로
'이번 버전 개선점'이 살아있는지 결정론적으로 검증한다. MCP 도구(search_provision 등)는
평범한 awaitable 코루틴이라 asyncio.run(tool(**args))로 직접 구동한다(별도 MCP transport·
라이브 커넥터 불필요). 라이브 커넥터는 배포 전 구버전을 서빙하므로 여기서 쓰지 않는다.

★false-block 안전 (Andy 최우선 = 끊김없는 서비스 = 정상 배포를 막지 않음):
  - 자동 hard-BLOCK 신호는 단 2종: returned 명백 감소(recall 회귀) · 대형규정 미도달(reaches 실패).
    그나마 2회 시도에서 *재현*될 때만 BLOCK(1회 통과하면 flaky→WARN).
  - skip(timeout)·latency 초과는 정상 cold tail(비결정 TLS 변동)에서도 발생 → 전부 WARN(BLOCK 금지).
  - 상위 API 다운/장애는 전건 parse_failed/auth_failed 또는 연결오류로 표면화 → infra-WARN(회귀 아님).
  - LAW_API_KEY 부재 → SKIP(키 없는 환경에서 false-BLOCK 금지).
  - 최종 BLOCK 판정은 사람(메인 스레드). 이 러너는 증거+분류만 제공(harness: 에이전트=증거·사람=판정).

보안: 키 값·앞자리·hash·URL/query(OC=) 어떤 형태도 출력 금지. 예외는 type 이름만. .env 직접 read 금지(load_dotenv만).

종료 코드: 0=PASS · 2=WARN(비차단) · 3=BLOCK(재현 회귀) · 4=SKIP(키 부재) · 5=spec/사용 오류.

사용: /Users/andykim/my_project/venv/bin/python tests/acceptance/run.py <version>
  예) ... run.py 0.2.7   (tests/acceptance/v0_2_7.py 의 CHECKS 실행)
"""
import asyncio
import importlib
import os
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

# 종료 코드
EXIT_PASS, EXIT_WARN, EXIT_BLOCK, EXIT_SKIP, EXIT_USAGE = 0, 2, 3, 4, 5

# ★assert 종류 동결 (4~6종). 새 종류 추가는 run.py 해석기 변경을 동반하므로 신중.
#   block-eligible(회귀 신호) = {fetched_ok, returned_not_below} 뿐. 나머지는 전부 WARN.
ASSERT_KINDS = {"fetched_ok", "returned_not_below", "absent_error_code", "latency_under", "field_equals"}
BLOCK_ELIGIBLE = {"fetched_ok", "returned_not_below"}

# infra(상위 API 장애) 시그니처 — 회귀가 아니라 WARN으로 분류할 오류 코드
INFRA_ERROR_CODES = {"parse_failed", "auth_failed"}
_ATTEMPTS = 2  # flaky/infra 구분용 재시도


def _norm_module(version: str) -> str:
    """'0.2.7' -> 'v0_2_7'. 이미 'v0_2_7' 형태면 그대로."""
    v = version.strip()
    if v.startswith("v"):
        return v.replace(".", "_")
    return "v" + v.replace(".", "_")


def _errors_by_code(resp):
    return Counter((e or {}).get("code") for e in (resp.get("errors") or []))


def _reg_ids_errored(resp):
    return {(e or {}).get("rule_set_id") for e in (resp.get("errors") or [])}


def _is_infra(resp, raised_type):
    """이 응답이 상위 API 장애(회귀 아님)로 보이는가."""
    if raised_type is not None:
        # 도구가 통째로 예외 → 연결/파싱 단계 광역 실패 = infra
        return True
    errs = _errors_by_code(resp)
    infra_n = sum(errs[c] for c in INFRA_ERROR_CODES)
    results_n = len(resp.get("results") or [])
    total = results_n + sum(errs.values())
    if total == 0:
        return False
    # 전건/과반이 parse_failed·auth_failed → 상위 API 다운 신호
    return infra_n >= max(2, total * 0.5)


async def _call_tool(tool_name, args):
    import korean_rnd_regs_mcp.main as m
    tool = getattr(m, tool_name, None)
    if tool is None or not asyncio.iscoroutinefunction(tool):
        raise ValueError(f"unknown_or_non_async_tool:{tool_name}")
    return await tool(**(args or {}))


def _eval_assert(a, resp, elapsed):
    """단일 assert 평가 → (ok: bool, detail: str). 보안: detail에 키/URL 미포함."""
    kind = a.get("kind")
    if kind == "fetched_ok":
        rid = a.get("rule_set_id")
        errored = _reg_ids_errored(resp)
        ok = rid not in errored
        return ok, f"reaches({rid}): {'도달' if ok else 'errors에 존재=미도달'}"
    if kind == "returned_not_below":
        n = len(resp.get("results") or [])
        ok = n >= a.get("value", 0)
        return ok, f"returned={n} (>= {a.get('value')})"
    if kind == "absent_error_code":
        errs = _errors_by_code(resp)
        cnt = errs.get(a.get("value"), 0)
        ok = cnt == 0
        return ok, f"error_code '{a.get('value')}' 건수={cnt} (0 기대)"
    if kind == "latency_under":
        ok = elapsed < a.get("value", 1e9)
        return ok, f"latency={elapsed:.2f}s (< {a.get('value')}s)"
    if kind == "field_equals":
        # path 예: 'results.0.content_format' / 'returned'
        val = resp
        try:
            for part in str(a.get("path", "")).split("."):
                val = val[int(part)] if part.isdigit() else val[part]
        except (KeyError, IndexError, TypeError):
            val = "<missing>"
        ok = val == a.get("value")
        return ok, f"{a.get('path')}={val!r} (== {a.get('value')!r})"
    return False, f"unknown_assert_kind:{kind}"


async def _run_check_once(check):
    """1회 시도. -> dict(resp, elapsed, infra, raised_type)."""
    raised_type = None
    resp = {}
    t0 = time.perf_counter()
    try:
        resp = await _call_tool(check["tool"], check.get("args"))
        if not isinstance(resp, dict):
            resp = {"results": [], "errors": []}
    except BaseException as e:  # 키/URL 누출 차단 — type 이름만
        raised_type = type(e).__name__
    elapsed = time.perf_counter() - t0
    infra = _is_infra(resp, raised_type)
    return {"resp": resp, "elapsed": elapsed, "infra": infra, "raised_type": raised_type}


def _classify_check(check, attempts):
    """2회 시도 결과로 check를 PASS/WARN/BLOCK 분류 + 증거 문자열.

    규칙(false-block 안전):
      - BLOCK: block-eligible assert가 *모든 시도에서* 실패 + *모든 시도가 infra 아님*.
      - WARN : (a) warn 종류 실패, (b) block-eligible이 일부 시도만 실패(flaky), (c) infra 의심.
      - PASS : 전 assert 통과.
    """
    any_infra = any(at["infra"] for at in attempts)
    all_infra = all(at["infra"] for at in attempts)
    lines = []
    block = False
    warn = False
    for a in check.get("asserts", []):
        kind = a.get("kind")
        results = []
        for at in attempts:
            ok, detail = _eval_assert(a, at["resp"], at["elapsed"])
            results.append((ok, detail, at["infra"], at["raised_type"]))
        passed_any = any(r[0] for r in results)
        passed_all = all(r[0] for r in results)
        last_detail = results[-1][1]
        if passed_all:
            lines.append(f"    PASS  {last_detail}")
            continue
        if kind in BLOCK_ELIGIBLE:
            # 모든 시도 실패 + 모든 시도 비-infra → 재현 회귀 = BLOCK
            failed_all = not passed_any
            non_infra_all = all(not r[2] for r in results)
            if failed_all and non_infra_all:
                block = True
                lines.append(f"    BLOCK {last_detail}  [재현 회귀 — 2회 모두 실패·infra 아님]")
            elif failed_all and not non_infra_all:
                warn = True
                lines.append(f"    WARN  {last_detail}  [infra 의심 — parse_failed/연결오류 동반]")
            else:
                warn = True
                lines.append(f"    WARN  {last_detail}  [flaky — 1회 통과, 2회 실패]")
        else:
            warn = True
            sev = "infra" if all_infra else "비결정(cold tail 등)"
            lines.append(f"    WARN  {last_detail}  [{sev} — 차단 안 함]")
    # check 레벨 infra 메모 — 오류가 가장 많은 시도(보통 cold) 기준
    if any_infra:
        worst = max(attempts, key=lambda at: sum(_errors_by_code(at["resp"]).values()))
        codes = _errors_by_code(worst["resp"])
        lines.append(f"    note  infra 의심(전건/과반 parse_failed·auth_failed 또는 연결오류): {dict(codes)}")
    verdict = "BLOCK" if block else ("WARN" if warn else "PASS")
    return verdict, lines


def main():
    if len(sys.argv) < 2:
        print("usage: run.py <version>  (예: run.py 0.2.7)", file=sys.stderr)
        return EXIT_USAGE

    # 키 로드 (값 미출력) — .env 직접 read 금지, load_dotenv만
    repo = Path(__file__).resolve().parents[2]
    try:
        from dotenv import load_dotenv
        load_dotenv(repo / ".env")
    except Exception:
        pass
    if not bool(os.environ.get("LAW_API_KEY")):
        print("SKIP — LAW_API_KEY 미설정(키 없는 환경). acceptance는 키 있는 환경에서만 의미.")
        return EXIT_SKIP

    mod_name = _norm_module(sys.argv[1])
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        spec = importlib.import_module(mod_name)
    except ModuleNotFoundError:
        print(f"spec 없음: tests/acceptance/{mod_name}.py — 버전 spec을 먼저 작성하세요.", file=sys.stderr)
        return EXIT_USAGE
    checks = getattr(spec, "CHECKS", None)
    if not checks:
        print(f"{mod_name}.CHECKS 비어있음.", file=sys.stderr)
        return EXIT_USAGE

    # spec 무결성(동결 종류) — 런타임 가드(별도 pytest 가드도 존재)
    for c in checks:
        for a in c.get("asserts", []):
            if a.get("kind") not in ASSERT_KINDS:
                print(f"미허용 assert kind: {a.get('kind')} (허용: {sorted(ASSERT_KINDS)})", file=sys.stderr)
                return EXIT_USAGE

    print(f"== LIVE acceptance: {mod_name} ({len(checks)} checks, 각 {_ATTEMPTS}회 시도) ==")
    overall_block = False
    overall_warn = False
    for c in checks:
        attempts = []
        for _ in range(_ATTEMPTS):
            attempts.append(asyncio.run(_run_check_once(c)))
        verdict, lines = _classify_check(c, attempts)
        if verdict == "BLOCK":
            overall_block = True
        elif verdict == "WARN":
            overall_warn = True
        _cold = max(at["elapsed"] for at in attempts)  # 1회째(cold)가 의미 있는 값
        print(f"  [{verdict}] {c.get('name')}  (cold latency {_cold:.2f}s)")
        for ln in lines:
            print(ln)

    # Level B(호스트 LLM 행동) advisory — 자동 판정 불가, 사람 수동 eval용 프롬프트만 출력
    lb = getattr(spec, "LEVEL_B_PROMPTS", None)
    if lb:
        print("\n-- Level B (호스트 LLM 행동 — 배포 후 라이브 커넥터에서 사람이 수동 확인, 게이트 판정 아님) --")
        for i, p in enumerate(lb, 1):
            print(f"  {i}. 프롬프트: {p.get('probe_prompt')}")
            print(f"     기대 행동: {p.get('expect_behavior')}")

    print()
    if overall_block:
        print("결과: BLOCK 후보 — 재현 회귀(returned 감소/대형규정 미도달, infra 아님) 발견. 메인 스레드가 증거 확인 후 최종 판정.")
        return EXIT_BLOCK
    if overall_warn:
        print("결과: WARN — 비차단(infra 의심·cold tail skip·latency 등). 정상 배포 가능, 재실행 권고. 메인 스레드 판단.")
        return EXIT_WARN
    print("결과: PASS — Level A 결정론 검증 전건 통과.")
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
