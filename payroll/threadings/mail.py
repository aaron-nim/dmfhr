"""
mail.py

This module is used handle mail sent in thread
"""

import logging
from threading import Thread

from django.core.mail import EmailMessage
from django.template.loader import render_to_string

from base.backends import ConfiguredEmailBackend
from employee.models import EmployeeWorkInformation
from payroll.models.models import Payslip
from payroll.views.views import payslip_pdf

logger = logging.getLogger(__name__)


class MailSendThread(Thread):
    """
    MailSend
    """

    def __init__(self, request, result_dict, ids):
        Thread.__init__(self)
        self.result_dict = result_dict
        self.ids = ids
        self.request = request
        self.host = request.get_host()
        self.protocol = "https" if request.is_secure() else "http"

    def run(self) -> None:
        super().run()
        for record in list(self.result_dict.values()):
            html_message = render_to_string(
                "payroll/mail_templates/default.html",
                {
                    "record": record,
                    "host": self.host,
                    "protocol": self.protocol,
                },
                request=self.request,
            )
            attachments = []
            attached_ids = []
            for instance in record["instances"]:
                response = payslip_pdf(self.request, instance.id)
                content = getattr(response, "content", b"") or b""
                status = getattr(response, "status_code", 200)
                # Only attach a genuine PDF. generate_payslip_pdf() returns an
                # error HttpResponse (text, status 500) when wkhtmltopdf fails;
                # attaching that produced unreadable "payslip.pdf" files.
                if status != 200 or not content.startswith(b"%PDF-"):
                    logger.error(
                        "Skipping payslip %s: PDF generation failed (status=%s, %d bytes)",
                        instance.id,
                        status,
                        len(content),
                    )
                    continue
                attachments.append(
                    (
                        f"{instance.get_payslip_title()}.pdf",
                        content,
                        "application/pdf",
                    )
                )
                attached_ids.append(instance.id)

            if not attachments:
                logger.error(
                    "No valid payslip PDFs generated for %s; email not sent.",
                    record["instances"][0].employee_id,
                )
                continue
            employee = record["instances"][0].employee_id
            email_backend = ConfiguredEmailBackend()
            # Keep From: aligned with the SMTP-authenticated sender so relays
            # that enforce sender alignment (e.g. securemail.pro) don't drop us.
            # Only the display name and Reply-To carry the acting user's identity.
            sender_address = email_backend.dynamic_mail_sent_from
            from_header = sender_address
            reply_to_address = sender_address
            if self.request:
                try:
                    user_name = self.request.user.employee_get.get_full_name()
                    user_email = self.request.user.employee_get.email
                    if sender_address:
                        from_header = f"{user_name} <{sender_address}>"
                    reply_to_address = f"{user_name} <{user_email}>"
                except Exception as exc:
                    logger.exception("Could not resolve request user for mail headers: %s", exc)

            email = EmailMessage(
                f"Hello, {record['instances'][0].get_name()} Your Payslips is Ready!",
                html_message,
                from_header,
                [employee.get_mail()],
                reply_to=[reply_to_address],
            )
            email.attachments = attachments

            # Send the email
            email.content_subtype = "html"
            try:
                email.send()
                Payslip.objects.filter(id__in=attached_ids).update(
                    sent_to_employee=True
                )
            except Exception as e:
                logger.exception(e)

        return
