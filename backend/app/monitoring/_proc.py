"""
==============================================================================
Module Name:   _proc.py
Description:   Process execution and encoding helper for subprocess calls.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 _proc.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

import sys
from typing import Any

_CREATE_NO_WINDOW = 0x08000000

NO_WINDOW: dict[str, Any] = (
    {"creationflags": _CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)


def oem_encoding() -> str:
    """Console tools on Windows (netsh, ipconfig, ping) write in the OEM
    code page, not UTF-8; decoding with the wrong one garbles non-ASCII
    SSIDs. Falls back to UTF-8 anywhere that can't be determined."""
    if sys.platform == "win32":
        try:
            import ctypes

            return f"cp{ctypes.windll.kernel32.GetOEMCP()}"  # type: ignore[attr-defined]
        except Exception:
            return "utf-8"
    return "utf-8"


def decode_output(data: bytes) -> str:
    enc = oem_encoding()
    try:
        return data.decode(enc, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")
