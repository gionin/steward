// api.js — web API bridge (port of app.py Api class)
// createWebApi() returns an object with the same method signatures
// that window.pywebview.api exposes on desktop.
// Exposes createWebApi as a window global. No ES modules.

(function () {
  'use strict';

  const APP_VERSION = "0.01.01f-web";

  async function createWebApi() {
    const { COLUMNS, WEEKDAYS, _dateFromKey } = window.StewardEngine;
    const { save, persistDatabase, exportDatabase, importDatabase } = window.StewardStorage;

    let { db, store } = await window.StewardStorage.openDatabase();

    // ---- internal helpers ----

    function _miscId() {
      for (const c of Object.values(store.containers)) { if (c.protected) return c.id; }
      return store.container_order[0] ?? null;
    }

    function _findItem(item_id) {
      item_id = parseInt(item_id, 10);
      for (const [k, items] of Object.entries(store.day_log))
        for (const it of items)
          if (it.id === item_id) return { it, k };
      return { it: null, k: null };
    }

    function _findItemIn(date_key, item_id) {
      item_id = parseInt(item_id, 10);
      return (store.day_log[date_key] || []).find(it => it.id === item_id) || null;
    }

    async function _saveAndPersist() {
      save(db, store);
      await persistDatabase(db);
    }

    // ---- snapshot builder ----

    function _resolveItem(it) {
      return {
        id: it.id, sourceType: it.source_type, sourceId: it.source_id,
        name: store.item_name(it), container: store.item_container(it),
        containerId: store.item_container_id(it),
        done: it.done, oneOff: it.one_off, recurring: it.source_type === "routine",
      };
    }

    function _futurePreview(view_key) {
      return store.compute_routine_draft(_dateFromKey(view_key)).map(([_st, sid]) => {
        const r = store.routines[sid];
        if (!r) return null;
        return {
          id: `preview-${sid}`, sourceType: "routine", sourceId: sid,
          name: r.name, container: store.container_name(r.container_id),
          containerId: r.container_id, done: false, oneOff: false, recurring: true, preview: true,
        };
      }).filter(Boolean);
    }

    function _buildSnapshot(today_key, viewed_key) {
      const live = today_key;
      const view = viewed_key || today_key;
      const is_future = view > live;
      const is_past = view < live;

      const today = is_future
        ? _futurePreview(view)
        : store.day_items(view).map(it => _resolveItem(it));

      const held = Object.values(store.tasks).filter(
        t => !t.completed && t.column !== "Ready" && store.is_active(t.container_id)
      ).length;

      const columns = {};
      for (const col of COLUMNS) {
        columns[col] = store.column_tasks(col).map(t => ({
          id: t.id, name: t.name, containerId: t.container_id,
          containerName: store.container_name(t.container_id),
          containerActive: store.is_active(t.container_id),
          column: t.column, position: t.position, completed: t.completed,
          logCount: store.task_log_count(t.id),
        }));
      }

      const containers = store.container_order
        .filter(cid => cid in store.containers)
        .map(cid => {
          const c = store.containers[cid];
          return {
            id: c.id, name: c.name, status: c.status, description: c.description,
            protected: c.protected,
            taskCount: Object.values(store.tasks).filter(t => t.container_id === cid && !t.completed).length,
            routineCount: Object.values(store.routines).filter(r => r.container_id === cid && !r.archived).length,
          };
        });

      const routines = store.routine_order
        .filter(rid => rid in store.routines)
        .map(rid => {
          const r = store.routines[rid];
          return {
            id: r.id, name: r.name, containerId: r.container_id,
            containerName: store.container_name(r.container_id),
            daysOfWeek: [...r.days_of_week], time: r.time, durationHours: r.duration_hours,
            active: r.active, archived: r.archived,
            hoursPerWeek: store.hours_per_week(r),
            logCount: store.routine_log_count(r.id),
          };
        });

      const hist_keys = Object.keys(store.day_log)
        .filter(k => k < live && store.day_log[k].length > 0)
        .sort((a, b) => b.localeCompare(a));
      const history = hist_keys.map(k => ({
        dateKey: k,
        entries: store.day_log[k].map(it => _resolveItem(it)),
      }));

      const tasksAll = Object.values(store.tasks).map(t => ({
        id: t.id, name: t.name, containerId: t.container_id, completed: t.completed,
      }));

      return {
        version: APP_VERSION, todayKey: view, liveKey: live,
        isLive: !is_future && !is_past, isPast: is_past, isFuture: is_future,
        miscId: _miscId(), today, heldCount: held,
        columns, containers, routines, history, tasksAll,
      };
    }

    async function _snap(today_key, viewed_key) {
      store.sync_day(_dateFromKey(today_key)); // only live day re-syncs
      const snap = _buildSnapshot(today_key, viewed_key);
      await _saveAndPersist();
      return snap;
    }

    // ---- context export (port of app.py _serialize) ----

    function _serialize(today_key) {
      const [y, m, d] = today_key.split("-").map(Number);
      const dayDate = new Date(y, m - 1, d);
      const dow = WEEKDAYS[(dayDate.getDay() + 6) % 7];
      const dmy = k => { const [yy, mm, dd] = k.split("-"); return `${dd}/${mm}/${yy}`; };

      let out = "STEWARD - STATE EXPORT\n";
      out += `Generated for: ${dow} ${dmy(today_key)}\n\nTODAY'S SLICE\n`;
      const items = store.day_items(today_key);
      if (items.length) {
        for (const it of items) {
          let flags = it.source_type === "routine" ? "  {routine}" : "";
          if (it.one_off && it.source_type === "routine") flags += " {one-off}";
          out += `  [${it.done ? "x" : " "}] ${store.item_name(it)}  (${store.item_container(it)})${flags}\n`;
        }
      } else {
        out += "  (nothing drafted)\n";
      }
      out += "\nACTIVE CONTAINERS\n";
      for (const cid of store.container_order) {
        const c = store.containers[cid];
        if (!c || c.status !== "active") continue;
        out += `  ${c.name}\n`;
        for (const col of [...COLUMNS].reverse()) {
          const ts = store.column_tasks(col).filter(t => t.container_id === cid);
          if (ts.length) out += `    ${col}: ${ts.map(t => t.name).join("; ")}\n`;
        }
      }
      const aside = store.container_order
        .map(id => store.containers[id])
        .filter(c => c && c.status !== "active");
      if (aside.length) out += "\nSET ASIDE: " + aside.map(c => `${c.name} (${c.status})`).join(", ") + "\n";
      out += "\nRECENT DAYS (done / planned)\n";
      const keys = Object.keys(store.day_log)
        .filter(k => k < today_key && store.day_log[k].length > 0)
        .sort((a, b) => b.localeCompare(a))
        .slice(0, 7);
      if (keys.length) {
        for (const k of keys) {
          const its = store.day_log[k];
          const done = its.filter(i => i.done).length;
          out += `  ${dmy(k)}: ${done}/${its.length} done\n`;
        }
      } else {
        out += "  (no past days yet)\n";
      }
      return out;
    }

    // ---- public API (mirrors app.py Api exactly) ----

    return {

      // queries
      async get_state(today_key, viewed_key) { return _snap(today_key, viewed_key); },

      async backfill_day(today_key, viewed_key) {
        const lst = store._day(viewed_key);
        const present = new Set(lst.map(it => `${it.source_type}:${it.source_id}`));
        for (const [st, sid] of store.compute_routine_draft(_dateFromKey(viewed_key)))
          if (!present.has(`${st}:${sid}`)) lst.push(store.new_day_item(st, sid, false, false));
        return _snap(today_key, viewed_key);
      },

      async task_done_key(task_id) { return store.task_done_key(parseInt(task_id, 10)); },

      async context_export(today_key) { return _serialize(today_key); },

      // Today commands
      async capture_task(name, today_key) {
        name = (name || "").trim();
        if (name) store.add_task(name, _miscId(), "Ready");
        return _snap(today_key);
      },

      async toggle_today_item(item_id, today_key, viewed_key) {
        const it = _findItemIn(viewed_key || today_key, item_id);
        if (it) store.set_done(it, !it.done);
        return _snap(today_key, viewed_key);
      },

      async reorder_today_item(item_id, idx, today_key, viewed_key) {
        const items = store.day_log[viewed_key || today_key];
        if (items) {
          item_id = parseInt(item_id, 10);
          const pos = items.findIndex(x => x.id === item_id);
          if (pos >= 0) {
            const it = items.splice(pos, 1)[0];
            items.splice(Math.max(0, Math.min(parseInt(idx, 10), items.length)), 0, it);
          }
        }
        return _snap(today_key, viewed_key);
      },

      // generator rename / refile
      async rename_item(item_id, name, today_key, viewed_key) {
        name = (name || "").trim();
        const { it } = _findItem(item_id);
        if (it && name) { const g = store.item_gen(it); if (g) g.name = name; }
        return _snap(today_key, viewed_key);
      },

      async set_item_container(item_id, container_id, today_key, viewed_key) {
        const { it } = _findItem(item_id);
        if (it) { const g = store.item_gen(it); if (g) g.container_id = parseInt(container_id, 10); }
        return _snap(today_key, viewed_key);
      },

      // Tasks board
      async add_task(name, container_id, column, today_key) {
        name = (name || "").trim();
        if (name) store.add_task(name, parseInt(container_id, 10), column);
        return _snap(today_key);
      },

      async rename_task(task_id, name, today_key) {
        name = (name || "").trim();
        const t = store.tasks[parseInt(task_id, 10)];
        if (t && name) t.name = name;
        return _snap(today_key);
      },

      async set_task_container(task_id, container_id, today_key) {
        const t = store.tasks[parseInt(task_id, 10)];
        if (t) t.container_id = parseInt(container_id, 10);
        return _snap(today_key);
      },

      async move_task(task_id, column, position, today_key) {
        store.move_task(task_id, column, position);
        return _snap(today_key);
      },

      async delete_task(task_id, today_key) {
        store.delete_task(parseInt(task_id, 10));
        return _snap(today_key);
      },

      async complete_task_today(task_id, today_key) {
        store.complete_task_today(task_id, _dateFromKey(today_key));
        return _snap(today_key);
      },

      // Routines
      async add_routine(name, container_id, today_key) {
        name = (name || "").trim();
        if (name) store.add_routine(name, parseInt(container_id, 10), [], null, null, true);
        return _snap(today_key);
      },

      async rename_routine(routine_id, name, today_key) {
        name = (name || "").trim();
        const r = store.routines[parseInt(routine_id, 10)];
        if (r && name) r.name = name;
        return _snap(today_key);
      },

      async set_routine_active(routine_id, active, today_key) {
        const r = store.routines[parseInt(routine_id, 10)];
        if (r) r.active = !!active;
        return _snap(today_key);
      },

      async toggle_routine_day(routine_id, day, today_key) {
        const r = store.routines[parseInt(routine_id, 10)];
        if (r) {
          day = parseInt(day, 10);
          const idx = r.days_of_week.indexOf(day);
          if (idx >= 0) r.days_of_week.splice(idx, 1); else r.days_of_week.push(day);
          r.days_of_week.sort((a, b) => a - b);
        }
        return _snap(today_key);
      },

      async set_routine_time(routine_id, time, today_key) {
        const r = store.routines[parseInt(routine_id, 10)];
        if (r) r.time = time || null;
        return _snap(today_key);
      },

      async set_routine_duration(routine_id, hours, today_key) {
        const r = store.routines[parseInt(routine_id, 10)];
        if (r) r.duration_hours = (hours == null || hours === "") ? null : parseFloat(hours);
        return _snap(today_key);
      },

      async archive_routine(routine_id, today_key) {
        store.archive_routine(parseInt(routine_id, 10)); return _snap(today_key);
      },

      async unarchive_routine(routine_id, today_key) {
        store.unarchive_routine(parseInt(routine_id, 10)); return _snap(today_key);
      },

      async delete_routine(routine_id, today_key) {
        store.delete_routine(parseInt(routine_id, 10)); return _snap(today_key);
      },

      async reorder_routine(routine_id, container_id, idx, today_key) {
        store.reorder_routine(routine_id, container_id, parseInt(idx, 10));
        return _snap(today_key);
      },

      async add_one_off(routine_id, today_key) {
        store.add_one_off(parseInt(routine_id, 10), today_key);
        return _snap(today_key);
      },

      // Containers
      async add_container(name, today_key, status) {
        name = (name || "").trim();
        if (name) store.add_container(name, status || "active");
        return _snap(today_key);
      },

      async set_container_status(container_id, status, today_key) {
        const c = store.containers[parseInt(container_id, 10)];
        if (c) c.status = status;
        return _snap(today_key);
      },

      async reorder_container(container_id, status, idx, today_key) {
        const c = store.containers[parseInt(container_id, 10)];
        if (c && c.status !== status) c.status = status;
        store.reorder_container(container_id, status, parseInt(idx, 10));
        return _snap(today_key);
      },

      async delete_container(container_id, today_key) {
        const ok = store.delete_container(parseInt(container_id, 10));
        return { ok, state: await _snap(today_key) };
      },

      // History
      async history_toggle(item_id, date_key, today_key) {
        const it = _findItemIn(date_key, item_id);
        if (it) store.set_done(it, !it.done);
        return _snap(today_key);
      },

      async mark_task_done(item_id, date_key, today_key) {
        const it = _findItemIn(date_key, item_id);
        if (it) store.mark_task_done_on(it, date_key);
        return _snap(today_key);
      },

      async move_item(item_id, from_key, to_key, today_key) {
        const it = _findItemIn(from_key, item_id);
        if (it) store.move_item(it, from_key, to_key);
        return _snap(today_key);
      },

      async move_item_to(item_id, from_key, to_key, idx, today_key) {
        const it = _findItemIn(from_key, item_id);
        let later_conflict = false;
        if (it) {
          store.move_item_to(it, from_key, to_key, parseInt(idx, 10));
          if (it.source_type === "task" && it.done) {
            later_conflict = Object.entries(store.day_log).some(
              ([k, items]) => k > to_key && items.some(
                x => x !== it && x.source_type === "task" && x.source_id === it.source_id && !x.done
              )
            );
          }
        }
        return { laterConflict: later_conflict, itemId: parseInt(item_id, 10), toKey: to_key, state: await _snap(today_key) };
      },

      async resolve_later_conflict(item_id, to_key, clear_later, today_key) {
        const it = _findItemIn(to_key, item_id);
        if (it) {
          if (clear_later) store.mark_task_done_on(it, to_key);
          else store.set_done(it, false);
        }
        return _snap(today_key);
      },

      async remove_item(item_id, date_key, today_key) {
        const it = _findItemIn(date_key, item_id);
        if (it) store.remove_item(it, date_key);
        return _snap(today_key);
      },

      async log_activity(kind, is_new, name, container_id, target_id, date_key, done, today_key, force) {
        if (kind === "task") {
          if (is_new) {
            name = (name || "").trim();
            if (!name) return { ok: false, state: await _snap(today_key) };
            const cid = parseInt(container_id, 10);
            if (done) {
              store.log_task_done(name, cid, date_key);
            } else {
              const t = store.add_task(name, cid, "Ready");
              store._day(date_key).push(store.new_day_item("task", t.id, false, false));
            }
          } else {
            const tid = parseInt(target_id, 10);
            if (done) {
              store.log_existing_task_done(tid, date_key);
            } else {
              const dd = store.task_done_key(tid);
              if (dd && dd < date_key && !force) {
                return {
                  ok: false, conflict: "taskDoneBefore",
                  doneDate: dd, taskName: store.tasks[tid] ? store.tasks[tid].name : "",
                  state: await _snap(today_key),
                };
              }
              if (dd && dd < date_key && force) {
                for (const items of Object.values(store.day_log))
                  for (const x of items)
                    if (x.source_type === "task" && x.source_id === tid && x.done) store.set_done(x, false);
              }
              const lst = store._day(date_key);
              const ex = lst.find(x => x.source_type === "task" && x.source_id === tid);
              if (ex) store.set_done(ex, false);
              else lst.push(store.new_day_item("task", tid, false, false));
            }
          }
        } else {
          if (is_new) {
            name = (name || "").trim();
            if (!name) return { ok: false, state: await _snap(today_key) };
            const r = store.add_routine(name, parseInt(container_id, 10), [], null, null, true);
            store._day(date_key).push(store.new_day_item("routine", r.id, !!done, false));
          } else {
            store.log_routine_on(parseInt(target_id, 10), date_key, !!done);
          }
        }
        return { ok: true, state: await _snap(today_key) };
      },

      // desktop-only stubs (keep so Settings UI wiring doesn't break)
      async data_location() { return { dbPath: "(browser OPFS)", folder: "" }; },
      async backup_database() { return { ok: false, error: "Use the Export button." }; },
      async open_data_folder() { return { ok: false }; },

      // web-only
      async exportDb() { await exportDatabase(db); },

      async importDb(file) {
        const result = await importDatabase(file);
        // rebind live references; all inner closures see the new values via let binding
        db = result.db;
        store = result.store;
      },
    };
  }

  window.createWebApi = createWebApi;

})();
