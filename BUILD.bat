@echo off
title CreditosPro v2.0 — Compilador .exe
color 0A

echo.
echo ============================================================
echo   CreditosPro v2.0  ^|  Compilador de Administrador .exe
echo ============================================================
echo.

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.11+
    pause & exit /b 1
)

:: Instalar dependencias
echo [1/4] Instalando dependencias...
pip install -r requirements.txt --quiet
pip install pywebview pyinstaller --quiet
echo      OK

:: Limpiar compilaciones anteriores
echo [2/4] Limpiando compilacion anterior...
if exist dist\CreditosProAdmin.exe del /f /q dist\CreditosProAdmin.exe 2>nul
if exist build rmdir /s /q build 2>nul
echo      OK

:: Compilar
echo [3/4] Compilando... (puede tardar 1-2 minutos)
pyinstaller ^
  --noconsole ^
  --onefile ^
  --name "CreditosProAdmin" ^
  --icon NONE ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "app;app" ^
  --hidden-import "passlib.handlers.bcrypt" ^
  --hidden-import "jose" ^
  --hidden-import "webview" ^
  --hidden-import "sqlalchemy.dialects.sqlite" ^
  administrador.py

if errorlevel 1 (
    echo [ERROR] Compilacion fallida. Revisa los mensajes arriba.
    pause & exit /b 1
)

echo [4/4] Moviendo ejecutable...
if not exist dist mkdir dist
echo.
echo ============================================================
echo   EXITO: dist\CreditosProAdmin.exe
echo.
echo   MODOS DE USO:
echo   - Local (DB local):
echo     CreditosProAdmin.exe
echo.
echo   - Remoto (DB en la nube, cobradores conectados):
echo     CreditosProAdmin.exe --url https://mi-app.railway.app
echo ============================================================
echo.
pause
