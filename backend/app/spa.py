"""
==============================================================================
Module Name:   spa.py
Description:   Safe static-file serving for the built single-page frontend.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-14
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         imported by app.main (mount_frontend)
Notes:         Requires Python 3.10+ (Path.is_relative_to)
==============================================================================
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def resolve_static_file(root: Path, requested: str) -> Path | None:
    """
    Maps a URL path onto a real file strictly *inside* ``root``, or returns
    None when it does not name one.

    The URL path reaches us already percent-decoded, so ``/..%2f..%2fsecret``
    arrives as ``../../secret``; joining that onto ``root`` and serving it
    would read arbitrary files. Resolving first (which also follows symlinks
    and collapses ``..``) and then requiring the result to still live under
    the resolved root closes that hole, including absolute-path inputs like
    ``/etc/passwd`` (``Path.__truediv__`` discards the left side for those).
    """
    if not requested:
        return None
    try:
        root_resolved = root.resolve()
        candidate = (root_resolved / requested).resolve()
        if candidate.is_file() and candidate.is_relative_to(root_resolved):
            return candidate
    except (OSError, ValueError):  # ValueError: embedded NUL byte in the path
        return None
    return None


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serves the built dashboard (assets + SPA fallback to index.html)."""
    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        candidate = resolve_static_file(dist_dir, full_path)
        if candidate is not None:
            return FileResponse(candidate)
        # Anything that is not a real file inside dist/ gets the SPA shell -
        # never the file the request tried to reach.
        return FileResponse(dist_dir / "index.html")
