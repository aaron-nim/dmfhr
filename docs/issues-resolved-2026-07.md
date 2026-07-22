# Issues resolved — July 2026

What / why / how for each issue diagnosed and fixed in this cycle. Host names,
addresses and account identifiers are deliberately omitted — this repo is
public. Operational specifics live in the private ops notes.

---

## 1. "Only admins can create Objectives" (PMS)

**What.** Users holding full PMS privileges could not see the "+" create
button on the Objectives page — only superusers could, regardless of the
roles or permissions granted. To the client this looked like a
role-configuration problem, but no configuration could ever fix it.

**Why.** The template gated the button on `perms.pms.add_objectives` — a
permission that does not exist (the real model permission is
`add_employeeobjective`). A check against a non-existent permission is false
for everyone except superusers, who bypass permission checks entirely.

**How.** One-line template fix (`add_objectives` → `add_employeeobjective`,
commit `d3ab64722`), aligning the button with the permission the create view
(`pms.views.objective_creation`) actually enforces. Verified end-to-end on
staging with a non-admin test user: button appears → form opens → objective
created → deleted. Live on production.

---

## 2. Production ran with development settings

**What.** Production served with `DEBUG=True` (full tracebacks exposed on any
error), Django's publicly-known default `SECRET_KEY` (which signs sessions —
forgeable), `ALLOWED_HOSTS=['*']`, and non-secure cookies.

**Why.** The host never received a `.env` file, so settings silently fell
back to the development defaults baked into the repo. Nothing visibly broke,
so it went unnoticed.

**How.** Created a production `.env` (DEBUG off, freshly generated unique
secret key, real allowed hosts, secure cookies + HSTS), validated with a
dry-run `manage.py check` in a separate process before restarting, then
verified live via response headers and a real login. No data touched; one-off
logout for all users as sessions re-keyed.

---

## 3. Production database was a single SQLite file

**What.** All live HR data sat in one ~179 MB SQLite file (named
`TestDB_…`), with no concurrent-write safety and a weak backup story.

**Why.** Horilla defaults to SQLite; the original provisioning never switched
it, and nothing forced the issue until real multi-user load arrived.

**How.** Migrated to PostgreSQL by copy, not conversion in place: full
export/import (338 tables, verified zero row-count mismatches), the SQLite
file kept untouched as a rollback anchor, cutover only after verification,
confirmed by real user logins.

---

## 4. Daily "Server Error (500)" bursts after the PostgreSQL migration

**What.** Production began throwing daily bursts of 500s — tens of thousands
of `FATAL: remaining connection slots are reserved` errors over three days —
each burst ending only when gunicorn force-killed a frozen worker.

**Why — two layers.**

*Direct cause:* Horilla starts its APScheduler background schedulers at
import time inside **every** web worker, and Django only closes database
connections on the web-request cycle — never for background threads. Each
scheduler pool thread therefore pinned one PostgreSQL connection **forever**.
With 7 scheduler modules × several workers, most of `max_connections` was
held by connections idle for days; normal traffic exhausted the rest. This is
an upstream Horilla bug — invisible on their default SQLite (no connection
limit), fatal on PostgreSQL. Upstream (checked at 1.6.0 / dev-2.0) has no
fix to cherry-pick.

*Aggravating cause:* with several workers, every background job also fired
once **per worker** — concurrently. This silently created duplicate work
records and duplicate draft payslips (the relevant uniqueness constraints
are missing or commented out upstream).

**How** (commit `cd288dffa`; both changes shipped together after an
adversarial multi-agent review):

1. **Release connections** — `horilla/scheduler_utils.close_db_connections`
   wraps all 25 job callables: it closes the thread's DB connections when the
   job finishes and discards dead/stale ones on entry (so a connection killed
   server-side can never wedge a job permanently). Inert inside atomic blocks
   so tests and synchronous callers are unaffected.
2. **Run once, not N×** — schedulers now start only in a dedicated
   `horilla-scheduler` systemd service running `manage.py run_schedulers`
   (template: `docs/deploy/horilla-scheduler.service`). Web workers start
   zero schedulers. The gate requires both the `run_schedulers` entry point
   (argv) and `HORILLA_RUN_SCHEDULERS=1` from the unit environment — the
   argv factor exists because settings exports `.env` into `os.environ`, so
   an env-var-only gate could be silently re-enabled from config.

**Proof (staging):** idle DB connections dropped from 48 to ~1 and never
climbed across sustained sampling; jobs verified running on schedule (the
attendance job logs every 30 minutes, single-fire through the daily 00:30
cron that previously triple-fired); zero job errors.

**Deploy note:** because web workers no longer run any schedulers, deploying
this change **requires** installing and starting `horilla-scheduler.service`
on the host — see the checklist in
[deployment-and-environments.md](deployment-and-environments.md). Without it,
background jobs stop silently.

---

## 5. Near-miss: infrastructure identifiers almost published

**What.** A docs commit was blocked moments before publishing server address
and account identifiers to this public repository.

**Why.** The repo is a public fork; deployment docs were first drafted with
host-specific values.

**How.** All host identifiers were scrubbed to placeholders before anything
was pushed, a leak scan now precedes such commits, and the standing rule is
recorded here and in the deploy docs: **no server addresses, account names,
or host identifiers in this repository.** Making the repository private
remains the recommended follow-up.

---

## Open follow-ups

- Deploy the scheduler fix to production (with the mandatory
  `horilla-scheduler.service` install).
- Audit and clean duplicate work records / draft payslips created by the
  historical per-worker triple-firing.
- Host resources: the production machine is memory-constrained and swaps
  under nightly maintenance; an upgrade is recommended.
- Make this repository private.
