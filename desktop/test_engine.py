"""Behavioural verification for the Python engine.

Mirrors engine2_test.mjs check-for-check against the PREVIEW's behaviour, and
adds the two things the JS suite did not cover:
  - the manual routine-order in the daily draft (the behaviour the standalone
    engine.mjs got wrong by sorting untimed routines alphabetically), and
  - the protected-container delete guard (Misc).

Zero dependencies. Run:  python test_engine.py
Exits non-zero if any check fails.
"""

from datetime import date
from engine import Store, Lifecycle, key_of

MON, TUE, WED = date(2026, 6, 22), date(2026, 6, 23), date(2026, 6, 24)
kMON, kTUE, kWED = key_of(MON), key_of(TUE), key_of(WED)

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


def names(s, k):
    return [s.item_name(it) for it in s.day_items(k)]


def dones(s, k):
    return [it.done for it in s.day_items(k)]


# ---- ported checks ----

def _cadence():
    s = Store(); c = s.add_container("Health"); s.add_routine("Gym", c.id, [0, 2, 4])
    s.sync_day(MON); s.sync_day(TUE); s.sync_day(WED)
    eq(names(s, kMON), ["Gym"]); eq(names(s, kTUE), []); eq(names(s, kWED), ["Gym"])
check("cadence: routine derives only on scheduled days", _cadence)


def _sink():
    s = Store(); c = s.add_container("Home"); t = s.add_task("Fix sink", c.id, "Ready")
    s.sync_day(MON); s.sync_day(TUE); s.sync_day(WED)
    it = next(x for x in s.day_items(kWED) if x.source_id == t.id)
    s.set_done(it, True)
    eq(dones(s, kMON), [False], "day1 miss")
    eq(dones(s, kTUE), [False], "day2 miss")
    eq(dones(s, kWED), [True], "day3 done")
    eq(s.tasks[t.id].completed, True, "task completed")
    eq(len(s.column_tasks("Ready")), 0, "completed task off the board")
check("sink: task in Ready 3 days logs 2 misses + 1 done; task ends completed", _sink)


def _routine_miss_once():
    s = Store(); c = s.add_container("Health"); s.add_routine("Run", c.id, [0, 2])
    s.sync_day(MON); s.sync_day(TUE); s.sync_day(WED)
    eq(len(s.day_items(kMON)), 1, "one miss Monday")
    eq(len(s.day_items(kTUE)), 0, "nothing Tuesday")
    eq(len(s.day_items(kWED)), 1, "single fresh Wednesday, no doubling")
check("routine miss is logged once per scheduled day, never accumulates", _routine_miss_once)


def _oneoff_sticky():
    s = Store(); c = s.add_container("Health"); gym = s.add_routine("Gym", c.id, [1, 3])
    s.add_one_off(gym.id, kMON)
    s.sync_day(MON); eq(names(s, kMON), ["Gym"], "one-off shows though unscheduled")
    gym.active = False; gym.days_of_week = [5]; c.status = Lifecycle.PLANNED
    s.sync_day(MON); eq(names(s, kMON), ["Gym"], "one-off survives all of it")
check("one-off persists through toggle, day change, and set-aside", _oneoff_sticky)


def _scheduled_plus_oneoff():
    s = Store(); c = s.add_container("Health"); gym = s.add_routine("Gym", c.id, [0])
    s.sync_day(MON); eq(len(s.day_items(kMON)), 1, "scheduled one")
    s.add_one_off(gym.id, kMON); s.sync_day(MON)
    eq(len(s.day_items(kMON)), 2, "second is the deliberate one-off")
check("scheduled + deliberate one-off = two items same day", _scheduled_plus_oneoff)


def _live_view_refile():
    s = Store(); a = s.add_container("Work"); b = s.add_container("Home")
    t = s.add_task("Email", a.id, "Ready"); s.sync_day(MON)
    it = s.day_items(kMON)[0]; s.set_done(it, True)
    eq(s.item_container(it), "Work")
    s.tasks[t.id].container_id = b.id
    eq(s.item_container(it), "Home", "past entry now reads the new container")
check("history is a live view: re-filing a task moves its past container", _live_view_refile)


def _uncheck_reverts():
    s = Store(); c = s.add_container("Work"); t = s.add_task("Pay rent", c.id, "Ready")
    s.sync_day(MON); it = s.day_items(kMON)[0]
    s.set_done(it, True); eq(s.tasks[t.id].completed, True)
    s.set_done(it, False)
    eq(s.tasks[t.id].completed, False, "back to active")
    eq([x.name for x in s.column_tasks("Ready")], ["Pay rent"], "back on the board")
    eq(len(s.day_items(kMON)), 1, "the day still records it was planned (not-done)")
check("uncheck in history reverts task to the board, keeps the not-done record", _uncheck_reverts)


def _adhoc_logtaskdone():
    s = Store(); c = s.add_container("Home")
    task, item = s.log_task_done("Cleaned gutters", c.id, kMON)
    eq(s.tasks[task.id].completed, True)
    eq(len(s.column_tasks("Ready")), 0, "born completed -> off board")
    eq(s.item_name(item), "Cleaned gutters")
    s.set_done(item, False)
    eq([x.name for x in s.column_tasks("Ready")], ["Cleaned gutters"], "undo pushes it onto the board")
check("ad-hoc log_task_done creates a completed referenced task; toggling reverts", _adhoc_logtaskdone)


def _delete_cascades():
    s = Store(); c = s.add_container("Work"); t = s.add_task("Report", c.id, "Ready")
    s.sync_day(MON); s.set_done(s.day_items(kMON)[0], True)
    a = s.day_log[kMON][0]; s.move_item(a, kMON, kTUE); s.move_item(a, kTUE, kMON)
    eq(s.task_log_count(t.id), 1)
    s.delete_task(t.id)
    eq(s.tasks.get(t.id), None, "task gone")
    eq(s.task_log_count(t.id), 0, "its entries gone")
check("delete a task cascades to its log entries (count first)", _delete_cascades)


def _archived_routine():
    s = Store(); c = s.add_container("Work"); standup = s.add_routine("Standup", c.id, [0])
    s.archive_routine(standup.id)
    s.sync_day(MON); eq(len(s.day_items(kMON)), 0, "archived -> no scheduled occurrence")
    eq(s.add_one_off(standup.id, kMON), None, "archived refuses one-off")
    gym = s.add_routine("Gym", c.id, [1]); gym.active = False
    oo = s.add_one_off(gym.id, kMON)
    if oo is None:
        raise AssertionError("toggled-off routine must allow one-off")
check("archived routine derives nothing and refuses one-offs; toggled-off still one-offs", _archived_routine)


def _hours_and_no_ties():
    s = Store(); c = s.add_container("X")
    r = s.add_routine("Gym", c.id, [0, 2, 4], None, 1.5); eq(s.hours_per_week(r), 4.5)
    a = s.add_task("A", c.id, "Ready"); b = s.add_task("B", c.id, "Ready"); cc = s.add_task("C", c.id, "Ready")
    s.move_task(cc.id, "Ready", 0); s.sync_day(MON)
    ts = [s.item_name(it) for it in s.day_items(kMON) if it.source_type == "task"]
    eq(ts, ["C", "A", "B"])
    pos = [t.position for t in s.column_tasks("Ready")]; eq(pos, [0, 1, 2], "contiguous unique")
check("hours/week and no-ties ordering still hold", _hours_and_no_ties)


def _single_completion():
    s = Store(); c = s.add_container("Home"); t = s.add_task("Fix sink", c.id, "Ready")
    s.sync_day(MON); s.sync_day(TUE); s.sync_day(WED)
    w = next(x for x in s.day_items(kWED) if x.source_id == t.id); s.set_done(w, True)
    eq(s.task_done_key(t.id), kWED, "initially done Wed")
    m = next(x for x in s.day_items(kMON) if x.source_id == t.id); s.set_done(m, True)
    eq(s.task_done_key(t.id), kMON, "re-asserting Mon moves the completion")
    eq(next(x for x in s.day_items(kWED) if x.source_id == t.id).done, False, "Wed reverts to not-done")
    dn = sum(1 for k in [kMON, kTUE, kWED] for it in s.day_items(k)
             if it.source_type == "task" and it.source_id == t.id and it.done)
    eq(dn, 1, "exactly one done entry")
check("single-completion: re-asserting moves the one completion date", _single_completion)


def _stringid_and_delete_after():
    s = Store(); c = s.add_container("W")
    a = s.add_task("A", c.id, "Ready"); b = s.add_task("B", c.id, "Ready"); cc = s.add_task("C", c.id, "Ready")
    s.move_task(str(cc.id), "Ready", 0)   # pass id as STRING, like the DOM does
    eq([t.name for t in s.column_tasks("Ready")], ["C", "A", "B"], "move_task works with a string id")
    eq([t.position for t in s.column_tasks("Ready")], [0, 1, 2], "positions stay unique after string-id move")
    s2 = Store(); c2 = s2.add_container("Home"); t = s2.add_task("Fix sink", c2.id, "Ready")
    s2.sync_day(MON); s2.sync_day(TUE); s2.sync_day(WED)
    m = next(x for x in s2.day_items(kMON) if x.source_id == t.id)
    s2.mark_task_done_on(m, kMON)
    eq(len([x for x in s2.day_items(kMON) if x.source_id == t.id and x.done]), 1, "done on Monday")
    eq(len(s2.day_items(kTUE)), 0, "Tuesday not-done record removed")
    eq(len(s2.day_items(kWED)), 0, "Wednesday not-done record removed")
check("string-id reorder regression + mark_task_done_on deletes later not-done", _stringid_and_delete_after)


def _logroutine_oneoff_rule():
    s = Store(); c = s.add_container("Health"); r = s.add_routine("Gym", c.id, [0])  # Mondays only
    s.log_routine_on(r.id, kMON, True)
    eq(s.day_items(kMON)[0].one_off, False, "scheduled day, no item yet -> NOT a one-off")
    s.log_routine_on(r.id, kTUE, True)
    eq(s.day_items(kTUE)[0].one_off, True, "non-scheduled day -> one-off")
    s.log_routine_on(r.id, kMON, False)
    eq(s.day_items(kMON)[1].one_off, True, "second log same day -> one-off")
check("log_routine_on one-off rule (scheduled slot vs off-schedule vs duplicate)", _logroutine_oneoff_rule)


def _one_record_per_day():
    s = Store(); c = s.add_container("W"); t = s.add_task("Ship", c.id, "Ready")
    s.sync_day(MON)
    s.log_existing_task_done(t.id, kMON)
    eq(len([x for x in s.day_items(kMON) if x.source_type == "task" and x.source_id == t.id]), 1,
       "task: one record per day after logging done")
    eq(s.day_items(kMON)[0].done, True, "that record is the completion")
    s2 = Store(); c2 = s2.add_container("W"); t2 = s2.add_task("Fix", c2.id, "Ready")
    s2.sync_day(MON); s2.sync_day(TUE)
    mon_it = s2.day_items(kMON)[0]; s2.set_done(mon_it, True)
    s2.move_item_to(mon_it, kMON, kTUE, 0)
    eq(len([x for x in s2.day_items(kTUE) if x.source_type == "task" and x.source_id == t2.id]), 1,
       "task: merge to one record on the target day")
    eq(len(s2.day_items(kMON)), 0, "source day record removed")
    s3 = Store(); c3 = s3.add_container("H"); r = s3.add_routine("Walk", c3.id, [])
    s3.add_one_off(r.id, kMON, True); s3.add_one_off(r.id, kMON, False)
    eq(len([x for x in s3.day_items(kMON) if x.source_type == "routine"]), 2,
       "routines: two records on one day allowed")
check("one task-item per day (dedup on log and on move); routines may repeat", _one_record_per_day)


# ---- NEW: manual routine order in the daily draft (engine.mjs got this wrong) ----

def _manual_routine_order():
    s = Store(); c = s.add_container("Health")
    z = s.add_routine("Zebra", c.id, [0])    # untimed, due Monday; added first
    ap = s.add_routine("Apple", c.id, [0])   # untimed, due Monday; added after -> later in routine_order
    # pure draft order
    d = s.compute_derived(MON)
    drafted = [s.routines[sid].name for (st, sid) in d if st == "routine"]
    eq(drafted, ["Zebra", "Apple"], "compute_derived: untimed routines follow manual order, NOT alphabetical")
    # observable list at fresh materialization
    s.sync_day(MON)
    eq(names(s, kMON), ["Zebra", "Apple"], "fresh sync materialises untimed routines in manual order")
    # reordering changes the draft
    s.reorder_routine(ap.id, c.id, 0)
    d2 = s.compute_derived(MON)
    drafted2 = [s.routines[sid].name for (st, sid) in d2 if st == "routine"]
    eq(drafted2, ["Apple", "Zebra"], "reordering routines changes the untimed draft order")
check("untimed routines draft in manual routine order, not alphabetically", _manual_routine_order)


def _timed_before_untimed_and_tasks_between():
    # full fixed order: timed routines (by time) -> Ready tasks (by position) -> untimed routines (manual)
    s = Store(); c = s.add_container("X")
    s.add_routine("Evening", c.id, [0], "18:00")   # timed, late
    s.add_routine("Morning", c.id, [0], "07:00")   # timed, early
    s.add_routine("Untimed", c.id, [0])            # untimed
    s.add_task("T1", c.id, "Ready")
    s.sync_day(MON)
    eq(names(s, kMON), ["Morning", "Evening", "T1", "Untimed"],
       "order: timed routines by time, then Ready tasks, then untimed routines")
check("daily draft order: timed routines by time, then Ready tasks, then untimed routines", _timed_before_untimed_and_tasks_between)


# ---- NEW: protected container (Misc) guard ----

def _protected_container():
    s = Store(); misc = s.add_container("Misc", protected=True); work = s.add_container("Work")
    eq(s.delete_container(misc.id), False, "protected container refuses deletion")
    if misc.id not in s.containers:
        raise AssertionError("protected container must still be present after a delete attempt")
    t = s.add_task("x", work.id, "Ready")
    eq(s.delete_container(work.id), True, "an unprotected container deletes")
    if work.id in s.containers or t.id in s.tasks:
        raise AssertionError("deleting a container must cascade to its tasks")
    # rename does not change protection
    misc.name = "Inbox"
    eq(s.containers[misc.id].protected, True, "protected survives a rename")
    eq(s.delete_container(misc.id), False, "still undeletable after rename")
check("protected container cannot be deleted; rename keeps the protection", _protected_container)


def _reorder_container():
    s = Store(); a = s.add_container("A"); b = s.add_container("B"); cc = s.add_container("C")
    eq([x.name for x in s.ordered_containers()], ["A", "B", "C"], "initial order is insertion order")
    s.reorder_container(cc.id, Lifecycle.ACTIVE, 0)
    eq([x.name for x in s.ordered_containers()], ["C", "A", "B"], "reorder moves C to front")
check("container manual ordering reorders as expected", _reorder_container)


print("")
print(f"{_fails} failed" if _fails else "all checks passed")
import sys
sys.exit(1 if _fails else 0)
