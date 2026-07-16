"""
App configuration for the 'payroll' app.
"""

import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class PayrollConfig(AppConfig):
    """
    AppConfig for the 'payroll' app.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "payroll"

    def ready(self) -> None:
        ready = super().ready()
        from django.urls import include, path

        from horilla.horilla_settings import APPS
        from horilla.urls import urlpatterns
        from payroll import signals

        APPS.append("payroll")
        urlpatterns.append(
            path("payroll/", include("payroll.urls.urls")),
        )
        try:
            from horilla.scheduler_utils import schedulers_enabled

            if schedulers_enabled():
                from payroll.scheduler import auto_payslip_generate

                auto_payslip_generate()
        except Exception:
            # Migrations must not be affected, but a skipped startup payslip
            # catch-up in the scheduler service (e.g. DB not up yet) has to
            # be visible in journalctl rather than silently swallowed.
            logging.getLogger(__name__).exception(
                "payroll startup auto_payslip_generate skipped"
            )

        return ready
