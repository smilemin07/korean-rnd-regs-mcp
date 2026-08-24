"""scripts/audit_law_stage_diff.py 순수 함수 가드(네트워크 0) — P2 v0.54.0 감사 도구.

extract_body(서버 파서와 같은 필터·조립) · diff_bodies(full diff + 형식 차이 분리) · stage_flags(시행 단계 표 플래그
+ ★공포↔시행 순서 역전 예측)를 2026-08-23 전수 감사 실측값(혁신법·시행령·중소기업기술혁신법) 형태의 fixture로 잠근다.
"""
import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from korean_rnd_regs_mcp.live_api import _build_article_content

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_law_stage_diff.py"
# 감사 스크립트는 저장소(GitHub) 수록물이며 PyPI sdist에는 포함되지 않는다(pyproject sdist include에 scripts/ 없음).
# sdist를 받아 pytest를 돌리는 downstream에서 collection이 깨지지 않도록 부재 시 skip한다(구현 diff 적대검토 Codex).
pytest.importorskip("pydantic")  # 런타임 의존성 확인(스크립트가 manifest 모듈을 import)
if not _SCRIPT.exists():  # pragma: no cover - sdist 배포본 경로
    pytest.skip("scripts/audit_law_stage_diff.py 미포함 배포본 — 감사 도구 가드는 저장소에서만 실행", allow_module_level=True)

_SPEC = importlib.util.spec_from_file_location("audit_law_stage_diff", _SCRIPT)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


def _law_xml(articles, annexes=()):
    arts = "".join(
        f"<조문단위><조문여부>조문</조문여부><조문번호>{no}</조문번호><조문가지번호>{br}</조문가지번호>"
        f"<조문제목>{title}</조문제목><조문내용>{body}</조문내용></조문단위>"
        for no, br, title, body in articles
    )
    anns = "".join(
        f"<별표단위><별표번호>{no}</별표번호><별표가지번호></별표가지번호><별표구분>{kind}</별표구분>"
        f"<별표제목>{title}</별표제목><별표내용>{body}</별표내용></별표단위>"
        for no, kind, title, body in annexes
    )
    return ET.fromstring(
        "<법령><기본정보><법령명_한글>테스트법</법령명_한글><시행일자>20260820</시행일자></기본정보>"
        f"<조문><조문단위><조문여부>전문</조문여부><조문번호>1</조문번호><조문내용>제1장 총칙</조문내용></조문단위>{arts}</조문>"
        f"<별표>{anns}</별표></법령>"
    )


def test_extract_body_filters_wrapper_and_keys_articles_with_branch():
    root = _law_xml([("1", "", "목적", "이  법은"), ("7", "2", "가지", "본문")], [("3", "별표", "제목", "[내용]")])
    out = mod.extract_body(root, _build_article_content)
    assert set(out["articles"]) == {"제1조", "제7조의2"}          # 전문(wrapper) 제외·가지조문 키
    assert out["articles"]["제1조"]["content"] == "이 법은"        # 공백 정규화
    assert set(out["annexes"]) == {"별표 3"} and out["basic"]["법령명_한글"] == "테스트법"


def test_diff_bodies_match_format_only_and_substantive():
    law = mod.extract_body(_law_xml([("2", "", "정의", "가 나"), ("35", "2", "신설", "미시행")], [("3", "별표", "t", "[■ 내용")]), _build_article_content)
    same = mod.extract_body(_law_xml([("2", "", "정의", "가 나"), ("35", "2", "신설", "미시행")], [("3", "별표", "t", "[■ 내용")]), _build_article_content)
    assert mod.diff_bodies(law, same)["is_match"]
    fmt = mod.extract_body(_law_xml([("2", "", "정의", "가  나"), ("35", "2", "신설", "미시행")], [("3", "별표", "t", "■ 내용")]), _build_article_content)
    d = mod.diff_bodies(law, fmt)
    assert not d["is_match"] and d["is_format_only"]              # 공백·괄호 1자 = 형식만
    assert all(c["ws_only"] for c in d["annexes"]["changed"])
    ef = mod.extract_body(_law_xml([("2", "", "정의", "가 나 6. 공공연구기관"), ("27", "4", "신설", "x")]), _build_article_content)
    d = mod.diff_bodies(law, ef)
    assert d["articles"]["only_in_law"] == ["제35조의2"] and d["articles"]["only_in_eflaw"] == ["제27조의4"]
    assert [c["key"] for c in d["articles"]["changed"]] == ["제2조"] and not d["articles"]["changed"][0]["ws_only"]
    assert d["annexes"]["only_in_law"] == ["별표 3"] and not d["is_format_only"]


def _row(mst, ef, code, pub):
    return {"법령일련번호": mst, "시행일자": ef, "현행연혁코드": code, "공포일자": pub}


def test_stage_flags_predictors_match_2026_08_23_census():
    today = "20260823"
    # 혁신법: 현행 283413(공포 02-19) · 283849(공포 03-10) 06-11 연혁 + 09-11 예정 → 누락 예측만(선노출 아님)
    st = mod.stage_flags([_row("283849", "20260911", "시행예정", "20260310"), _row("283413", "20260820", "현행", "20260219"),
                          _row("283849", "20260611", "연혁", "20260310")], "283413", "283413", today)
    assert st["flags"] == ["PENDING", "MISSING_PREDICTED"] and st["efyd"] == "20260820"
    assert st["missing_predicted"] == [("283849", "20260611", "20260310")] and st["premature_predicted"] == []
    # 시행령: 현행 288773(공포 08-18) · 288335(공포 07-28) 09-11·2027 예정 → 선노출 예측
    st = mod.stage_flags([_row("288335", "20270101", "시행예정", "20260728"), _row("288335", "20260911", "시행예정", "20260728"),
                          _row("288773", "20260820", "현행", "20260818"), _row("288335", "20260728", "연혁", "20260728")],
                         "288773", "288773", today)
    assert "PREMATURE_PREDICTED" in st["flags"] and "MISSING_PREDICTED" not in st["flags"]
    # 중소기업기술혁신법: 현행 281987(공포 12-30·시행 07-01) · 286263(공포 05-26·시행 05-26) 연혁 → 누락 예측
    st = mod.stage_flags([_row("281987", "20260701", "현행", "20251230"), _row("286263", "20260526", "연혁", "20260526")],
                         "281987", "281987", today)
    assert st["flags"] == ["MISSING_PREDICTED"]
    # 다단계 완료(국방 258057 04-10/07-10) = DONE · manifest가 시행예정 행에만 = FAIL 플래그
    st = mod.stage_flags([_row("283941", "20260911", "시행예정", "20260310"), _row("258057", "20240710", "현행", "20240109"),
                          _row("258057", "20240410", "연혁", "20240109")], "258057", "283941", today)
    assert st["flags"] == ["MULTI_STAGE_DONE", "PENDING", "MANIFEST_FUTURE_ONLY"] and st["served_stages"] == ["20240410", "20240710"]
    # 다단계 열림: 서빙 MST 자체에 미도래 단계(09-11 가정 시 288335 2027 단계)
    st = mod.stage_flags([_row("288335", "20270101", "시행예정", "20260728"), _row("288335", "20260911", "현행", "20260728")],
                         "288335", "288335", "20260911")
    # 서빙 MST 자체의 미도래 단계 = 선노출 예측에 포함(redteam 반영)
    assert st["flags"] == ["MULTI_STAGE_OPEN", "PENDING", "PREMATURE_PREDICTED"] and st["efyd"] == "20260911"
    assert st["premature_predicted"] == [("288335", "20270101", "20260728")]
    # 같은 날 공포된 다른 공포본 → 선후 판정 불가 플래그
    st = mod.stage_flags([_row("A", "20260701", "현행", "20260101"), dict(_row("B", "20260301", "연혁", "20260101"), 공포번호="2")],
                         "A", "A", today)
    assert "SAME_DAY_AMBIGUOUS" in st["flags"]


def test_extract_body_reports_key_collisions():
    root = _law_xml([("3", "", "a", "x"), ("3", "", "b", "y")])
    out = mod.extract_body(root, _build_article_content)
    assert out["key_collisions"] == {"articles": 1, "annexes": 0}


def test_promote_unknown_is_fail_closed():
    """오류·키 충돌·현행 행 모호는 MATCH로 남지 않고 UNKNOWN으로 승격된다(승격 전 판정 보존)."""
    clean = {"verdict": "MATCH", "errors": [], "current_count": 1}
    mod._promote_unknown(clean)
    assert clean["verdict"] == "MATCH" and "verdict_before_promotion" not in clean
    collided = {"verdict": "MATCH", "errors": ["key_collision"], "current_count": 1}
    mod._promote_unknown(collided)
    assert collided["verdict"] == "UNKNOWN" and collided["verdict_before_promotion"] == "MATCH"
    ambiguous = {"verdict": "DIFF", "errors": [], "current_count": 2}
    mod._promote_unknown(ambiguous)
    assert ambiguous["verdict"] == "UNKNOWN" and ambiguous["errors"] == ["current_rows_ambiguous:2"]


def test_extract_body_empty_shape_is_not_a_match():
    """★fail-open 부정 테스트: 기본정보만 있는 응답 두 개는 '차이 없음'이 아니라 수집 실패로 다뤄야 한다.

    diff_bodies 자체는 빈 dict 두 개를 MATCH로 계산하므로(순수 함수로서 정상), 그 상태가 판정까지
    올라오지 못하게 막는 것은 Collector.body()의 조문 0건 예외다 — 두 사실을 함께 잠근다.
    """
    empty = mod.extract_body(_law_xml([]), _build_article_content)
    assert empty["articles"] == {} and empty["basic"]["법령명_한글"] == "테스트법"
    assert mod.diff_bodies(empty, empty)["is_match"]          # 순수 함수는 MATCH를 낸다(= 상류에서 막아야 함)
    src = (Path(__file__).resolve().parents[1] / "scripts" / "audit_law_stage_diff.py").read_text(encoding="utf-8")
    assert 'raise RuntimeError("empty_articles")' in src      # 상류 차단이 실재
    assert 'efyd_provenance_mismatch' in src                  # 요청 기준일↔응답 시행일자 provenance 검사
