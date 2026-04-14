"""
email_backend.py — platform-aware email sending backends.

Provides three concrete backends and a factory function:

  SMTPEmailBackend      — SMTP/STARTTLS, works on every platform
  OutlookEmailBackend   — Outlook COM via win32com (Windows only)
  MailAppEmailBackend   — Mail.app via osascript/AppleScript (macOS only)

  get_best_backend(send_config) -> EmailBackend
      Returns the highest-priority available backend for the running platform:
        Windows → OutlookEmailBackend (falls back to SMTP if win32com absent)
        macOS   → MailAppEmailBackend (falls back to SMTP if osascript absent)
        Linux   → SMTPEmailBackend

Each backend exposes a single public method:

    backend.send(
        to="alice@example.com",
        subject="Your Report",
        body="Dear Alice, ...",
        attachment_path=Path("/tmp/report.pdf"),
    )

All backends raise on failure; callers decide whether to mark the
recipient as failed and continue or abort.
"""

from __future__ import annotations

import smtplib
import subprocess
import sys
from pathlib import Path

from utils.constants import SMTP_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class EmailBackend:
    """Abstract email sending backend."""

    @property
    def name(self) -> str:
        """Human-readable name shown in log output."""
        raise NotImplementedError

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        attachment_path: Path,
    ) -> None:
        """Send one email with a PDF attachment.  Raises on any failure."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SMTP backend — universal
# ---------------------------------------------------------------------------


class SMTPEmailBackend(EmailBackend):
    """Send via SMTP + STARTTLS.  Works on Windows, macOS, and Linux."""

    def __init__(
        self,
        server: str,
        port: int,
        username: str,
        password: str,
        from_addr: str,
    ) -> None:
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.from_addr = from_addr

    @property
    def name(self) -> str:
        return f"SMTP ({self.server}:{self.port})"

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        attachment_path: Path,
    ) -> None:
        from email import encoders
        from email.mime.base import MIMEBase
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart()
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with open(attachment_path, "rb") as fh:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(fh.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{attachment_path.name}"',
            )
            msg.attach(part)

        server = smtplib.SMTP(self.server, self.port, timeout=SMTP_TIMEOUT_SECONDS)
        try:
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                server.close()


# ---------------------------------------------------------------------------
# Outlook COM backend — Windows only
# ---------------------------------------------------------------------------


class OutlookEmailBackend(EmailBackend):
    """Send via Outlook COM automation.

    Raises ``ImportError`` on non-Windows platforms (win32com not installed).
    Selects a sending account from *priority_accounts* (list of SMTP addresses)
    before falling back to whichever account Outlook has as default.
    """

    def __init__(self, priority_accounts: list[str] | None = None) -> None:
        import win32com.client  # noqa: F401 — raises ImportError on non-Windows

        self._win32 = win32com.client
        self.priority_accounts: list[str] = priority_accounts or []

    @property
    def name(self) -> str:
        return "Outlook COM"

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        attachment_path: Path,
    ) -> None:
        outlook = self._win32.Dispatch("Outlook.Application")

        # Enumerate available accounts once per call
        available: list[tuple[str, object]] = []
        try:
            for i in range(1, outlook.Session.Accounts.Count + 1):
                acct = outlook.Session.Accounts.Item(i)
                available.append((acct.SmtpAddress, acct))
        except Exception:
            pass

        # Pick the highest-priority configured account
        selected_account: object | None = None
        for priority_addr in self.priority_accounts:
            for smtp_addr, acct in available:
                if smtp_addr.lower() == priority_addr.lower():
                    selected_account = acct
                    break
            if selected_account is not None:
                break
        if selected_account is None and available:
            _, selected_account = available[0]

        mail = outlook.CreateItem(0)  # 0 = olMailItem
        mail.To = to
        mail.Subject = subject
        mail.Body = body
        if selected_account is not None:
            mail.SendUsingAccount = selected_account
        mail.Attachments.Add(str(attachment_path.resolve()))
        mail.Send()


# ---------------------------------------------------------------------------
# Mail.app AppleScript backend — macOS only
# ---------------------------------------------------------------------------


class MailAppEmailBackend(EmailBackend):
    """Send via macOS Mail.app using ``osascript`` (AppleScript).

    Requires:
    - macOS (``osascript`` on PATH)
    - Mail.app configured with at least one outgoing account

    The email is delivered synchronously (``send`` blocks until Mail.app
    confirms the send).  If Mail.app is offline the message lands in the
    Outbox and is sent when connectivity returns.
    """

    @property
    def name(self) -> str:
        return "Mail.app (AppleScript)"

    @staticmethod
    def _as_str(value: str) -> str:
        """Escape *value* for embedding in an AppleScript double-quoted string."""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _as_body(text: str) -> str:
        """Convert a multi-line Python string to an AppleScript string expression.

        Each line becomes a quoted literal; lines are joined with ``& return &``.
        Example: ``"Hello" & return & "" & return & "World"``
        """
        lines = text.replace("\\", "\\\\").replace('"', '\\"').split("\n")
        return " & return & ".join(f'"{line}"' for line in lines)

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        attachment_path: Path,
    ) -> None:
        posix_path = str(attachment_path.resolve())

        # Build the AppleScript.  Body is constructed as a concatenated string
        # expression so that newlines are preserved without embedding literal
        # line breaks inside an AppleScript string literal.
        script = (
            f"set msgBody to {self._as_body(body)}\n"
            f'tell application "Mail"\n'
            f"    set newMsg to make new outgoing message with properties"
            f' {{subject:"{self._as_str(subject)}", content:msgBody}}\n'
            f"    tell newMsg\n"
            f"        set visible to false\n"
            f"        make new to recipient at end of to recipients"
            f' with properties {{address:"{self._as_str(to)}"}}\n'
            f"        make new attachment with properties"
            f' {{file name:POSIX file "{self._as_str(posix_path)}"}}\n'
            f"    end tell\n"
            f"    send newMsg\n"
            f"end tell\n"
        )

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Mail.app AppleScript error (rc={result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_best_backend(send_config: dict) -> EmailBackend:
    """Return the highest-priority available backend for the running platform.

    Platform priority:
      Windows → ``OutlookEmailBackend``  (falls back to SMTP if win32com absent)
      macOS   → ``MailAppEmailBackend``  (falls back to SMTP if osascript absent)
      Linux   → ``SMTPEmailBackend``

    *send_config* must contain the keys used by ``SMTPEmailBackend.__init__``:
    ``smtp_server``, ``smtp_port``, ``smtp_username``, ``smtp_password``,
    ``smtp_from``.  Optional: ``outlook_accounts`` (list of SMTP addresses for
    Outlook account priority on Windows).
    """
    smtp = SMTPEmailBackend(
        server=send_config["smtp_server"],
        port=send_config["smtp_port"],
        username=send_config["smtp_username"],
        password=send_config["smtp_password"],
        from_addr=send_config["smtp_from"],
    )

    if sys.platform == "win32":
        try:
            return OutlookEmailBackend(
                priority_accounts=send_config.get("outlook_accounts", [])
            )
        except ImportError:
            return smtp

    if sys.platform == "darwin":
        try:
            subprocess.run(
                ["osascript", "-e", "return 0"],
                capture_output=True,
                timeout=5,
                check=True,
            )
            return MailAppEmailBackend()
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            return smtp

    return smtp
