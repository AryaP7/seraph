# Operations — O03: the daily schedule for the market/prediction pipeline.
"""When the daily sequence should run, and how to register that with the OS.

`AGENTS.md` §2 chose "cron + idempotent scripts" over a workflow engine, and
then no schedule was ever defined: `run_market_jobs.py` ran when somebody
launched the console. That made the prediction panel current only on days the
application happened to be opened, which is not a refresh schedule.

This module owns the decisions; `scripts/schedule_market_jobs.py` is the
command-line surface and the thing that actually talks to the OS. The split
exists so the decisions are testable without registering anything.

**Holidays, honestly.** No ingested exchange calendar exists in this
repository — `SessionCalendar`'s `SPECIAL_SESSIONS` is deliberately partial
and holds no holiday list. `MarketClock.is_session` is therefore
weekday-plus-registry, and this module reuses it rather than inventing a
holiday table, which would be fabricating exchange data. The consequence is
stated rather than hidden: on an unregistered NSE holiday the task fires, the
corpus has no new session, and the run is recorded as **executed with
unchanged data**. That is the correct outcome and it is why execution success
and data freshness are reported as two separate facts.

**Why a weekday trigger and not a daily one.** Saturday and Sunday are never
NSE equity sessions, so a Mon-Fri trigger skips two certain non-sessions
without needing a calendar. Everything else is decided by the job at run
time, where the corpus is the authority on what a trading day was.
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta

from seraph.shared_types import IST

#: The Windows Task Scheduler task name, and the ledger/lease name the run
#: records itself under. The lease name is what makes the run visible in the
#: HEALTH panel, because `monitoring.job_checks` reads the job ledger.
TASK_NAME = "SERAPH Daily Market Jobs"
JOB_NAME = "market.daily"

#: 18:30 IST: three hours after the 15:30 regular close, which leaves room for
#: the end-of-day files to be published before the corpus is asked for a new
#: session. Earlier than this and the ordinary outcome would be "executed,
#: data unchanged" every day, which would make a real failure unremarkable.
RUN_AT_IST = time(18, 30)

#: How long after the expected session a refresh may be missing before the
#: saved prediction is called stale. One session plus a margin: a single
#: unregistered holiday must not read as a broken pipeline.
STALE_AFTER_SESSIONS = 2


def run_at_local(at_ist: time = RUN_AT_IST, *, on: date | None = None) -> time:
    """`at_ist` expressed in this machine's local time.

    Task Scheduler and cron both fire in local time. On a machine set to IST
    these are the same value, which is the easy case to get wrong by assuming
    it everywhere -- a developer machine in another zone would otherwise run
    the job at 18:30 of its own day, which may be before the NSE close or
    after the next one.
    """
    on = on or date.today()
    moment = datetime.combine(on, at_ist, tzinfo=IST)
    return moment.astimezone().timetz().replace(tzinfo=None)


def local_equals_ist(*, on: date | None = None) -> bool:
    on = on or date.today()
    reference = datetime.combine(on, time(12, 0), tzinfo=IST)
    return reference.astimezone().utcoffset() == IST.utcoffset(None)


def expected_session(at: datetime | None = None, clock=None) -> str:
    """The most recent day that is a session by weekday-plus-registry.

    Before the close, the expected session is the previous one: the current
    day's data does not exist yet, so calling it expected would make every
    morning look behind.
    """
    from seraph.live.clock import MarketClock

    clock = clock or MarketClock()
    moment = at or datetime.now(IST)
    day = moment.date()
    if clock.is_session(day.isoformat()) and moment.timetz().replace(
            tzinfo=None) < RUN_AT_IST:
        day -= timedelta(days=1)
    for _ in range(14):
        if clock.is_session(day.isoformat()):
            return day.isoformat()
        day -= timedelta(days=1)
    return day.isoformat()


def should_run(day: str | None = None, clock=None) -> dict:
    """Whether the sequence should do work today, and why.

    A weekend is the only case this refuses outright, because it is the only
    one that is certain without a calendar. A holiday is not refused: the job
    runs, finds no new session and records unchanged data, which is a more
    useful signal than silence.
    """
    from seraph.live.clock import MarketClock

    clock = clock or MarketClock()
    target = day or datetime.now(IST).date().isoformat()
    if clock.is_session(target):
        return dict(run=True, day=target, reason=(
            "a session by weekday-plus-registry. An unregistered exchange "
            "holiday also lands here and is resolved by the corpus having no "
            "new session, which is recorded as unchanged data rather than a "
            "failure"))
    return dict(run=False, day=target, reason=(
        "not a trading day: a weekend, or a registered non-session. Nothing "
        "to acquire, so the sequence is skipped rather than recorded as a "
        "failure"))


# --- freshness: two separate facts ---------------------------------------

def freshness(*, previous_session: str | None, current_session: str | None,
              expected: str | None = None) -> dict:
    """Did new data arrive, and is the corpus current? Two questions.

    The directive this implements is explicit that a successful job execution
    and successful acquisition of fresh data are different claims, and
    conflating them is how a green dashboard sits on top of a corpus that
    stopped updating a week ago. `acquired` answers the first; `currency`
    answers the second.
    """
    expected = expected or expected_session()
    if current_session is None:
        return dict(acquired="unknown", currency="unknown",
                    previous_session=previous_session,
                    current_session=None, expected_session=expected,
                    sessions_behind=None,
                    detail="the corpus could not be read, so neither question "
                           "can be answered")

    if previous_session is None:
        acquired = "first_run"
    elif current_session > previous_session:
        acquired = "fresh"
    elif current_session == previous_session:
        acquired = "unchanged"
    else:
        acquired = "regressed"

    behind = None
    if current_session >= expected:
        currency = "current"
    else:
        behind = (date.fromisoformat(expected)
                  - date.fromisoformat(current_session)).days
        currency = "behind"

    details = {
        "fresh": f"the corpus advanced to {current_session}",
        "unchanged": (f"the job ran and the corpus still ends at "
                      f"{current_session}: an exchange holiday, or the "
                      f"loader has not been run"),
        "regressed": (f"the corpus now ends at {current_session}, EARLIER "
                      f"than {previous_session}. That is data loss, not "
                      f"staleness"),
        "first_run": f"no previous run to compare; the corpus ends at "
                     f"{current_session}",
    }
    detail = details[acquired]
    if currency == "behind":
        detail += (f"; {behind} calendar day(s) behind the expected session "
                   f"{expected}")
        # A one- or two-session gap is what an unregistered holiday or a
        # single missed run looks like. Sixty days is not: that is the extent
        # of the loaded corpus, and saying "holiday" there would send a
        # reader looking for an exchange notice instead of at the loader.
        if behind <= 4:
            detail += ", which an unregistered holiday also looks like"
        else:
            detail += (". A gap this wide is the extent of the loaded corpus, "
                       "not a holiday: the vendored snapshot ends here, so "
                       "extending it needs an ingestion run, not another "
                       "scheduled execution")
    return dict(acquired=acquired, currency=currency,
                previous_session=previous_session,
                current_session=current_session, expected_session=expected,
                sessions_behind=behind, detail=detail)


def prediction_staleness(as_of: str | None, *, expected: str | None = None
                         ) -> dict:
    """Is the saved prediction still for the session it should be?

    A failed refresh must not discard the last valid forecast -- the console
    keeps showing it -- but it must not present it as current either. This is
    the marking.
    """
    expected = expected or expected_session()
    if not as_of:
        return dict(stale=True, as_of=None, expected=expected,
                    days_behind=None,
                    detail="no saved prediction")
    behind = (date.fromisoformat(expected) - date.fromisoformat(as_of)).days
    if behind <= 0:
        return dict(stale=False, as_of=as_of, expected=expected,
                    days_behind=0,
                    detail=f"current for the expected session {expected}")
    stale = behind > STALE_AFTER_SESSIONS
    if not stale:
        tail = "Within the allowance for a holiday or a single missed run."
    elif behind <= 4:
        tail = ("This is the last valid forecast and it is NOT current. A gap "
                "this size is a missed run or an unregistered holiday.")
    else:
        tail = ("This is the last valid forecast and it is NOT current. A gap "
                "this wide means the corpus itself ends here, so running the "
                "pipeline again will reproduce the same date: extending it "
                "needs an ingestion run.")
    return dict(
        stale=stale, as_of=as_of, expected=expected, days_behind=behind,
        detail=(f"the saved forecast is for {as_of}, {behind} calendar day(s) "
                f"before the expected session {expected}. " + tail))


# --- the OS surface, as data rather than side effects --------------------

def python_executable() -> str:
    """The interpreter the task should use.

    `sys.executable` inside the project's virtual environment, because a task
    registered against a bare `python` would resolve to whatever is on the
    machine's PATH at fire time and miss every dependency.
    """
    import sys

    return sys.executable


def register_command(*, python: str, script: str, task_name: str = TASK_NAME,
                     at_local: time | None = None,
                     working_directory: str | None = None) -> list[str]:
    # `working_directory` is accepted and deliberately unused: the cron line
    # takes one (cron has no equivalent of resolving from __file__ for the
    # shell it spawns) and keeping one signature avoids two call sites that
    # differ by an argument nobody remembers the reason for.
    """The `schtasks` argv that creates the weekday task.

    Returned rather than run, so the exact command can be asserted in a test
    and shown to the operator before anything is registered. `/f` makes
    re-registration idempotent: the same name is replaced, not duplicated.
    """
    at_local = at_local or run_at_local()
    # No `cmd /c cd /d ... &&` wrapper. Both scripts resolve every path from
    # `__file__` and run their children with `cwd=ROOT`, so the scheduler's
    # working directory is irrelevant -- verified by running `--status` from
    # C:\Windows. The wrapper only added a layer of shell quoting that
    # schtasks and PowerShell disagree about, which is how the first
    # registration attempt failed on `Invalid argument/option - '&&'`.
    command = f'"{python}" "{script}" --scheduled'
    return [
        "schtasks", "/create", "/tn", task_name, "/tr", command,
        "/sc", "weekly", "/d", "MON,TUE,WED,THU,FRI",
        "/st", at_local.strftime("%H:%M"), "/f",
    ]


def query_command(task_name: str = TASK_NAME) -> list[str]:
    return ["schtasks", "/query", "/tn", task_name, "/v", "/fo", "LIST"]


def delete_command(task_name: str = TASK_NAME) -> list[str]:
    return ["schtasks", "/delete", "/tn", task_name, "/f"]


def run_now_command(task_name: str = TASK_NAME) -> list[str]:
    return ["schtasks", "/run", "/tn", task_name]


def cron_line(*, python: str, script: str, at_ist: time = RUN_AT_IST,
              working_directory: str | None = None) -> str:
    """The crontab equivalent, for the other supported environments.

    cron fires in the machine's local time, so the comment states the IST
    intent and the line uses the converted hour -- the same trap as Task
    Scheduler.
    """
    local = run_at_local(at_ist)
    prefix = f"cd {working_directory} && " if working_directory else ""
    return (f"# SERAPH daily market, prediction and warning pipeline.\n"
            f"# {at_ist.strftime('%H:%M')} IST, weekdays"
            + ("" if local_equals_ist() else
               f" (= {local.strftime('%H:%M')} local on this machine)")
            + f"\n{local.minute} {local.hour} * * 1-5 "
              f"{prefix}{python} {script} --scheduled\n")


def task_name_override() -> str:
    return os.environ.get("SERAPH_SCHEDULED_TASK_NAME", TASK_NAME)
