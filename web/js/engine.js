// engine.js — deterministic core engine (JavaScript port of engine.py)
// Exposes StewardEngine as a window global. No ES modules; loaded via <script> tag.

(function () {
  'use strict';

  const COLUMNS = ["Idea", "Planned", "Soon", "Ready"];
  const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const _END = Number.MAX_SAFE_INTEGER;

  // ---- date utilities ----

  function keyOf(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${dd}`;
  }

  function weekdayMon(d) {
    // Monday=0 .. Sunday=6  (matches Python date.weekday())
    return (d.getDay() + 6) % 7;
  }

  function _weekdayOfKey(k) {
    const [y, mo, dd] = k.split("-").map(Number);
    return weekdayMon(new Date(y, mo - 1, dd));
  }

  function _dateFromKey(k) {
    const [y, mo, dd] = k.split("-").map(Number);
    return new Date(y, mo - 1, dd);
  }

  function _indexOf(arr, item) {
    // Identity search — mirrors Python's reference equality on DayItem objects.
    for (let i = 0; i < arr.length; i++) {
      if (arr[i] === item) return i;
    }
    return -1;
  }

  function _coerceId(x) {
    return parseInt(x, 10);
  }

  // ---- factory functions (replace Python @dataclass) ----

  function makeContainer(id, name, status, description, protected_) {
    return { id, name, status: status || "active", description: description || "", protected: !!protected_ };
  }

  function makeTask(id, name, container_id, column, position, completed, ready_date) {
    return { id, name, container_id, column: column || "Ready", position: position || 0, completed: !!completed, ready_date: ready_date || null };
  }

  function makeRoutine(id, name, container_id, days_of_week, time, duration_hours, active, archived) {
    return {
      id, name, container_id,
      days_of_week: days_of_week ? [...days_of_week] : [],
      time: time || null,
      duration_hours: (duration_hours != null) ? duration_hours : null,
      active: active !== false,
      archived: !!archived,
    };
  }

  function makeDayItem(id, source_type, source_id, done, one_off) {
    return { id, source_type, source_id, done: !!done, one_off: !!one_off };
  }

  // ---- Store factory ----

  function makeStore() {
    const s = {
      containers: {},       // id → Container
      tasks: {},            // id → Task
      routines: {},         // id → Routine
      day_log: {},          // date_key → DayItem[]
      container_order: [],  // [id, ...]
      routine_order: [],    // [id, ...]
      _next_id: 1,
    };

    s._genId = () => s._next_id++;

    // ---- containers ----

    s.add_container = (name, status, description, protected_) => {
      const c = makeContainer(s._genId(), name, status || "active", description || "", !!protected_);
      s.containers[c.id] = c;
      s.container_order.push(c.id);
      return c;
    };

    s.ordered_containers = (status) =>
      s.container_order
        .filter(id => id in s.containers && (status == null || s.containers[id].status === status))
        .map(id => s.containers[id]);

    s.reorder_container = (drag_id, status, target_idx) => {
      drag_id = _coerceId(drag_id);
      const group = s.ordered_containers(status).filter(c => c.id !== drag_id).map(c => c.id);
      const arr = s.container_order.filter(i => i !== drag_id);
      const before_id = (target_idx >= 0 && target_idx < group.length) ? group[target_idx] : null;
      const insert_at = before_id !== null
        ? arr.indexOf(before_id)
        : (group.length > 0 ? arr.indexOf(group[group.length - 1]) + 1 : arr.length);
      arr.splice(insert_at, 0, drag_id);
      s.container_order = arr;
    };

    s.delete_container = (cid) => {
      cid = _coerceId(cid);
      const c = s.containers[cid];
      if (!c || c.protected) return false;
      Object.values(s.tasks).filter(t => t.container_id === cid).forEach(t => s.delete_task(t.id));
      Object.values(s.routines).filter(r => r.container_id === cid).forEach(r => s.delete_routine(r.id));
      delete s.containers[cid];
      s.container_order = s.container_order.filter(i => i !== cid);
      return true;
    };

    s.is_active = (cid) => { const c = s.containers[cid]; return !!(c && c.status === "active"); };

    s.container_name = (cid) => s.containers[cid] ? s.containers[cid].name : "?";

    // ---- tasks ----

    s.column_tasks = (col) =>
      Object.values(s.tasks).filter(t => t.column === col && !t.completed).sort((a, b) => a.position - b.position);

    s.next_position = (col) => s.column_tasks(col).length;

    s.reindex = (col) => { s.column_tasks(col).forEach((t, i) => { t.position = i; }); };

    s.add_task = (name, container_id, column) => {
      column = column || "Ready";
      const t = makeTask(s._genId(), name, container_id, column, s.next_position(column), false);
      s.tasks[t.id] = t;
      return t;
    };

    s.move_task = (task_id, column, position) => {
      const tid = _coerceId(task_id);
      const t = s.tasks[tid];
      if (!t) return;
      const old = t.column;
      t.column = column;
      const ordered = s.column_tasks(column).filter(x => x.id !== tid);
      if (position == null || position >= ordered.length) position = ordered.length;
      ordered.splice(position, 0, t);
      ordered.forEach((x, i) => { x.position = i; });
      if (old !== column) s.reindex(old);
    };

    s.delete_task = (task_id) => {
      task_id = _coerceId(task_id);
      delete s.tasks[task_id];
      for (const k of Object.keys(s.day_log)) {
        s.day_log[k] = s.day_log[k].filter(it => !(it.source_type === "task" && it.source_id === task_id));
      }
    };

    s.task_log_count = (task_id) => {
      task_id = _coerceId(task_id);
      let n = 0;
      for (const items of Object.values(s.day_log))
        for (const it of items)
          if (it.source_type === "task" && it.source_id === task_id) n++;
      return n;
    };

    // ---- routines ----

    s.add_routine = (name, container_id, days_of_week, time, duration_hours, active) => {
      const r = makeRoutine(s._genId(), name, container_id, days_of_week || [],
        time || null, (duration_hours != null) ? duration_hours : null, active !== false, false);
      s.routines[r.id] = r;
      s.routine_order.push(r.id);
      return r;
    };

    s.ordered_routines = (container_id) => {
      container_id = _coerceId(container_id);
      return s.routine_order
        .filter(id => id in s.routines && !s.routines[id].archived && s.routines[id].container_id === container_id)
        .map(id => s.routines[id]);
    };

    s.reorder_routine = (drag_id, container_id, target_idx) => {
      drag_id = _coerceId(drag_id);
      container_id = _coerceId(container_id);
      const r = s.routines[drag_id];
      if (!r) return;
      r.container_id = container_id;
      const group = s.ordered_routines(container_id).filter(x => x.id !== drag_id).map(x => x.id);
      const arr = s.routine_order.filter(i => i !== drag_id);
      const before_id = (target_idx >= 0 && target_idx < group.length) ? group[target_idx] : null;
      const insert_at = before_id !== null
        ? arr.indexOf(before_id)
        : (group.length > 0 ? arr.indexOf(group[group.length - 1]) + 1 : arr.length);
      arr.splice(insert_at, 0, drag_id);
      s.routine_order = arr;
    };

    s.hours_per_week = (r) => {
      if (r.duration_hours == null) return null;
      return Math.round(r.duration_hours * r.days_of_week.length * 10000) / 10000;
    };

    s.routine_due_on = (r, d) => r.days_of_week.includes(weekdayMon(d));

    s.archive_routine = (rid) => { rid = _coerceId(rid); if (s.routines[rid]) s.routines[rid].archived = true; };
    s.unarchive_routine = (rid) => { rid = _coerceId(rid); if (s.routines[rid]) s.routines[rid].archived = false; };

    s.delete_routine = (rid) => {
      rid = _coerceId(rid);
      delete s.routines[rid];
      for (const k of Object.keys(s.day_log)) {
        s.day_log[k] = s.day_log[k].filter(it => !(it.source_type === "routine" && it.source_id === rid));
      }
    };

    s.routine_log_count = (rid) => {
      rid = _coerceId(rid);
      let n = 0;
      for (const items of Object.values(s.day_log))
        for (const it of items)
          if (it.source_type === "routine" && it.source_id === rid) n++;
      return n;
    };

    // ---- day-item helpers ----

    s.new_day_item = (source_type, source_id, done, one_off) =>
      makeDayItem(s._genId(), source_type, source_id, done, one_off);

    s.day_items = (k) => s.day_log[k] || [];

    s._day = (k) => { if (!s.day_log[k]) s.day_log[k] = []; return s.day_log[k]; };

    s.item_gen = (it) =>
      it.source_type === "task" ? (s.tasks[it.source_id] || null) : (s.routines[it.source_id] || null);

    s.item_name = (it) => { const g = s.item_gen(it); return g ? g.name : "(deleted)"; };
    s.item_container_id = (it) => { const g = s.item_gen(it); return g ? g.container_id : null; };
    s.item_container = (it) => s.container_name(s.item_container_id(it));
    s.item_recurring = (it) => it.source_type === "routine";

    // ---- derivation for a live day ----

    s.compute_derived = (d) => {
      const timed = [], untimed = [];
      for (const r of Object.values(s.routines)) {
        if (!r.active || r.archived || !s.routine_due_on(r, d) || !s.is_active(r.container_id)) continue;
        (r.time ? timed : untimed).push(r);
      }
      timed.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
      const rord = {};
      s.routine_order.forEach((rid, i) => { rord[rid] = i; });
      untimed.sort((a, b) => (rord[a.id] ?? _END) - (rord[b.id] ?? _END));
      const ready = s.column_tasks("Ready").filter(t => s.is_active(t.container_id));
      const out = [];
      for (const r of timed) out.push(["routine", r.id]);
      for (const t of ready) out.push(["task", t.id]);
      for (const r of untimed) out.push(["routine", r.id]);
      return out;
    };

    s.compute_routine_draft = (d) => {
      const timed = [], untimed = [];
      for (const r of Object.values(s.routines)) {
        if (!r.active || r.archived || !s.routine_due_on(r, d) || !s.is_active(r.container_id)) continue;
        (r.time ? timed : untimed).push(r);
      }
      timed.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
      const rord = {};
      s.routine_order.forEach((rid, i) => { rord[rid] = i; });
      untimed.sort((a, b) => (rord[a.id] ?? _END) - (rord[b.id] ?? _END));
      return [...timed.map(r => ["routine", r.id]), ...untimed.map(r => ["routine", r.id])];
    };

    s.sync_day = (d) => {
      const k = keyOf(d);
      const items = s._day(k);
      const derived = s.compute_derived(d);
      const derived_set = new Set(derived.map(([st, sid]) => `${st}:${sid}`));
      for (let i = items.length - 1; i >= 0; i--) {
        const it = items[i];
        if (it.one_off) continue;
        if (it.done && s.is_active(s.item_container_id(it))) continue;
        if (derived_set.has(`${it.source_type}:${it.source_id}`)) continue;
        items.splice(i, 1);
      }
      const present = new Set(
        items.filter(it => !it.one_off).map(it => `${it.source_type}:${it.source_id}`)
      );
      for (const [st, sid] of derived) {
        if (!present.has(`${st}:${sid}`)) items.push(s.new_day_item(st, sid, false, false));
      }
      return items;
    };

    // ---- completion cache ----

    s.recompute_task = (task_id) => {
      let done = false;
      outer: for (const items of Object.values(s.day_log)) {
        for (const it of items) {
          if (it.source_type === "task" && it.source_id === task_id && it.done) { done = true; break outer; }
        }
      }
      const t = s.tasks[task_id];
      if (!t) return;
      const was = t.completed;
      t.completed = done;
      if (was && !done) { t.position = _END; s.reindex(t.column); }
    };

    s.task_done_key = (task_id) => {
      for (const [k, items] of Object.entries(s.day_log))
        for (const it of items)
          if (it.source_type === "task" && it.source_id === task_id && it.done) return k;
      return null;
    };

    s.set_done = (item, done) => {
      if (item.source_type === "task" && done) {
        for (const items of Object.values(s.day_log))
          for (const it of items)
            if (it !== item && it.source_type === "task" && it.source_id === item.source_id && it.done)
              it.done = false;
      }
      item.done = done;
      if (item.source_type === "task") s.recompute_task(item.source_id);
    };

    s.mark_task_done_on = (item, date_key) => {
      for (const items of Object.values(s.day_log))
        for (const it of items)
          if (it !== item && it.source_type === "task" && it.source_id === item.source_id && it.done)
            it.done = false;
      item.done = true;
      for (const k of Object.keys(s.day_log)) {
        if (k > date_key)
          s.day_log[k] = s.day_log[k].filter(
            it => !(it.source_type === "task" && it.source_id === item.source_id && !it.done)
          );
      }
      s.recompute_task(item.source_id);
    };

    s.log_existing_task_done = (task_id, date_key) => {
      task_id = _coerceId(task_id);
      const lst = s._day(date_key);
      let it = lst.find(x => x.source_type === "task" && x.source_id === task_id);
      if (!it) { it = s.new_day_item("task", task_id, false, false); lst.push(it); }
      s.mark_task_done_on(it, date_key);
      return it;
    };

    s.move_item_to = (item, from_key, to_key, idx) => {
      const a = s.day_log[from_key];
      if (a) { const i = _indexOf(a, item); if (i >= 0) a.splice(i, 1); }
      const b = s._day(to_key);
      if (item.source_type === "task") {
        for (let i = b.length - 1; i >= 0; i--) {
          const x = b[i];
          if (x !== item && x.source_type === "task" && x.source_id === item.source_id) {
            if (x.done && !item.done) item.done = true;
            b.splice(i, 1);
          }
        }
      }
      if (idx == null || idx < 0 || idx > b.length) idx = b.length;
      b.splice(idx, 0, item);
      if (item.source_type === "task") s.recompute_task(item.source_id);
      return item;
    };

    s.move_item = (item, from_key, to_key) => {
      const a = s.day_log[from_key];
      if (a) { const i = _indexOf(a, item); if (i >= 0) a.splice(i, 1); }
      s._day(to_key).push(item);
    };

    s.remove_item = (item, date_key) => {
      const a = s.day_log[date_key];
      if (a) { const i = _indexOf(a, item); if (i >= 0) a.splice(i, 1); }
      if (item.source_type === "task") {
        const t = s.tasks[item.source_id];
        if (t && t.ready_date === date_key) t.ready_date = null;
        s.recompute_task(item.source_id);
      }
    };

    s.promote_due_tasks = (today_key) => {
      const toPromote = Object.values(s.tasks).filter(t => t.ready_date && t.ready_date <= today_key);
      for (const t of toPromote) {
        const sched = t.ready_date;
        // backfill from sched through yesterday
        let d = _dateFromKey(sched);
        const yesterday = new Date(_dateFromKey(today_key).getTime() - 86400000);
        while (d <= yesterday) {
          const k = keyOf(d);
          const day = s._day(k);
          if (!day.some(it => it.source_type === "task" && it.source_id === t.id))
            day.push(s.new_day_item("task", t.id, false, true));
          d = new Date(d.getTime() + 86400000);
        }
        if (t.column !== "Ready") s.move_task(t.id, "Ready");
        t.ready_date = null;
      }
    };

    s.add_one_off = (routine_id, date_key, done) => {
      routine_id = _coerceId(routine_id);
      const r = s.routines[routine_id];
      if (!r || r.archived) return null;
      const it = s.new_day_item("routine", routine_id, !!done, true);
      s._day(date_key).push(it);
      return it;
    };

    s.log_routine_on = (routine_id, date_key, done) => {
      routine_id = _coerceId(routine_id);
      const r = s.routines[routine_id];
      if (!r || r.archived) return null;
      const dow = _weekdayOfKey(date_key);
      const scheduled = r.days_of_week.includes(dow);
      const exists = (s.day_log[date_key] || []).some(
        it => it.source_type === "routine" && it.source_id === routine_id
      );
      const one_off = !(scheduled && !exists);
      const it = s.new_day_item("routine", routine_id, !!done, one_off);
      s._day(date_key).push(it);
      return it;
    };

    s.log_task_done = (name, container_id, date_key) => {
      const t = s.add_task(name, container_id, "Ready");
      t.completed = true;
      s.reindex("Ready");
      const it = s.new_day_item("task", t.id, true, true);
      s._day(date_key).push(it);
      return [t, it];
    };

    s.complete_task_today = (task_id, d) => {
      const tid = _coerceId(task_id);
      const k = keyOf(d);
      const lst = s._day(k);
      let it = lst.find(x => x.source_type === "task" && x.source_id === tid);
      if (!it) { it = s.new_day_item("task", tid, false, false); lst.push(it); }
      s.mark_task_done_on(it, k);
      return it;
    };

    return s;
  }

  window.StewardEngine = { makeStore, keyOf, weekdayMon, _dateFromKey, COLUMNS, WEEKDAYS };

})();
