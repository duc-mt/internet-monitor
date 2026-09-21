"""
Desktop notifications.

- Linux: `notify-send` (part of libnotify, present on virtually every Linux
  desktop - GNOME, KDE, XFCE, etc.).
- macOS: `osascript` (AppleScript), which ships with every Mac - no install
  needed. This gets a real Notification Center banner without pulling in
  any third-party dependency.
- Windows: `powershell` (Windows PowerShell 5.1, bundled with every
  Windows 10/11 install) driving the WinRT toast-notification API
  directly - no extra module (e.g. BurntToast) needs installing. This is
  the one platform branch in this file that is unverified on real
  hardware (see the docstring on _windows_toast_script below for the
  specific, known risk).

Either way we shell out with argv-list subprocess calls (no shell=True),
keeping the monitoring service itself free of any GUI-toolkit dependency
and safe to run headless - and safe from injection even though titles and
messages can contain target names/error text we don't fully control.

State transitions (offline/online) always fire immediately - a user always
wants to know the instant they lose or regain connectivity. Threshold
alerts (latency/packet-loss) are debounced per (kind, target) key so a
flapping metric doesn't spam five notifications a minute.
"""
from __future__ import annotations

import logging
import shutil
import sys
import time
from asyncio import create_subprocess_exec
from asyncio.subprocess import DEVNULL

logger = logging.getLogger("internet_monitor.notifications")

_last_sent: dict[str, float] = {}

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


async def send(title: str, message: str, *, urgency: str = "normal", key: str | None = None,
                cooldown_seconds: int = 0) -> None:
    if key is not None and cooldown_seconds > 0:
        last = _last_sent.get(key)
        now = time.monotonic()
        if last is not None and (now - last) < cooldown_seconds:
            return
        _last_sent[key] = now

    if not notifier_available():
        logger.info("[notification suppressed - %s not found] %s: %s", _BACKEND_BINARY, title, message)
        return

    try:
        if _IS_MACOS:
            script = (
                f'display notification "{_applescript_escape(message)}" '
                f'with title "{_applescript_escape(title)}"'
            )
            proc = await create_subprocess_exec(
                "osascript", "-e", script, stdout=DEVNULL, stderr=DEVNULL,
            )
        elif _IS_WINDOWS:
            script = _windows_toast_script(title, message)
            proc = await create_subprocess_exec(
                "powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                "-Command", script,
                stdout=DEVNULL, stderr=DEVNULL,
            )
        else:
            proc = await create_subprocess_exec(
                "notify-send", "--app-name=Internet Monitor", f"--urgency={urgency}",
                title, message,
                stdout=DEVNULL, stderr=DEVNULL,
            )
        await proc.wait()
    except OSError as exc:
        logger.warning("Failed to send desktop notification: %s", exc)


def reset_cooldowns() -> None:
    """Used by tests."""
    _last_sent.clear()
