"""Notification transports. The worker depends on the protocol, tests on a fake."""

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol


class NotificationSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str, message_id: str) -> None: ...


class SmtpSender:
    def __init__(self, host: str, port: int, sender: str, timeout_s: float = 10.0) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._timeout_s = timeout_s

    def _send_blocking(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout_s) as smtp:
            smtp.send_message(message)

    async def send(self, *, to: str, subject: str, body: str, message_id: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        # Deterministic Message-ID: a resend after a crash is recognizable as the same message.
        message["Message-ID"] = message_id
        message.set_content(body)
        await asyncio.to_thread(self._send_blocking, message)
