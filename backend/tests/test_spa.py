"""
==============================================================================
Module Name:   test_spa.py
Description:   Static frontend serving: path-traversal protection and SPA fallback.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-14
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         pytest backend/tests/test_spa.py
Notes:         See module docstrings of the code under test.
==============================================================================
"""

from __future__ import annotations

import pytest
from app.spa import mount_frontend, resolve_static_file
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = "TOP-SECRET-OUTSIDE-DIST"


@pytest.fixture
def site(tmp_path):
    """tmp/ has a secret *next to* dist/, exactly like backend/ or the project root would."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPA SHELL</html>")
    (dist / "favicon.svg").write_text("<svg>icon</svg>")
    (dist / "assets" / "app.js").write_text("console.log('ok')")
    (tmp_path / "secret.txt").write_text(SECRET)
    app = FastAPI()
    mount_frontend(app, dist)
    return dist, TestClient(app)


def test_real_files_and_spa_fallback_still_work(site):
    _dist, client = site
    assert client.get("/favicon.svg").text == "<svg>icon</svg>"
    assert client.get("/assets/app.js").status_code == 200
    assert "SPA SHELL" in client.get("/").text
    assert "SPA SHELL" in client.get("/history/deep/link").text  # client-side route -> index.html


@pytest.mark.parametrize(
    "path",
    [
        "/../secret.txt",
        "/..%2fsecret.txt",
        "/%2e%2e/secret.txt",
        "/%2e%2e%2fsecret.txt",
        "/assets/../../secret.txt",
        "/assets/..%2f..%2fsecret.txt",
        "/..%2f..%2f..%2f..%2fetc/passwd",
        "//etc/passwd",
        "/%2fetc%2fpasswd",
    ],
)
def test_traversal_never_leaks_files_outside_dist(site, path):
    _dist, client = site
    response = client.get(path)
    assert SECRET not in response.text
    assert "root:" not in response.text  # /etc/passwd
    # Safe outcome: the SPA shell (or a 404) - never the targeted file.
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        assert "SPA SHELL" in response.text


def test_resolve_static_file_unit(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "a.txt").write_text("a")
    (tmp_path / "outside.txt").write_text("x")
    assert resolve_static_file(dist, "a.txt") == (dist / "a.txt").resolve()
    assert resolve_static_file(dist, "../outside.txt") is None
    assert resolve_static_file(dist, "") is None
    assert resolve_static_file(dist, "missing.txt") is None
    assert resolve_static_file(dist, "sub/../a.txt") == (dist / "a.txt").resolve()  # stays inside: fine
    assert resolve_static_file(dist, "a\x00.txt") is None  # NUL byte must not raise
    assert resolve_static_file(dist, str(tmp_path / "outside.txt")) is None  # absolute path


@pytest.mark.skipif(not hasattr(__import__("os"), "symlink"), reason="needs symlinks")
def test_symlink_escaping_dist_is_not_followed(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (tmp_path / "secret.txt").write_text(SECRET)
    try:
        (dist / "link.txt").symlink_to(tmp_path / "secret.txt")
    except OSError:
        pytest.skip("cannot create symlinks here")
    assert resolve_static_file(dist, "link.txt") is None
