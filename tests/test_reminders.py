from datetime import datetime, time, timedelta

from services.reminder_service import (
    MovementConfig, MovementState, MovementTracker, QuietHours, WaterConfig, WaterReminder,
    in_quiet_hours, parse_hhmm,
)

T0 = datetime(2026, 10, 27, 10, 0, 0)
NO_QUIET = QuietHours(enabled=False)


def test_quiet_hours_wrap_midnight():
    s, e = time(22, 0), time(8, 0)
    assert in_quiet_hours(time(23, 30), s, e)
    assert in_quiet_hours(time(2, 0), s, e)
    assert not in_quiet_hours(time(8, 0), s, e)
    assert not in_quiet_hours(time(12, 0), s, e)
    assert in_quiet_hours(time(13, 0), time(12, 0), time(14, 0))
    assert not in_quiet_hours(time(23, 0), s, e, enabled=False)


def test_parse_hhmm():
    assert parse_hhmm("07:45") == time(7, 45)
    assert parse_hhmm("garbage", time(1, 2)) == time(1, 2)


def test_water_reminder_interval_and_snooze():
    r = WaterReminder(WaterConfig(True, 60, 15, NO_QUIET), T0)
    assert not r.check(T0 + timedelta(minutes=59), False)
    assert r.check(T0 + timedelta(minutes=60), False)
    assert not r.check(T0 + timedelta(minutes=61), False)  # fires once per interval
    r.snooze(T0 + timedelta(minutes=61))
    assert not r.check(T0 + timedelta(minutes=75), False)
    assert r.check(T0 + timedelta(minutes=76), False)


def test_water_reminder_logging_resets_and_goal_stops():
    r = WaterReminder(WaterConfig(True, 60, 15, NO_QUIET), T0)
    r.on_logged(T0 + timedelta(minutes=50))
    assert not r.check(T0 + timedelta(minutes=60), False)
    assert not r.check(T0 + timedelta(minutes=200), True)  # goal reached


def test_water_reminder_quiet_hours():
    quiet = QuietHours(True, time(22, 0), time(8, 0))
    start = datetime(2026, 10, 27, 21, 30)
    r = WaterReminder(WaterConfig(True, 60, 15, quiet), start)
    for minutes in range(60, 600, 5):  # 22:30 .. 07:25 - always quiet
        assert not r.check(start + timedelta(minutes=minutes), False)
    assert r.check(datetime(2026, 10, 28, 8, 0), False)  # first reminder after quiet hours


def _tracker(**kw):
    cfg = MovementConfig(enabled=True, interval_min=60, break_min=5, snooze_min=10, idle_reset_min=5,
                         quiet=NO_QUIET)
    for k, v in kw.items():
        setattr(cfg, k, v)
    return MovementTracker(cfg)


def run(tracker, start, seconds, step=5, idle=0.0, active=True):
    events = []
    t = start
    for _ in range(int(seconds // step)):
        t += timedelta(seconds=step)
        events += tracker.update(t, idle, active)
    return t, events


def test_movement_reminder_after_an_hour():
    tr = _tracker()
    tr.update(T0, 0, True)
    t, ev = run(tr, T0, 59 * 60)
    assert "reminder_due" not in ev
    t, ev = run(tr, t, 70)
    assert ev.count("reminder_due") == 1
    t, ev = run(tr, t, 600)
    assert "reminder_due" not in ev  # no repeat while due
    assert tr.state == MovementState.DUE


def test_movement_idle_resets_estimate():
    tr = _tracker()
    tr.update(T0, 0, True)
    t, _ = run(tr, T0, 40 * 60)
    assert tr.desk_seconds > 0
    tr.update(t + timedelta(seconds=5), 5 * 60 + 1, True)
    assert tr.desk_seconds == 0


def test_movement_snooze():
    tr = _tracker()
    tr.update(T0, 0, True)
    t, ev = run(tr, T0, 3605)
    assert "reminder_due" in ev
    tr.snooze(t)
    t2, ev = run(tr, t, 9 * 60)
    assert "reminder_due" not in ev
    t3, ev = run(tr, t2, 2 * 60)
    assert ev.count("reminder_due") == 1


def test_movement_break_flow_no_reminders_during_break():
    tr = _tracker()
    tr.update(T0, 0, True)
    t, _ = run(tr, T0, 3605)
    tr.start_break(t)
    assert tr.break_remaining(t) == 300
    t2, ev = run(tr, t, 290)
    assert "reminder_due" not in ev and tr.state == MovementState.ON_BREAK
    t3, ev = run(tr, t2, 15)
    assert "break_finished" in ev
    assert tr.state == MovementState.TRACKING and tr.desk_seconds < 30


def test_movement_dismiss_and_cancel_break():
    tr = _tracker()
    tr.update(T0, 0, True)
    t, _ = run(tr, T0, 3605)
    tr.dismiss(t)
    assert tr.desk_seconds == 0 and tr.state == MovementState.TRACKING
    t, _ = run(tr, t, 3605)
    tr.start_break(t)
    tr.cancel_break(t + timedelta(seconds=30))
    assert tr.state == MovementState.TRACKING and tr.desk_seconds >= 3600
    assert tr.snoozed_until == t + timedelta(seconds=30, minutes=10)


def test_movement_quiet_hours_and_sleep_gap():
    quiet = QuietHours(True, time(9, 0), time(12, 0))
    tr = _tracker(quiet=quiet)
    tr.update(T0, 0, True)
    _, ev = run(tr, T0, 3700)
    assert "reminder_due" not in ev  # 10:00-11:01 is quiet
    tr2 = _tracker()
    tr2.update(T0, 0, True)
    t, _ = run(tr2, T0, 1800)
    tr2.update(t + timedelta(hours=2), 0, True)  # laptop slept
    assert tr2.desk_seconds == 0


def test_movement_inactive_time_not_counted():
    tr = _tracker()
    tr.update(T0, 0, False)
    run(tr, T0, 600, active=False)
    assert tr.desk_seconds == 0
