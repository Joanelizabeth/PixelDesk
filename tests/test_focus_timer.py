from datetime import datetime

from services.focus_timer import FocusTimer, Phase, TimerState


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(focus=1500, brk=300):
    clk = FakeClock()
    return FocusTimer(focus, brk, monotonic=clk, wall=lambda: datetime(2026, 10, 27, 10).astimezone()), clk


def test_run_to_completion_and_switch_to_break():
    t, clk = make()
    t.start(task_id=7)
    clk.t += 1499
    assert t.tick() is None
    clk.t += 1
    rec = t.tick()
    assert rec.status == "completed" and rec.kind == "focus" and rec.actual_seconds == 1500 and rec.task_id == 7
    assert t.phase == Phase.BREAK and t.state == TimerState.IDLE
    assert t.task_id == 7


def test_pause_and_resume_excludes_paused_time():
    t, clk = make()
    t.start()
    clk.t += 600
    t.pause()
    clk.t += 5000  # paused for a long time
    assert t.elapsed() == 600 and t.remaining() == 900
    t.resume()
    clk.t += 899
    assert t.tick() is None
    clk.t += 1
    assert t.tick().status == "completed"


def test_no_drift_with_irregular_ticks():
    t, clk = make(focus=60)
    t.start()
    for step in (0.3, 7.7, 0.01, 22, 15, 14.98):
        clk.t += step
        t.tick()
    assert t.state == TimerState.RUNNING and abs(t.remaining() - 0.01) < 1e-6


def test_cancel_gives_no_completion_credit():
    t, clk = make()
    t.start(task_id=3)
    clk.t += 30
    assert t.reset() is None  # under a minute: nothing stored
    t.start(task_id=3)
    clk.t += 600
    rec = t.reset()
    assert rec.status == "cancelled" and rec.actual_seconds == 600
    assert t.state == TimerState.IDLE and t.phase == Phase.FOCUS


def test_completion_recorded_once():
    t, clk = make(focus=60)
    t.start()
    clk.t += 120
    assert t.tick() is not None
    assert t.tick() is None
    assert t.reset() is None


def test_auto_start_break():
    t, clk = make(focus=60, brk=30)
    t.start()
    clk.t += 60
    rec = t.tick(auto_start_break=True)
    assert rec.kind == "focus"
    assert t.phase == Phase.BREAK and t.state == TimerState.RUNNING
    clk.t += 30
    rec2 = t.tick(auto_start_focus=False)
    assert rec2.kind == "break" and rec2.session_uid != rec.session_uid
    assert t.phase == Phase.FOCUS and t.state == TimerState.IDLE


def test_focus_controller_persists(repo, qapp):
    from app.settings_store import SettingsStore
    from services.focus_timer import FocusController
    from services.streak_service import ProgressService

    settings = SettingsStore(repo)
    ctl = FocusController(repo, settings, ProgressService(repo))
    clk = FakeClock()
    ctl.timer._mono = clk
    tid = repo.add_task("Study Python")
    ctl.start(tid)
    clk.t += 25 * 60
    ctl._on_tick()
    ctl._on_tick()
    sessions = repo.focus_sessions(tid)
    assert len(sessions) == 1 and sessions[0]["status"] == "completed"
    assert repo.total_xp() == 15
