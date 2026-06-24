# Steward — running and verifying

Deterministic core (task + routine manager). Python owns the engine and the
SQLite state; the web UI renders from a snapshot and sends one command per
action across the pywebview bridge.

## Files

    engine.py          the engine, ported from the authoritative preview
    storage.py         SQLite persistence + the schema-migration chain
    app.py             the pywebview bridge (Api) + the window entry point
    index.html         the UI (preview's look), driven by the bridge
    test_engine.py     19 behavioural checks for the engine
    test_storage.py    4 checks: first-run, round-trip, real v1->v2 migration
    test_api.py        11 checks: every command, the snapshot, persistence

## Run the app

    python -m pip install -r requirements.txt      # Linux: pywebview[qt] or [gtk]
    python app.py

### Day-to-day launch (Windows, no console window)

`run.bat` keeps a console open to report crashes. For daily use, launch without
one instead:

    run-quiet.vbs        double-click; starts the app via the windowless
                         pythonw.exe, so no console appears

For a clickable/pinnable icon, there is a `Steward` shortcut on the Desktop that
points at `.venv\Scripts\pythonw.exe app.py`; right-click it to pin to the
taskbar or Start. Either way, startup and crash detail still land in the log
below.

First launch creates the database and seeds the single protected "Misc"
container. By default the file lives at:

    ~/.steward/steward.db        (override with the STEWARD_HOME env var)

Your data persists across restarts and across app-version upgrades: a newer
build opens an older database and migrates it forward without losing anything.

## Run the tests (no GUI needed)

    python test_engine.py
    python test_storage.py
    python test_api.py

Each exits non-zero on any failure.

## Version

The display version shown in Settings starts at 0.01.00a. It is separate from
the database's integer schema_version, which is what actually drives migrations.
