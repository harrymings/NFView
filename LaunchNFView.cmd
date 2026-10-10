@echo off
cd /d "%~dp0"
if exist "%~dp0dist\NFView.exe" (
    start "" "%~dp0dist\NFView.exe" %*
) else (
    py "%~dp0image_screener.py" %*
)
