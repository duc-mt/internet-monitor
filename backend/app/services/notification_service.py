
"""
==============================================================================
Module Name:   notification_service.py
Description:   Desktop notifications.  - Linux: `notify-send` (part of libnotify, present on virtually every Linux   desktop - GNOME, KDE, XFCE, etc.). - macOS: `osascript` (AppleScript), which ships with every Mac - no install   needed. This gets a real Notification Center banner without pulling in   any third-party dependency. - Windows: `powershell` (Windows PowerShell 5.1, bundled with every   Windows 10/11 install) driving the WinRT toast-notification API   directly - no extra module (e.g. BurntToast) needs installing. This is   the one platform branch in this file that is unverified on real   hardware (see the docstring on _windows_toast_script below for the   specific, known risk).  Either way we shell out with argv-list subprocess calls (no shell=True), keeping the monitoring service itself free of any GUI-toolkit dependency and safe to run headless - and safe from injection even though titles and messages can contain target names/error text we don't fully control.  State transitions (offline/online) always fire immediately - a user always wants to know the instant they lose or regain connectivity. Threshold alerts (latency/packet-loss) are debounced per (kind, target) key so a flapping metric doesn't spam five notifications a minute.  Webhooks: when a webhook URL is configured, every alert is also POSTed there, independently of the desktop notifier - so a headless server (no notify-send, no desktop session) still gets alerts. Delivery runs as a background task with a short timeout so a slow or dead endpoint can never stall a monitoring loop, and the URL is never logged because Slack and Discord webhook URLs embed their credential.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 notification_service.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
import time
from asyncio import create_subprocess_exec
from asyncio.subprocess import DEVNULL
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger("internet_monitor.notifications")

_last_sent: dict[str, float] = {}

_WEBHOOK_TIMEOUT_SECONDS = 10.0
_DISCORD_MAX_CONTENT = 1900  # Discord rejects content over 2000 characters
# Strong references to in-flight deliveries; the event loop only keeps weak ones.
_webhook_tasks: set[asyncio.Task] = set()

_IS_MACOS = sys.platform == "darwin"
_IS_WINDOWS = sys.platform == "win32"

if _IS_MACOS:
    _BACKEND_BINARY = "osascript"
elif _IS_WINDOWS:
    _BACKEND_BINARY = "powershell"
else:
    _BACKEND_BINARY = "notify-send"


def notifier_available() -> bool:
    return shutil.which(_BACKEND_BINARY) is not None


# Backwards-compatible alias (the original Linux-only name).
notify_send_available = notifier_available


def _applescript_escape(text: str) -> str:
    # We're building a double-quoted AppleScript string literal, not a shell
    # string - only backslash and double-quote need escaping here.
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _powershell_escape(text: str) -> str:
    # Building a single-quoted PowerShell string literal - only the single
    # quote itself needs escaping, by doubling it (PowerShell's equivalent
    # of backslash-escaping).
    return text.replace("'", "''")


def _windows_toast_script(title: str, message: str) -> str:
    """
    Builds a real Windows toast notification (not a MessageBox popup) using
    the WinRT ToastNotificationManager API directly from Windows
    PowerShell - a well-documented pattern that needs no extra module
    install, unlike the more commonly cited `BurntToast` module.

    Known, unverified risk: WinRT toasts normally associate with an
    "AppUserModelID" (AUMID) that a properly installed/shortcut-registered
    app would have; a bare script invocation like this typically ends up
    borrowing PowerShell's own AUMID; some Windows versions still show the
    toast fine under "Windows PowerShell" as the sender, others may
    suppress it if PowerShell itself has notifications disabled in
    Settings, or if a given build enforces stricter AUMID requirements.
    This is exactly the kind of platform-specific behavior that needs a
    real Windows machine to confirm - written to the documented API
    surface, not yet verified end-to-end.
    """
    t = _powershell_escape(title)
    m = _powershell_escape(message)
    return (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
        "$textNodes = $template.GetElementsByTagName('text'); "
        f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{t}')) | Out-Null; "
        f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{m}')) | Out-Null; "
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'Internet Monitor').Show($toast)"
    )


def build_webhook_payload(url: str, title: str, message: str, urgency: str) -> dict:
    """
    JSON body for the destination, chosen from the URL because Slack and
    Discord disagree on the key: Slack reads ``text`` (and bolds with ``*x*``),
    Discord reads ``content`` (bold is ``**x**``) and rejects a body without it.
    Anything else gets a generic body carrying both a ready-made ``text`` and
    the separate fields.
    """
    host = (urlsplit(url).hostname or "").lower()
    if host in ("discord.com", "discordapp.com") or host.endswith((".discord.com", ".discordapp.com")):
        content = f"**{title}**\n{message}"
        return {
            "content": content[:_DISCORD_MAX_CONTENT],
            # Target names are user-controlled; never let one @everyone the channel.
            "allowed_mentions": {"parse": []},
        }
    if host == "hooks.slack.com":
        return {"text": f"*{title}*\n{message}"}
    return {"text": f"**{title}**\n{message}", "title": title, "message": message, "urgency": urgency}


async def _send_webhook(url: str, title: str, message: str, urgency: str) -> None:
    payload = build_webhook_payload(url, title, message, urgency)
    try:
        async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = await client.post(url, json=payload)
        if response.status_code >= 400:
            logger.warning("Webhook endpoint answered HTTP %s", response.status_code)
    except Exception as exc:  # never let a bad endpoint raise out of a background task
        # Only the exception type: httpx messages can include the request URL.
        logger.warning("Webhook delivery failed (%s)", type(exc).__name__)


def _dispatch_webhook(url: str, title: str, message: str, urgency: str) -> None:
    task = asyncio.create_task(_send_webhook(url, title, message, urgency))
    _webhook_tasks.add(task)
    task.add_done_callback(_webhook_tasks.discard)


async def flush_webhooks() -> None:
    """Waits for in-flight webhook deliveries (used by tests and clean shutdown)."""
    if _webhook_tasks:
        await asyncio.gather(*list(_webhook_tasks), return_exceptions=True)


async def send(
    title: str,
    message: str,
    *,
    urgency: str = "normal",
    key: str | None = None,
    cooldown_seconds: int = 0,
    webhook_url: str | None = None,
) -> None:
    if key is not None and cooldown_seconds > 0:
        last = _last_sent.get(key)
        now = time.monotonic()
        if last is not None and (now - last) < cooldown_seconds:
            return
        _last_sent[key] = now

    # Before the desktop check on purpose: a headless server has no desktop
    # notifier, and the webhook is exactly how it gets alerted.
    if webhook_url:
        _dispatch_webhook(webhook_url, title, message, urgency)

    if not notifier_available():
        logger.info("[notification suppressed - %s not found] %s: %s", _BACKEND_BINARY, title, message)
        return

    try:
        if _IS_MACOS:
            script = f'display notification "{_applescript_escape(message)}" with title "{_applescript_escape(title)}"'
            proc = await create_subprocess_exec(
                "osascript",
                "-e",
                script,
                stdout=DEVNULL,
                stderr=DEVNULL,
            )
        elif _IS_WINDOWS:
            script = _windows_toast_script(title, message)
            proc = await create_subprocess_exec(
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
                stdout=DEVNULL,
                stderr=DEVNULL,
            )
        else:
            proc = await create_subprocess_exec(
                "notify-send",
                "--app-name=Internet Monitor",
                f"--urgency={urgency}",
                title,
                message,
                stdout=DEVNULL,
                stderr=DEVNULL,
            )
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("Notification subprocess timed out")
    except OSError as exc:
        logger.warning("Failed to send desktop notification: %s", exc)


def reset_cooldowns() -> None:
    """Used by tests."""
    _last_sent.clear()
