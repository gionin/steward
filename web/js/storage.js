// storage.js — SQLite persistence via sql.js + OPFS (port of storage.py)
// Exposes StewardStorage as a window global. No ES modules; loaded via <script> tag.

(function () {
  'use strict';

  const SCHEMA_VERSION = 2;

  // ---- meta / versioning ----

  function _ensureMeta(db) {
    db.run("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)");
  }

  function _getVersion(db) {
    _ensureMeta(db);
    const res = db.exec("SELECT value FROM meta WHERE key='schema_version'");
    if (!res.length || !res[0].values.length) return 0;
    return parseInt(res[0].values[0][0], 10);
  }

  function _setVersion(db, v) {
    db.run(
      "INSERT INTO meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
      [String(v)]
    );
  }

  // ---- migrations ----

  function _migrationToV1(db) {
    db.run(`CREATE TABLE containers (
      id          INTEGER PRIMARY KEY,
      name        TEXT    NOT NULL,
      status      TEXT    NOT NULL,
      description TEXT    NOT NULL DEFAULT '',
      ord         INTEGER NOT NULL
    )`);
    db.run(`CREATE TABLE tasks (
      id           INTEGER PRIMARY KEY,
      name         TEXT    NOT NULL,
      container_id INTEGER NOT NULL,
      col          TEXT    NOT NULL,
      position     INTEGER NOT NULL,
      completed    INTEGER NOT NULL DEFAULT 0
    )`);
    db.run(`CREATE TABLE routines (
      id             INTEGER PRIMARY KEY,
      name           TEXT    NOT NULL,
      container_id   INTEGER NOT NULL,
      days_of_week   TEXT    NOT NULL DEFAULT '[]',
      time           TEXT,
      duration_hours REAL,
      active         INTEGER NOT NULL DEFAULT 1,
      archived       INTEGER NOT NULL DEFAULT 0,
      ord            INTEGER NOT NULL
    )`);
    db.run(`CREATE TABLE day_log (
      id          INTEGER PRIMARY KEY,
      date_key    TEXT    NOT NULL,
      source_type TEXT    NOT NULL,
      source_id   INTEGER NOT NULL,
      done        INTEGER NOT NULL DEFAULT 0,
      one_off     INTEGER NOT NULL DEFAULT 0,
      seq         INTEGER NOT NULL
    )`);
    db.run("CREATE INDEX idx_daylog_date ON day_log(date_key, seq)");
  }

  function _migrationToV2(db) {
    db.run("ALTER TABLE containers ADD COLUMN protected INTEGER NOT NULL DEFAULT 0");
    const hasProtected = db.exec("SELECT 1 FROM containers WHERE protected=1 LIMIT 1");
    if (!hasProtected.length || !hasProtected[0].values.length) {
      const existingMisc = db.exec("SELECT id FROM containers WHERE name='Misc' ORDER BY id LIMIT 1");
      if (existingMisc.length && existingMisc[0].values.length) {
        db.run("UPDATE containers SET protected=1 WHERE id=?", [existingMisc[0].values[0][0]]);
      } else {
        const ordRes = db.exec("SELECT COALESCE(MAX(ord),-1)+1 FROM containers");
        const nextOrd = ordRes.length ? ordRes[0].values[0][0] : 0;
        db.run(
          "INSERT INTO containers(name,status,description,ord,protected) VALUES('Misc','active','',?,1)",
          [nextOrd]
        );
      }
    }
  }

  const _MIGRATIONS = [_migrationToV1, _migrationToV2];

  function applyMigrations(db) {
    const current = _getVersion(db);
    for (let i = current; i < _MIGRATIONS.length; i++) {
      _MIGRATIONS[i](db);
      _setVersion(db, i + 1);
    }
  }

  // ---- load ----

  function load(db) {
    const { makeStore } = window.StewardEngine;
    const store = makeStore();

    const containers = db.exec("SELECT * FROM containers ORDER BY ord, id");
    if (containers.length) {
      const cols = containers[0].columns;
      for (const row of containers[0].values) {
        const r = Object.fromEntries(cols.map((c, i) => [c, row[i]]));
        store.containers[r.id] = { id: r.id, name: r.name, status: r.status, description: r.description, protected: !!r.protected };
        store.container_order.push(r.id);
      }
    }

    const tasks = db.exec("SELECT * FROM tasks");
    if (tasks.length) {
      const cols = tasks[0].columns;
      for (const row of tasks[0].values) {
        const r = Object.fromEntries(cols.map((c, i) => [c, row[i]]));
        store.tasks[r.id] = { id: r.id, name: r.name, container_id: r.container_id, column: r.col, position: r.position, completed: !!r.completed };
      }
    }

    const routines = db.exec("SELECT * FROM routines ORDER BY ord, id");
    if (routines.length) {
      const cols = routines[0].columns;
      for (const row of routines[0].values) {
        const r = Object.fromEntries(cols.map((c, i) => [c, row[i]]));
        store.routines[r.id] = {
          id: r.id, name: r.name, container_id: r.container_id,
          days_of_week: JSON.parse(r.days_of_week || "[]"),
          time: r.time || null, duration_hours: r.duration_hours != null ? r.duration_hours : null,
          active: !!r.active, archived: !!r.archived,
        };
        store.routine_order.push(r.id);
      }
    }

    const daylog = db.exec("SELECT * FROM day_log ORDER BY date_key, seq, id");
    if (daylog.length) {
      const cols = daylog[0].columns;
      for (const row of daylog[0].values) {
        const r = Object.fromEntries(cols.map((c, i) => [c, row[i]]));
        if (!store.day_log[r.date_key]) store.day_log[r.date_key] = [];
        store.day_log[r.date_key].push({ id: r.id, source_type: r.source_type, source_id: r.source_id, done: !!r.done, one_off: !!r.one_off });
      }
    }

    // reseed id generator above every persisted id
    let maxId = 0;
    for (const id of [...Object.keys(store.containers), ...Object.keys(store.tasks), ...Object.keys(store.routines)])
      if (Number(id) > maxId) maxId = Number(id);
    for (const items of Object.values(store.day_log))
      for (const it of items)
        if (it.id > maxId) maxId = it.id;
    store._next_id = maxId + 1;

    return store;
  }

  // ---- save (full transactional rewrite) ----

  function save(db, store) {
    db.run("BEGIN");
    try {
      for (const tbl of ["containers", "tasks", "routines", "day_log"]) {
        db.run(`DELETE FROM ${tbl}`);
      }

      const allCids = [
        ...store.container_order,
        ...Object.keys(store.containers).map(Number).filter(id => !store.container_order.includes(id)),
      ];
      allCids.forEach((cid, ordn) => {
        const c = store.containers[cid];
        if (!c) return;
        db.run(
          "INSERT INTO containers(id,name,status,description,ord,protected) VALUES(?,?,?,?,?,?)",
          [c.id, c.name, c.status, c.description, ordn, c.protected ? 1 : 0]
        );
      });

      for (const t of Object.values(store.tasks)) {
        db.run(
          "INSERT INTO tasks(id,name,container_id,col,position,completed) VALUES(?,?,?,?,?,?)",
          [t.id, t.name, t.container_id, t.column, t.position, t.completed ? 1 : 0]
        );
      }

      const allRids = [
        ...store.routine_order,
        ...Object.keys(store.routines).map(Number).filter(id => !store.routine_order.includes(id)),
      ];
      allRids.forEach((rid, ordn) => {
        const r = store.routines[rid];
        if (!r) return;
        db.run(
          "INSERT INTO routines(id,name,container_id,days_of_week,time,duration_hours,active,archived,ord) VALUES(?,?,?,?,?,?,?,?,?)",
          [r.id, r.name, r.container_id, JSON.stringify(r.days_of_week), r.time, r.duration_hours, r.active ? 1 : 0, r.archived ? 1 : 0, ordn]
        );
      });

      for (const [date_key, items] of Object.entries(store.day_log)) {
        items.forEach((it, seq) => {
          db.run(
            "INSERT INTO day_log(id,date_key,source_type,source_id,done,one_off,seq) VALUES(?,?,?,?,?,?,?)",
            [it.id, date_key, it.source_type, it.source_id, it.done ? 1 : 0, it.one_off ? 1 : 0, seq]
          );
        });
      }

      _setVersion(db, SCHEMA_VERSION);
      db.run("COMMIT");
    } catch (e) {
      db.run("ROLLBACK");
      throw e;
    }
  }

  // ---- OPFS persistence ----

  async function _readOpfs() {
    try {
      const root = await navigator.storage.getDirectory();
      const fh = await root.getFileHandle("steward.db", { create: false });
      const file = await fh.getFile();
      return new Uint8Array(await file.arrayBuffer());
    } catch {
      return null; // file doesn't exist yet
    }
  }

  async function persistDatabase(db) {
    const data = db.export();
    const root = await navigator.storage.getDirectory();
    const fh = await root.getFileHandle("steward.db", { create: true });
    const writable = await fh.createWritable();
    await writable.write(data);
    await writable.close();
  }

  async function openDatabase() {
    const bytes = await _readOpfs();
    const SQL = await initSqlJs({ locateFile: f => `./vendor/${f}` });
    const db = bytes ? new SQL.Database(bytes) : new SQL.Database();
    applyMigrations(db);
    const store = load(db);
    return { db, store };
  }

  // ---- export / import ----

  async function exportDatabase(db) {
    const data = db.export();
    const blob = new Blob([data], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "steward.db";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function importDatabase(file) {
    const data = new Uint8Array(await file.arrayBuffer());
    const SQL = await initSqlJs({ locateFile: f => `./vendor/${f}` });
    const db = new SQL.Database(data);
    applyMigrations(db); // handles v1 → v2 if importing an older desktop file
    const store = load(db);
    await persistDatabase(db);
    return { db, store };
  }

  window.StewardStorage = { openDatabase, persistDatabase, save, load, exportDatabase, importDatabase };

})();
