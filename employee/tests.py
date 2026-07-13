import datetime
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from employee.models import Actiontype, DisciplinaryAction, Employee
from employee.scheduler import block_unblock_disciplinary
from horilla.horilla_middlewares import _thread_locals
from horilla_audit.models import AccountBlockUnblock


class ArchiveSyncsUserActiveTestCase(TestCase):
    """Regression tests for the archive/un-archive views.

    Archiving an employee must also deactivate the linked Django ``User``
    (so the person can no longer log in), and un-archiving must reactivate
    it. Previously the views only persisted ``Employee.is_active`` and never
    saved the user, so archived employees could still authenticate.
    """

    def setUp(self):
        # HorillaModel audit fields read the current request from a thread
        # local; clear it so rows created here don't reference a rolled-back
        # user from a previous test (which trips deferred FK checks).
        _thread_locals.request = None

        # Horilla's custom login_required requires the *requesting* user to
        # have an active linked Employee, and ForcePasswordChangeMiddleware
        # bounces "new" employees to /change-password, so build a fully
        # provisioned admin.
        admin_employee = Employee.objects.create(
            employee_first_name="Admin",
            email="arch_admin@example.com",
            phone="9999999999",
        )
        self.admin = admin_employee.employee_user_id
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.is_new_employee = False
        self.admin.save()

        self.employee = Employee.objects.create(
            employee_first_name="Archy",
            employee_last_name="McTest",
            email="archy@example.com",
            phone="1234567890",
        )
        # Employee.save() auto-creates the linked login user.
        self.user = self.employee.employee_user_id
        self.assertIsNotNone(self.user)
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.user.is_active)
        self.client.force_login(self.admin)

    def tearDown(self):
        _thread_locals.request = None

    def _refresh(self):
        self.employee.refresh_from_db()
        self.user.refresh_from_db()

    def test_single_archive_then_unarchive_syncs_user(self):
        url = reverse("employee-archive", args=[self.employee.id])

        self.client.post(url, **{"HTTP_HX_REQUEST": "true"})
        self._refresh()
        self.assertFalse(self.employee.is_active)
        self.assertFalse(self.user.is_active, "user must be deactivated on archive")

        self.client.post(url, **{"HTTP_HX_REQUEST": "true"})
        self._refresh()
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.user.is_active, "user must be reactivated on un-archive")

    def test_bulk_archive_then_unarchive_syncs_user(self):
        url = reverse("employee-bulk-archive")
        ids = json.dumps([self.employee.id])

        # is_active query param defaults to False -> archive
        self.client.post(url, {"ids": ids})
        self._refresh()
        self.assertFalse(self.employee.is_active)
        self.assertFalse(self.user.is_active)

        # is_active=True -> un-archive
        self.client.post(url + "?is_active=True", {"ids": ids})
        self._refresh()
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.user.is_active)

    def test_get_manager_in_archive_syncs_user(self):
        url = reverse("get-manager-in")

        self.client.get(url, {"employee_id": self.employee.id})
        self._refresh()
        self.assertFalse(self.employee.is_active)
        self.assertFalse(self.user.is_active)

        self.client.get(url, {"employee_id": self.employee.id})
        self._refresh()
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.user.is_active)


class DisciplinaryBlockRespectsToggleTestCase(TestCase):
    """The disciplinary-action scheduler must honour the global
    ``AccountBlockUnblock`` switch.

    A blocking disciplinary action (dismissal/suspension) re-applies
    ``User.is_active = False`` every 25s. When the global feature is off, the
    scheduler must not touch the account, otherwise a reactivated user is
    re-blocked within seconds.
    """

    def setUp(self):
        _thread_locals.request = None
        self.employee = Employee.objects.create(
            employee_first_name="Disc",
            email="disc@example.com",
            phone="1112223333",
        )
        self.user = self.employee.employee_user_id
        # A dismissal action type that blocks login, effective in the past.
        action = Actiontype.objects.create(
            title="Dismissal", action_type="dismissal", block_option=True
        )
        disc = DisciplinaryAction.objects.create(
            action=action,
            description="test",
            start_date=datetime.date(2020, 1, 1),
        )
        disc.employee_id.add(self.employee)

    def tearDown(self):
        _thread_locals.request = None

    def test_does_not_block_when_feature_disabled(self):
        # No AccountBlockUnblock row => feature off => account left alone.
        self.assertFalse(AccountBlockUnblock.objects.exists())
        block_unblock_disciplinary()
        self.user.refresh_from_db()
        self.assertTrue(
            self.user.is_active,
            "scheduler must not block while the global feature is disabled",
        )

    def test_blocks_when_feature_enabled(self):
        AccountBlockUnblock.objects.create(is_enabled=True)
        block_unblock_disciplinary()
        self.user.refresh_from_db()
        self.assertFalse(
            self.user.is_active,
            "scheduler should block when the global feature is enabled",
        )
