"""One supervised worker, whichever command started the dashboard.

`launch_prototype.ps1` started a supervisor; `.claude/launch.json` and a
bare `streamlit run` did not, so the same application had live news or a
frozen store depending on the command the operator happened to use. The
screen's only clue was a heartbeat age, which nobody reads as "your IDE
launch does not fetch".

These pin the three properties that make moving the decision into the
application safe: exactly one worker, only our own process is ever
signalled, and nothing is left fetching after the app goes away.

Process spawning is faked. The real spawn/stop path was exercised against
live sources separately; see
`docs/evidence/news-intelligence/news-completion-2026-10-19/`.
"""
from __future__ import annotations

import pathlib

import pytest

from seraph.dashboard import news_service

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _FakeChild:
    def __init__(self, pid=4242):
        self.pid, self.returncode, self.signals = pid, None, []

    def poll(self):
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        self.returncode = 0

    def terminate(self):
        self.signals.append("terminate")
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Each test decides for itself; the memo is process-wide by design."""
    monkeypatch.setattr(news_service, "_state", None, raising=False)
    monkeypatch.delenv(news_service.ENV_FLAG, raising=False)
    yield
    news_service._state = None


@pytest.fixture
def spawned(monkeypatch):
    children = []

    def fake_spawn(store_path, interval, log):
        child = _FakeChild(5000 + len(children))
        children.append(child)
        return child

    monkeypatch.setattr(news_service, "_spawn", fake_spawn)
    monkeypatch.setattr(news_service, "lock_held_override", None, raising=False)
    return children


def _free_lock(monkeypatch, held=False):
    import seraph.news.worker_lock as wl
    monkeypatch.setattr(wl, "lock_held", lambda *_a, **_k: held)


def test_the_dashboard_starts_one_worker(tmp_path, spawned, monkeypatch):
    _free_lock(monkeypatch)
    state = news_service.ensure_worker(tmp_path / "news.sqlite")
    assert state["started"] is True and state["owner"] == "dashboard"
    assert len(spawned) == 1


def test_reruns_and_tabs_do_not_spawn_a_second(tmp_path, spawned, monkeypatch):
    """Streamlit re-runs the script on every interaction and per tab."""
    _free_lock(monkeypatch)
    path = tmp_path / "news.sqlite"
    first = news_service.ensure_worker(path)
    for _ in range(10):
        again = news_service.ensure_worker(path)
        assert again["pid"] == first["pid"]
    assert len(spawned) == 1, "one decision per server process"


def test_it_stands_aside_when_a_launcher_already_owns_one(tmp_path, spawned, monkeypatch):
    _free_lock(monkeypatch, held=True)
    state = news_service.ensure_worker(tmp_path / "news.sqlite")
    assert state["started"] is False and state["owner"] == "external"
    assert spawned == [], "a second supervisor would only refuse and exit"


def test_acquisition_can_be_switched_off_honestly(tmp_path, spawned, monkeypatch):
    monkeypatch.setenv(news_service.ENV_FLAG, "0")
    state = news_service.ensure_worker(tmp_path / "news.sqlite")
    assert state["started"] is False and state["owner"] == "disabled"
    assert "not acquiring news" in state["reason"]
    assert spawned == []


def test_stopping_touches_only_our_own_child(tmp_path, spawned, monkeypatch):
    _free_lock(monkeypatch)
    news_service.ensure_worker(tmp_path / "news.sqlite")
    result = news_service.stop_worker()
    assert result["stopped"] is True
    assert spawned[0].signals, "the child we started was signalled"


def test_stopping_without_a_worker_is_not_an_error(monkeypatch):
    assert news_service.stop_worker()["stopped"] is False


def test_an_exited_worker_is_reported_rather_than_respawned(tmp_path, spawned,
                                                            monkeypatch):
    _free_lock(monkeypatch)
    path = tmp_path / "news.sqlite"
    news_service.ensure_worker(path)
    spawned[0].returncode = 1
    state = news_service.ensure_worker(path)
    assert state["owner"] == "exited"
    assert len(spawned) == 1, (
        "the supervisor already escalated; respawning here would just "
        "re-run that escalation in a second place")


# ------------------------------------------- the launch paths agree

def test_the_dashboard_asks_for_a_worker_on_every_launch_path():
    app = (ROOT / "seraph/dashboard/prototype_app.py").read_text(encoding="utf-8")
    assert "news_service.ensure_worker" in app, (
        "a bare `streamlit run` or IDE launch would fetch nothing")


def test_the_launcher_starts_one_immediately():
    """A server with no browser session attached has not run the app script
    yet, so the launcher cannot wait for the first page view."""
    script = (ROOT / "launch_prototype.ps1").read_text(encoding="utf-8")
    assert "news_supervisor.py" in script
    assert "--owner-pid" in script, (
        "a launcher-started worker must stop when the launcher does")


def test_the_worker_can_be_told_to_outlive_nothing():
    supervisor = (ROOT / "scripts/news_supervisor.py").read_text(encoding="utf-8")
    assert "--owner-pid" in supervisor
    assert "pid_alive(owner_pid) is False" in supervisor, (
        "an unanswerable liveness question must not stop acquisition")


def test_the_console_reports_which_situation_it_is_in():
    app = (ROOT / "seraph/dashboard/prototype_app.py").read_text(encoding="utf-8")
    assert "def acquisition_panel" in app
    for owner in ("dashboard", "external", "disabled"):
        assert f"'{owner}'" in app, f"the panel cannot describe {owner}"
