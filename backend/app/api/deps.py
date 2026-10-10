
"""
==============================================================================
Module Name:   deps.py
Description:   Implementation and logic for deps.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 deps.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

from app.database.connection import get_db

__all__ = ["get_db"]
