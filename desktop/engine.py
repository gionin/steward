"""Steward / Trusted-Offload Assistant - deterministic core engine (Python).

Ported faithfully from the authoritative engine embedded in preview_12.html.
This is a direct behavioural port; it does not redesign the model.

Key ideas (mirrored from the preview):
  - A day record is a list of *references* (DayItem), not copies. Names and
    containers are read live off the referenced generator, so renaming or
    re-filing a generator propagates to every past record at once.
  - Task.completed is a CACHE: true iff some day-item marks it done. Completed
    tasks are hidden from the board but persist (identity + container intact).
  - A routine has two distinct off-states: active (toggle) and archived
    (permanent).
  - The store owns dayLog for every date. The current date is the one the UI
    keeps synced via sync_day; past dates are static, edited only by explicit
    history operations.
  - Scheduled occurrences are DERIVED (re-synced). One-offs / ad-hoc logs are
    STICKY (one_off=True): they ignore schedule and survive toggles/set-aside.
  - Untimed routines in the daily draft are ordered by the manual routine_order
    (NOT alphabetically; this is the behaviour the standalone engine.mjs lacked).
  - Containers may be `protected`: a protected container cannot be deleted, so
    the app always keeps at least one home for tasks (the seeded "Misc").

Weekday convention: Monday=0 .. Sunday=6 (Python date.weekday()).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


# ----- constants -----
class Lifecycle:
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    PLANNED = "planned"


COLUMNS = ["Idea", "Planned", "Soon", "Ready"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Mirror of JS Number.MAX_SAFE_INTEGER: a sentinel large position that sorts
# last, immediately re-collapsed to a contiguous index by reindex().
_END = 2 ** 53 - 1


def key_of(d) -> str:
    """Date -> 'YYYY-MM-DD' key. Accepts date/datetime."""
    if isinstance(d, datetime):
        d = d.date()
    return d.isoformat()


def weekday_mon(d) -> int:
    """Monday=0 .. Sunday=6."""
    if isinstance(d, datetime):
        d = d.date()
    return d.weekday()


def _weekday_of_key(date_key: str) -> int:
    y, m, dd = (int(x) for x in date_key.split("-"))
    return date(y, m, dd).weekday()


# ----- entities -----
@dataclass
class Container:
    id: int
    name: str
    status: str = Lifecycle.ACTIVE
    description: str = ""
    protected: bool = False


@dataclass
class Task:
    id: int
    name: str
    container_id: int
    column: str = "Ready"
    position: int = 0
    completed: bool = False


@dataclass
class Routine:
    id: int
    name: str
    container_id: int
    days_of_week: list = field(default_factory=list)
    time: Optional[str] = None
    duration_hours: Optional[float] = None
    active: bool = True
    archived: bool = False


@dataclass(eq=False)  # identity equality: DayItems are compared/indexed by reference
class DayItem:
    id: int
    source_type: str  # "task" | "routine"
    source_id: int
    done: bool
    one_off: bool


def _index_of(lst, item) -> int:
    """List index by identity (mirrors JS indexOf on object references)."""
    for i, x in enumerate(lst):
        if x is item:
            return i
    return -1


class Store:
    def __init__(self):
        self.containers: dict[int, Container] = {}
        self.tasks: dict[int, Task] = {}
        self.routines: dict[int, Routine] = {}
        self.day_log: dict[str, list[DayItem]] = {}
        self.container_order: list[int] = []
        self.routine_order: list[int] = []
        self._next_id = 1

    # id generation (instance-local; reseeded above max on load)
    def _gen_id(self) -> int:
        v = self._next_id
        self._next_id += 1
        return v

    @staticmethod
    def _coerce_id(x) -> int:
        """Mirror JS Number(id): the DOM hands ids over as strings."""
        return int(x)

    # ---- containers ----
    def add_container(self, name, status=Lifecycle.ACTIVE, description="", protected=False) -> Container:
        c = Container(id=self._gen_id(), name=name, status=status, description=description, protected=protected)
        self.containers[c.id] = c
        self.container_order.append(c.id)
        return c

    def ordered_containers(self, status=None) -> list:
        return [self.containers[i] for i in self.container_order
                if i in self.containers and (status is None or self.containers[i].status == status)]

    def reorder_container(self, drag_id, status, target_idx):
        drag_id = self._coerce_id(drag_id)
        group = [c.id for c in self.ordered_containers(status) if c.id != drag_id]
        arr = [i for i in self.container_order if i != drag_id]
        before_id = group[target_idx] if 0 <= target_idx < len(group) else None
        if before_id is not None:
            insert_at = arr.index(before_id)
        else:
            insert_at = (arr.index(group[-1]) + 1) if group else len(arr)
        arr.insert(insert_at, drag_id)
        self.container_order = arr

    def delete_container(self, cid) -> bool:
        """Delete a container and cascade to its tasks/routines and their log
        entries. Refuses protected containers (returns False), so the app always
        keeps at least one home for tasks."""
        cid = self._coerce_id(cid)
        c = self.containers.get(cid)
        if not c or c.protected:
            return False
        for t in [t for t in self.tasks.values() if t.container_id == cid]:
            self.delete_task(t.id)
        for r in [r for r in self.routines.values() if r.container_id == cid]:
            self.delete_routine(r.id)
        del self.containers[cid]
        self.container_order = [i for i in self.container_order if i != cid]
        return True

    def is_active(self, cid) -> bool:
        c = self.containers.get(cid)
        return bool(c and c.status == Lifecycle.ACTIVE)

    def container_name(self, cid) -> str:
        return self.containers[cid].name if cid in self.containers else "?"

    # ---- tasks (positions unique within a column, across the board) ----
    def column_tasks(self, col) -> list:
        return sorted((t for t in self.tasks.values() if t.column == col and not t.completed),
                      key=lambda t: t.position)

    def next_position(self, col) -> int:
        return len(self.column_tasks(col))

    def reindex(self, col):
        for i, t in enumerate(self.column_tasks(col)):
            t.position = i

    def add_task(self, name, container_id, column="Ready") -> Task:
        t = Task(id=self._gen_id(), name=name, container_id=container_id,
                 column=column, position=self.next_position(column), completed=False)
        self.tasks[t.id] = t
        return t

    def move_task(self, task_id, column, position=None):
        tid = self._coerce_id(task_id)
        t = self.tasks.get(tid)
        if not t:
            return
        old = t.column
        t.column = column
        ordered = [x for x in self.column_tasks(column) if x.id != tid]
        if position is None or position >= len(ordered):
            position = len(ordered)
        ordered.insert(position, t)
        for i, x in enumerate(ordered):
            x.position = i
        if old != column:
            self.reindex(old)

    def delete_task(self, task_id):
        task_id = self._coerce_id(task_id)
        self.tasks.pop(task_id, None)
        for k in self.day_log:
            self.day_log[k] = [it for it in self.day_log[k]
                               if not (it.source_type == "task" and it.source_id == task_id)]

    def task_log_count(self, task_id) -> int:
        task_id = self._coerce_id(task_id)
        return sum(1 for k in self.day_log for it in self.day_log[k]
                   if it.source_type == "task" and it.source_id == task_id)

    # ---- routines ----
    def add_routine(self, name, container_id, days_of_week=None, time=None,
                    duration_hours=None, active=True) -> Routine:
        r = Routine(id=self._gen_id(), name=name, container_id=container_id,
                    days_of_week=list(days_of_week or []), time=time,
                    duration_hours=duration_hours, active=active, archived=False)
        self.routines[r.id] = r
        self.routine_order.append(r.id)
        return r

    def ordered_routines(self, container_id) -> list:
        container_id = self._coerce_id(container_id)
        return [self.routines[i] for i in self.routine_order
                if i in self.routines and not self.routines[i].archived
                and self.routines[i].container_id == container_id]

    def reorder_routine(self, drag_id, container_id, target_idx):
        drag_id = self._coerce_id(drag_id)
        container_id = self._coerce_id(container_id)
        r = self.routines.get(drag_id)
        if not r:
            return
        r.container_id = container_id
        group = [x.id for x in self.ordered_routines(container_id) if x.id != drag_id]
        arr = [i for i in self.routine_order if i != drag_id]
        before_id = group[target_idx] if 0 <= target_idx < len(group) else None
        if before_id is not None:
            insert_at = arr.index(before_id)
        else:
            insert_at = (arr.index(group[-1]) + 1) if group else len(arr)
        arr.insert(insert_at, drag_id)
        self.routine_order = arr

    def hours_per_week(self, r) -> Optional[float]:
        if r.duration_hours is None:
            return None
        return round(r.duration_hours * len(r.days_of_week), 4)

    def routine_due_on(self, r, d) -> bool:
        return weekday_mon(d) in r.days_of_week

    def archive_routine(self, rid):
        rid = self._coerce_id(rid)
        if rid in self.routines:
            self.routines[rid].archived = True

    def unarchive_routine(self, rid):
        rid = self._coerce_id(rid)
        if rid in self.routines:
            self.routines[rid].archived = False

    def delete_routine(self, rid):
        rid = self._coerce_id(rid)
        self.routines.pop(rid, None)
        for k in self.day_log:
            self.day_log[k] = [it for it in self.day_log[k]
                               if not (it.source_type == "routine" and it.source_id == rid)]

    def routine_log_count(self, rid) -> int:
        rid = self._coerce_id(rid)
        return sum(1 for k in self.day_log for it in self.day_log[k]
                   if it.source_type == "routine" and it.source_id == rid)

    # ---- day-item helpers ----
    def new_day_item(self, source_type, source_id, done, one_off) -> DayItem:
        return DayItem(id=self._gen_id(), source_type=source_type,
                       source_id=source_id, done=done, one_off=one_off)

    def day_items(self, k) -> list:
        return self.day_log.get(k, [])

    def _day(self, k) -> list:
        return self.day_log.setdefault(k, [])

    def item_gen(self, it):
        return self.tasks.get(it.source_id) if it.source_type == "task" else self.routines.get(it.source_id)

    def item_name(self, it) -> str:
        g = self.item_gen(it)
        return g.name if g else "(deleted)"

    def item_container_id(self, it):
        g = self.item_gen(it)
        return g.container_id if g else None

    def item_container(self, it) -> str:
        return self.container_name(self.item_container_id(it))

    def item_recurring(self, it) -> bool:
        return it.source_type == "routine"

    # ---- derivation for a live day ----
    def compute_derived(self, d) -> list:
        timed, untimed = [], []
        for r in self.routines.values():
            if not r.active or r.archived or not self.routine_due_on(r, d) or not self.is_active(r.container_id):
                continue
            (timed if r.time else untimed).append(r)
        timed.sort(key=lambda r: r.time)
        rord = {rid: i for i, rid in enumerate(self.routine_order)}
        untimed.sort(key=lambda r: rord.get(r.id, _END))
        ready = [t for t in self.column_tasks("Ready") if self.is_active(t.container_id)]
        out = []
        for r in timed:
            out.append(("routine", r.id))
        for t in ready:
            out.append(("task", t.id))
        for r in untimed:
            out.append(("routine", r.id))
        return out

    def compute_routine_draft(self, d) -> list:
        """The routines that would appear on date d, with no tasks: timed by time,
        then untimed by the manual routine order. Used for future-day previews and
        for back-filling a skipped past day, where projecting tasks makes no sense."""
        timed, untimed = [], []
        for r in self.routines.values():
            if not r.active or r.archived or not self.routine_due_on(r, d) or not self.is_active(r.container_id):
                continue
            (timed if r.time else untimed).append(r)
        timed.sort(key=lambda r: r.time)
        rord = {rid: i for i, rid in enumerate(self.routine_order)}
        untimed.sort(key=lambda r: rord.get(r.id, _END))
        return [("routine", r.id) for r in timed] + [("routine", r.id) for r in untimed]

    def sync_day(self, d) -> list:
        """Sync ONLY the live (current) day. Past days must never be passed here."""
        k = key_of(d)
        items = self._day(k)
        derived = self.compute_derived(d)
        derived_set = {(st, sid) for (st, sid) in derived}
        for i in range(len(items) - 1, -1, -1):
            it = items[i]
            if it.one_off:
                continue                                              # sticky
            if it.done and self.is_active(self.item_container_id(it)):
                continue                                              # completed stays visible
            if (it.source_type, it.source_id) in derived_set:
                continue                                              # still derived
            del items[i]                                              # dropped
        present = {(it.source_type, it.source_id) for it in items if not it.one_off}
        for (st, sid) in derived:
            if (st, sid) not in present:
                items.append(self.new_day_item(st, sid, False, False))
        return items

    # ---- completion as a cache over the log ----
    def recompute_task(self, task_id):
        done = False
        for k in self.day_log:
            for it in self.day_log[k]:
                if it.source_type == "task" and it.source_id == task_id and it.done:
                    done = True
                    break
            if done:
                break
        t = self.tasks.get(task_id)
        if not t:
            return
        was = t.completed
        t.completed = done
        if was and not done:                 # re-entering the board -> end slot
            t.position = _END
            self.reindex(t.column)

    def task_done_key(self, task_id):
        for k in self.day_log:
            for it in self.day_log[k]:
                if it.source_type == "task" and it.source_id == task_id and it.done:
                    return k
        return None

    def set_done(self, item, done):
        if item.source_type == "task" and done:
            # a task has one completion: clear any other done entry first
            for k in self.day_log:
                for it in self.day_log[k]:
                    if it is not item and it.source_type == "task" and it.source_id == item.source_id and it.done:
                        it.done = False
        item.done = done
        if item.source_type == "task":
            self.recompute_task(item.source_id)

    def mark_task_done_on(self, item, date_key):
        for k in self.day_log:
            for it in self.day_log[k]:
                if it is not item and it.source_type == "task" and it.source_id == item.source_id and it.done:
                    it.done = False
        item.done = True
        # not-done records of this task on LATER days are removed
        for k in list(self.day_log.keys()):
            if k > date_key:
                self.day_log[k] = [it for it in self.day_log[k]
                                   if not (it.source_type == "task" and it.source_id == item.source_id and not it.done)]
        self.recompute_task(item.source_id)

    def log_existing_task_done(self, task_id, date_key):
        task_id = self._coerce_id(task_id)
        lst = self._day(date_key)
        it = next((x for x in lst if x.source_type == "task" and x.source_id == task_id), None)
        if it is None:
            it = self.new_day_item("task", task_id, False, False)
            lst.append(it)
        self.mark_task_done_on(it, date_key)
        return it

    def move_item_to(self, item, from_key, to_key, idx):
        a = self.day_log.get(from_key)
        if a is not None:
            i = _index_of(a, item)
            if i >= 0:
                del a[i]
        b = self._day(to_key)
        if item.source_type == "task":
            # merge to a single record per task per day on the target
            for i in range(len(b) - 1, -1, -1):
                x = b[i]
                if x is not item and x.source_type == "task" and x.source_id == item.source_id:
                    if x.done and not item.done:
                        item.done = True
                    del b[i]
        if idx is None or idx < 0 or idx > len(b):
            idx = len(b)
        b.insert(idx, item)
        if item.source_type == "task":
            self.recompute_task(item.source_id)
        return item

    def move_item(self, item, from_key, to_key):
        a = self.day_log.get(from_key)
        if a is not None:
            i = _index_of(a, item)
            if i >= 0:
                del a[i]
        self._day(to_key).append(item)

    def remove_item(self, item, date_key):
        a = self.day_log.get(date_key)
        if a is not None:
            i = _index_of(a, item)
            if i >= 0:
                del a[i]
        if item.source_type == "task":
            self.recompute_task(item.source_id)

    def add_one_off(self, routine_id, date_key, done=False):
        routine_id = self._coerce_id(routine_id)
        r = self.routines.get(routine_id)
        if not r or r.archived:
            return None
        it = self.new_day_item("routine", routine_id, done, True)
        self._day(date_key).append(it)
        return it

    def log_routine_on(self, routine_id, date_key, done):
        routine_id = self._coerce_id(routine_id)
        r = self.routines.get(routine_id)
        if not r or r.archived:
            return None
        dow = _weekday_of_key(date_key)
        scheduled = dow in r.days_of_week
        exists = any(it.source_type == "routine" and it.source_id == routine_id
                     for it in self.day_log.get(date_key, []))
        one_off = not (scheduled and not exists)
        it = self.new_day_item("routine", routine_id, done, one_off)
        self._day(date_key).append(it)
        return it

    def log_task_done(self, name, container_id, date_key):
        t = self.add_task(name, container_id, "Ready")
        t.completed = True
        self.reindex("Ready")
        it = self.new_day_item("task", t.id, True, True)
        self._day(date_key).append(it)
        return t, it

    def complete_task_today(self, task_id, d):
        """Preview convenience: complete a board task into today's record (find-or-create)."""
        tid = self._coerce_id(task_id)
        k = key_of(d)
        lst = self._day(k)
        it = next((x for x in lst if x.source_type == "task" and x.source_id == tid), None)
        if it is None:
            it = self.new_day_item("task", tid, False, False)
            lst.append(it)
        self.mark_task_done_on(it, k)
        return it
