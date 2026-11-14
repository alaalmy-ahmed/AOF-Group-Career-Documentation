"""
Tests for alerts.py. No real email is sent: smtplib.SMTP_SSL is replaced
by FakeServer, which only remembers what it was asked to do.
"""

import pytest

import alerts


class FakeServer:
    sent = []  # (server, message) for every email "sent"

    def __init__(self, host, port):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def login(self, user, password):
        self.login_details = (user, password)

    def send_message(self, message):
        FakeServer.sent.append((self, message))


@pytest.fixture
def fake_server(monkeypatch):
    FakeServer.sent = []
    monkeypatch.setattr(alerts.smtplib, "SMTP_SSL", FakeServer)
    monkeypatch.setattr(alerts, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(alerts, "SMTP_PORT", 465)
    monkeypatch.setattr(alerts, "ALERT_EMAIL_FROM", "sender@example.com")
    monkeypatch.setattr(alerts, "ALERT_EMAIL_PASSWORD", "app-password")
    monkeypatch.setattr(alerts, "ALERT_EMAIL_TO", "me@example.com, boss@example.com")
    return FakeServer


def test_sends_the_email(fake_server):
    alerts.send_email("OK: daily_issues / distribute_issues", "Done: 6 issues from 2026-10-26.")

    [(server, message)] = fake_server.sent
    assert (server.host, server.port) == ("smtp.gmail.com", 465)
    assert server.login_details == ("sender@example.com", "app-password")
    assert message["Subject"] == "OK: daily_issues / distribute_issues"
    assert message["From"] == "sender@example.com"
    assert message["To"] == "me@example.com, boss@example.com"
    assert message.get_content().strip() == "Done: 6 issues from 2026-10-26."


def test_missing_setting_is_named(fake_server, monkeypatch):
    monkeypatch.setattr(alerts, "ALERT_EMAIL_PASSWORD", None)

    with pytest.raises(RuntimeError, match="Not set: ALERT_EMAIL_PASSWORD"):
        alerts.send_email("subject", "body")
    assert fake_server.sent == []
