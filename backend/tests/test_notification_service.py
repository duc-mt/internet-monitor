from __future__ import annotations

import logging

import httpx
import pytest
from app.services import notification_service as ns


@pytest.fixture(autouse=True)
def _reset():
    ns.reset_cooldowns()
    yield
    ns.reset_cooldowns()


def test_applescript_escape_handles_quotes_and_backslashes():
    assert ns._applescript_escape('He said "hi"') == 'He said \\"hi\\"'
    assert ns._applescript_escape("back\\slash") == "back\\\\slash"


def test_powershell_escape_doubles_single_quotes():
    assert ns._powershell_escape("it's down") == "it''s down"


def test_windows_toast_script_embeds_escaped_title_and_message():
    script = ns._windows_toast_script("Internet down", "can't reach 1.1.1.1")
    assert "CreateTextNode('Internet down')" in script
    assert "CreateTextNode('can''t reach 1.1.1.1')" in script  # ' escaped to ''
    assert "ToastNotificationManager" in script


@pytest.mark.asyncio
async def test_send_on_macos_calls_osascript(monkeypatch):
    monkeypatch.setattr(ns, "_IS_MACOS", True)
    monkeypatch.setattr(ns, "_IS_WINDOWS", False)
    monkeypatch.setattr(ns, "notifier_available", lambda: True)
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)

        class P:
            async def wait(self_inner):
                return 0

        return P()

    monkeypatch.setattr(ns, "create_subprocess_exec", fake_exec)
    await ns.send("Title", "Message")
    assert calls[0][0] == "osascript"
    assert calls[0][1] == "-e"


@pytest.mark.asyncio
async def test_send_on_windows_calls_powershell(monkeypatch):
    monkeypatch.setattr(ns, "_IS_MACOS", False)
    monkeypatch.setattr(ns, "_IS_WINDOWS", True)
    monkeypatch.setattr(ns, "notifier_available", lambda: True)
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)

        class P:
            async def wait(self_inner):
                return 0

        return P()

    monkeypatch.setattr(ns, "create_subprocess_exec", fake_exec)
    await ns.send("Title", "Message")
    assert calls[0][0] == "powershell"
    assert "-NonInteractive" in calls[0]
    assert "-Command" in calls[0]


@pytest.mark.asyncio
async def test_send_on_linux_calls_notify_send(monkeypatch):
    monkeypatch.setattr(ns, "_IS_MACOS", False)
    monkeypatch.setattr(ns, "_IS_WINDOWS", False)
    monkeypatch.setattr(ns, "notifier_available", lambda: True)
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)

        class P:
            async def wait(self_inner):
                return 0

        return P()

    monkeypatch.setattr(ns, "create_subprocess_exec", fake_exec)
    await ns.send("Title", "Message")
    assert calls[0][0] == "notify-send"


@pytest.mark.asyncio
async def test_send_skips_entirely_when_backend_unavailable(monkeypatch):
    monkeypatch.setattr(ns, "notifier_available", lambda: False)
    called = False

    async def fake_exec(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(ns, "create_subprocess_exec", fake_exec)
    await ns.send("Title", "Message")
    assert called is False


@pytest.mark.asyncio
async def test_send_respects_cooldown(monkeypatch):
    monkeypatch.setattr(ns, "notifier_available", lambda: True)
    call_count = 0

    async def fake_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        class P:
            async def wait(self_inner):
                return 0

        return P()

    monkeypatch.setattr(ns, "create_subprocess_exec", fake_exec)
    await ns.send("Title", "Message", key="k", cooldown_seconds=60)
    await ns.send("Title", "Message", key="k", cooldown_seconds=60)
    assert call_count == 1


# --- Webhooks -------------------------------------------------------------
# Dummy endpoints only; the "secret" path segments below stand in for the token
# real Slack/Discord webhook URLs carry.

SLACK_URL = "https://hooks.slack.com/services/T000/B000/secret-token"
DISCORD_URL = "https://discord.com/api/webhooks/123456/secret-token"
GENERIC_URL = "https://alerts.example.net/hook/secret-token"


class _FakeWebhookClient:
    """Stands in for httpx.AsyncClient; records posts instead of touching the network."""

    posts: list[tuple[str, dict]] = []
    status_code = 204
    error: Exception | None = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, json):
        if _FakeWebhookClient.error is not None:
            raise _FakeWebhookClient.error
        _FakeWebhookClient.posts.append((url, json))

        class _Response:
            status_code = _FakeWebhookClient.status_code

        return _Response()


@pytest.fixture
def webhook_client(monkeypatch):
    _FakeWebhookClient.posts = []
    _FakeWebhookClient.status_code = 204
    _FakeWebhookClient.error = None
    monkeypatch.setattr(ns.httpx, "AsyncClient", _FakeWebhookClient)
    return _FakeWebhookClient


def test_slack_payload_uses_text_with_slack_bold():
    payload = ns.build_webhook_payload(SLACK_URL, "Internet connection lost", "All targets down", "critical")
    assert payload == {"text": "*Internet connection lost*\nAll targets down"}


def test_discord_payload_uses_content_and_blocks_mentions():
    payload = ns.build_webhook_payload(DISCORD_URL, "Internet connection lost", "All targets down", "critical")
    # Discord rejects a body without "content" (or embeds): {"text": ...} would be a 400.
    assert payload["content"] == "**Internet connection lost**\nAll targets down"
    assert "text" not in payload
    assert payload["allowed_mentions"] == {"parse": []}


def test_discord_payload_is_truncated_below_the_2000_character_limit():
    payload = ns.build_webhook_payload(DISCORD_URL, "Title", "x" * 5000, "normal")
    assert len(payload["content"]) <= 2000


def test_generic_payload_carries_text_and_the_separate_fields():
    payload = ns.build_webhook_payload(GENERIC_URL, "High latency: Google DNS", "180 ms", "normal")
    assert payload == {
        "text": "**High latency: Google DNS**\n180 ms",
        "title": "High latency: Google DNS",
        "message": "180 ms",
        "urgency": "normal",
    }


def test_lookalike_hosts_do_not_get_the_discord_or_slack_format():
    for url in ("https://discord.com.evil.example/x", "https://notdiscord.com/x", "https://hooks.slack.com.evil.example/x"):
        assert "urgency" in ns.build_webhook_payload(url, "T", "M", "normal")


@pytest.mark.asyncio
async def test_send_posts_to_the_webhook_even_without_a_desktop_notifier(monkeypatch, webhook_client):
    # The headless-server case: no notify-send, but the webhook must still fire.
    monkeypatch.setattr(ns, "notifier_available", lambda: False)
    await ns.send("Internet connection lost", "All targets down", urgency="critical", webhook_url=SLACK_URL)
    await ns.flush_webhooks()
    assert webhook_client.posts == [(SLACK_URL, {"text": "*Internet connection lost*\nAll targets down"})]


@pytest.mark.asyncio
async def test_send_without_a_webhook_url_never_calls_http(monkeypatch, webhook_client):
    monkeypatch.setattr(ns, "notifier_available", lambda: False)
    await ns.send("Title", "Message")
    await ns.send("Title", "Message", webhook_url=None)
    await ns.send("Title", "Message", webhook_url="")
    await ns.flush_webhooks()
    assert webhook_client.posts == []


@pytest.mark.asyncio
async def test_webhook_is_sent_alongside_the_desktop_notification(monkeypatch, webhook_client):
    monkeypatch.setattr(ns, "_IS_MACOS", False)
    monkeypatch.setattr(ns, "_IS_WINDOWS", False)
    monkeypatch.setattr(ns, "notifier_available", lambda: True)
    desktop_calls = []

    async def fake_exec(*args, **kwargs):
        desktop_calls.append(args)

        class P:
            async def wait(self_inner):
                return 0

        return P()

    monkeypatch.setattr(ns, "create_subprocess_exec", fake_exec)
    await ns.send("Title", "Message", webhook_url=GENERIC_URL)
    await ns.flush_webhooks()
    assert desktop_calls and desktop_calls[0][0] == "notify-send"
    assert len(webhook_client.posts) == 1


@pytest.mark.asyncio
async def test_webhook_shares_the_cooldown_with_the_desktop_notification(monkeypatch, webhook_client):
    monkeypatch.setattr(ns, "notifier_available", lambda: False)
    for _ in range(3):
        await ns.send("Packet loss", "50% loss", key="loss:1", cooldown_seconds=60, webhook_url=GENERIC_URL)
    await ns.flush_webhooks()
    assert len(webhook_client.posts) == 1


@pytest.mark.asyncio
async def test_a_failing_webhook_does_not_raise_and_never_logs_the_url(monkeypatch, webhook_client, caplog):
    monkeypatch.setattr(ns, "notifier_available", lambda: False)
    webhook_client.error = httpx.ConnectError(f"connection refused for {GENERIC_URL}")
    with caplog.at_level(logging.WARNING, logger="internet_monitor.notifications"):
        await ns.send("Title", "Message", webhook_url=GENERIC_URL)
        await ns.flush_webhooks()
    assert "Webhook delivery failed (ConnectError)" in caplog.text
    assert "secret-token" not in caplog.text


@pytest.mark.asyncio
async def test_an_http_error_status_is_logged_without_the_url(monkeypatch, webhook_client, caplog):
    monkeypatch.setattr(ns, "notifier_available", lambda: False)
    webhook_client.status_code = 400
    with caplog.at_level(logging.WARNING, logger="internet_monitor.notifications"):
        await ns.send("Title", "Message", webhook_url=DISCORD_URL)
        await ns.flush_webhooks()
    assert "HTTP 400" in caplog.text
    assert "secret-token" not in caplog.text
