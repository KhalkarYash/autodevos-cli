@echo off
REM Build script for Windows .exe installer

echo Building AutoDevOS for Windows...

REM Ensure we're in project root
cd /d "%~dp0\.."

REM Install build dependencies
pip install pyinstaller

REM Build the executable
pyinstaller build\autodevos.spec --clean --noconfirm

echo.
echo ✅ Built: dist\ados.exe
echo.
echo To create an installer, use Inno Setup with build\installer.iss
pause
