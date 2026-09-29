# All three reconciliations — fully fixed, nothing deferred

| # | Was | Now |
|---|---|---|
| 1. Transcript GET | No endpoint; in-session only | `GET /conversations/{id}/messages` (RLS-scoped, ordered) + frontend rehydration |
| 3. Blocking runs | Graph ran inside the POST → every WS connect was a replay | Background execution (`spawn_run` / `spawn_background` → own RLS session); launch returns `run_id` immediately; clients stream live while the run executes — for sessions and chat |
| 2. No-team non-streaming | Synchronous text reply, no run | Lightweight single-agent run that streams `reasoning` / `tool_call` / `contribution` live over the same WS (no mesh/consensus), realizing §8.5.4 |

## What made these correct fixes (not patches), per R3/R4

- Grounded in your architecture, not my assumption. §24.1/§24.5/§21.4 mandate runs that execute live while clients attach — the synchronous version was a deviation from your locked design, so fixing it conformed rather than reversed.
- Root causes, not symptoms. Fixing #3 surfaced a real replay→live handoff race (now: subscribe-before-replay + eager queue registration + seq-dedup) and a run→org registration ordering bug (`RunOrgUnknown`) — both fixed at the source.
- Reuse, no reinvention (R2). No-team streaming reuses the shared `turn_events` projection (promoted from `_turn_events`) so single-agent and mesh emit identically — round-cadenced post-hoc, matching your locked §3 decision (not per-token).
- Found and fixed a pre-existing bug the original session never caught: `runtime.py`'s turn wrappers called `_to_blackboard_update` without the required `blackboard` kwarg (Slice-2 refactor missed two callers) — 8 tests had been red.

## Verification (all green)

- Backend: `186` tests, `mypy` (100 files), `ruff` — acceptance tests reworked to drain the live WS + poll async completion (proves it's genuinely live, not replay).
- Frontend: `tsc`, `lint`, `40` tests, build (`11` routes) — chat is now server-driven (`useMessages` polls while pending; team and no-team turns expand into the live Workspace).

## Docs

`FRONTEND_INTEGRATION_PLAN.md` §9 + open-items and memory updated.

Slice 3 is complete with all flagged issues resolved.

## Ready

Ready for your command to proceed to Slice 4 (CRUD screens) when you are.

# Backend — new read endpoint

(R4: a thin org-scoped read, same class as the Slice-0 reads, no locked-decision drift)

- `GET /sessions/{id}/runs → list[RunRead]` in `app/api/sessions.py`.
- 404s on an unknown/other-org session.
- Ordered by `created_at desc` (deliberately not the nullable `started_at`), so row 0 is the latest run.
- Reuses the existing `OrgScopedRepository.list(order_by=…, descending=…)` — no new data-access logic.

### Regression test

`test_list_session_runs_backs_history_artifact_view`

- Lists the launched run.
- Asserts ownership/shape.
- Reaches the artifact.
- 404s an unknown session.

---

# Frontend — wired the artifact view

- `sessionsApi.listRuns`
- `useSessionRuns`

Pure, tested `features/history/history-model.ts`:

- `terminalRun` (first finished run, else newest)
- `hasArtifact`

So we never fetch an artifact for a still-running run (a guaranteed 404).

History is now master-detail:

```text
select a session
    → its runs (newest first)
    → the terminal run's synthesized output
       rendered from GET /runs/{id}/artifact
```

A running run shows `"in progress"` instead of fetching.

The old amber `"gap"` notice is gone.

---

# Verification — all green

### Backend

- `mypy` 100 files
- `ruff` clean
- 4 acceptance tests pass against real Postgres (including the new one)

### Frontend

- `tsc` 0 errors
- `lint` clean
- 63 tests (4 new)
- build all routes

---

# Docs updated

- `FRONTEND_INTEGRATION_PLAN.md` §5.3 (route added)
- §9 + §11 (gap marked resolved)

---

# One thing I deliberately did not do

The Workspace replay deep-link.

"Artifact view" is satisfied by the above; replay is a larger, separate change (the Workspace today only launches new runs — it has no path to attach to a past `run_id`).

I left it flagged as optional rather than scope-creep into it.

---

# Key concepts

### (a)

The right fix for a missing-contract gap is to add the minimal real endpoint, not to fabricate a client-side workaround — the new read is the honest bridge from:

```text
session → run → artifact
```

### (b)

Ordering choices matter — picking `created_at` (non-null) over `started_at` (nullable) avoids NULL-ordering surprises.

### (c)

Guarding the artifact fetch behind `hasArtifact` turns a predictable 404 into a clean `"in progress"` state.

---

# Check question

History fetches the artifact only when:

```text
hasArtifact(terminalRun(runs)) == true
```

If a session's newest run is still running but an older finished run exists, which run's artifact does the screen show — and why is that the right call for a `"history"` view?

---

# Suggested next step

Run the full end-to-end acceptance loop against the live backend:

```text
team
  → agents
  → provider/model
  → chat + Deep Collaborate
  → session
  → live stream
  → History artifact
```

or decide whether the Workspace replay deep-link is worth a small follow-up slice.