@echo off
REM ============================================================================
REM COPIAR A USB - CreditosPro v3.0
REM Uso: copiar_a_usb.bat
REM Copia los 2 archivos necesarios a USB automáticamente
REM ============================================================================

setlocal enabledelayedexpansion

cls
echo.
echo ========================================================================
echo    COPIAR ARCHIVOS A USB - CreditosPro v3.0
echo ========================================================================
echo.

echo Buscar USB...
set USB_FOUND=0
for %%A in (D: E: F: G: H: I: J: K: L: M: N: O: P: Q: R: S: T: U: V: W: X: Y: Z:) do (
    if exist %%A\nul (
        echo   Encontrado: %%A
        set USB_DRIVE=%%A
        set USB_FOUND=1
    )
)

if "%USB_FOUND%"=="0" (
    echo.
    echo [ERROR] No se detectó USB conectado
    echo Conecta un USB e intenta de nuevo
    echo.
    pause
    exit /b 1
)

set /p CONFIRMAR="¿Usar %USB_DRIVE%? (s/n): "
if /i "%CONFIRMAR%"=="n" (
    set /p USB_DRIVE="Ingresa la letra de la unidad USB (ej: E): "
)

echo.
echo ========================================================================
echo ORIGEN: %CD%
echo DESTINO: %USB_DRIVE%\
echo ========================================================================
echo.

echo Copiando archivos...
echo.

REM 1. base.html
echo [1/2] Copiando templates\base.html...
copy /Y "%CD%\templates\base.html" "%USB_DRIVE%\base.html" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se pudo copiar base.html
    pause
    exit /b 1
) else (
    echo      [OK] ✓ Copiado
)

REM 2. limpiar_elruso_duplicado.py
echo [2/2] Copiando limpiar_elruso_duplicado.py...
copy /Y "%CD%\limpiar_elruso_duplicado.py" "%USB_DRIVE%\limpiar_elruso_duplicado.py" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se pudo copiar limpiar_elruso_duplicado.py
    pause
    exit /b 1
) else (
    echo      [OK] ✓ Copiado
)

echo.
echo ========================================================================
echo ✓ ARCHIVOS COPIADOS AL USB EXITOSAMENTE
echo ========================================================================
echo.
echo USB (%USB_DRIVE%\) contiene:
echo   - base.html
echo   - limpiar_elruso_duplicado.py
echo.
echo PRÓXIMOS PASOS EN EL OTRO PC:
echo.
echo 1. Conecta este USB al otro PC
echo 2. Copia base.html a:           CreditosPro_v2\templates\
echo 3. Copia limpiar... .py a:      CreditosPro_v2\
echo 4. Abre PowerShell en CreditosPro_v2
echo 5. Ejecuta:  python limpiar_elruso_duplicado.py
echo 6. Ejecuta:  python run.py
echo.
echo ========================================================================
echo.
pause
