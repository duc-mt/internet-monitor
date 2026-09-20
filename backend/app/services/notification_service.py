"""
Desktop notifications.

- Linux: `notify-send` (part of libnotify, present on virtually every Linux
  desktop - GNOME, KDE, XFCE, etc.).
- macOS: `osascript` (AppleScript), which ships with every Mac - no install
  needed. This gets a real Notification Center banner without pulling in
  any third-party dependency.

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
_BACKEND_BINARY = "osascript" if _IS_MACOS else "notify-send"


def notifier_available() -> bool:
    return shutil.which(_BACKEND_BINARY) is not None


# Backwards-compatible alias (the original Linux-only name).
notify_send_available = notifier_available


def _applescript_escape(text: str) -> str:
    # We're building a double-quoted AppleScript string literal, not a shell
    # string - only backslash and double-quote need escaping here.
    return text.replace("\\", "\\\\").replace('"', '\\"')


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
