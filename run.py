#!/usr/bin/env python3
"""
==============================================================================
Module Name:   run.py
Description:   Implementation and logic for run.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 run.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

import os
import platform
import subprocess
import sys
from pathlib import Path


def check_python_version():
    pass


def is_stale(stamp_file: Path, source_files: list[Path]) -> bool:
    if not stamp_file.exists():
        return True
    stamp_time = stamp_file.stat().st_mtime
    for sf in source_files:
        if sf.exists() and sf.stat().st_mtime > stamp_time:
            return True
    return False


def mark_fresh(stamp_file: Path):
    # Ensure directory exists before creating stamp
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    stamp_file.touch()


def main():
    check_python_version()

    # Ensure we operate from the project root
    root_dir = Path(__file__).parent.resolve()
    os.chdir(root_dir)

    is_windows = platform.system() == "Windows"

    # Determine OS-specific virtual environment paths
    venv_dir = root_dir / ".venv"
    if is_windows:
        venv_bin = venv_dir / "Scripts"
        python_exe = venv_bin / "python.exe"
        pip_exe = venv_bin / "pip.exe"
        cli_exe = venv_bin / "internet-monitor.exe"
        npm_cmd = "npm.cmd"
    else:
        venv_bin = venv_dir / "bin"
        python_exe = venv_bin / "python"
        pip_exe = venv_bin / "pip"
        cli_exe = venv_bin / "internet-monitor"
        npm_cmd = "npm"

    # 1. Setup Backend / CLI Virtual Environment
    backend_reqs = root_dir / "backend" / "requirements.txt"
    cli_reqs = root_dir / "cli" / "pyproject.toml"
    py_stamp = venv_dir / ".deps_installed_stamp"

    if is_stale(py_stamp, [backend_reqs, cli_reqs]) or not cli_exe.exists():
        print("Checking and installing Python dependencies...")

        if not venv_dir.exists():
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

        subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip", "-q"], check=True)
        subprocess.run([str(pip_exe), "install", "-r", str(backend_reqs), "uvicorn"], check=True)
        subprocess.run([str(pip_exe), "install", "-e", str(root_dir / "cli")], check=True)
        mark_fresh(py_stamp)

    # 2. Setup Frontend
    frontend_dir = root_dir / "frontend"
    pkg_json = frontend_dir / "package.json"
    pkg_lock = frontend_dir / "package-lock.json"
    node_stamp = frontend_dir / "node_modules" / ".deps_installed_stamp"
    frontend_dist = frontend_dir / "dist"

    import shutil

    has_npm = shutil.which(npm_cmd) is not None

    if has_npm:
        if is_stale(node_stamp, [pkg_json, pkg_lock]) or not frontend_dist.exists():
            print("Checking and installing frontend dependencies...")
            try:
                subprocess.run([npm_cmd, "install"], cwd=frontend_dir, check=True)
                subprocess.run([npm_cmd, "run", "build"], cwd=frontend_dir, check=True)
                mark_fresh(node_stamp)
            except subprocess.CalledProcessError:
                print("Warning: Frontend build failed.")
    else:
        if not frontend_dist.exists():
            print(f"Warning: '{npm_cmd}' is required to build the frontend but not found.")
            print("The dashboard will not be available until you install Node.js and build it.")

    # 3. Execution
    args = sys.argv[1:]
    if not args:
        print("Starting Internet Monitor backend server on http://127.0.0.1:8765...")
        os.chdir(root_dir / "backend")

        # On Windows, replace the current process isn't natively supported the same way,
        # so we use subprocess.run. On Unix, we could use os.execv but run() is simpler across OS.
        try:
            subprocess.run([str(python_exe), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765"])
        except KeyboardInterrupt:
            pass  # Suppress traceback when user presses Ctrl+C
    else:
        try:
            subprocess.run([str(cli_exe)] + args)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
