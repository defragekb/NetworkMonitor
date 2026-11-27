"""Recalculate the published evidence using Python's standard library."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).parent / "evidence"


def load(name):
    return json.loads((ROOT / name).read_text())


def difference(first, last, key):
    return last[key] - first[key]


def sums(rows, start, end):
    by_role = defaultdict(lambda: [0, 0])
    for ms, role, rx, tx in rows:
        if start <= ms <= end:
            by_role[role][0] += rx
            by_role[role][1] += tx
    return dict(by_role)


def filter_delta(events):
    if not events:
        return None
    candidates = []
    for opened in events:
        if opened["event"] != "open" or opened["owner"] != "webkit" or not -14_000 < opened["ms"] <= 0:
            continue
        reports = [line for line in events
                   if line["flow"] == opened["flow"] and line["event"] in ("statistics", "close")]
        before = [line for line in reports if line["ms"] < 0]
        during = [line for line in reports if 0 <= line["ms"] <= 12_000]
        if before and during:
            observed = before + during
            assert all(b["in"] >= a["in"] for a, b in zip(observed, observed[1:]))
            rx = difference(before[-1], during[-1], "in")
            if rx >= 1_000_000:
                candidates.append({
                    "flow": opened["flow"], "kind": opened["kind"],
                    "rx_tx": [rx, difference(before[-1], during[-1], "out")],
                    "late_close_delta": next((difference(during[-1], line, "in") for line in reports
                                              if line["event"] == "close" and line["ms"] > 12_000), None),
                })
    assert len(candidates) == 1, candidates
    return candidates[0]


def verify_safari():
    expected = {
        "relay-off-probe": ([2_272_141, 41_266], [0, 0], None, 0),
        "relay-on-probe": ([2_264_402, 49_707], [0, 0], [2_008_998, 2_322], 1),
        "direct-off-probe": ([2_231_642, 39_818], [2_008_830, 6_458], None, 0),
        "direct-on-probe": ([2_482_774, 85_407], [2_008_809, 5_366], [2_008_809, 2_322], 1),
    }
    replay_inputs = {}
    for label, run in load("safari-fixed-size.json").items():
        receipt = run["receipt"]
        before, after = run["samples"]["before"], run["samples"]["after"]
        interface = [difference(before, after, key) for key in ("received", "sent")]
        duration = (after["ms"] - before["ms"]) / 1000
        cpu_cs = difference(before, after, "filter_cpu_centiseconds")
        assert receipt["server_reports_direct_egress"] == [label.startswith("direct")] * 2
        assert receipt["bytes"] == 2_000_000
        modes = run["nettop"]
        burst = {mode: sums(capture["nonzero_process_deltas"], -180, receipt["duration_ms"] + 1250)
                 for mode, capture in modes.items()}
        webkit = burst["external"].get("webkit", [0, 0])
        assert burst["all"].get("webkit", [0, 0]) == webkit
        full = sums(modes["all"]["nonzero_process_deltas"], 0, after["ms"] + 350)
        peak = max((rx for rx, _ in full.values()), default=0)
        if label.startswith("relay"):
            assert peak < 117_000
        flow = filter_delta(run["filter_events"])
        filtered = flow["rx_tx"] if flow else None
        if label == "relay-on-probe":
            assert flow["late_close_delta"] == 0
        assert (interface, webkit, filtered, cpu_cs) == expected[label]
        if filtered:
            replay_inputs[label] = (interface[0], webkit[0], filtered[0])
        print(f"{label:18} interface={interface} nettop={webkit} filter={filtered} "
              f"all-nettop peak RX={peak:,} CPU={cpu_cs/100:.2f}s/{duration:.2f}s")
    return replay_inputs


def verify_vps():
    expected = ((4096, 4096), (4096, 64640), (32768, 32768),
                (32768, 64640), (8167, 76760), (4787, 4787))
    actual = []
    for row in load("vps-runs.json")["same_route"]:
        payload = row["receiver"]["payload_bytes"]
        reports = row["filter_reports"]
        assert len(reports) == 1 and reports[0][-1][0] == "close"
        recorded = reports[0][-1][2]
        actual.append((payload, recorded))
        print(f'{row["client"]:25} receiver={payload:6,} B filter={recorded:6,} B')
    assert tuple(actual) == expected
    debugger = load("outbound-debugger.json")
    frame = debugger["frame_fields"]
    available = frame["allocation"] - frame["headroom"] - frame["filled"]
    assert available == frame["available"] == 2020
    assert [row["forwarded_bytes"] for row in debugger["length_samples"].values()] == [4096, 8159]
    for key, row in debugger["length_samples"].items():
        assert row["reserved_frames"] * available == row["reserved_bytes"]
        print(f'{key}: {row["reserved_frames"]} × {available} B reserved, {row["forwarded_bytes"]:,} B forwarded')


def replay_usage_history(source, inputs):
    content = source.read_text()
    start = content.index("            -- #799. Keep the two sources separate.")
    end = content.index("            -- Connections (#115).", start)
    # Minimal input tables used by the actual PR's read-side logic.
    with sqlite3.connect(":memory:") as db:
        db.executescript("""
            CREATE TABLE sessions(id, started_at);
            INSERT INTO sessions VALUES(1, 1.0);
            CREATE TABLE traffic(hour, session_id, iface_in, local_in, app_in);
            CREATE TABLE app_traffic(hour, session_id, app_key, bytes_in, bytes_out,
                                     PRIMARY KEY(hour, session_id, app_key));
        """)
        db.executescript(content[start:end])
        relay, direct = (inputs[key] for key in ("relay-on-probe", "direct-on-probe"))
        combined = tuple(map(sum, zip(relay, direct)))
        credit_expected = (2_008_998, 0, 2_008_998)
        for hour, (interface, nettop, filtered) in enumerate((relay, direct, combined), start=1):
            db.execute("INSERT INTO traffic VALUES(?, 1, ?, 0, ?)", (hour, interface, nettop))
            db.execute("INSERT INTO app_traffic VALUES(?, 1, 'Safari', ?, 0)", (hour, nettop))
            db.execute("INSERT INTO filter_downloads VALUES(?, 1, 'Safari', 1.0, ?)", (hour, filtered))
            credited = db.execute("SELECT bytes_in FROM history_app_traffic WHERE hour=?", (hour,)).fetchone()[0]
            assert credited - nettop == credit_expected[hour-1]
            source_total = db.execute("SELECT iface_in FROM traffic WHERE hour=?", (hour,)).fetchone()[0]
            assert source_total == interface
            print(f"PR #815 SQL replay {hour}: Safari={credited:,} B, new credit={credited-nettop:,} B")


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--usage-history", type=Path, help="Sources/NetworkMonitorCore/UsageHistory.swift from PR #815")
args = parser.parse_args()
inputs = verify_safari()
verify_vps()
if args.usage_history:
    replay_usage_history(args.usage_history, inputs)
