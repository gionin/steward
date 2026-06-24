"""Headless verification of the bridge (app.Api).

Drives the Api the way the UI would and asserts the snapshots, then reopens the
database file to prove everything persisted. Run:  python test_api.py
"""

import os
import tempfile
from datetime import date

from engine import key_of, Lifecycle
import storage
from app import Api, APP_VERSION

MON, TUE = date(2026, 6, 22), date(2026, 6, 23)
kMON, kTUE = key_of(MON), key_of(TUE)

_fails = 0


def check(name, fn):
    global _fails
    try:
        fn()
        print("  pass  " + name)
    except Exception as e:
        _fails += 1
        print("  FAIL  " + name + "\n          " + str(e))


def eq(a, b, m=""):
    if a != b:
        raise AssertionError(f"{m} expected {b!r}, got {a!r}")


def fresh_api():
    d = tempfile.mkdtemp(prefix="custodian_api_")
    path = os.path.join(d, "custodian.db")
    conn, store = storage.open_database(path)
    return Api(conn, store), path


def names_today(state):
    return [it["name"] for it in state["today"]]


def col_names(state, col):
    return [t["name"] for t in state["columns"][col]]


# ---- fresh state ----

def _fresh():
    api, _ = fresh_api()
    st = api.get_state(kMON)
    eq(st["version"], APP_VERSION, "version string present")
    eq(len(st["containers"]), 1, "one container at first run")
    eq(st["containers"][0]["name"], "Misc", "it is Misc")
    eq(st["containers"][0]["protected"], True, "Misc is protected")
    eq(st["miscId"], st["containers"][0]["id"], "miscId points at the protected container")
    eq(st["today"], [], "nothing drafted")
    eq(col_names(st, "Ready"), [], "empty board")
    eq(st["history"], [], "no history")
check("bridge: fresh state is empty except a protected Misc", _fresh)


# ---- capture + board ----

def _capture_and_board():
    api, _ = fresh_api()
    st = api.capture_task("Buy milk", kMON)
    eq(names_today(st), ["Buy milk"], "captured task lands in today")
    eq(col_names(st, "Ready"), ["Buy milk"], "and on the Ready board")
    eq(st["columns"]["Ready"][0]["containerName"], "Misc", "filed under Misc")

    st = api.add_container("Work", kMON)
    work = next(c for c in st["containers"] if c["name"] == "Work")
    st = api.add_task("Write report", work["id"], "Soon", kMON)
    eq(col_names(st, "Soon"), ["Write report"], "added to Soon")
    eq(names_today(st), ["Buy milk"], "Soon task not drafted into today")

    tid = next(t["id"] for t in st["columns"]["Soon"] if t["name"] == "Write report")
    st = api.move_task(tid, "Ready", 0, kMON)
    eq(col_names(st, "Ready"), ["Write report", "Buy milk"], "board: moved to Ready position 0")
    eq(names_today(st), ["Buy milk", "Write report"],
       "today keeps materialisation order; board position only sets a fresh draft")
check("bridge: capture, add task, move between columns", _capture_and_board)


# ---- complete from today hides from board, persists ----

def _complete_and_persist():
    api, path = fresh_api()
    st = api.capture_task("Fix sink", kMON)
    item_id = st["today"][0]["id"]
    st = api.toggle_today_item(item_id, kMON)
    eq(st["today"][0]["done"], True, "today item shows done")
    eq(col_names(st, "Ready"), [], "completed task hidden from the board")

    api.conn.close()
    conn2, store2 = storage.open_database(path)
    st2 = Api(conn2, store2).get_state(kMON)
    eq(st2["today"][0]["done"], True, "completion persisted across reopen")
    eq(col_names(st2, "Ready"), [], "still hidden after reopen")
check("bridge: completing in Today hides from board and persists across reopen", _complete_and_persist)


# ---- routines ----

def _routines():
    api, _ = fresh_api()
    st = api.add_container("Health", kMON)
    health = next(c for c in st["containers"] if c["name"] == "Health")
    st = api.add_routine("Run", health["id"], kMON)
    rid = next(r["id"] for r in st["routines"] if r["name"] == "Run")
    st = api.toggle_routine_day(rid, 0, kMON)   # Monday
    st = api.set_routine_time(rid, "07:00", kMON)
    st = api.set_routine_duration(rid, 0.5, kMON)
    r = next(r for r in st["routines"] if r["id"] == rid)
    eq(r["daysOfWeek"], [0], "Monday scheduled")
    eq(r["hoursPerWeek"], 0.5, "hours/week computed")
    eq(names_today(st), ["Run"], "due routine appears in today")

    st = api.archive_routine(rid, kMON)
    eq(names_today(st), [], "archived routine drops out of today")
    eq(next(r for r in st["routines"] if r["id"] == rid)["archived"], True, "marked archived")
    st = api.unarchive_routine(rid, kMON)
    eq(names_today(st), ["Run"], "restored routine returns")
check("bridge: routine add, schedule, duration, archive/restore", _routines)


def _routine_order_in_today():
    api, _ = fresh_api()
    st = api.add_container("Health", kMON)
    h = next(c for c in st["containers"] if c["name"] == "Health")
    st = api.add_routine("Zebra", h["id"], kMON)
    z = next(r["id"] for r in st["routines"] if r["name"] == "Zebra")
    st = api.add_routine("Apple", h["id"], kMON)
    a = next(r["id"] for r in st["routines"] if r["name"] == "Apple")
    for rid in (z, a):                       # both due Monday and Tuesday
        api.toggle_routine_day(rid, 0, kMON)
        api.toggle_routine_day(rid, 1, kMON)
    st = api.get_state(kMON)
    eq(names_today(st), ["Zebra", "Apple"], "untimed routines in manual order, not alphabetical")
    api.reorder_routine(a, h["id"], 0, kMON)
    st = api.get_state(kTUE)                  # Tuesday is freshly drafted after the reorder
    eq(names_today(st), ["Apple", "Zebra"], "a freshly drafted day reflects the new routine order")
check("bridge: untimed routines follow manual order in the draft", _routine_order_in_today)


# ---- container set-aside removes from today ----

def _container_setaside():
    api, _ = fresh_api()
    st = api.add_container("Side", kMON)
    side = next(c for c in st["containers"] if c["name"] == "Side")
    st = api.add_task("Sketch logo", side["id"], "Ready", kMON)
    eq(names_today(st), ["Sketch logo"], "active container's Ready task is drafted")
    st = api.set_container_status(side["id"], Lifecycle.PLANNED, kMON)
    eq(names_today(st), [], "setting the container aside pulls it from today")
    sketch = next(t for t in st["columns"]["Ready"] if t["name"] == "Sketch logo")
    eq(sketch["containerActive"], False, "its container is inactive, so the board view hides it")
    st = api.set_container_status(side["id"], Lifecycle.ACTIVE, kMON)
    eq(names_today(st), ["Sketch logo"], "reactivating restores it")
check("bridge: set-aside removes a container's items from today, reactivation restores", _container_setaside)


# ---- protected delete guard via the bridge ----

def _protected_guard():
    api, _ = fresh_api()
    st = api.get_state(kMON)
    misc_id = st["miscId"]
    res = api.delete_container(misc_id, kMON)
    eq(res["ok"], False, "protected Misc refuses deletion")
    eq(len(res["state"]["containers"]), 1, "Misc still present")
    st = api.add_container("Temp", kMON)
    temp = next(c for c in st["containers"] if c["name"] == "Temp")
    res = api.delete_container(temp["id"], kMON)
    eq(res["ok"], True, "a normal container deletes")
    eq([c["name"] for c in res["state"]["containers"]], ["Misc"], "only Misc remains")
check("bridge: protected Misc cannot be deleted, others can", _protected_guard)


# ---- history: advance day, then edit the log ----

def _history_flow():
    api, _ = fresh_api()
    api.capture_task("Pay rent", kMON)   # Ready task, left undone on Monday
    st = api.get_state(kTUE)              # advance: Monday freezes into history
    eq(len(st["history"]), 1, "Monday is now a history day")
    eq(st["history"][0]["dateKey"], kMON, "history keyed by Monday")
    entry = st["history"][0]["entries"][0]
    eq(entry["name"], "Pay rent", "the missed task is recorded")
    eq(entry["done"], False, "recorded as not done")
    # check it done in history (task -> mark_task_done)
    st = api.mark_task_done(entry["id"], kMON, kTUE)
    hist_entry = st["history"][0]["entries"][0]
    eq(hist_entry["done"], True, "history check marks the task done")
    # uncheck via history_toggle
    st = api.history_toggle(hist_entry["id"], kMON, kTUE)
    eq(st["history"][0]["entries"][0]["done"], False, "history uncheck reverts")
    # delete the entry
    st = api.remove_item(st["history"][0]["entries"][0]["id"], kMON, kTUE)
    eq(st["history"], [], "removing the only entry empties history")
check("bridge: advance day creates history; check/uncheck/delete entries", _history_flow)


def _log_activity_and_conflict():
    api, _ = fresh_api()
    st = api.add_container("Work", kTUE)
    work = next(c for c in st["containers"] if c["name"] == "Work")
    kSUN = key_of(date(2026, 6, 21))
    # a brand-new done task logged on Sunday
    res = api.log_activity("task", True, "Cleaned desk", work["id"], None, kSUN, True, kTUE)
    eq(res["ok"], True, "new done task logged")
    sun = next(d for d in res["state"]["history"] if d["dateKey"] == kSUN)
    eq(sun["entries"][0]["name"], "Cleaned desk", "appears in history")
    eq(sun["entries"][0]["done"], True, "as done")

    # existing task: complete it Sunday, then log a miss on Monday (AFTER the completion) -> conflict
    api.capture_task("Ship it", kTUE)
    tid = next(t["id"] for t in api.get_state(kTUE)["tasksAll"] if t["name"] == "Ship it")
    api.log_activity("task", False, None, None, tid, kSUN, True, kTUE)        # done Sunday
    res = api.log_activity("task", False, None, None, tid, kMON, False, kTUE)  # miss Monday
    eq(res["ok"], False, "a miss logged after the completion flags a conflict")
    eq(res["conflict"], "taskDoneBefore", "conflict type reported")
    res = api.log_activity("task", False, None, None, tid, kMON, False, kTUE, force=True)
    eq(res["ok"], True, "forcing resolves the conflict")
    eq(api.get_state(kTUE)["columns"]["Ready"][0]["name"], "Ship it",
       "after forcing, the completion is cleared and the task is active again")
check("bridge: log_activity for new/existing items and the completion conflict path", _log_activity_and_conflict)


# ---- context export ----

def _export():
    api, _ = fresh_api()
    api.capture_task("Buy milk", kMON)
    txt = api.context_export(kMON)
    if "TODAY'S SLICE" not in txt or "Buy milk" not in txt or "ACTIVE CONTAINERS" not in txt:
        raise AssertionError("export text missing expected sections")
check("bridge: context export produces the expected text", _export)


# ---- end-to-end persistence through the bridge ----

def _persistence_e2e():
    api, path = fresh_api()
    st = api.add_container("Work", kMON)
    work = next(c for c in st["containers"] if c["name"] == "Work")
    api.add_task("A", work["id"], "Ready", kMON)
    api.add_task("B", work["id"], "Soon", kMON)
    st = api.add_routine("Standup", work["id"], kMON)
    rid = next(r["id"] for r in st["routines"] if r["name"] == "Standup")
    api.toggle_routine_day(rid, 0, kMON)
    api.conn.close()

    conn2, store2 = storage.open_database(path)
    st2 = Api(conn2, store2).get_state(kMON)
    eq(sorted(c["name"] for c in st2["containers"]), ["Misc", "Work"], "containers persisted")
    eq(col_names(st2, "Ready"), ["A"], "Ready task persisted")
    eq(col_names(st2, "Soon"), ["B"], "Soon task persisted")
    eq([r["name"] for r in st2["routines"]], ["Standup"], "routine persisted")
    eq(names_today(st2), ["A", "Standup"], "draft rebuilt: Ready task then untimed routine")
check("bridge: a session of commands survives a full reopen of the database", _persistence_e2e)


print("")
print(f"{_fails} failed" if _fails else "all checks passed")
import sys
sys.exit(1 if _fails else 0)
