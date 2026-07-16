"""Regression tests for horilla.scheduler_utils.

The close_db_connections decorator must release the calling thread's DB
connection after a scheduled job runs (APScheduler pool threads never receive
Django's request-cycle cleanup, which exhausted PostgreSQL max_connections in
production), while staying inert inside atomic blocks so jobs can still be
called directly from TestCase tests.
"""

import os
import sys
import threading
from unittest import mock

from django.contrib.auth.models import User
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from horilla.scheduler_utils import close_db_connections, schedulers_enabled


class CloseDbConnectionsThreadTestCase(TransactionTestCase):
    def test_job_thread_releases_its_connection(self):
        results = {}

        @close_db_connections
        def job():
            results["user_count"] = User.objects.count()

        def run():
            try:
                job()
                # Raw DBAPI connection must be gone once the job returns.
                results["raw_connection_after"] = connection.connection
            except Exception as exc:  # pragma: no cover - surfaced via assert
                results["error"] = exc

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=30)

        self.assertNotIn("error", results, f"job raised: {results.get('error')}")
        self.assertIn("user_count", results, "job body did not run")
        self.assertIsNone(
            results["raw_connection_after"],
            "job thread must not keep a DB connection open after the job",
        )

    def test_job_recovers_after_connection_closed_underneath(self):
        # Simulates a server-side kill (e.g. Postgres reaping the session):
        # the next decorated run must heal and succeed, not fail forever.
        results = {}

        @close_db_connections
        def job():
            results["count"] = User.objects.count()

        def run():
            try:
                job()
                # Break the thread's connection the way an external kill does:
                # close the raw socket-level connection but leave Django's
                # wrapper thinking it is still connected.
                User.objects.count()  # re-open a connection outside the job
                connection.connection.close()
                job()  # decorator's entry pass must discard the dead conn
                results["recovered"] = True
            except Exception as exc:  # pragma: no cover - surfaced via assert
                results["error"] = exc

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=30)

        self.assertNotIn("error", results, f"job raised: {results.get('error')}")
        self.assertTrue(results.get("recovered"))


class CloseDbConnectionsAtomicTestCase(TestCase):
    def test_decorator_is_inert_inside_atomic_block(self):
        # TestCase wraps each test in a transaction; the decorator must not
        # close the connection mid-transaction (that would poison it).
        @close_db_connections
        def job():
            return User.objects.count()

        self.assertEqual(job(), 0)
        # The test transaction must still be usable afterwards.
        User.objects.create(username="conn-still-alive@example.com")
        self.assertEqual(User.objects.count(), 1)


class SchedulersEnabledTestCase(SimpleTestCase):
    SERVING_ARGV = ["manage.py", "run_schedulers"]

    def test_disabled_without_env_flag(self):
        with mock.patch.object(sys, "argv", self.SERVING_ARGV):
            with mock.patch.dict(os.environ, {"HORILLA_RUN_SCHEDULERS": ""}):
                self.assertFalse(schedulers_enabled())

    def test_enabled_with_env_flag(self):
        with mock.patch.object(sys, "argv", self.SERVING_ARGV):
            with mock.patch.dict(os.environ, {"HORILLA_RUN_SCHEDULERS": "1"}):
                self.assertTrue(schedulers_enabled())

    def test_blocked_during_non_serving_commands_even_with_env_flag(self):
        for cmd in ["migrate", "test", "shell", "collectstatic"]:
            with mock.patch.object(sys, "argv", ["manage.py", cmd]):
                with mock.patch.dict(os.environ, {"HORILLA_RUN_SCHEDULERS": "1"}):
                    self.assertFalse(schedulers_enabled(), cmd)

    def test_disabled_under_gunicorn_even_with_env_flag(self):
        # settings exports .env into os.environ (read_env overwrite=True), so
        # the env flag alone must never enable schedulers in web workers —
        # only the run_schedulers entry point may start them.
        with mock.patch.object(sys, "argv", ["gunicorn", "horilla.wsgi:application"]):
            with mock.patch.dict(os.environ, {"HORILLA_RUN_SCHEDULERS": "1"}):
                self.assertFalse(schedulers_enabled())
