"""manifest api_doc_id의 lawService 상세 시행일자 감사 — 미래(미시행 판본)면 FAIL.

(v0.51.0 §5.42 동반 도구 · 2026-08-20 3-AI /disc 3/3 합의) 기존 /regs-audit(현행성 전수 감사)는
lawSearch 검색 행 기준이라, 합본 MST가 현행 행으로 등재되지만 lawService 본문은 미래 분리시행분인
C12 창(2026-06-12~08-19 혁신법 283849로 69일 실측 — 그 기간 검색 행 기준 감사 3회 전건 통과)을
구조적으로 놓친다. 본 스크립트는 resolve를 거치지 않고 manifest의 api_doc_id를 lawService에
직접 전달해, fallback(및 C12 창의 정상 resolve)이 실제로 서빙하게 될 상세 본문의 시행일자를
오늘과 비교한다.

판정(3분류 — UNKNOWN을 PASS로 처리하지 않는다):
  PASS    : 상세 시행일자가 유효(8자리)하고 오늘 이하 = 현행 본문 서빙.
  FAIL    : 상세 시행일자가 유효하고 오늘보다 미래 = 미시행 본문 서빙 위험 → 배포 보류·사람 판정
            NO-GO(manifest를 현행 MST로 갱신 후 재실행).
  UNKNOWN : 조회 실패·시행일자 누락·형식 이상 = 확인 불가 → 재실행(반복되면 사람 판정).

종료 코드: 0 = 전건 PASS / 3 = FAIL 존재 / 2 = FAIL 없음·UNKNOWN 존재.

사용(read-only — manifest·코드를 수정하지 않는다):
  /Users/andykim/my_project/venv/bin/python scripts/audit_manifest_effective_dates.py            # 전체
  /Users/andykim/my_project/venv/bin/python scripts/audit_manifest_effective_dates.py innovation_act ...  # 지정만

키(LAW_API_KEY/OC)는 어떤 형태로도 출력하지 않는다.
"""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


def classify(raw_date: str | None, today: str, fetch_error: bool = False) -> str:
    """단일 규정 판정 — 순수 함수(단위 테스트 대상: tests/test_audit_script.py).

    _is_future_date와 동일 규약: 하이픈·공백 정규화 후 8자리 숫자만 판정, 당일 시행은 현행(PASS).
    형식 이상(8자리 아님·달력 무효)은 미래로 단정하지 않되 PASS도 아님(UNKNOWN — 재확인 필요).
    """
    if fetch_error:
        return "UNKNOWN"
    d = (raw_date or "").strip().replace("-", "")
    if len(d) != 8 or not d.isdigit():
        return "UNKNOWN"
    try:
        time.strptime(d, "%Y%m%d")  # 달력 유효성(예: 20261340 월 13 배제)
    except ValueError:
        return "UNKNOWN"
    return "FAIL" if d > today else "PASS"


def main(argv: list[str]) -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not bool(os.environ.get("LAW_API_KEY")):
        print("LAW_API_KEY 미설정 — .env를 확인하십시오 (값은 출력하지 않습니다).")
        return 2
    from korean_rnd_regs_mcp.live_api import LawApiClient, LawApiError
    from korean_rnd_regs_mcp.manifest import Retrieval, load_manifest

    only = set(argv)
    items = [rs for rs in load_manifest() if rs.retrieval == Retrieval.LIVE_API]
    # fail-closed(diff 적대검토 Codex 조건 2): 미인식 ID·선택 결과 0건이 "전건 PASS"로
    # 헛통과하지 않게 네트워크 호출 전에 차단한다.
    unknown = only - {rs.id for rs in items}
    if unknown:
        print(f"지정 rule_set_id 미인식: {', '.join(sorted(unknown))} — 오타 확인 후 재실행 (fail-closed).")
        return 2
    targets = [rs for rs in items if not only or rs.id in only]
    if not targets:
        print("감사 대상 0건 — 지정 조건을 확인하십시오 (fail-closed).")
        return 2
    client = LawApiClient()
    today = client._today_kst()
    counts = {"PASS": 0, "FAIL": 0, "UNKNOWN": 0}
    rows = []
    for rs in targets:
        raw, err = None, False
        try:
            if rs.api_target.value == "law":
                detail = client.get_law_detail(rs.api_doc_id)
            else:
                detail = client.get_admin_rule_detail(rs.api_doc_id)
            raw = detail.get("시행일자")
        except LawApiError:
            err = True
        except Exception:
            err = True
        verdict = classify(raw, today, fetch_error=err)
        counts[verdict] += 1
        shown = (raw or "").strip() if not err else "(조회 실패)"
        rows.append(f"{verdict:7} | {rs.id:32} | {rs.api_target.value:6} | {rs.api_doc_id:14} | 상세 시행일자 {shown or '(없음)'}")
    print(f"기준일(오늘·KST): {today}")
    for r in rows:
        print(r)
    print(f"요약: PASS {counts['PASS']} / FAIL {counts['FAIL']} / UNKNOWN {counts['UNKNOWN']} (전체 {sum(counts.values())})")
    if counts["FAIL"]:
        print("→ FAIL 존재: 미시행 판본 서빙 위험 — 배포 보류·manifest 현행화 후 재실행 (사람 판정 NO-GO).")
        return 3
    if counts["UNKNOWN"]:
        print("→ UNKNOWN 존재: 확인 불가 — 재실행 필요 (PASS로 간주하지 말 것).")
        return 2
    print("→ 전건 PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
