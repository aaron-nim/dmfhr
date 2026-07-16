"""
scheduler_utils.py

Shared helpers for the APScheduler background jobs registered by the various
``*/scheduler.py`` modules.
"""

import functools
import os
import sys

from django.db import connections

# Defense-in-depth only: the primary gate is the run_schedulers argv check in
# schedulers_enabled(). These commands never start schedulers even when run
# with the scheduler service's environment loaded.
NON_SERVING_COMMANDS = [
    "makemigrations",
    "migrate",
    "compilemessages",
    "flush",
    "shell",
    "test",
    "collectstatic",
]


def schedulers_enabled():
    """Whether this process may start APScheduler background schedulers.

    Background jobs must run in exactly one process. Historically every
    gunicorn worker imported the scheduler modules and started its own copy,
    so each job fired once per worker (duplicate work records / payslips) and
    every scheduler thread pinned a database connection forever, exhausting
    PostgreSQL's max_connections. Two conditions, both required:

    * The process is the dedicated scheduler entry point (``manage.py
      run_schedulers`` — checked via argv). gunicorn and other management
      commands can never satisfy this, which also makes a stray
      ``HORILLA_RUN_SCHEDULERS`` line in ``.env`` harmless: settings exports
      ``.env`` into ``os.environ`` (``read_env(overwrite=True)``), so an
      env-var-only gate could be silently re-enabled in every web worker
      from the project's own config file.
    * ``HORILLA_RUN_SCHEDULERS=1`` in the environment, set by the systemd
      unit (see docs/deploy/horilla-scheduler.service) — a second factor so
      a casual ``manage.py run_schedulers`` on a dev box stays inert.
    """
    if "run_schedulers" not in sys.argv:
        return False
    if any(cmd in sys.argv for cmd in NON_SERVING_COMMANDS):
        return False
    return os.environ.get("HORILLA_RUN_SCHEDULERS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _close_thread_connections(force=False):
    # Connections inside an atomic block are left untouched: closing one
    # mid-transaction poisons the transaction (closed_in_transaction), which
    # would break jobs invoked directly from TestCase tests.
    for conn in connections.all(initialized_only=True):
        if conn.in_atomic_block:
            continue
        if force:
            conn.close()
            continue
        conn.close_if_unusable_or_obsolete()
        # With CONN_MAX_AGE=0 (project default) the call above has already
        # closed the connection. If CONN_MAX_AGE is ever raised, a connection
        # killed server-side survives it (errors_occurred stays False), so
        # probe and drop it here instead of failing the next job run.
        if conn.connection is not None and not conn.is_usable():
            conn.close()


def close_db_connections(func):
    """Release this thread's DB connections after a scheduled job runs.

    Django only closes connections via the request_started/request_finished
    signals, which never fire in APScheduler pool threads — without this
    wrapper every job thread keeps its thread-local connection open forever.
    The entry pass also discards connections that a previous failure or a
    server-side kill left unusable, so a broken connection never wedges a job
    permanently.

    Wrapped jobs may also be called synchronously from request code (e.g.
    ``PayslipAutoGenerate.save`` calls ``auto_payslip_generate``); outside an
    atomic block the caller's connection is then recycled — harmless, Django
    reconnects lazily on the next query.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        _close_thread_connections()
        try:
            return func(*args, **kwargs)
        finally:
            _close_thread_connections(force=True)

    return wrapper
