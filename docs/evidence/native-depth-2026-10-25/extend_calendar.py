"""Extend the bounded exchange calendar to 2026-10-30, from evidence in hand.

The interval ended 2026-10-23, so `configured().verified_for('2026-10-26')`
was False and Monday could only be assumed to be a session. F02's remaining
requirement is a genuine IN-SESSION publication, and assuming the session is
exactly the thing this calendar exists to avoid.

No new evidence is fetched. `CMTR71775.pdf`, already stored and hashed under
`2026-10-21/`, is NSE's trading-holiday circular for the WHOLE of calendar
year 2026 (Download Ref NSE/CMTR/71775, 12 December 2025), so it already
covers next week. The holiday rows are parsed OUT of that PDF and the day
statuses are derived from them, rather than transcribed by hand -- a
transcription slip is the realistic failure here, so the circular decides.

Bounded deliberately at 2026-10-30. The circular's next entries are Sunday
2026-11-08 (Diwali Laxmi Pujan, with Muhurat trading whose "timings shall be
notified subsequently") and Tuesday 2026-11-10 (Diwali-Balipratipada).
Muhurat is a non-standard session with unpublished hours, so extending past
2026-11-07 needs that later notice and is not done here.
"""
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CAL = ROOT / "prototype_runs/exchange_calendar"
START, END = date(2026, 10, 19), date(2026, 10, 30)
MUHURAT_LIMIT = date(2026, 11, 7)

existing = json.loads((CAL / "current.json").read_text(encoding="utf-8"))
evidence = existing["evidence"]          # same files, same hashes, unchanged
for item in evidence:
    path = CAL / item["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], item["file"]

# Holidays, read from the circular itself.
from pypdf import PdfReader                                     # noqa: E402
text = "\n".join((p.extract_text() or "")
                 for p in PdfReader(CAL / evidence[0]["file"]).pages)
assert "trading holidays for the calendar year 202" in text.lower(), \
    "the cited PDF is not the annual trading-holiday circular"

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}
holidays = {}
for month, day, desc in re.findall(
        r"([A-Z][a-z]+) (\d{1,2}), 2026\s+[A-Z][a-z]+day\s+([^\n]+)", text):
    if month in MONTHS:
        holidays[date(2026, MONTHS[month], int(day))] = desc.strip()
assert date(2026, 10, 20) in holidays, "Dussehra row not found; parse is wrong"
assert END < MUHURAT_LIMIT, "extending past 2026-11-07 needs the Muhurat notice"

days, closed_note = [], []
cursor = START
while cursor <= END:
    iso = cursor.isoformat()
    if cursor in holidays:
        days.append(dict(date=iso, status="closed", evidence_indices=[0, 1]))
        closed_note.append(f"{iso} {holidays[cursor]}")
    elif cursor.weekday() >= 5:
        days.append(dict(date=iso, status="closed", evidence_indices=[0, 1]))
    else:
        days.append(dict(date=iso, status="open", evidence_indices=[0, 1],
                         kind="regular", windows=[["09:15:00", "15:30:00"]]))
    cursor += timedelta(days=1)

doc = dict(
    schema="nse-cash-calendar/1", start=START.isoformat(), end=END.isoformat(),
    evidence=evidence, days=days,
    note=("Bounded transcription; no authority outside this interval. Holiday "
          "statuses are parsed from the cited annual circular, not hand-entered: "
          + "; ".join(closed_note) + ". Weekends are closed. Ordinary NSE cash "
          "hours; not derivatives or pre-open hours. Deliberately ends "
          "2026-10-30: the circular's next entries are Sunday 2026-11-08 "
          "(Diwali Laxmi Pujan, Muhurat trading with timings to be notified "
          "subsequently) and 2026-11-10 (Diwali-Balipratipada), and Muhurat "
          "hours are not yet published, so a later notice is required to go "
          "beyond 2026-11-07."))

(CAL / "current.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
print(f"wrote {CAL/'current.json'}: {START} .. {END}, {len(days)} days enumerated")
print("closed days from the circular:", closed_note or "none")
