@echo off
REM Run this with Blender CLOSED. Renames corrupted scripts\modules so Blender stops using it.
set "BLENDER_SCRIPTS=%APPDATA%\Blender Foundation\Blender\4.5\scripts"
set "MODULES=%BLENDER_SCRIPTS%\modules"
set "BACKUP=%BLENDER_SCRIPTS%\modules_broken_backup"

if not exist "%MODULES%" (
    echo Folder not found: %MODULES%
    echo Nothing to fix.
    pause
    exit /b 0
)

echo Renaming corrupted folder to modules_broken_backup...
echo   From: %MODULES%
echo   To:   %BACKUP%

if exist "%BACKUP%" (
    echo Backup folder already exists. Remove it first if you want to re-run.
    pause
    exit /b 1
)

ren "%MODULES%" "modules_broken_backup"
if errorlevel 1 (
    echo Failed to rename. Try closing Blender and any Python processes, then run again.
    pause
    exit /b 1
)

echo Done. You can now open Blender; addons should load using Blender's built-in numpy.
echo To use FastF1, in Blender click "Upgrade / Reinstall FastF1 (3.8.1+)" - it installs to f1_studio_modules (no conflict).
pause
