# Project Status

Working state for the Trusted-Offload Assistant. This is the mutable counterpart to the stable documents: the Project Vision (why the system exists and how it should feel) and the Project Architecture (how it is built). This document is updated at the end of each working session: keep the snapshot and backlog current, and append a dated entry to the session log.

---

## Documentation set

Four governing documents, each answering exactly one question:

- **Collaboration Charter.** How we work together: roles, the phase gate, conventions. Shared across projects; never edited with project-specific content. Changes rarely.
- **Project Vision.** Why the system exists and what it is meant to feel like: value proposition, design philosophy, a day-in-the-life. No mechanism. Changes rarely.
- **Project Architecture.** How the system is built: the deterministic core (data model, columns, routines, the daily draft, history, and the realization in process, persistence, and versioning) and the planned AI facilitation layer on top of it. Changes only when a design decision changes it.
- **Project Status.** This document. Where we are now: backlog, decisions awaiting, session log. Mutable, every session.

Boundary rule: settled mechanics live in Architecture; open mechanical questions and their history live here in Status; when one resolves, the answer lands in Architecture.

Framing rule: the system is deterministic first. The deterministic core is the product and must work with no AI involved. The AI facilitation layer is additive and never replaces core functionality. Backlog items are tagged accordingly, and the AI-layer items are deferred behind the deterministic build.

---

## Snapshot

- **Phase:** 2 (Build). The Phase 1 design for the deterministic v1 is complete, the build gate is passed, and the deterministic desktop application is built and running.
- **Design state:** The deterministic core is fully designed and captured in the Project Architecture document (sections 2 to 7). It was realized first as a single-file interactive HTML preview, and is now realized as the Python plus SQLite plus pywebview desktop application. The AI facilitation layer is designed at the architecture level (Architecture section 8) and deferred.
- **What is built:** The deterministic desktop application, confirmed launching and running on the lead designer's machine. Four layers, each covered by headless tests that were actually run:
  - `engine.py` — the engine ported from the authoritative preview (not the older `engine.mjs`, which lagged on routine ordering). `test_engine.py`: 19 checks, including the manual untimed-routine order the JS suite never tested, and the protected-container guard.
  - `storage.py` — SQLite persistence with a migration chain. `test_storage.py`: 4 checks (first-run state, full save/reload round-trip, and a real v1 to v2 upgrade that preserves legacy data).
  - `app.py` — the pywebview bridge: `get_state` plus one command per UI action; structured logging to `~/.steward/steward.log`. `test_api.py`: 11 checks driving every command and a full database reopen.
  - `index.html` — the preview UI adapted to render from the bridge snapshot, preserving the dark-mode ledger aesthetic, kanban board, routines, today, editable history, drag-and-drop, dd/mm/yyyy, and the context export; with the version string in Settings and the Misc anchor icon added.
  - Supporting: `requirements.txt`, `RUN.md`, and double-click launchers (`setup`/`run` as `.bat` and `.command`).
- **Verified vs asserted:** Engine, storage, and bridge are covered by passing headless tests that were run. The window, the bridge end to end, and the visual feel were asserted in the sandbox and then confirmed running on the lead designer's machine, where the logging surfaced a cross-thread SQLite error that was fixed. Packaging to a standalone executable is not yet done.
- **Immediate next action:** Per the lead designer, either the container weekday-schedule design pass (item 1) or packaging to a standalone executable (item 3), plus two small follow-ups now in the backlog (expose container deletion, item 4; the Today drag-to-top reorder bug, item 5). The project is being handed to Claude Code for continued build.

---

## Backlog

Ordered by priority and dependency. Every item carries one lifecycle status:

- **Spotted** — identified and scoped; not yet being built. Covers raised bugs, pending design passes, and items blocked on a decision.
- **Ready** — greenlit to build: the design is settled and nothing blocks the work.
- **Awaiting test** — built and covered by passing headless tests; awaiting the lead designer's hands-on confirmation on a real run.

When confirmation lands, an item leaves the backlog: a genuinely new capability is written up as a feature in the Project Architecture (or folds into an existing feature description); a fix to existing behaviour just drops off, since its feature is already documented. Item numbers are stable references used elsewhere in this document, so a closed item is marked graduated rather than renumbered.

1. **Container weekday availability schedule.** Spotted (design). Top priority for the next design pass. Containers should carry a day-of-week schedule. Ready tasks in a container surface on the daily checklist automatically only on days that container is active per its weekday schedule (for example, "only work this project on Mondays"; "no work on weekends, but Home and Health still show up"). A manually added task overrides and always appears. This is distinct from the manual set-aside lifecycle state: it is automatic, recurring, per-weekday availability that feeds the daily draft. It is a genuine extension to the deterministic layer and wants its own design pass, including how it interacts with the lifecycle enum and the draft.

2. **Desktop application build.** Done — graduated out of the backlog (built, tested, and documented: see the Snapshot, Architecture §7, and the 2026-06-24 session log). The Python engine was ported from the authoritative preview with its own passing test suite; SQLite persistence with a migration chain was added and tested; the pywebview bridge exposes `get_state` plus one command per action with its own headless tests; the preview UI now renders from the bridge snapshot, with the version string in Settings and the protected Misc container with its anchor icon. Verified by the three headless suites and confirmed launching and running on the lead designer's machine. Packaging is split out as item 3.

3. **Package the desktop app as a standalone executable.** Ready (build). Bundle the Python runtime and the web view into one double-clickable artifact (PyInstaller or similar), per operating system, so the app runs without the setup and run scripts. The window, bridge, and persistence are already confirmed; this is the remaining piece of item 2. Known friction: the platform web-view runtime (Edge WebView2 on Windows, system WebKit on macOS, WebKitGTK or Qt on Linux), code-signing to avoid security warnings, and making sure `index.html` ships beside the bundled code. Interim, until this lands: a console-free Windows launch already exists — `run-quiet.vbs` and a pinnable `Steward` desktop shortcut, both via `pythonw.exe` (see `RUN.md`).

4. **Delete containers.** Spotted. The engine already supports a guarded, cascading delete: a protected container refuses, and deleting a normal container removes its tasks, routines, and their day-log records. No interface affordance is exposed yet. Add the UI path and finalize the UX: the confirmation copy, what the user is told about cascaded history, and whether an archive or close alternative should be offered alongside outright deletion.

5. **Bug: dragging an item to the top of Today's checklist does not register.** Awaiting test (bug). Root cause found: the `dragover`/`drop` handlers live only on `#todayList`, which has no top padding, so its box hugs the first card. A release aimed above the first card lands outside the box, where no handler exists, and the drop is lost; every other position sits inside the box and works. (The index math and the `reorder_today_item`/`sync_day` commit path were verified correct for index 0 — the board avoids the bug only because its handlers sit on the taller `.col`.) Fix: a top catch strip on `#todayList` (`padding-top:14px` in `index.html`) so a release just above the first card still lands in the list and maps to index 0. Added a bridge regression check that reordering a Today item to index 0 moves it to the front and persists (`test_api.py`). Awaiting the lead designer's confirmation on a real run that the top drop now registers; on confirmation this drops off the backlog (the Today drag-reorder feature is already documented).

6. **Blessed container shapes.** Spotted. Finalize the small sanctioned set of container patterns (for example, standing life-area and finite effort) that keeps the filing decision small and prevents organizational overhead.

7. **Product language.** Spotted. The user works in Portuguese and English. Decide whether the product operates bilingually or in one language. Likely bilingual; confirm.

### Raised in the 2026-06-24 daily-use review

Five adoption blockers the lead designer named before committing to daily use. Higher priority than the deferred AI layer below; numbered 15–17 only because item numbers are stable references (container deletion is already item 4). Items 4, 15, and 16 are the proposed next build batch — no design decisions, engine support already exists; item 17 wants a design pass first.

15. **Add containers with the same "+" affordance as tasks and routines.** Spotted. Containers are added through a separate "New area" form at the bottom of the Containers view (a name field plus an "Add container" button), inconsistent with the inline "+ add routine" affordance and the task "+". Replace it with the same inline "+ add container" pattern so adding an area matches adding a task or routine. UI-only; the `add_container` bridge command already exists.

16. **Data peace-of-mind: show where the data lives, and one-click backup.** Spotted. State is a single SQLite file at `~/.steward/steward.db` (on the lead designer's machine, `C:\Users\Pichau\.steward\steward.db`) — outside the project folder and the repo. The app never shows this, which feeds a fear of losing everything. Surface the exact path in Settings, add an "open data folder" affordance, and add a one-click "Back up database now" that copies the live file to a timestamped `.db` (the existing context export is AI text, not a backup). Needs a small bridge method to copy the file; the rest is UI.

17. **Today as a navigable single-day lens; History as the calendar (one shared day model).** Spotted (design). Today and History already read the same `day_log` — Today renders `currentDate`, History renders the frozen past. The ask: Today shows the date with prev/next buttons to move day to day, and History becomes a calendar over the same data, so the two are one-to-one; and the blunt "Start new day →" (a mis-click jumps forward with no way back) is retired. Crux to settle first: the engine invariant is "the live day re-syncs; past days are frozen" (`sync_day` must never run on a past day), yet `_snapshot` currently syncs whatever day it is handed — so backward navigation needs a defined notion of "the live day" and a rule for whether a past day is editable from the Today lens or only in History. Covers the review points "Start new day is weak" and "Today and History should be in sync." A prev/next pair also makes an accidental advance a one-click undo.

### Deferred: the AI facilitation layer

These sit on top of the deterministic core and are deferred behind the desktop build. They correspond to Architecture section 8.

8. **Selection and suppression tuning.** Spotted (deferred). The AI selector's draft-and-comment behaviour, the light-day pull-forward from staging columns, and the suppression decision. Mechanics tunable by simulation; the felt quality validated only through real use with retained redundancy.

9. **Conversational touchpoints.** Spotted (deferred). Morning agreement, evening contrast, weekly reflection, and conversational capture, layered over the deterministic draft and check-off.

10. **Routine baseline and permissioned self-update.** Spotted (deferred). A canonical baseline of the normal week, maintained by manual audit and a directional self-update rule (add on a clear statement; ask before edit or remove).

11. **Memory: remember/forget policy and index.** Spotted (deferred). The hardest case is the long tail of light tasks (unbounded growth, forgetting both valuable and dangerous). Criterion for every choice: does it increase trustable offload.

12. **Self-improvement and personality.** Spotted (deferred). Memory accretion, workflow self-improvement, optional code self-modification; the hot/cold loop split; and how the companion's personality forms over time with guardrails against undesirable drift.

13. **Local model selection.** Spotted (deferred). Validate that small local models can perform reliable task extraction and the peer-level judgment the companion needs; the live conversational judgment may need the frontier path. Test before committing.

14. **Routing and provider policy.** Spotted (deferred). Route by sensitivity, not task type (in Architecture). Candidate providers to evaluate: Claude for the capable path, Groq for fast free-tier access to several open models (Groq the inference provider, not Grok). Reconcile each provider's data-retention terms with the privacy goal.

---

## Decisions resolved (now in Architecture)

- **Stack.** pywebview (Python backend, web UI in a native window) with SQLite storage. Closes the former technology-stack question.
- **Build architecture (single command).** Python owns the engine and the SQLite state; the web UI renders from a snapshot and sends one command per action across the pywebview bridge; every command mutates the engine, saves to SQLite, and returns a fresh snapshot. The UI holds no engine logic. (Architecture section 7.)
- **Port source.** The Python engine was ported from the authoritative preview engine, not the older standalone `engine.mjs`, which lagged on untimed-routine ordering (it sorted alphabetically; the preview and the prose use the manual routine order). The Python tests assert the preview's behaviour, including the manual untimed-routine order.
- **Protected container.** A container may be protected; a protected container cannot be deleted; exactly one protected Misc is guaranteed, renamable and reorderable, with a distinct icon, produced by the migration chain. (Architecture sections 2 and 7.)
- **Persistence and migration.** SQLite tables mirror the model; the day log is reference-based via foreign keys; saves are full transactional rewrites; the completion cache is persisted and trusted on load; schema evolution is a migration chain run identically on fresh installs and upgrades. (Architecture section 7.)
- **Versioning.** An integer schema version in the database drives migrations; a separate human-facing display version (the `0.01.00a` scheme: zero-padded number segments, trailing letter per bug-fix attempt) is shown in Settings. (Architecture section 7.)
- **The day log.** A log keyed by date, whose entries are lightweight references to live generators rather than denormalized copies, so renames and re-filing propagate. The store owns every day; the current day re-syncs, past days are frozen.
- **Single completion and one record per day.** A task has one completion date; completing on an earlier day clears later not-done records; there is at most one record of a task on a day. Routines may have two on a day (scheduled plus one-off).
- **Completion as cache.** `task.completed` is derived from the day log; completed tasks persist hidden, not deleted.
- **Routines off-states.** A temporary active toggle and a permanent archive, distinct.
- **One-offs.** Explicit off-schedule routine occurrences, sticky across reschedule, toggle, and set-aside; a scheduled-day log with no record yet fills the scheduled slot rather than creating a one-off.
- **Container lifecycle / set-aside.** The enum {active, completed, cancelled, planned}; "planned" is the set-aside state, freezing contents in place and surfacing nothing until reactivated. Closes the former dormancy question.
- **Container deletion.** A separate operation from lifecycle; deleting a container cascades to its tasks, routines, and their records; a protected container refuses. (Engine behaviour settled; exposing it in the interface is backlog item 4.)
- **Columns.** Tasks sit in one of four named columns, Idea, Planned, Soon, Ready; only Ready feeds the day; the other three are inactive staging columns for structure and future AI context. Closes the former column-nomenclature question.
- **Routines are not on the column model.** Corrected from an earlier documentation error; routines are ordered by schedule and a manual order.
- **Urgency.** Fully absorbed by the column structure and routine schedules; not a separate authored signal. Closes the former urgency question.
- **Deterministic-first framing.** The system is a task and routine manager at its core and works with no AI; AI is additive and never load-bearing.

---

## Decisions awaiting the lead designer

- **Container weekday schedule** (item 1): the design itself, and how it sits alongside the lifecycle enum and the daily draft.
- **Delete-containers UX** (item 4): the confirmation copy, how cascaded history is communicated, and whether an archive or close alternative sits beside outright deletion.
- **Blessed container shapes** (item 6): whether to lock them now or after more design.
- **Product language** (item 7).
- **Today/History model** (item 17): what counts as "the live day," whether a past day is editable from the Today lens or only in History, and the prev/next interaction — settle before code, since it bears on the frozen-past-day invariant.
- The shape and sequencing of the **AI facilitation layer** (items 8 to 14), once the deterministic desktop build is in hand.

---

## Session log

Newest first. Each session appends what it advanced or decided.

### 2026-06-24 (Claude Code — continued build)

- Renamed the project from the artifact name "Custodian" to "Steward" across all source, docs, and config: the env vars (`STEWARD_HOME`, `STEWARD_DEBUG`), the `~/.steward/steward.db` and `steward.log` paths, the window title, the logger name, and the test fixtures. Left the one metaphorical use of the common noun "custodian" in the Vision untouched. All 34 headless checks still pass.
- Revised `.gitignore` ahead of the git repo: dropped entries copied from an unrelated "SpeakSelection" project and added Steward's runtime data (`.steward/`, `*.db` and its WAL sidecars).
- Adopted a backlog lifecycle — **Spotted → Ready → Awaiting test → graduate** — and recorded it as the legend at the top of the Backlog. Migrated every item to it. Item numbers are kept as stable references.
- Item 5 (Today drag-to-top bug): found the root cause — the reorder `dragover`/`drop` handlers sit only on the tight `#todayList` box, so a release above the first card falls outside it and is lost. Verified the index math and the engine commit path are correct for index 0. Fixed with a top catch strip on `#todayList` in `index.html`, and added a bridge regression check in `test_api.py` (reorder to index 0 → front, persists). Now **Awaiting test**: needs hands-on confirmation that the top drop registers.
- Added a console-free Windows launch for daily use (the lead designer is adopting the app now): `run-quiet.vbs` starts the app via the venv's `pythonw.exe` so no console window appears, plus a pinnable `Steward` desktop shortcut to the same. `run.bat` stays for troubleshooting (it keeps a console to show crashes). Documented in `RUN.md`; noted under item 3. Login auto-start was offered and not set up. Awaiting confirmation that the shortcut launches cleanly.
- Daily-use review: the lead designer named five adoption blockers. Confirmed the data is a single SQLite file at `~/.steward/steward.db`, outside the project and the repo (32 KB, already holding his test data). Registered the blockers — container delete (existing item 4), container "+" add (item 15), data peace-of-mind/backup (item 16), and the Today single-day-lens + History calendar model (item 17, design) — and proposed items 4/15/16 as the next build batch (no design decisions, engine support exists). Docs updated; no app code changed this turn.

### 2026-06-24

- Built the standalone desktop application (former backlog item 2, now DONE). Four layers, each verified by headless tests that were actually run: a Python engine ported from the authoritative preview (`engine.py`; 19 checks, including the manual untimed-routine order the old JS suite never tested, and the protected-container guard); SQLite persistence with a migration chain (`storage.py`; 4 checks: first-run state, full round-trip, and a real v1 to v2 upgrade preserving legacy data); a pywebview bridge exposing `get_state` plus one command per action (`app.py`; 11 checks driving every command and a full reopen); and the preview UI adapted to render from the bridge snapshot (`index.html`), preserving its aesthetic, with the version string added to Settings and the Misc anchor icon.
- Adopted the single command architecture: Python owns the engine and the SQLite state; the UI renders a snapshot and sends one command per action; every command mutates, saves, and returns the fresh snapshot. Settled in Architecture section 7.
- Added a protected Misc container as a deliberate deviation from the preview: undeletable so the project always keeps a home for tasks, renamable and reorderable, with a distinct anchor icon, guaranteed by the migration chain on both fresh installs and upgrades.
- Adopted the version scheme: a display version `0.01.00a` shown in Settings (zero-padded segments, trailing letter per bug-fix attempt), kept separate from the integer schema version that drives migrations.
- Flagged and resolved a discrepancy: the standalone `engine.mjs` lagged the preview, sorting untimed routines alphabetically where the preview and the prose use the manual routine order. Ported from the preview engine and added the routine-order test the JS suite was missing.
- Added structured logging to `~/.steward/steward.log` and the console.
- Confirmed the application launches and runs on the lead designer's machine. The logging immediately surfaced a cross-thread SQLite error (pywebview dispatches bridge calls on threads other than the one that opened the connection); fixed by opening the connection with `check_same_thread=False` and serializing every bridge call with a lock, and verified the cross-thread path headlessly.
- Handed the project to Claude Code for continued build. Registered three backlog items: package to a standalone executable (item 3), expose and finalize container deletion (item 4), and a Today drag-to-top reorder bug (item 5).

### 2026-06-22

- Reframed the project as deterministic-first. The system is a task and routine manager at its core and must work with no AI; the AI features are an additive facilitation layer that never replaces core functionality. Rewrote the Vision around this, and restructured the Architecture into a deterministic core plus a planned AI layer on top.
- Reshaped the data model to a reference-based day log: entries are lightweight references to live generators, so renaming or re-filing propagates to all history. The store owns every day; the current day re-syncs while past days are frozen.
- Settled completion semantics: a single completion date per task; completing on an earlier day clears later not-done records; at most one record of a task per day; `task.completed` is a cache and completed tasks persist hidden.
- Settled routines: corrected the earlier error that placed importance on routines (routines are not on the column model); added the temporary active toggle versus permanent archive distinction; defined one-offs as sticky off-schedule occurrences, with a scheduled-day log filling the scheduled slot rather than creating a one-off; added a manual routine order driving untimed-routine draft order.
- Named the task columns Idea, Planned, Soon, Ready, with only Ready feeding the day and the other three as inactive staging columns for structure and future AI context. Resolved that "planned" (container lifecycle) is the set-aside state, and that urgency is fully absorbed by columns and schedules.
- Decided the stack: pywebview plus SQLite. Closes the technology-stack question.
- Built and verified the deterministic core as a single-file HTML preview with an embedded reference-based engine, iterated over several rounds (kanban board, routines screen with inline editing and drag-reorder, today checklist, editable history with ad-hoc logging, drag-and-drop, dd/mm/yyyy display). Model logic is covered by a passing Node test suite; rendering and interaction are asserted and confirmed by opening the preview in a desktop browser.
- Registered a new design item at the top of the backlog: container weekday availability schedules.

### 2026-06-19

- Specified the selector's input/output contract (then backlog item 1), moving it to DONE with a few small residual opens. (Subsequently recontextualized: the deterministic draft is the built core, and the AI selector is the planned layer on top. See 2026-06-22.)
- Collapsed the multi-force model to a single authored importance value realized as the kanban column, with a strict within-column position as the only tiebreaker. (Subsequently: columns renamed and reframed; routines removed from the model. See 2026-06-22.)
- Settled that containers carry a lifecycle status enum {active, completed, cancelled, planned} and no importance number; only active containers feed the daily draft.
- Retired the other forces as authored signals: urgency absorbed into columns and schedules; neglect and variety left to optional AI judgment from context; fit made non-numeric.
- Confirmed the touchpoints are bidirectional capture-and-consume surfaces. (Now a property of the AI conversational layer; the deterministic core captures via the board and routines views.)
- Ran the charter's strongest-case-against on the lean output (suppression leaves no contemporaneous record) and resolved it by the weekly sweep plus on-demand reachability.
- Restructured the documentation from three documents to four, splitting the stable Vision from the settled Architecture and adopting the boundary rule.

### 2026-06-13

- Completed Phase 1 design exploration end to end.
- Established the core reframe of that stage: the product is trusted offload, not planning; the companion is a dry, competent peer; offload is gradual and trust-earned with user-held redundancy.
- Settled the first architecture: containers (finite or standing) holding generators (recurrent routines, single tasks) that emit disposable daily items; ladders for lifecycle and importance; three touchpoints (morning, evening, weekly).
- Settled the routine subsystem (reverse log against a canonical baseline) and the selector concept (balance of forces, suppression as the hard half).
- Produced the Project Vision document and split working state into this Project Status document.
