# Custodian — running and verifying

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

First launch creates the database and seeds the single protected "Misc"
container. By default the file lives at:

    ~/.custodian/custodian.db        (override with the CUSTODIAN_HOME env var)

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
