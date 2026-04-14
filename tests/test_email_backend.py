"""
test_email_backend.py — unit tests for app.email_backend.

Covers:
- SMTPEmailBackend.send(): success path, SMTPAuthenticationError, OSError
- OutlookEmailBackend: ImportError on non-Windows when win32com absent
- MailAppEmailBackend.send(): osascript success, non-zero returncode → RuntimeError
- MailAppEmailBackend._as_body(): newline splitting, quote escaping
- MailAppEmailBackend._as_str(): backslash and quote escaping
- get_best_backend(): linux → SMTP; darwin + osascript → MailApp;
                      darwin + no osascript → SMTP; win32 + no win32com → SMTP
"""

from __future__ import annotations

import smtplib
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.email_backend import (  # noqa: E402
    EmailBackend,
    MailAppEmailBackend,
    OutlookEmailBackend,
    SMTPEmailBackend,
    get_best_backend,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEND_CONFIG = {
    "smtp_server": "smtp.example.com",
    "smtp_port": 587,
    "smtp_username": "user@example.com",
    "smtp_password": "secret",
    "smtp_from": "from@example.com",
    "outlook_accounts": [],
}


def _make_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "report.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


# ---------------------------------------------------------------------------
# EmailBackend abstract base
# ---------------------------------------------------------------------------


def test_abstract_backend_name_raises():
    class Bare(EmailBackend):
        pass

    with pytest.raises(NotImplementedError):
        _ = Bare().name


def test_abstract_backend_send_raises():
    class Bare(EmailBackend):
        @property
        def name(self):
            return "Bare"

    with pytest.raises(NotImplementedError):
        Bare().send(to="a@b.com", subject="s", body="b", attachment_path=Path("."))


# ---------------------------------------------------------------------------
# SMTPEmailBackend
# ---------------------------------------------------------------------------


def test_smtp_backend_name():
    b = SMTPEmailBackend("smtp.example.com", 587, "u", "p", "f@e.com")
    assert "smtp.example.com" in b.name
    assert "587" in b.name


def test_smtp_backend_send_success(tmp_path):
    pdf = _make_pdf(tmp_path)
    mock_server = MagicMock()
    mock_smtp_cls = MagicMock(return_value=mock_server)

    b = SMTPEmailBackend("smtp.example.com", 587, "user", "pass", "from@e.com")
    with patch("app.email_backend.smtplib.SMTP", mock_smtp_cls):
        b.send(to="to@e.com", subject="Subj", body="Hello", attachment_path=pdf)

    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user", "pass")
    mock_server.send_message.assert_called_once()
    mock_server.quit.assert_called_once()


def test_smtp_backend_auth_error_propagates(tmp_path):
    pdf = _make_pdf(tmp_path)
    mock_server = MagicMock()
    mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad creds")
    mock_smtp_cls = MagicMock(return_value=mock_server)

    b = SMTPEmailBackend("smtp.example.com", 587, "u", "p", "f@e.com")
    with patch("app.email_backend.smtplib.SMTP", mock_smtp_cls):
        with pytest.raises(smtplib.SMTPAuthenticationError):
            b.send(to="t@e.com", subject="S", body="B", attachment_path=pdf)

    # quit/close called in finally block even on failure
    assert mock_server.quit.called or mock_server.close.called


def test_smtp_backend_connection_error_propagates(tmp_path):
    pdf = _make_pdf(tmp_path)
    with patch(
        "app.email_backend.smtplib.SMTP", side_effect=OSError("Connection refused")
    ):
        b = SMTPEmailBackend("smtp.example.com", 587, "u", "p", "f@e.com")
        with pytest.raises(OSError):
            b.send(to="t@e.com", subject="S", body="B", attachment_path=pdf)


def test_smtp_backend_quit_failure_does_not_mask_success(tmp_path):
    """If quit() raises, the email was still sent — no exception should propagate."""
    pdf = _make_pdf(tmp_path)
    mock_server = MagicMock()
    mock_server.quit.side_effect = smtplib.SMTPServerDisconnected()
    mock_smtp_cls = MagicMock(return_value=mock_server)

    b = SMTPEmailBackend("smtp.example.com", 587, "u", "p", "f@e.com")
    with patch("app.email_backend.smtplib.SMTP", mock_smtp_cls):
        # Should not raise — close() is called as fallback
        b.send(to="t@e.com", subject="S", body="B", attachment_path=pdf)

    mock_server.close.assert_called_once()


# ---------------------------------------------------------------------------
# OutlookEmailBackend
# ---------------------------------------------------------------------------


def test_outlook_backend_import_error_when_no_win32com():
    """On a machine without win32com, OutlookEmailBackend raises ImportError."""
    with patch.dict(sys.modules, {"win32com": None, "win32com.client": None}):
        with pytest.raises((ImportError, TypeError)):
            OutlookEmailBackend()


# ---------------------------------------------------------------------------
# MailAppEmailBackend — string helpers
# ---------------------------------------------------------------------------


def test_mailapp_as_str_escapes_backslash():
    assert MailAppEmailBackend._as_str("a\\b") == "a\\\\b"


def test_mailapp_as_str_escapes_double_quote():
    assert MailAppEmailBackend._as_str('say "hi"') == 'say \\"hi\\"'


def test_mailapp_as_body_single_line():
    result = MailAppEmailBackend._as_body("Hello World")
    assert result == '"Hello World"'


def test_mailapp_as_body_multiline():
    result = MailAppEmailBackend._as_body("Hello\nWorld")
    assert result == '"Hello" & return & "World"'


def test_mailapp_as_body_escapes_quotes():
    result = MailAppEmailBackend._as_body('Say "hi"')
    assert '\\"hi\\"' in result


# ---------------------------------------------------------------------------
# MailAppEmailBackend — send()
# ---------------------------------------------------------------------------


def test_mailapp_send_calls_osascript(tmp_path):
    pdf = _make_pdf(tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    b = MailAppEmailBackend()
    with patch(
        "app.email_backend.subprocess.run", return_value=mock_result
    ) as mock_run:
        b.send(to="a@b.com", subject="Test", body="Hello\nWorld", attachment_path=pdf)

    mock_run.assert_called_once()
    args = mock_run.call_args
    cmd = args[0][0]
    assert cmd[0] == "osascript"
    assert cmd[1] == "-e"
    script = cmd[2]
    assert "Mail" in script
    assert "a@b.com" in script
    assert str(pdf.resolve()) in script


def test_mailapp_send_nonzero_returncode_raises(tmp_path):
    pdf = _make_pdf(tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Mail.app not running"
    mock_result.stdout = ""

    b = MailAppEmailBackend()
    with patch("app.email_backend.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="Mail.app AppleScript error"):
            b.send(to="a@b.com", subject="S", body="B", attachment_path=pdf)


def test_mailapp_send_escapes_special_chars_in_subject(tmp_path):
    pdf = _make_pdf(tmp_path)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    b = MailAppEmailBackend()
    with patch(
        "app.email_backend.subprocess.run", return_value=mock_result
    ) as mock_run:
        b.send(
            to="a@b.com",
            subject='Report "Q1" results',
            body="See attached.",
            attachment_path=pdf,
        )

    script = mock_run.call_args[0][0][2]
    # Double quotes in subject must be escaped
    assert '\\"Q1\\"' in script


# ---------------------------------------------------------------------------
# get_best_backend
# ---------------------------------------------------------------------------


def test_get_best_backend_linux_returns_smtp(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    b = get_best_backend(_SEND_CONFIG)
    assert isinstance(b, SMTPEmailBackend)


def test_get_best_backend_darwin_osascript_available(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("app.email_backend.subprocess.run", return_value=mock_result):
        b = get_best_backend(_SEND_CONFIG)
    assert isinstance(b, MailAppEmailBackend)


def test_get_best_backend_darwin_osascript_missing_falls_back(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    with patch(
        "app.email_backend.subprocess.run",
        side_effect=FileNotFoundError("osascript not found"),
    ):
        b = get_best_backend(_SEND_CONFIG)
    assert isinstance(b, SMTPEmailBackend)


def test_get_best_backend_darwin_osascript_timeout_falls_back(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    with patch(
        "app.email_backend.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=5),
    ):
        b = get_best_backend(_SEND_CONFIG)
    assert isinstance(b, SMTPEmailBackend)


def test_get_best_backend_win32_no_win32com_falls_back(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    with patch.dict(sys.modules, {"win32com": None, "win32com.client": None}):
        b = get_best_backend(_SEND_CONFIG)
    assert isinstance(b, SMTPEmailBackend)
