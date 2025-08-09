import json
import threading
import time
from datetime import datetime

from workflow.scheduler import CronScheduler
from workflow import scheduler


def test_scheduler_exclusive_access(tmp_path):
    counter = tmp_path / "count.txt"
    counter.write_text("0")

    def job():
        count = int(counter.read_text())
        time.sleep(0.1)
        counter.write_text(str(count + 1))

    lock = tmp_path / "job.lock"
    cron = "* * * * * *"
    s1 = CronScheduler()
    s2 = CronScheduler()
    s1.add_job(cron, job, lock)
    s2.add_job(cron, job, lock)
    now = datetime.now().replace(microsecond=0)

    t1 = threading.Thread(target=lambda: s1.run_pending(now))
    t2 = threading.Thread(target=lambda: s2.run_pending(now))
    t1.start(); t2.start(); t1.join(); t2.join()

    assert counter.read_text() == "1"


def test_crash_report_creation(tmp_path):
    log_file = tmp_path / "run.log"
    log_file.write_text("start\n")

    def job():
        log_file.write_text(log_file.read_text() + "before crash\n")
        raise RuntimeError("boom")

    reports = tmp_path / "reports"
    s = CronScheduler()
    s.add_job("* * * * * *", job, tmp_path / "lock", log_file=log_file, report_dir=reports)
    s.run_pending(datetime.now())

    files = list(reports.glob("crash_*.json"))
    assert files
    data = json.loads(files[0].read_text())
    assert data["error"] == "boom"
    assert "python" in data["env"]
    assert "before crash" in data["log"]


def test_condition_callbacks_skip_job(tmp_path):
    called = False

    def job():
        nonlocal called
        called = True

    def check():
        return False

    s = CronScheduler()
    s.add_job("* * * * * *", job, tmp_path / "lock", conditions=[check])
    s.run_pending(datetime.now())

    assert not called


def test_is_vpn_connected(monkeypatch):
    monkeypatch.setattr(scheduler.sys, "platform", "linux")

    def fake_run(cmd, capture_output, text, check=False):
        class Result:
            stdout = "1: lo:...\n2: tun0: <POINTOPOINT>"

        return Result()

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)
    assert scheduler.is_vpn_connected()


def test_is_ac_powered(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduler.sys, "platform", "linux")
    base = tmp_path
    ac = base / "AC"
    ac.mkdir()
    (ac / "online").write_text("1")
    monkeypatch.setattr(scheduler, "_POWER_SUPPLY_BASE", base)
    assert scheduler.is_ac_powered()


def test_is_screen_locked(monkeypatch):
    monkeypatch.setattr(scheduler.sys, "platform", "linux")

    def fake_run(cmd, capture_output, text, check=False):
        class Result:
            stdout = "The screensaver is active"

        return Result()

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)
    assert scheduler.is_screen_locked()
