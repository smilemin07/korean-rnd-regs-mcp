"""스냅샷 신선도 매일 확인 도구 — 비교·알림 규칙·키 마스킹·종료 코드(네트워크 0, 알림·git은 mock)."""
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_article_history_freshness as chk  # noqa: E402

_SNAP = {"schema": 1, "generated_at": "2026-10-28 23:24 KST",
         "laws": {"a_act": {"mst": "100", "efyd": "2026-01-01", "articles": {}},
                  "b_act": {"mst": "200", "efyd": "2026-02-02", "articles": {}}}}


def test_parse_snapshot_and_date_normalization():
    gen, laws = chk.parse_snapshot(json.dumps(_SNAP))
    assert gen == "2026-10-28 23:24 KST" and laws == {"a_act": ("100", "20260101"), "b_act": ("200", "20260202")}
    with pytest.raises(ValueError):
        chk.parse_snapshot(json.dumps({"schema": 2, "laws": {}}))
    with pytest.raises(ValueError):
        chk.parse_snapshot(json.dumps({"schema": 1, "laws": {}}))


def test_compare_iso_and_8digit_dates_equal():
    base = {"a_act": ("100", "20260101"), "b_act": ("200", "20260202")}
    assert chk.compare(base, {"a_act": ("100", "2026-01-01"), "b_act": ("200", "20260202")}) == ([], [])
    changed, failed = chk.compare(base, {"a_act": ("101", "20261001"), "b_act": None})
    assert changed == [("a_act", "100", "20260101", "101", "20261001")] and failed == ["b_act"]
    assert chk.compare(base, {"a_act": ("100", "20260101")}) == ([], ["b_act"])  # 빠진 법령 = 실패


def test_decide_change_alert_rules():
    ch = [("a_act", "100", "20260101", "101", "20261001")]
    sig = json.dumps(ch, ensure_ascii=False)
    d = date(2026, 11, 2)
    assert chk.decide(ch, [], {}, d)[0] is True                                   # 첫 변경
    assert chk.decide(ch, [], {"alert_sig": sig, "alerted_on": "2026-11-01"}, d)[0] is False  # 같은 변경, 1일 뒤
    assert chk.decide(ch, [], {"alert_sig": sig, "alerted_on": "2026-10-26"}, d)[0] is True   # 7일 지남
    other = ch + [("b_act", "200", "20260202", "201", "20261101")]
    assert chk.decide(other, [], {"alert_sig": sig, "alerted_on": "2026-11-01"}, d)[0] is True  # 목록이 바뀜
    assert chk.decide(ch, [], {"alert_sig": sig, "alerted_on": "망가짐"}, d)[0] is True
    _, _, st = chk.decide([], [], {"alert_sig": sig, "alerted_on": "2026-11-01"}, d)
    assert st["alert_sig"] == "" and st["alerted_on"] is None                    # 해소되면 초기화


def test_decide_failure_needs_two_consecutive_runs_and_does_not_hide_change():
    ch = [("a_act", "100", "20260101", "101", "20261001")]
    nc, nf, st = chk.decide(ch, ["b_act"], {}, date(2026, 11, 2))
    assert nc is True and nf is False and st["fail_streak"] == 1                 # 첫 실패라도 변경은 알림
    nc, nf, st = chk.decide([], ["b_act"], st, date(2026, 11, 3))
    assert nf is True and st["fail_streak"] == 2
    assert chk.decide([], [], st, date(2026, 11, 4))[2]["fail_streak"] == 0      # 성공 실행이면 0


def test_mask_removes_key_and_oc_values():
    assert chk.mask("x SECRET9 y OC=abc&type=XML", "SECRET9") == "x *** y OC=***&type=XML"


def test_load_state_missing_and_corrupt(tmp_path):
    assert chk.load_state(tmp_path / "none.json") == ({}, False)
    p = tmp_path / "s.json"
    p.write_text("{망가짐", encoding="utf-8")
    assert chk.load_state(p) == ({}, True)


class _Res(SimpleNamespace):
    pass


class _Client:
    api_key = "SECRET-KEY-77"
    calls = 0

    def __init__(self, table=None, raise_for=()):
        self.table = table or {"A법": ("100", "2026-01-01"), "B법": ("200", "2026-02-02")}
        self.raise_for = set(raise_for)

    def resolve_latest_doc_id(self, title, target, doc_id, ministry):
        _Client.calls += 1
        if title in self.raise_for:
            raise RuntimeError(f"connection failed for https://x/DRF?OC={self.api_key}&target=law")
        doc, ef = self.table[title]
        return _Res(doc_id=doc, effective_date=ef, resolve_failed=False)


def _setup(tmp_path, monkeypatch, client, notified):
    import korean_rnd_regs_mcp.live_api as la
    import korean_rnd_regs_mcp.manifest as mf
    snap = tmp_path / "base.json"
    snap.write_text(json.dumps(_SNAP), encoding="utf-8")
    monkeypatch.setattr(chk, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(chk, "RETRY_WAIT_S", 0.0)
    monkeypatch.setattr(la, "LawApiClient", lambda: client)
    rs = [SimpleNamespace(id="a_act", title="A법", api_doc_id="1", ministry="x", api_target=SimpleNamespace(value="law")),
          SimpleNamespace(id="b_act", title="B법", api_doc_id="2", ministry="x", api_target=SimpleNamespace(value="law"))]
    monkeypatch.setattr(mf, "load_manifest", lambda *a, **k: rs)
    monkeypatch.setattr(chk, "notify", lambda t, m: notified.append(m) or True)
    return snap


def test_main_no_change_exit_0(tmp_path, monkeypatch, capsys):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 0 and notified == []
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st["last_success"] == st["last_run"]


def test_main_change_exit_1_and_alert_once(tmp_path, monkeypatch):
    notified = []
    c = _Client({"A법": ("101", "20261001"), "B법": ("200", "20260202")})
    snap = _setup(tmp_path, monkeypatch, c, notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 1
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 1
    assert notified == ["판본 변경 1건. 로그를 확인하십시오."]  # 같은 변경은 두 번째에 알리지 않음


def test_main_failed_notify_is_retried_next_run(tmp_path, monkeypatch):
    notified = []
    c = _Client({"A법": ("101", "20261001"), "B법": ("200", "20260202")})
    snap = _setup(tmp_path, monkeypatch, c, notified)
    monkeypatch.setattr(chk, "notify", lambda t, m: False)
    chk.main(["--notify", "--snapshot", str(snap)])
    monkeypatch.setattr(chk, "notify", lambda t, m: notified.append(m) or True)
    chk.main(["--notify", "--snapshot", str(snap)])
    assert notified == ["판본 변경 1건. 로그를 확인하십시오."]  # 알림 실패는 기록하지 않아 다음 실행에 다시 알림


def test_main_failure_exit_2_with_retry_and_no_key_in_output(tmp_path, monkeypatch, capsys):
    notified = []
    _Client.calls = 0
    snap = _setup(tmp_path, monkeypatch, _Client(raise_for={"B법"}), notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert _Client.calls == 3  # A 1회 + B 2회(재시도)
    assert notified == []      # 실패 1회째는 알리지 않음
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["조회 실패 1건. 로그를 확인하십시오."]
    out = capsys.readouterr()
    assert "SECRET-KEY-77" not in out.out + out.err and "OC=" not in out.out + out.err


def test_main_top_level_exception_prints_type_only(tmp_path, monkeypatch, capsys):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)

    def boom(*a, **k):
        raise RuntimeError("https://x/DRF?OC=SECRET-KEY-77")
    monkeypatch.setattr(chk, "compare", boom)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    out = capsys.readouterr()
    assert "오류: RuntimeError" in out.out and "SECRET-KEY-77" not in out.out + out.err
    assert notified == ["확인 중 오류가 났습니다. 로그를 확인하십시오."]


def test_main_manifest_mismatch_and_corrupt_state_alert_immediately(tmp_path, monkeypatch):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)
    (tmp_path / "state.json").write_text("{망가짐", encoding="utf-8")
    data = json.loads(snap.read_text(encoding="utf-8"))
    data["laws"]["c_act"] = {"mst": "300", "efyd": "2026-03-03"}
    snap.write_text(json.dumps(data), encoding="utf-8")
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["조회 실패 1건 · 설정 오류 2건. 로그를 확인하십시오."]


def test_main_missing_key_exit_3(tmp_path, monkeypatch):
    notified = []
    c = _Client()
    c.api_key = ""
    snap = _setup(tmp_path, monkeypatch, c, notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 3 and len(notified) == 1


def test_main_missing_baseline_exit_2(tmp_path, monkeypatch):
    notified = []
    _setup(tmp_path, monkeypatch, _Client(), notified)
    assert chk.main(["--notify", "--snapshot", str(tmp_path / "nope.json")]) == 2 and len(notified) == 1


def test_record_deployed_rejects_option_like_ref():
    assert chk.record_deployed("--output=/tmp/x") == 2


def test_record_deployed_writes_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(chk, "BASELINE_PATH", tmp_path / "base.json")
    assert chk.record_deployed("HEAD") == 0
    gen, laws = chk.parse_snapshot((tmp_path / "base.json").read_text(encoding="utf-8"))
    assert len(laws) >= 30
