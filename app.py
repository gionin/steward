"""Steward desktop app: the pywebview bridge and entry point.

Architecture: Python owns the engine (engine.py) and the SQLite state
(storage.py). The web UI renders from a snapshot and sends one command per user
action across the pywebview JS bridge. Every command mutates the engine, saves
to SQLite, and returns the fresh snapshot. The UI runs no engine logic.

The snapshot uses the field names the existing UI already reads (camelCase), so
the view layer barely changes.

What is verified vs asserted (per the collaboration charter):
  - The Api command/query logic and the snapshot shape are covered by
    test_api.py, which runs headlessly here.
  - Launching the window, the JS bridge end to end, and packaging cannot run in
    the build sandbox and are confirmed on the user's machine.
"""

import os
import sys
import threading
import functools
from pathlib import Path

from engine import Store, Lifecycle, COLUMNS, WEEKDAYS, key_of
import storage

# Human-facing display version (separate from the DB's integer schema_version).
# Trailing letter steps a->b->c for bug-fix attempts; resets when numbers move.
APP_VERSION = "0.01.00a"


def _date_from_key(k: str):
    from datetime import date
    y, m, d = (int(x) for x in k.split("-"))
    return date(y, m, d)


class Api:
    """Exposed to JavaScript as window.pywebview.api. Every public method is
    callable from the UI. Commands return a snapshot; queries return a value."""

    def __init__(self, conn, store: Store):
        self.conn = conn
        self.store = store
        self._lock = threading.RLock()
        # Wrap every public method so each bridge call runs under one lock.
        # pywebview may dispatch calls on separate threads; this keeps the
        # engine mutation and the SQLite write for one command atomic.
        for name, attr in list(type(self).__dict__.items()):
            if not name.startswith("_") and callable(attr):
                setattr(self, name, self._locked(getattr(self, name)))

    def _locked(self, fn):
        @functools.wraps(fn)
        def wrap(*a, **k):
            with self._lock:
                return fn(*a, **k)
        return wrap

    # ----- internal helpers -----

    def _misc_id(self):
        for c in self.store.containers.values():
            if c.protected:
                return c.id
        # Fallback: first container, or None. (Migration guarantees a protected one.)
        return self.store.container_order[0] if self.store.container_order else None

    def _find_item(self, item_id):
        """Find a day item by id across every day. Returns (item, date_key)."""
        item_id = int(item_id)
        for k, items in self.store.day_log.items():
            for it in items:
                if it.id == item_id:
                    return it, k
        return None, None

    def _find_item_in(self, date_key, item_id):
        item_id = int(item_id)
        for it in self.store.day_log.get(date_key, []):
            if it.id == item_id:
                return it
        return None

    def _save(self):
        storage.save(self.store, self.conn)

    def _db_file(self):
        """Absolute path of the live database file, or '' for an in-memory DB."""
        try:
            for _seq, name, fname in self.conn.execute("PRAGMA database_list"):
                if name == "main":
                    return fname or ""
        except Exception:
            pass
        return ""

    # ----- snapshot -----

    def _resolve_item(self, it):
        return {
            "id": it.id,
            "sourceType": it.source_type,
            "sourceId": it.source_id,
            "name": self.store.item_name(it),
            "container": self.store.item_container(it),
            "containerId": self.store.item_container_id(it),
            "done": it.done,
            "oneOff": it.one_off,
            "recurring": it.source_type == "routine",
        }

    def _future_preview(self, view_key):
        s = self.store
        out = []
        # First: persisted items (manually scheduled tasks + one-off routines)
        for it in s.day_items(view_key):
            out.append({**self._resolve_item(it), "scheduled": True})
        # Then: routine previews not already in the persisted list
        persisted_ids = {(it.source_type, it.source_id) for it in s.day_items(view_key)}
        for (_st, sid) in s.compute_routine_draft(_date_from_key(view_key)):
            if ("routine", sid) in persisted_ids:
                continue
            r = s.routines.get(sid)
            if not r:
                continue
            out.append({
                "id": "preview-%d" % sid, "sourceType": "routine", "sourceId": sid,
                "name": r.name, "container": s.container_name(r.container_id),
                "containerId": r.container_id, "done": False, "oneOff": False,
                "recurring": True, "preview": True,
            })
        return out

    def _snapshot(self, today_key, viewed_key=None):
        s = self.store
        live = today_key                 # the real current day (the client sends it)
        view = viewed_key or today_key   # the day the Today lens is showing
        s.promote_due_tasks(live)          # promote any tasks whose ready_date has arrived
        s.sync_day(_date_from_key(live))  # only the live day ever re-syncs
        self._save()                      # persist the freshly synced live day

        is_future = view > live
        is_past = view < live
        if is_future:
            today = self._future_preview(view)     # routines-only, transient
        else:
            # live or past: render that day's stored record (past is never re-derived)
            today = [self._resolve_item(it) for it in s.day_items(view)]
        held = len([t for t in s.tasks.values()
                    if not t.completed and t.column != "Ready" and s.is_active(t.container_id)])

        columns = {}
        for col in COLUMNS:
            columns[col] = [{
                "id": t.id, "name": t.name, "containerId": t.container_id,
                "containerName": s.container_name(t.container_id),
                "containerActive": s.is_active(t.container_id),
                "column": t.column, "position": t.position, "completed": t.completed,
                "logCount": s.task_log_count(t.id),
            } for t in s.column_tasks(col)]

        containers = []
        for cid in s.container_order:
            c = s.containers[cid]
            containers.append({
                "id": c.id, "name": c.name, "status": c.status,
                "description": c.description, "protected": c.protected,
                "taskCount": len([t for t in s.tasks.values()
                                  if t.container_id == cid and not t.completed]),
                "routineCount": len([r for r in s.routines.values()
                                     if r.container_id == cid and not r.archived]),
            })

        routines = []
        for rid in s.routine_order:
            r = s.routines[rid]
            routines.append({
                "id": r.id, "name": r.name, "containerId": r.container_id,
                "containerName": s.container_name(r.container_id),
                "daysOfWeek": list(r.days_of_week), "time": r.time,
                "durationHours": r.duration_hours, "active": r.active,
                "archived": r.archived, "hoursPerWeek": s.hours_per_week(r),
                "logCount": s.routine_log_count(r.id),
            })

        hist_keys = sorted([k for k in s.day_log
                            if k < live and s.day_log[k]], reverse=True)
        history = [{
            "dateKey": k,
            "entries": [self._resolve_item(it) for it in s.day_log[k]],
        } for k in hist_keys]

        tasks_all = [{"id": t.id, "name": t.name, "containerId": t.container_id,
                      "completed": t.completed, "readyDate": t.ready_date} for t in s.tasks.values()]

        return {
            "version": APP_VERSION,
            "todayKey": view,
            "liveKey": live,
            "isLive": not is_future and not is_past,
            "isPast": is_past,
            "isFuture": is_future,
            "miscId": self._misc_id(),
            "today": today,
            "heldCount": held,
            "columns": columns,
            "containers": containers,
            "routines": routines,
            "history": history,
            "tasksAll": tasks_all,
        }

    # ----- queries -----

    def get_state(self, today_key, viewed_key=None):
        return self._snapshot(today_key, viewed_key)

    def backfill_day(self, today_key, viewed_key):
        """Reconstruct a skipped past day by pulling in the routines that were
        scheduled then, so the user can record what actually happened. Routines
        only; tasks are never projected backward."""
        lst = self.store._day(viewed_key)
        present = {(it.source_type, it.source_id) for it in lst}
        for (st, sid) in self.store.compute_routine_draft(_date_from_key(viewed_key)):
            if (st, sid) not in present:
                lst.append(self.store.new_day_item(st, sid, False, False))
        self._save()
        return self._snapshot(today_key, viewed_key)

    def task_done_key(self, task_id):
        return self.store.task_done_key(int(task_id))

    def context_export(self, today_key):
        return self._serialize(today_key)

    # ----- Today commands -----

    def capture_task(self, name, today_key):
        name = (name or "").strip()
        if name:
            self.store.add_task(name, self._misc_id(), "Ready")
        return self._snapshot(today_key)

    def toggle_today_item(self, item_id, today_key, viewed_key=None):
        day = viewed_key or today_key
        it = self._find_item_in(day, item_id)
        if it:
            self.store.set_done(it, not it.done)
        return self._snapshot(today_key, viewed_key)

    def reorder_today_item(self, item_id, idx, today_key, viewed_key=None):
        items = self.store.day_log.get(viewed_key or today_key, [])
        item_id = int(item_id)
        pos = next((i for i, x in enumerate(items) if x.id == item_id), -1)
        if pos >= 0:
            it = items.pop(pos)
            idx = max(0, min(int(idx), len(items)))
            items.insert(idx, it)
        return self._snapshot(today_key, viewed_key)

    # ----- generator rename / refile (Today + History) -----

    def rename_item(self, item_id, name, today_key, viewed_key=None):
        name = (name or "").strip()
        it, _ = self._find_item(item_id)
        if it and name:
            g = self.store.item_gen(it)
            if g:
                g.name = name
        return self._snapshot(today_key, viewed_key)

    def set_item_container(self, item_id, container_id, today_key, viewed_key=None):
        it, _ = self._find_item(item_id)
        if it:
            g = self.store.item_gen(it)
            if g:
                g.container_id = int(container_id)
        return self._snapshot(today_key, viewed_key)

    # ----- Tasks board -----

    def add_task(self, name, container_id, column, today_key):
        name = (name or "").strip()
        if name:
            self.store.add_task(name, int(container_id), column)
        return self._snapshot(today_key)

    def rename_task(self, task_id, name, today_key):
        name = (name or "").strip()
        t = self.store.tasks.get(int(task_id))
        if t and name:
            t.name = name
        return self._snapshot(today_key)

    def set_task_container(self, task_id, container_id, today_key):
        t = self.store.tasks.get(int(task_id))
        if t:
            t.container_id = int(container_id)
        return self._snapshot(today_key)

    def move_task(self, task_id, column, position, today_key):
        self.store.move_task(task_id, column, position)
        return self._snapshot(today_key)

    def delete_task(self, task_id, today_key):
        self.store.delete_task(int(task_id))
        return self._snapshot(today_key)

    def complete_task_today(self, task_id, today_key):
        self.store.complete_task_today(task_id, _date_from_key(today_key))
        return self._snapshot(today_key)

    # ----- Routines -----

    def add_routine(self, name, container_id, today_key):
        name = (name or "").strip()
        if name:
            self.store.add_routine(name, int(container_id), [], None, None, True)
        return self._snapshot(today_key)

    def rename_routine(self, routine_id, name, today_key):
        name = (name or "").strip()
        r = self.store.routines.get(int(routine_id))
        if r and name:
            r.name = name
        return self._snapshot(today_key)

    def set_routine_active(self, routine_id, active, today_key):
        r = self.store.routines.get(int(routine_id))
        if r:
            r.active = bool(active)
        return self._snapshot(today_key)

    def toggle_routine_day(self, routine_id, day, today_key):
        r = self.store.routines.get(int(routine_id))
        if r:
            day = int(day)
            if day in r.days_of_week:
                r.days_of_week.remove(day)
            else:
                r.days_of_week.append(day)
            r.days_of_week.sort()
        return self._snapshot(today_key)

    def set_routine_time(self, routine_id, time, today_key):
        r = self.store.routines.get(int(routine_id))
        if r:
            r.time = time or None
        return self._snapshot(today_key)

    def set_routine_duration(self, routine_id, hours, today_key):
        r = self.store.routines.get(int(routine_id))
        if r:
            r.duration_hours = None if hours in (None, "") else float(hours)
        return self._snapshot(today_key)

    def archive_routine(self, routine_id, today_key):
        self.store.archive_routine(int(routine_id))
        return self._snapshot(today_key)

    def unarchive_routine(self, routine_id, today_key):
        self.store.unarchive_routine(int(routine_id))
        return self._snapshot(today_key)

    def delete_routine(self, routine_id, today_key):
        self.store.delete_routine(int(routine_id))
        return self._snapshot(today_key)

    def reorder_routine(self, routine_id, container_id, idx, today_key):
        self.store.reorder_routine(routine_id, container_id, int(idx))
        return self._snapshot(today_key)

    def add_one_off(self, routine_id, today_key, date_key=None):
        target = date_key or today_key
        self.store.add_one_off(int(routine_id), target)
        return self._snapshot(today_key)

    def add_task_to_date(self, name, container_id, date_key, today_key):
        name = (name or "").strip()
        if not name:
            return self._snapshot(today_key)
        t = self.store.add_task(name, int(container_id), "Soon")
        t.ready_date = date_key
        self.store._day(date_key).append(self.store.new_day_item("task", t.id, False, True))
        return self._snapshot(today_key, date_key)

    def schedule_task_on_date(self, task_id, date_key, today_key):
        t = self.store.tasks.get(int(task_id))
        if not t:
            return {"conflict": None, "state": self._snapshot(today_key, date_key)}
        if t.ready_date and t.ready_date != date_key:
            return {"conflict": t.ready_date, "state": self._snapshot(today_key, date_key)}
        # No conflict: schedule it
        if t.column == "Ready":
            self.store.move_task(t.id, "Soon")
        t.ready_date = date_key
        day = self.store._day(date_key)
        if not any(it.source_type == "task" and it.source_id == t.id for it in day):
            day.append(self.store.new_day_item("task", t.id, False, True))
        return {"conflict": None, "state": self._snapshot(today_key, date_key)}

    def confirm_schedule_task(self, task_id, date_key, keep_old, today_key):
        t = self.store.tasks.get(int(task_id))
        if not t:
            return self._snapshot(today_key, date_key)
        old_date = t.ready_date
        if not keep_old and old_date:
            # remove old DayItem
            old_day = self.store.day_log.get(old_date, [])
            self.store.day_log[old_date] = [it for it in old_day
                if not (it.source_type == "task" and it.source_id == t.id)]
        # schedule on new date
        if t.column == "Ready":
            self.store.move_task(t.id, "Soon")
        t.ready_date = min(old_date, date_key) if keep_old and old_date else date_key
        day = self.store._day(date_key)
        if not any(it.source_type == "task" and it.source_id == t.id for it in day):
            day.append(self.store.new_day_item("task", t.id, False, True))
        return self._snapshot(today_key, date_key)

    # ----- Containers -----

    def add_container(self, name, today_key, status=None):
        name = (name or "").strip()
        if name:
            if status:
                self.store.add_container(name, status)
            else:
                self.store.add_container(name)
        return self._snapshot(today_key)

    def set_container_status(self, container_id, status, today_key):
        c = self.store.containers.get(int(container_id))
        if c:
            c.status = status
        return self._snapshot(today_key)

    def reorder_container(self, container_id, status, idx, today_key):
        c = self.store.containers.get(int(container_id))
        if c and c.status != status:
            c.status = status
        self.store.reorder_container(container_id, status, int(idx))
        return self._snapshot(today_key)

    def delete_container(self, container_id, today_key):
        ok = self.store.delete_container(int(container_id))
        return {"ok": ok, "state": self._snapshot(today_key)}

    def rename_container(self, container_id, name, today_key):
        name = (name or "").strip()
        c = self.store.containers.get(int(container_id))
        if c and name:
            c.name = name
        return self._snapshot(today_key)

    # ----- data location / backup (item 16) -----

    def data_location(self):
        """Where the live SQLite state lives, for the Settings panel."""
        path = self._db_file()
        return {"dbPath": path, "folder": os.path.dirname(path) if path else ""}

    def backup_database(self):
        """Write a consistent, timestamped copy of the database beside it, using
        SQLite's own backup so it is safe even mid-write. Returns the new path."""
        import sqlite3
        from datetime import datetime
        src = self._db_file()
        if not src:
            return {"ok": False, "error": "no database file"}
        dest = os.path.join(os.path.dirname(src),
                            "steward-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".db")
        dst = sqlite3.connect(dest)
        try:
            self.conn.backup(dst)
        finally:
            dst.close()
        return {"ok": True, "path": dest}

    def open_data_folder(self):
        """Open the data folder in the OS file manager (best effort)."""
        folder = os.path.dirname(self._db_file())
        if not folder or not os.path.isdir(folder):
            return {"ok": False}
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", folder])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            return {"ok": False}
        return {"ok": True, "folder": folder}

    # ----- History -----

    def history_toggle(self, item_id, date_key, today_key):
        """Routine toggle, or task uncheck. (Checking a task uses mark_task_done.)"""
        it = self._find_item_in(date_key, item_id)
        if it:
            self.store.set_done(it, not it.done)
        return self._snapshot(today_key)

    def mark_task_done(self, item_id, date_key, today_key):
        it = self._find_item_in(date_key, item_id)
        if it:
            self.store.mark_task_done_on(it, date_key)
        return self._snapshot(today_key)

    def move_item(self, item_id, from_key, to_key, today_key):
        it = self._find_item_in(from_key, item_id)
        if it:
            self.store.move_item(it, from_key, to_key)
        return self._snapshot(today_key)

    def move_item_to(self, item_id, from_key, to_key, idx, today_key):
        it = self._find_item_in(from_key, item_id)
        later_conflict = False
        if it:
            self.store.move_item_to(it, from_key, to_key, int(idx))
            if it.source_type == "task" and it.done:
                later_conflict = any(
                    k > to_key and any(
                        x is not it and x.source_type == "task"
                        and x.source_id == it.source_id and not x.done
                        for x in self.store.day_log[k])
                    for k in self.store.day_log)
        return {"laterConflict": later_conflict, "itemId": int(item_id),
                "toKey": to_key, "state": self._snapshot(today_key)}

    def resolve_later_conflict(self, item_id, to_key, clear_later, today_key):
        it = self._find_item_in(to_key, item_id)
        if it:
            if clear_later:
                self.store.mark_task_done_on(it, to_key)
            else:
                self.store.set_done(it, False)
        return self._snapshot(today_key)

    def remove_item(self, item_id, date_key, today_key):
        it = self._find_item_in(date_key, item_id)
        if it:
            self.store.remove_item(it, date_key)
        return self._snapshot(today_key)

    def log_activity(self, kind, is_new, name, container_id, target_id, date_key, done,
                     today_key, force=False):
        s = self.store
        if kind == "task":
            if is_new:
                name = (name or "").strip()
                if not name:
                    return {"ok": False, "state": self._snapshot(today_key)}
                cid = int(container_id)
                if done:
                    s.log_task_done(name, cid, date_key)
                else:
                    t = s.add_task(name, cid, "Ready")
                    s.day_log.setdefault(date_key, []).append(s.new_day_item("task", t.id, False, False))
            else:
                tid = int(target_id)
                if done:
                    s.log_existing_task_done(tid, date_key)
                else:
                    dd = s.task_done_key(tid)
                    if dd and dd < date_key and not force:
                        return {"ok": False, "conflict": "taskDoneBefore",
                                "doneDate": dd, "taskName": s.tasks[tid].name,
                                "state": self._snapshot(today_key)}
                    if dd and dd < date_key and force:
                        for k in s.day_log:
                            for x in s.day_log[k]:
                                if x.source_type == "task" and x.source_id == tid and x.done:
                                    s.set_done(x, False)
                    lst = s.day_log.setdefault(date_key, [])
                    ex = next((x for x in lst if x.source_type == "task" and x.source_id == tid), None)
                    if ex:
                        s.set_done(ex, False)
                    else:
                        lst.append(s.new_day_item("task", tid, False, False))
        else:  # routine
            if is_new:
                name = (name or "").strip()
                if not name:
                    return {"ok": False, "state": self._snapshot(today_key)}
                r = s.add_routine(name, int(container_id), [], None, None, True)
                s.day_log.setdefault(date_key, []).append(s.new_day_item("routine", r.id, bool(done), False))
            else:
                rid = int(target_id)
                s.log_routine_on(rid, date_key, bool(done))
        return {"ok": True, "state": self._snapshot(today_key)}

    # ----- context export -----

    def _serialize(self, today_key):
        s = self.store
        from datetime import date

        def dmy(k):
            y, m, d = k.split("-")
            return f"{d}/{m}/{y}"

        d = _date_from_key(today_key)
        out = "STEWARD - STATE EXPORT\n"
        out += f"Generated for: {WEEKDAYS[d.weekday()]} {dmy(today_key)}\n\nTODAY'S SLICE\n"
        items = s.day_items(today_key)
        if items:
            for it in items:
                flags = ""
                if it.source_type == "routine":
                    flags += "  {routine}"
                if it.one_off and it.source_type == "routine":
                    flags += " {one-off}"
                out += f"  [{'x' if it.done else ' '}] {s.item_name(it)}  ({s.item_container(it)}){flags}\n"
        else:
            out += "  (nothing drafted)\n"
        out += "\nACTIVE CONTAINERS\n"
        for cid in s.container_order:
            c = s.containers[cid]
            if c.status != "active":
                continue
            out += f"  {c.name}\n"
            for col in reversed(COLUMNS):
                ts = [t for t in s.column_tasks(col) if t.container_id == cid]
                if ts:
                    out += f"    {col}: {'; '.join(t.name for t in ts)}\n"
        aside = [s.containers[cid] for cid in s.container_order if s.containers[cid].status != "active"]
        if aside:
            out += "\nSET ASIDE: " + ", ".join(f"{c.name} ({c.status})" for c in aside) + "\n"
        out += "\nRECENT DAYS (done / planned)\n"
        keys = sorted([k for k in s.day_log if k < today_key and s.day_log[k]], reverse=True)[:7]
        if keys:
            for k in keys:
                its = s.day_log[k]
                done = len([i for i in its if i.done])
                out += f"  {dmy(k)}: {done}/{len(its)} done\n"
        else:
            out += "  (no past days yet)\n"
        return out


# --------------------------------------------------------------------------
# Entry point (asserted; confirmed on the user's machine)
# --------------------------------------------------------------------------

def _steward_home():
    base = Path(os.environ.get("STEWARD_HOME", Path.home() / ".steward"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _db_path():
    return str(_steward_home() / "steward.db")


def _setup_logging():
    import logging
    logfile = _steward_home() / "steward.log"
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s")
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = [fh, sh]
    return logfile


def main():
    import logging
    logfile = _setup_logging()
    log = logging.getLogger("steward")
    log.info("=" * 60)
    log.info("Steward %s starting", APP_VERSION)
    log.info("Log file: %s", logfile)
    log.info("Python: %s", sys.version.replace("\n", " "))

    try:
        import webview  # lazy so the tests need no GUI dependency
        log.info("pywebview %s loaded", getattr(webview, "__version__", "?"))
    except Exception:
        log.exception("Could not import pywebview. Run setup first, "
                      "or: python -m pip install pywebview")
        raise

    try:
        dbp = _db_path()
        log.info("Opening database: %s", dbp)
        conn, store = storage.open_database(dbp)
        log.info("Database ready (%d container(s))", len(store.containers))

        here = os.path.dirname(os.path.abspath(__file__))
        index = os.path.join(here, "index.html")
        if not os.path.exists(index):
            log.error("index.html is not next to app.py. Expected at: %s", index)
            log.error("Put all the files in the same folder and try again.")
            raise FileNotFoundError(index)
        log.info("UI file: %s", index)

        api = Api(conn, store)
        debug = os.environ.get("STEWARD_DEBUG") == "1"
        log.info("Creating window (debug=%s)", debug)
        webview.create_window(
            "Steward", url=index, js_api=api,
            width=1180, height=820, min_size=(900, 600),
        )
        log.info("Opening window. Close it to quit.")
        webview.start(debug=debug)
        log.info("Window closed. Goodbye.")
        conn.close()
    except Exception:
        log.exception("Steward failed to start")
        raise


if __name__ == "__main__":
    main()
