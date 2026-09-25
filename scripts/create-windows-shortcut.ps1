<#
.SYNOPSIS
    Creates a desktop shortcut for Internet Monitor on Windows.

.DESCRIPTION
    This script creates an "Internet Monitor" shortcut on the current user's Desktop.
    The shortcut will automatically open PowerShell, navigate to this project directory,
    and start the backend Uvicorn server using the local Python virtual environment.
#>

$ErrorActionPreference = "Stop"

# Get the absolute path to the project root (one folder up from /scripts)
$ScriptDir = $PSScriptRoot
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$BackendDir = Join-Path $ProjectRoot "backend"

# Get the user's Desktop path
$WshShell = New-Object -comObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $DesktopPath "Internet Monitor.lnk"

# Create the shortcut
Write-Host "Creating shortcut at: $ShortcutPath"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "powershell.exe"

# The command navigates to the backend folder and runs the local venv python
$Command = "cd '$BackendDir'; & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8765"
$Shortcut.Arguments = "-NoExit -Command `"$Command`""
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.IconLocation = "powershell.exe,0"

$Shortcut.Save()

Write-Host "Done! You can now double-click 'Internet Monitor' on your Desktop."
