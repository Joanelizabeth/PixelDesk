from datetime import datetime

from services.activity_monitor import ActivityAggregator, UsageRecorder, split_by_hour
from winintegration.probe import Sample

BASE = datetime(2026, 10, 27, 10, 0, 0).timestamp()


def s(exe="code.exe", idle=0.0, locked=False):
    return Sample(exe, None, 1, idle, locked)


def totals(deltas):
    out = {}
    for d in deltas:
        key = d.exe if d.kind == "active" else "IDLE"
        out[key] = out.get(key, 0) + d.seconds
    return out


def drive(agg, samples, start=BASE, step=1.0):
    deltas = []
    t = start
    for sm in samples:
        deltas += agg.tick(t, sm)
        t += step
    return deltas, t


def test_basic_attribution_no_double_count():
    agg = ActivityAggregator(idle_threshold_s=300)
    seq = [s("code.exe")] * 61 + [s("chrome.exe")] * 31
    deltas, _ = drive(agg, seq)
    deltas += agg.flush()
    tot = totals(deltas)
    assert round(tot["code.exe"]) == 61 and round(tot["chrome.exe"]) == 30
    assert round(sum(tot.values())) == 91  # 92 samples -> 91 intervals, each counted once
    assert agg.flush() == []


def test_idle_period_reclassified_not_counted_as_active():
    agg = ActivityAggregator(idle_threshold_s=300)
    seq = [s(idle=0)] * 60
    seq += [s(idle=float(i)) for i in range(1, 400)]  # no input for 399 s
    seq += [s(idle=0)] * 10
    deltas, _ = drive(agg, seq)
    deltas += agg.flush()
    tot = totals(deltas)
    assert 395 <= tot["IDLE"] <= 400
    assert 65 <= tot["code.exe"] <= 72
    assert abs(sum(tot.values()) - (len(seq) - 1)) < 1e-6


def test_short_pause_counts_as_active():
    agg = ActivityAggregator(idle_threshold_s=300)
    seq = [s(idle=0)] * 10 + [s(idle=float(i)) for i in range(1, 120)] + [s(idle=0)] * 10
    deltas, _ = drive(agg, seq)
    deltas += agg.flush()
    tot = totals(deltas)
    assert "IDLE" not in tot
    assert round(tot["code.exe"]) == len(seq) - 1


def test_locked_time_excluded():
    agg = ActivityAggregator(idle_threshold_s=300)
    seq = [s()] * 30 + [s(exe=None, locked=True, idle=500)] * 100 + [s()] * 30
    deltas, _ = drive(agg, seq)
    deltas += agg.flush()
    tot = totals(deltas)
    assert "IDLE" not in tot
    assert 55 <= tot["code.exe"] <= 60


def test_sleep_gap_and_clock_change_excluded():
    agg = ActivityAggregator(idle_threshold_s=300, max_gap_s=15)
    d1, t = drive(agg, [s()] * 20)
    d2 = agg.tick(t + 3600, s())          # resumed after sleeping an hour
    d3, t2 = drive(agg, [s()] * 10, start=t + 3601)
    d4 = agg.tick(t2 - 7200, s())          # clock moved backwards
    total = totals(d1 + d2 + d3 + d4 + agg.flush())
    assert total["code.exe"] < 40


def test_split_by_hour_and_midnight_boundary():
    start = datetime(2026, 10, 27, 23, 59, 30).timestamp()
    parts = list(split_by_hour(start, start + 60))
    assert [(p[0], p[1], round(p[2])) for p in parts] == [("2026-10-27", 23, 30), ("2026-10-28", 0, 30)]


def test_recorder_writes_aggregates(repo):
    agg = ActivityAggregator(idle_threshold_s=300)
    rec = UsageRecorder(repo)
    rec.note_app("code.exe", None)
    deltas, _ = drive(agg, [s()] * 121)
    rec.add(deltas + agg.flush())
    rec.flush()
    rec.flush()  # nothing left: no double write
    day = datetime.fromtimestamp(BASE).date()
    usage = repo.app_usage_for(day)
    assert len(usage) == 1 and usage[0].display_name == "VS Code" and usage[0].category == "productive"
    assert round(usage[0].seconds) == 120
    assert round(repo.daily_usage(day)["active_seconds"]) == 120
    assert round(sum(a for a, _ in repo.hourly_usage(day))) == 120


def test_browser_not_assumed_unproductive(repo):
    rec = UsageRecorder(repo)
    agg = ActivityAggregator()
    deltas, _ = drive(agg, [s("chrome.exe")] * 5)
    rec.add(deltas + agg.flush())
    rec.flush()
    assert repo.list_apps()[0]["category"] == "other"


def test_monitor_thread_with_mock_probe(repo, qapp):
    import time
    from services.activity_monitor import ActivityMonitor

    class MockProbe:
        available = True

        def sample(self):
            return Sample("code.exe", None, 1, 0.0, False)

    mon = ActivityMonitor(repo, MockProbe(), poll_interval=0.05, flush_interval=0.2)
    statuses = []
    mon.status.connect(lambda st: statuses.append(st), type=__import__("PySide6.QtCore").QtCore.Qt.DirectConnection)
    mon.start()
    time.sleep(0.6)
    mon.stop()
    assert statuses and statuses[-1].state.value == "active"
    used = repo.app_usage_for(datetime.now().date())
    assert used and 0.3 < used[0].seconds < 1.0


def test_unavailable_probe_records_nothing(repo, qapp):
    import time
    from services.activity_monitor import ActivityMonitor
    from winintegration.probe import UnavailableProbe

    mon = ActivityMonitor(repo, UnavailableProbe(), poll_interval=0.05, flush_interval=0.1)
    mon.start()
    time.sleep(0.3)
    mon.stop()
    assert repo.app_usage_for(datetime.now().date()) == []
