@echo off
REM ════════════════════════════════════════════════════════════════════════════
REM CreditosPro v2.1 — Inicio automático sin terminal visible
REM ════════════════════════════════════════════════════════════════════════════
setlocal enabledelayedexpansion

REM ── Obtener directorio actual ───────────────────────────────────────────────
cd /d "%~dp0"

REM ── Verificar que Python esté instalado ──────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en PATH
    echo.
    echo Por favor:
    echo 1. Descarga Python 3.11+ desde python.org
    echo 2. Durante la instalacion MARCA "Add Python to PATH"
    echo 3. Reinicia este script
    echo.
    pause
    exit /b 1
)

REM ── Mostrar IP local para acceso desde otros dispositivos ────────────────────
echo.
echo ╔════════════════════════════════════════════════════════════════════════════╗
echo ║                         CreditosPro v2.1                                   ║
echo ╚════════════════════════════════════════════════════════════════════════════╝
echo.
echo [INFO] Iniciando servidor...
echo.

for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /R "IPv4"') do (
    for /f "tokens=1" %%j in ("%%i") do (
        set "LOCAL_IP=%%j"
        goto :ip_found
    )
)
:ip_found

if defined LOCAL_IP (
    echo [✓] Acceso local:        http://127.0.0.1:8000
    echo [✓] Desde otros PCs:     http://!LOCAL_IP!:8000
    echo [✓] Celular en WiFi:     http://!LOCAL_IP!:8000
) else (
    echo [✓] Acceso local:        http://127.0.0.1:8000
)

echo.
echo Cerrando esta ventana en 2 segundos...
timeout /t 2 /nobreak

REM ── Ejecutar en background sin mostrar terminal ──────────────────────────────
start "" /b python run.py

REM ── Esperar un poco para que el navegador abra y luego cerrar esta ventana ────
timeout /t 3 /nobreak
exit /b 0
