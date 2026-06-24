"""SQLite persistence + schema migrations for the Custodian engine.

Design choices:
  - The database mirrors the in-memory Store exactly. `save` does a full
    transactional rewrite of the data tables. For a personal backlog (tens to a
    few hundred items) this is microseconds and is the least bug-prone option:
    the file is always an exact image of the engine after each operation.
  - Schema evolution is a migration CHAIN. Version N means "N migrations
    applied." A fresh database starts at 0 and runs every migration up to
    SCHEMA_VERSION, so the create path and the upgrade path are the same code,
    and the migration chain is exercised on every fresh install.
  - This is what lets a newer build open an older file without data loss: it
    reads the stored version and runs only the migrations the file is missing.

Migration history:
  v1  baseline schema (the preview's model, persisted)
  v2  add `protected` to containers, and guarantee a protected "Misc" exists
      (promote an existing one named "Misc", else create it). This is the
      deliberate addition on top of the preview; it is a migration so that any
      pre-protected file upgrades cleanly, and so the first-run empty state
      (exactly one protected Misc) falls out of the chain.

The display version string (e.g. "0.01.00a") is a separate, human-facing thing
owned by the app UI; this integer schema_version is the only thing that drives
migrations.
"""

import json
import sqlite3
from engine import Store, Container, Task, Routine, DayItem


# ---------- meta / versioning ----------

def _ensure_meta(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")


def _get_version(conn) -> int:
    _ensure_meta(conn)
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return int(row[0]) if row else 0


def _set_version(conn, v: int):
    conn.execute(
        "INSERT INTO meta(key,value) VALUES('schema_version',?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(v),),
    )


# ---------- migrations ----------

def _migration_to_v1(conn):
    conn.execute("""
        CREATE TABLE containers (
            id          INTEGER PRIMARY KEY,
            name        TEXT    NOT NULL,
            status      TEXT    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            ord         INTEGER NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE tasks (
            id           INTEGER PRIMARY KEY,
            name         TEXT    NOT NULL,
            container_id INTEGER NOT NULL,
            col          TEXT    NOT NULL,
            position     INTEGER NOT NULL,
            completed    INTEGER NOT NULL DEFAULT 0
        )""")
    conn.execute("""
        CREATE TABLE routines (
            id             INTEGER PRIMARY KEY,
            name           TEXT    NOT NULL,
            container_id   INTEGER NOT NULL,
            days_of_week   TEXT    NOT NULL DEFAULT '[]',
            time           TEXT,
            duration_hours REAL,
            active         INTEGER NOT NULL DEFAULT 1,
            archived       INTEGER NOT NULL DEFAULT 0,
            ord            INTEGER NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE day_log (
            id          INTEGER PRIMARY KEY,
            date_key    TEXT    NOT NULL,
            source_type TEXT    NOT NULL,
            source_id   INTEGER NOT NULL,
            done        INTEGER NOT NULL DEFAULT 0,
            one_off     INTEGER NOT NULL DEFAULT 0,
            seq         INTEGER NOT NULL
        )""")
    conn.execute("CREATE INDEX idx_daylog_date ON day_log(date_key, seq)")


def _migration_to_v2(conn):
    conn.execute("ALTER TABLE containers ADD COLUMN protected INTEGER NOT NULL DEFAULT 0")
    # Guarantee a protected Misc so the project always keeps a home for tasks.
    has_protected = conn.execute("SELECT 1 FROM containers WHERE protected=1 LIMIT 1").fetchone()
    if not has_protected:
        existing_misc = conn.execute(
            "SELECT id FROM containers WHERE name='Misc' ORDER BY id LIMIT 1"
        ).fetchone()
        if existing_misc:
            conn.execute("UPDATE containers SET protected=1 WHERE id=?", (existing_misc[0],))
        else:
            row = conn.execute("SELECT COALESCE(MAX(ord),-1)+1 FROM containers").fetchone()
            next_ord = row[0]
            conn.execute(
                "INSERT INTO containers(name,status,description,ord,protected) "
                "VALUES('Misc','active','',?,1)",
                (next_ord,),
            )


# Index i applies the upgrade to version i+1.
_MIGRATIONS = [_migration_to_v1, _migration_to_v2]
SCHEMA_VERSION = len(_MIGRATIONS)


def _apply_migrations(conn, up_to: int = None):
    target = SCHEMA_VERSION if up_to is None else up_to
    current = _get_version(conn)
    for i in range(current, target):
        _MIGRATIONS[i](conn)
        _set_version(conn, i + 1)
    conn.commit()


# ---------- load ----------

def load(conn) -> Store:
    conn.row_factory = sqlite3.Row
    store = Store()

    for r in conn.execute("SELECT * FROM containers ORDER BY ord, id"):
        store.containers[r["id"]] = Container(
            id=r["id"], name=r["name"], status=r["status"],
            description=r["description"], protected=bool(r["protected"]),
        )
        store.container_order.append(r["id"])

    for r in conn.execute("SELECT * FROM tasks"):
        store.tasks[r["id"]] = Task(
            id=r["id"], name=r["name"], container_id=r["container_id"],
            column=r["col"], position=r["position"], completed=bool(r["completed"]),
        )

    for r in conn.execute("SELECT * FROM routines ORDER BY ord, id"):
        store.routines[r["id"]] = Routine(
            id=r["id"], name=r["name"], container_id=r["container_id"],
            days_of_week=json.loads(r["days_of_week"]), time=r["time"],
            duration_hours=r["duration_hours"], active=bool(r["active"]),
            archived=bool(r["archived"]),
        )
        store.routine_order.append(r["id"])

    for r in conn.execute("SELECT * FROM day_log ORDER BY date_key, seq, id"):
        store.day_log.setdefault(r["date_key"], []).append(DayItem(
            id=r["id"], source_type=r["source_type"], source_id=r["source_id"],
            done=bool(r["done"]), one_off=bool(r["one_off"]),
        ))

    # resume id generation above every persisted id
    max_id = 0
    for d in (store.containers, store.tasks, store.routines):
        if d:
            max_id = max(max_id, max(d.keys()))
    for items in store.day_log.values():
        for it in items:
            max_id = max(max_id, it.id)
    store._next_id = max_id + 1
    return store


# ---------- save (full transactional rewrite) ----------

def save(store: Store, conn):
    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        for tbl in ("containers", "tasks", "routines", "day_log"):
            cur.execute(f"DELETE FROM {tbl}")

        ordered_cids = store.container_order + [cid for cid in store.containers
                                                if cid not in store.container_order]
        for ordn, cid in enumerate(ordered_cids):
            c = store.containers[cid]
            cur.execute(
                "INSERT INTO containers(id,name,status,description,ord,protected) "
                "VALUES(?,?,?,?,?,?)",
                (c.id, c.name, c.status, c.description, ordn, int(c.protected)),
            )

        for t in store.tasks.values():
            cur.execute(
                "INSERT INTO tasks(id,name,container_id,col,position,completed) "
                "VALUES(?,?,?,?,?,?)",
                (t.id, t.name, t.container_id, t.column, t.position, int(t.completed)),
            )

        ordered_rids = store.routine_order + [rid for rid in store.routines
                                              if rid not in store.routine_order]
        for ordn, rid in enumerate(ordered_rids):
            r = store.routines[rid]
            cur.execute(
                "INSERT INTO routines(id,name,container_id,days_of_week,time,"
                "duration_hours,active,archived,ord) VALUES(?,?,?,?,?,?,?,?,?)",
                (r.id, r.name, r.container_id, json.dumps(r.days_of_week), r.time,
                 r.duration_hours, int(r.active), int(r.archived), ordn),
            )

        for date_key, items in store.day_log.items():
            for seq, it in enumerate(items):
                cur.execute(
                    "INSERT INTO day_log(id,date_key,source_type,source_id,done,one_off,seq) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (it.id, date_key, it.source_type, it.source_id,
                     int(it.done), int(it.one_off), seq),
                )

        _set_version(conn, SCHEMA_VERSION)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------- entry point ----------

def open_database(path: str):
    """Open (or create) a database at `path`, run any pending migrations, and
    return (conn, store). A brand-new file ends up with exactly one protected
    Misc container, produced by the migration chain.

    check_same_thread=False: pywebview dispatches bridge calls on threads other
    than the one that opens the connection. The Api serializes every call with a
    lock, so the connection is only ever touched by one thread at a time."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _apply_migrations(conn)
    store = load(conn)
    return conn, store
