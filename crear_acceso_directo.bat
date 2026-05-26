@echo off
REM ════════════════════════════════════════════════════════════════════════════
REM Crear acceso directo de CreditosPro en el escritorio
REM ════════════════════════════════════════════════════════════════════════════
setlocal enabledelayedexpansion

echo.
echo Creando acceso directo en el escritorio...
echo.

REM ── Obtener ruta del escritorio ─────────────────────────────────────────────
for /f "tokens=3" %%i in ('reg query "HKEY_CURRENT_USER\Shell Folders" /v Desktop') do (
    set "DESKTOP=%%i"
)

if not defined DESKTOP (
    echo [ERROR] No se pudo encontrar el escritorio
    pause
    exit /b 1
)

REM ── Ruta del archivo .bat ───────────────────────────────────────────────────
set "BAT_PATH=%~dp0Iniciar CreditosPro.bat"
set "SHORTCUT=%DESKTOP%\CreditosPro.lnk"

REM ── Crear acceso directo con PowerShell ──────────────────────────────────────
powershell -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; " ^
    "$Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); " ^
    "$Shortcut.TargetPath = '%BAT_PATH%'; " ^
    "$Shortcut.WorkingDirectory = '%~dp0'; " ^
    "$Shortcut.IconLocation = 'C:\Windows\System32\pngfile.dll'; " ^
    "$Shortcut.Save()"

if errorlevel 0 (
    echo [✓] Acceso directo creado en el escritorio
    echo [✓] Ruta: !DESKTOP!\CreditosPro.lnk
    echo.
    echo Ahora puedes hacer doble clic en el icono del escritorio para iniciar
    echo CreditosPro sin ver la terminal.
) else (
    echo [ERROR] No se pudo crear el acceso directo
)

echo.
pause
