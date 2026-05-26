@echo off
REM ════════════════════════════════════════════════════════════════════════════
REM Configurar inicio automático de CreditosPro al encender el PC
REM ════════════════════════════════════════════════════════════════════════════
setlocal enabledelayedexpansion

echo.
echo Configurando inicio automático de CreditosPro...
echo.

REM ── Obtener ruta de Startup ─────────────────────────────────────────────────
for /f "tokens=3" %%i in ('reg query "HKEY_CURRENT_USER\Shell Folders" /v Startup') do (
    set "STARTUP=%%i"
)

if not defined STARTUP (
    echo [ERROR] No se pudo encontrar la carpeta Startup
    pause
    exit /b 1
)

REM ── Ruta del archivo .bat ───────────────────────────────────────────────────
set "BAT_PATH=%~dp0Iniciar CreditosPro.bat"
set "SHORTCUT=%STARTUP%\CreditosPro.lnk"

REM ── Crear acceso directo en Startup ─────────────────────────────────────────
powershell -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; " ^
    "$Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); " ^
    "$Shortcut.TargetPath = '%BAT_PATH%'; " ^
    "$Shortcut.WorkingDirectory = '%~dp0'; " ^
    "$Shortcut.Save()"

if errorlevel 0 (
    echo [✓] Acceso directo creado en Startup
    echo [✓] Ruta: !STARTUP!\CreditosPro.lnk
    echo.
    echo CreditosPro ahora se iniciara automaticamente al encender el PC
    echo.
    echo Para desactivar:
    echo   1. Presiona Win + R
    echo   2. Escribe: shell:startup
    echo   3. Borra el acceso directo "CreditosPro"
) else (
    echo [ERROR] No se pudo crear el acceso directo
)

echo.
pause
