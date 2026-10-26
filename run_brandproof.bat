@echo off
setlocal EnableExtensions

rem BrandProof AI one-click local runner for Windows.
rem Run this file from File Explorer or from PowerShell.

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "PYTHON=%BACKEND%\.venv\Scripts\python.exe"
set "PY_LAUNCHER="

echo.
echo ========================================
echo       BrandProof AI local launcher
echo ========================================
echo.

where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm was not found.
    echo Install Node.js 20 or newer, then run this file again.
    pause
    exit /b 1
)

if exist "%PYTHON%" goto :python_ready

where py >nul 2>&1
if not errorlevel 1 set "PY_LAUNCHER=py -3"
if defined PY_LAUNCHER goto :create_venv

python --version >nul 2>&1
if not errorlevel 1 set "PY_LAUNCHER=python"
if defined PY_LAUNCHER goto :create_venv

python3 --version >nul 2>&1
if not errorlevel 1 set "PY_LAUNCHER=python3"
if defined PY_LAUNCHER goto :create_venv

echo ERROR: Python was not found as py, python, or python3.
echo Install Python 3.11 or newer, then run this file again.
pause
exit /b 1

:create_venv
echo Creating the backend virtual environment...
%PY_LAUNCHER% -m venv "%BACKEND%\.venv"
if errorlevel 1 (
    echo ERROR: Could not create the backend virtual environment.
    pause
    exit /b 1
)

:python_ready

echo Checking backend dependencies...
"%PYTHON%" -c "import fastapi, uvicorn, sqlalchemy, pydantic_settings, pypdf, psycopg" >nul 2>&1
if errorlevel 1 (
    echo Installing backend dependencies. This may take a few minutes...
    "%PYTHON%" -m pip install -r "%BACKEND%\requirements.txt"
    if errorlevel 1 (
        echo ERROR: Backend dependency installation failed.
        pause
        exit /b 1
    )
)

if not exist "%FRONTEND%\node_modules" (
    echo Installing frontend dependencies. This may take a few minutes...
    pushd "%FRONTEND%"
    call npm install
    if errorlevel 1 (
        popd
        echo ERROR: Frontend dependency installation failed.
        pause
        exit /b 1
    )
    popd
)

echo Starting the backend on http://localhost:8000 ...
start "BrandProof Backend" /D "%BACKEND%" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

echo Starting the frontend on http://localhost:3000 ...
start "BrandProof Frontend" /D "%FRONTEND%" cmd /k "npm run dev"

echo Waiting for the frontend to start...
timeout /t 4 /nobreak >nul
start "" http://localhost:3000

echo.
echo BrandProof AI is starting in two new windows.
echo Frontend: http://localhost:3000
echo Backend:  http://localhost:8000/docs
echo Close the two server windows to stop the application.
echo.
pause

endlocal
