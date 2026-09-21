from __future__ import annotations

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
