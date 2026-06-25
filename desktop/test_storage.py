"""Persistence + migration verification.

Run:  python test_storage.py
Exits non-zero if any check fails.
"""

import os
import sqlite3
import tempfile
from datetime import date

from engine import Store, Lifecycle, key_of
import storage
from storage import open_database, save, load, SCHEMA_VERSION, _apply_migrations, _get_version

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


def _tmp(name="steward.db"):
    d = tempfile.mkdtemp(prefix="steward_test_")
    return os.path.join(d, name)


def snapshot(store):
    """Plain-data image of a store for deep comparison (order included)."""
    return {
        "containers": [
            (c.id, c.name, c.status, c.description, c.protected)
            for c in (store.containers[i] for i in store.container_order)
        ],
        "tasks": sorted(
            (t.id, t.name, t.container_id, t.column, t.position, t.completed)
            for t in store.tasks.values()
        ),
        "routines": [
            (r.id, r.name, r.container_id, tuple(r.days_of_week), r.time,
             r.duration_hours, r.active, r.archived)
            for r in (store.routines[i] for i in store.routine_order)
        ],
        "day_log": {
            k: [(it.id, it.source_type, it.source_id, it.done, it.one_off) for it in items]
            for k, items in store.day_log.items() if items
        },
    }


# ---- 1. first-run state ----

def _first_run():
    path = _tmp()
    conn, store = open_database(path)
    eq(_get_version(conn), SCHEMA_VERSION, "fresh db is at the current schema version")
    eq(len(store.containers), 1, "fresh db has exactly one container")
    misc = next(iter(store.containers.values()))
    eq(misc.name, "Misc", "the seeded container is Misc")
    eq(misc.protected, True, "Misc is protected")
    eq(misc.status, Lifecycle.ACTIVE, "Misc is active")
    eq(len(store.tasks), 0, "no tasks at first run")
    eq(len(store.routines), 0, "no routines at first run")
    eq(store.day_log, {}, "no day log at first run")
    eq(store.delete_container(misc.id), False, "the seeded Misc cannot be deleted")
    conn.close()
check("first run: empty except one protected, active Misc", _first_run)


# ---- 2. full round-trip ----

def _round_trip():
    s = Store()
    misc = s.add_container("Misc", protected=True)
    work = s.add_container("Work")
    side = s.add_container("Side", Lifecycle.PLANNED)
    health = s.add_container("Health")
    t1 = s.add_task("Email", work.id, "Ready")
    s.add_task("Deck", work.id, "Ready")
    s.add_task("Roadmap", work.id, "Soon")
    s.add_task("Logo", side.id, "Ready")
    s.add_task("Renew passport", misc.id, "Ready")
    r1 = s.add_routine("Inbox", work.id, [0, 1, 2, 3, 4], "09:00", 0.5)
    r2 = s.add_routine("Run", health.id, [0, 2, 4], "07:00", 0.75)
    r3 = s.add_routine("Stretch", health.id, [0, 1, 2, 3, 4, 5, 6], None, 0.25)
    r4 = s.add_routine("Old habit", health.id, [1, 3])
    s.archive_routine(r4.id)
    s.sync_day(MON)
    done_item = next(x for x in s.day_items(kMON) if x.source_type == "task" and x.source_id == t1.id)
    s.set_done(done_item, True)
    s.add_one_off(r2.id, kMON)              # deliberate one-off alongside its scheduled slot
    s.log_routine_on(r1.id, kTUE, True)     # fills Tuesday's scheduled slot
    s.reorder_container(health.id, Lifecycle.ACTIVE, 0)
    s.reorder_routine(r3.id, health.id, 0)

    before = snapshot(s)
    max_id_before = s._next_id - 1

    path = _tmp()
    conn, _ = open_database(path)   # creates schema (+ throwaway Misc)
    save(s, conn)                   # full rewrite with our data
    conn.close()

    conn2, s2 = open_database(path)  # reopen with a fresh connection
    after = snapshot(s2)

    eq(after, before, "round-trip preserves the full store exactly")
    eq(s2._next_id, max_id_before + 1, "id generation resumes above the max persisted id")
    new = s2.add_task("brand new", misc.id, "Ready")
    if new.id <= max_id_before:
        raise AssertionError("a new id must not collide with persisted ids")

    # live-reference behaviour still holds after load
    loaded_t1 = s2.tasks[t1.id]
    loaded_t1.name = "Emailed Dana"
    past = next(x for x in s2.day_items(kMON) if x.source_type == "task" and x.source_id == t1.id)
    eq(s2.item_name(past), "Emailed Dana", "renaming a task after load updates its past record")
    loaded_t1.container_id = misc.id
    eq(s2.item_container(past), "Misc", "re-filing after load updates the past record's container")
    conn2.close()
check("round-trip: save then reload reproduces the store, ids resume, references stay live", _round_trip)


# ---- 3. real version upgrade with legacy data preserved ----

def _build_v1_db(path, rows):
    conn = sqlite3.connect(path)
    _apply_migrations(conn, up_to=1)   # baseline schema only; no `protected` column
    for sql, params in rows:
        conn.execute(sql, params)
    conn.commit()
    conn.close()


def _migration_preserves_data():
    path = _tmp("legacy.db")
    _build_v1_db(path, [
        ("INSERT INTO containers(id,name,status,description,ord) VALUES(?,?,?,?,?)", (1, "Work", "active", "", 0)),
        ("INSERT INTO containers(id,name,status,description,ord) VALUES(?,?,?,?,?)", (2, "Home", "active", "", 1)),
        ("INSERT INTO tasks(id,name,container_id,col,position,completed) VALUES(?,?,?,?,?,?)", (3, "Fix sink", 2, "Ready", 0, 0)),
        ("INSERT INTO routines(id,name,container_id,days_of_week,time,duration_hours,active,archived,ord) VALUES(?,?,?,?,?,?,?,?,?)",
         (4, "Run", 1, "[0, 2, 4]", "07:00", 0.75, 1, 0, 0)),
        ("INSERT INTO day_log(id,date_key,source_type,source_id,done,one_off,seq) VALUES(?,?,?,?,?,?,?)", (5, kMON, "task", 3, 0, 0, 0)),
    ])

    # a newer build opens the older file
    conn, store = open_database(path)
    eq(_get_version(conn), SCHEMA_VERSION, "older file is upgraded to the current version")

    # legacy data is intact
    eq(store.containers[1].name, "Work", "legacy container preserved")
    eq(store.containers[2].name, "Home", "legacy container preserved")
    eq(store.tasks[3].name, "Fix sink", "legacy task preserved")
    eq(store.tasks[3].container_id, 2, "legacy task's container preserved")
    eq(store.routines[4].name, "Run", "legacy routine preserved")
    eq(store.routines[4].days_of_week, [0, 2, 4], "legacy routine schedule preserved")
    eq(len(store.day_items(kMON)), 1, "legacy day-log entry preserved")

    # the v2 addition took effect
    protected = [c for c in store.containers.values() if c.protected]
    eq(len(protected), 1, "exactly one protected container after upgrade")
    eq(protected[0].name, "Misc", "the protected container is Misc")
    eq(len(store.containers), 3, "Misc was added; Work and Home remain")
    conn.close()
check("migration v1->v2 upgrades an older file with no data loss and adds protected Misc", _migration_preserves_data)


# ---- 4. migration promotes an existing Misc instead of duplicating ----

def _migration_promotes_existing_misc():
    path = _tmp("hasmisc.db")
    _build_v1_db(path, [
        ("INSERT INTO containers(id,name,status,description,ord) VALUES(?,?,?,?,?)", (1, "Work", "active", "", 0)),
        ("INSERT INTO containers(id,name,status,description,ord) VALUES(?,?,?,?,?)", (2, "Misc", "active", "", 1)),
        ("INSERT INTO containers(id,name,status,description,ord) VALUES(?,?,?,?,?)", (3, "Home", "active", "", 2)),
    ])
    conn, store = open_database(path)
    miscs = [c for c in store.containers.values() if c.name == "Misc"]
    eq(len(miscs), 1, "no duplicate Misc is created")
    eq(miscs[0].id, 2, "the existing Misc is the one kept")
    eq(miscs[0].protected, True, "the existing Misc is promoted to protected")
    eq(len(store.containers), 3, "container count is unchanged")
    conn.close()
check("migration promotes an existing 'Misc' rather than creating a duplicate", _migration_promotes_existing_misc)


print("")
print(f"{_fails} failed" if _fails else "all checks passed")
import sys
sys.exit(1 if _fails else 0)
