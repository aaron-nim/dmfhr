"""
run_schedulers.py

Keeps Horilla's APScheduler background jobs running in a single dedicated
process (systemd: horilla-scheduler.service, template in docs/deploy/).
"""

import signal
import sys
import time

from django.core.management.base import BaseCommand

from horilla.scheduler_utils import schedulers_enabled


class Command(BaseCommand):
    help = (
        "Run Horilla's background schedulers in this process and block "
        "forever. Requires HORILLA_RUN_SCHEDULERS=1 in the environment: the "
        "scheduler modules start their schedulers at import time (during "
        "Django setup), gated on that variable, so it must be set by the "
        "service unit before this command starts — setting it here would be "
        "too late."
    )

    def handle(self, *args, **options):
        if not schedulers_enabled():
            self.stderr.write(
                self.style.ERROR(
                    "Schedulers are not enabled in this process. Set "
                    "HORILLA_RUN_SCHEDULERS=1 in the systemd service "
                    "environment (not in .env, not inside this command) "
                    "and restart."
                )
            )
            raise SystemExit(1)
        # systemd stop/restart sends SIGTERM; turn it into a normal
        # interpreter shutdown so concurrent.futures joins in-flight job
        # threads (finishing e.g. a payslip batch) instead of killing them
        # mid-write.
        signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
        self.stdout.write(
            self.style.SUCCESS("Background schedulers running; process will block.")
        )
        while True:
            time.sleep(3600)
