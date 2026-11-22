@echo off
cd /d "%~dp0"
chcp 65001 >nul
set "PYFILE="
for %%f in (*.py) do set "PYFILE=%%f"
if not defined PYFILE (
  echo No .py file found in this folder.
  pause
  exit /b
)
python "%PYFILE%"
if errorlevel 1 (
  echo.
  echo Failed to start. Please install Python and pygame: pip install pygame
  pause
)
