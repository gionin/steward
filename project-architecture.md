# Project Architecture: Trusted-Offload Assistant

This document describes how the system is built: the settled mechanical design that realizes the Project Vision. The Vision says why the system exists and what it is meant to feel like; this document says how the pieces work. It is stable and changes only when a design decision changes it. Current progress, open questions, and the decision history live in the Project Status document. It assumes the Collaboration Charter.

---

## 1. Two layers

The system is built in two layers, and the order between them is a rule, not a convenience.

The **deterministic core** is a complete task and routine manager that works on its own, behaving exactly as the user authored it. It is what is built today, and sections 2 through 7 specify it.

The **AI facilitation layer** sits on top of that core. It adds smarter daily selection, confident suppression, and conversation. It is designed but not yet built, and it never replaces core functionality: removing it entirely would leave a working manager. Section 8 describes it, and section 9 describes the gradual-trust principle that governs it.

Work is organized into **containers** (areas of life or finite projects). Containers hold **generators**: recurring routines, and single tasks. Generators emit **disposable daily items** into a given day, and a **day log** of lightweight references records what actually happened. From those records the system derives a daily checklist and keeps a history.

---

## 2. Data model: containers, generators, day log

**Containers.** A container is a named grouping of related tasks and routines, with a name, description, and metadata. Whether a container ends is a property of the container, expressed through its lifecycle status (section 3), not part of its definition. A container may hold any mix of tasks, routines, and finite sub-efforts. A small number of catch-all standing containers (for example a general Misc) absorb loose light tasks so that quick capture never requires a filing decision.

**Protected containers.** A container may be **protected**. A protected container cannot be deleted, which guarantees the system always keeps at least one home for tasks. Exactly one protected container, named **Misc** by default, is guaranteed to exist (section 7). It can be renamed and reordered like any other and carries a distinct icon, so its special behavior stays recognizable even after a rename; deletion is the only thing it refuses.

**Generators.** Two kinds. A **routine** (recurrent generator) is scheduled by days of the week. A **task** (single generator) resolves once. Generators are the persistent sources; the records they produce for a given day are disposable.

**The day log.** The system keeps a log keyed by date. Each entry is a lightweight **reference**, holding only a source type (task or routine), a source id, a done flag, and a one-off flag. It points at the live generator rather than storing a copy of it. The consequences are deliberate:

- Renaming a generator, or re-filing it into another container, propagates to every past record at once, because the records read the generator's current name and container rather than a snapshot.
- The store owns every day's record. The current day is the only one that re-syncs to changes in the backlog; past days are frozen and change only through explicit history edits.

**The disposable layer.** Generators emit disposable daily items; the day log records what happened to them. This puts a barrier between what a generator is scheduled to produce and what is actually recorded for a day. A routine that fell on a day but was never done is recorded once as not done, rather than lingering as a standing obligation. This barrier is the seam at which the AI layer's morning agreement will later sit (section 8), but the layer itself, the separation between schedule and record, is part of the deterministic core.

**Light tasks.** A light, standalone task is simply a task in a catch-all container. Grouping tasks under containers preserves their relative order through a postponement: when a container is set aside, its contents freeze in place and keep their internal ordering (section 3), so that on the container's return the tasks come back in the order they held.

---

## 3. Tasks: columns, position, completion, lifecycle

**Columns.** A task sits in one of four columns: **Idea, Planned, Soon, Ready**. The column is a single authored placement, expressing how far along the task is from someday-idea to actionable-now. Only **Ready** feeds the daily checklist. Idea, Planned, and Soon are inactive staging columns: they hold tasks that are not yet on deck, give the backlog structure, and provide context for the future AI layer, but they have no behavior of their own at present and may gain column-specific behavior later. The names are settled.

**Position.** Within a column, every task holds a strict **position**, unique within that column, with no ties. Position is a manual ordering, and in Ready it is the do-first order in which tasks appear on the daily checklist. Because no two tasks share a position, the column decides whether a task is on deck and position decides the order, and the two never compete.

**Completion.** A task has a single completion: exactly one done date. Marking it done on one day clears any other day that had it marked done, so completion can be moved but never duplicated. Completing a task on a given day also clears any not-done records of that task on later days, since once finished it would not have appeared again. There is at most **one record of a given task on a given day**; logging or completing it reuses that day's record rather than adding a second. (Routines are not bound by this; see section 4.)

`task.completed` is a **cache**, true exactly when some day record marks the task done. A completed task is not deleted; it persists, hidden from the board, and remains in history. Removing its last done record reverts it to an active task.

**Lifecycle.** Lifecycle belongs to the container and is a status enum: **active, completed, cancelled, planned**. Only **active** containers feed the daily draft. **Planned** is the set-aside state: setting a once-active container to planned removes its tasks and routines from the day at once, freezes them in place with their columns and positions intact, and surfaces nothing of their contents; returning it to active restores them in the order they held. Completed and cancelled are the terminal states of a finite container.

**Deletion.** Deletion is a separate operation from lifecycle, not one of its states. Deleting a container cascades to its tasks, routines, and their day-log records; deleting a task removes the task with all of its records. A protected container (section 2) refuses deletion.

---

## 4. Routines

A routine is **not** placed on the column model. (An earlier version of this document applied importance, the column, to both tasks and routines; that was a documentation error and is corrected here.) Routines live on their own and are ordered by schedule and by a manual routine order, not by column.

A routine carries a name, a container, a days-of-the-week schedule, an optional time, and an optional duration. Duration and schedule together yield an emergent hours-per-week figure. A routine has two distinct off-states:

- **Active toggle.** Turned off, the routine is still listed and can still take a one-off, but it emits no scheduled occurrences. This is a temporary pause.
- **Archive.** An archived routine emits nothing at all, drops out of the active list, and keeps its history. This is a permanent retirement, reversible by restoring it.

**One-offs.** A one-off is an explicit occurrence of a routine on a day outside its schedule. One-offs are sticky: they survive a change of schedule, an active-toggle off, and a container set-aside. Logging a routine on a day it **is** scheduled, when no record for it exists yet that day, fills the scheduled occurrence and is not a one-off; a second log on the same day, or a log on an unscheduled day, is a one-off. A scheduled occurrence and a deliberate one-off can therefore coexist on the same day, while merely forgetting and re-logging never produces a duplicate.

**Reverse log.** Routine history is a record of what was actually done, reported after the fact and editable later, rather than a forward checklist ticked in advance. Routines never roll over: a routine appears only on the days it is scheduled, a missed scheduled day is recorded once as not done, and nothing accumulates.

**Routine order.** Routines carry a manual order. It governs where untimed routines fall in the daily draft (section 5) and how routines are grouped under their containers in the routines view.

The routine canonical baseline, and permissioned self-update of it, belong to the AI layer (section 8). The deterministic core records routines and their occurrences; it does not maintain a learned baseline.

---

## 5. The deterministic daily draft

Each day the system derives a checklist deterministically from the active containers. The order is fixed: timed routines due today, by time; then Ready tasks, by position; then untimed routines due today, by the manual routine order. Only Ready tasks and routines due today appear. The rest of the backlog stays off the day.

The checklist is **disposable and regenerated**. An unfinished Ready task is re-derived onto the next day, because it is still ready and still unfinished. Routines never roll over. The current day re-syncs to membership changes as they happen: setting a container aside removes its items from today at once, while an item already checked stays visible as long as its container is active. Reordering items within today is ephemeral, a rearrangement of that day's records that never touches a generator's stored position.

**One record, two views; nothing is frozen.** Today and History are two lenses on the same per-day record: a day's items are the same day-log entries in both. Today is the single-day lens — it opens on the current day and steps day to day with prev/next and a jump-to-today control, which retires the old one-way "start new day"; History is the calendar overview of those same records. Every day is editable, the past included.

**The schedule flows forward; the past is a record.** Deriving a day from the schedule applies to the current day and to any future day reached by navigating ahead, where it shows that day's scheduled **routines only** — open Ready tasks are not projected ahead, since they belong to the current day and roll forward only as it advances. Past days are never re-derived: each keeps the record of what was actually drafted and checked, so adjusting a routine today never rewrites an earlier day; a skipped past day can be reconstructed on demand by pulling its scheduled routines in. An unchecked item carries **no failure framing** — in the past it reads as simply not done, in the future as still to come.

This deterministic draft is the real mechanism, not a placeholder. The AI selection described in section 8 operates on top of it and never replaces it.

---

## 6. History and rhythm (deterministic)

**History** is the calendar view of the day log and the day log made editable — the same per-day records the Today lens shows (section 5), in a different lens. Within it the user can check or uncheck a record, rename a task or routine (which edits the generator and so propagates everywhere), move a record to another day, drag records to reorder within a day or move them between days, and delete an individual record. The user can also log activity after the fact, a new or existing task or routine, as done or as not done, with the single-completion and one-record-per-day rules enforced. Logging an existing task as not done on a day later than its recorded completion prompts before resolving the contradiction; moving a completed record ahead of later unfinished records of the same task prompts likewise.

**Rhythm.** In the deterministic core the rhythm is: a daily checklist derived each day, the user checking items off, and history holding the record of what happened. Organizing the backlog, moving tasks between columns, adjusting routines, setting containers aside, is manual, done in the board and routines views. A weekly review, and the promotion and demotion of items between days and columns, are part of the richer rhythm the AI layer adds (section 8); the core does not move items on the user's behalf.

**Context export.** A function emits the current state as text. It is the deliberate seam at which the AI layer attaches to the deterministic core, and it is realized as part of the bridge described in section 7.

---

## 7. Realization: process, persistence, and versioning

The deterministic core above is realized as a desktop application. Python owns the engine and the stored state; the interface is a web view that renders and captures events only. The shape is a **single command boundary**: every user action sends one command to Python, Python mutates the engine and writes the result to the store, then returns a fresh snapshot of the state for the interface to draw. The interface holds no engine logic and no authority of its own; it is a renderer over a snapshot the engine produced. This is the same seam the AI layer will sit behind later (the context export of section 6 is one face of it), so the boundary is drawn once and reused.

**Persistence.** The store is a SQLite database whose tables mirror the model: containers, tasks, routines, the dated day log, and a small meta table. The day log's reference nature is native to the store: each entry holds a foreign-key reference to its live generator, so a rename or a re-filing is read through at query time and never stored as a copy, exactly as section 2 requires. Each save is a full, transactional rewrite of the data tables, which keeps the file an exact image of the engine and is the least error-prone option at personal scale. The completion cache (`task.completed`) is persisted and trusted on load; the day log remains the source of truth, and the engine keeps the two in agreement.

**Migration.** Schema evolution is a chain. A schema version of N means N migrations have been applied; a fresh database starts at zero and runs every migration up to the current version, so the create path and the upgrade path are the same code and the chain is exercised on every fresh install. This is what lets a newer build open an older database and carry the data forward without loss. The protected Misc container (section 2) is produced by this chain rather than by separate seed code, so a fresh install and any older file both arrive at the same guaranteed first-run state.

**Versioning.** Two numbers, deliberately separate. An integer **schema version** lives in the database and is the only thing that drives migrations. A human-facing **display version** is shown in Settings, written as `0.01.00a`: zero-padded number segments leave headroom, and a trailing letter steps a, b, c with each bug-fix attempt and resets when a number changes. The display version is for the person; the schema version is for the engine; neither is derived from the other.

---

## 8. Planned: the AI facilitation layer

This layer is designed but not built. It sits on the deterministic core, draws on the same data, and never replaces core functionality; with it removed, a complete manager remains. Its detailed open questions live in the Project Status document.

**Selection and suppression.** On top of the deterministic draft, an AI selector judges the drafted day: whether it looks like too much for one day, framing that as a question when in doubt; pulling candidates forward from the staging columns when the day is light; and, most valuably, **suppressing**, confidently setting items aside so the user can stop holding them, and being right often enough to be believed. Wrongly suppressing something important is the gravest error, while wrongly surfacing something is minor. The safety of suppression does not rest on emitting a record of each decision; it rests on the user's retained redundancy, on a weekly sweep of the held-back remainder, and on that remainder being reachable on demand through ordinary conversation.

**Conversation.** The morning, evening, and weekly touchpoints become short conversations rather than a derived list and a check-off: a morning agreement on what today's list should be, an evening contrast between intention and reality, and a weekly reflection that carries the sense of accomplishment finite projects deliver through completion. Capture by conversation files an item into a container and makes it a candidate at once.

**Routine baseline and self-update.** The system holds a canonical baseline of the user's normal week, maintained by periodic manual audit and by a permissioned self-update: it adds to the baseline autonomously when the user states something clearly, simply reporting that it did so, and asks before editing or removing anything.

**Self-improvement.** Memory accretion (learning the user's containers, people, and shorthand), workflow self-improvement (revising its own prompts and rules from observed corrections, snoozes, and rot), and, in its safe form, proposing changes to its own implementation for the user to apply. A hot loop of small local models runs continuously for capture, parsing, and classification; a cold loop runs rarely on a frontier model, recorded as a reversible changelog.

**Models, routing, security.** Local-first, with frontier-model calls the exception. Routing is governed by sensitivity rather than task type: personal content stays local or goes to a paid, privacy-respecting API, while only sanitized or generic work is sent to a free tier.

**Memory.** A selective memory that decides what to remember and what to let go, paired with an index for retrieval. The hardest case is the long tail of light tasks, where unbounded growth is a risk and forgetting is both valuable and dangerous. Every choice answers to a single criterion: whether it increases trustable offload.

---

## 9. Gradual trust and authority

The deterministic core is reliable by construction and needs no trust earned. This section governs the AI layer of section 8.

That layer's authority is a deliberate, adjustable property that scales with demonstrated reliability. Early, it surfaces and the user decides; later, it holds more back on the user's behalf. Because its central act, deciding what the user can stop thinking about, cannot be verified from the inside, the user's retained redundancy is the safety net beneath it, and that is what lets the layer earn its role gradually rather than having to be reliable from the start. The quality of selection and suppression is partly experiential and is validated only through real use with redundancy retained, not in the abstract.
