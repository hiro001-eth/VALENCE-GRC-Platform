"""Shared SMTP delivery for alerts and scheduled auditor reports."""
from __future__ import annotations

import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class EmailDelivery:
    def __init__(self) -> None:
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.default_from = os.getenv("SMTP_FROM", self.smtp_user or "valence@grc.internal")

    @property
    def configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_pass)

    async def send_html(self, to_email: str, subject: str, html_body: str) -> bool:
        if not self.configured or not to_email:
            logger.warning("email_skipped_smtp_unconfigured", to=to_email)
            return False
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.default_from
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))
        return await self._send(msg, to_email)

    async def send_report_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        pdf_path: Path,
    ) -> bool:
        if not self.configured or not to_email:
            logger.warning("report_email_skipped_smtp_unconfigured", to=to_email)
            return False
        if not pdf_path.exists():
            logger.error("report_email_pdf_missing", path=str(pdf_path))
            return False

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = self.default_from
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with pdf_path.open("rb") as fh:
            attachment = MIMEApplication(fh.read(), _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
        msg.attach(attachment)
        return await self._send(msg, to_email)

    async def _send(self, msg: MIMEMultipart, to_email: str) -> bool:
        try:
            import aiosmtplib

            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_pass,
                use_tls=(self.smtp_port == 465),
                start_tls=(self.smtp_port == 587),
            )
            logger.info("email_delivered", to=to_email)
            return True
        except ImportError:
            logger.warning("email_send_failed_aiosmtplib_missing")
            return False
        except Exception as exc:
            logger.error("email_delivery_failed", to=to_email, error=str(exc))
            return False
