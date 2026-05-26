@echo off
REM ============================================================================
REM SCRIPT: Sincronizar archivos actualizados a otro PC por RED
REM Uso: sync_archivos.bat
REM Copia solo los archivos modificados desde este PC a otra máquina en red
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ========================================================================
echo    SINCRONIZAR CREDITOSPRO v3.0 - Archivos Modificados
echo ========================================================================
echo.

REM Variables
set "ESTE_PC_CARPETA=%CD%"
set /p OTRO_PC_IP="Ingresa la IP del otro PC (ej: 192.168.1.50): "
set /p OTRO_PC_USUARIO="Ingresa el usuario del otro PC (ej: johan): "
set /p OTRO_PC_CARPETA="Ingresa la ruta en el otro PC (ej: C:\Users\johan\Desktop\CreditosPro_v2): "

REM Construir ruta UNC
set "RUTA_RED=\\%OTRO_PC_IP%\c$\Users\%OTRO_PC_USUARIO%\Desktop\CreditosPro_v2"

echo.
echo ESTE PC:        %ESTE_PC_CARPETA%
echo OTRO PC (RED):  %RUTA_RED%
echo.
echo Archivos a copiar:
echo  1. templates\base.html (CRÍTICO - Interfaz visible)
echo  2. limpiar_elruso_duplicado.py (Script limpieza)
echo.

set /p CONFIRMAR="¿Continuar con la sincronización? (s/n): "
if /i "%CONFIRMAR%"=="n" (
    echo Cancelado.
    exit /b 0
)

REM Intentar conectar a la carpeta compartida
echo.
echo Conectando a %OTRO_PC_IP%...
net use %RUTA_RED% /user:%OTRO_PC_USUARIO% 2>nul
if errorlevel 1 (
    echo.
    echo [!] No se puede conectar a %OTRO_PC_IP%
    echo.
    echo SOLUCIONES:
    echo 1. Verifica que la IP es correcta
    echo 2. Ambos PCs deben estar en la MISMA RED
    echo 3. Compartir carpeta en otro PC:
    echo    - Click derecho en CreditosPro_v2
    echo    - Propiedades ^> Compartir ^> Compartir
    echo    - Agregar usuario "Todos" con permisos
    echo 4. Alternativamente, usa USB o Google Drive
    echo.
    pause
    exit /b 1
)

REM Copiar archivos
echo.
echo [+] Copiando archivos...
echo.

REM 1. templates/base.html
echo  ^ Copiando templates\base.html...
copy /Y "%ESTE_PC_CARPETA%\templates\base.html" "%RUTA_RED%\templates\base.html" >nul 2>&1
if errorlevel 1 (
    echo    [ERROR] No se pudo copiar base.html
) else (
    echo    [OK] base.html copiado exitosamente
)

REM 2. limpiar_elruso_duplicado.py
echo  ^ Copiando limpiar_elruso_duplicado.py...
copy /Y "%ESTE_PC_CARPETA%\limpiar_elruso_duplicado.py" "%RUTA_RED%\limpiar_elruso_duplicado.py" >nul 2>&1
if errorlevel 1 (
    echo    [ERROR] No se pudo copiar limpiar_elruso_duplicado.py
) else (
    echo    [OK] limpiar_elruso_duplicado.py copiado exitosamente
)

REM 3. Archivos de documentación (opcional)
echo.
set /p DOCS="¿Copiar también archivos de documentación? (s/n): "
if /i "%DOCS%"=="s" (
    echo  ^ Copiando GUIA_SINCRONIZACION_OTRO_PC.md...
    copy /Y "%ESTE_PC_CARPETA%\GUIA_SINCRONIZACION_OTRO_PC.md" "%RUTA_RED%\GUIA_SINCRONIZACION_OTRO_PC.md" >nul 2>&1
    
    echo  ^ Copiando RESUMEN_CAMBIOS_v3_0.md...
    copy /Y "%ESTE_PC_CARPETA%\RESUMEN_CAMBIOS_v3_0.md" "%RUTA_RED%\RESUMEN_CAMBIOS_v3_0.md" >nul 2>&1
    
    echo    [OK] Documentación copiada
)

echo.
echo ========================================================================
echo ✓ SINCRONIZACIÓN COMPLETADA
echo ========================================================================
echo.
echo PRÓXIMOS PASOS EN EL OTRO PC:
echo.
echo 1. Abre PowerShell en la carpeta CreditosPro_v2
echo.
echo 2. Ejecuta la limpieza de duplicados:
echo    python limpiar_elruso_duplicado.py
echo    (responde "s" a la confirmación)
echo.
echo 3. Reinicia el servidor:
echo    python run.py
echo.
echo 4. Abre Chrome y verifica:
echo    http://127.0.0.1:8000/dashboard
echo    (El dashboard debe ser visible, no transparente)
echo.
echo ========================================================================
echo.
pause
