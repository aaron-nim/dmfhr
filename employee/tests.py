import json

from django.test import TestCase
from django.urls import reverse

from employee.models import Employee
from horilla.horilla_middlewares import _thread_locals


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
