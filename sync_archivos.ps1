# ============================================================================
# SCRIPT PowerShell: Sincronizar archivos modificados a otro PC
# Uso: .\sync_archivos.ps1
# Copia solo los archivos cambiados desde este PC a otra máquina
# ============================================================================

Write-Host "`n========================================================================" -ForegroundColor Cyan
Write-Host "   SINCRONIZAR CREDITOSPRO v3.0 - Archivos Modificados" -ForegroundColor Cyan
Write-Host "========================================================================`n" -ForegroundColor Cyan

# Carpeta actual
$ESTE_PC_CARPETA = Get-Location

Write-Host "📍 Carpeta actual: $ESTE_PC_CARPETA`n"

# Pedir datos del otro PC
$OTRO_PC_IP = Read-Host "Ingresa la IP del otro PC (ej: 192.168.1.50)"
$OTRO_PC_USUARIO = Read-Host "Ingresa el usuario del otro PC (ej: johan)"
$OTRA_CARPETA_LOCAL = Read-Host "Ingresa la ruta en el otro PC (ej: C:\Users\johan\Desktop\CreditosPro_v2)"

# Construir ruta UNC
$RUTA_UNC = "\\$OTRO_PC_IP\c$"
if ($OTRA_CARPETA_LOCAL -match "^[A-Z]:\\(.+)") {
    $RUTA_RELATIVA = $matches[1]
    $RUTA_RED = "$RUTA_UNC\$RUTA_RELATIVA"
} else {
    $RUTA_RED = $OTRA_CARPETA_LOCAL
}

Write-Host "`n════════════════════════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "ORIGEN:  $ESTE_PC_CARPETA" -ForegroundColor White
Write-Host "DESTINO: $RUTA_RED" -ForegroundColor White
Write-Host "════════════════════════════════════════════════════════════════════════`n" -ForegroundColor Yellow

# Listar archivos a copiar
Write-Host "📦 Archivos que serán copiados:" -ForegroundColor Green
Write-Host "   1️⃣  templates\base.html (CRÍTICO - Interfaz visible)"
Write-Host "   2️⃣  limpiar_elruso_duplicado.py (Script limpieza)`n"

$CONFIRMAR = Read-Host "¿Continuar? (s/n)"
if ($CONFIRMAR -ne "s") {
    Write-Host "`n❌ Cancelado." -ForegroundColor Red
    exit
}

# Intentar conectar
Write-Host "`n🔗 Conectando a $OTRO_PC_IP..." -ForegroundColor Cyan

try {
    # Verificar si la carpeta existe
    if (-not (Test-Path $RUTA_RED)) {
        Write-Host "❌ No se puede acceder a $RUTA_RED`n" -ForegroundColor Red
        Write-Host "SOLUCIONES:" -ForegroundColor Yellow
        Write-Host "1. Verifica que la IP es correcta"
        Write-Host "2. Ambos PCs deben estar en la MISMA RED"
        Write-Host "3. En el otro PC, comparte la carpeta CreditosPro_v2:"
        Write-Host "   - Click derecho ^> Propiedades ^> Compartir"
        Write-Host "   - Agregar 'Todos' con permisos"
        Write-Host "4. Alternativamente, usa USB o Google Drive`n"
        exit 1
    }
    
    Write-Host "✓ Conexión exitosa`n" -ForegroundColor Green
    
} catch {
    Write-Host "❌ Error de conexión: $_`n" -ForegroundColor Red
    exit 1
}

# Copiar archivos
Write-Host "📋 Copiando archivos...`n" -ForegroundColor Cyan

$ARCHIVOS = @(
    @{
        origen = "templates\base.html"
        destino = "$RUTA_RED\templates\base.html"
        descripcion = "HTML mejorado (Interfaz visible)"
    },
    @{
        origen = "limpiar_elruso_duplicado.py"
        destino = "$RUTA_RED\limpiar_elruso_duplicado.py"
        descripcion = "Script limpieza BD"
    }
)

$EXITOS = 0
$ERRORES = 0

foreach ($archivo in $ARCHIVOS) {
    $origen_full = Join-Path $ESTE_PC_CARPETA $archivo.origen
    
    if (-not (Test-Path $origen_full)) {
        Write-Host "   ⚠️  $($archivo.origen) - NO ENCONTRADO en este PC" -ForegroundColor Yellow
        $ERRORES++
        continue
    }
    
    try {
        Write-Host "   📤 Copiando $($archivo.origen)..." -ForegroundColor White
        Copy-Item -Path $origen_full -Destination $archivo.destino -Force -ErrorAction Stop
        Write-Host "       ✓ $($archivo.descripcion)" -ForegroundColor Green
        $EXITOS++
    } catch {
        Write-Host "       ❌ Error: $_" -ForegroundColor Red
        $ERRORES++
    }
}

# Documentación opcional
Write-Host "`n"
$DOCS = Read-Host "¿Copiar también archivos de documentación? (s/n)"

if ($DOCS -eq "s") {
    $DOCS_ARCHIVOS = @(
        @{origen = "GUIA_SINCRONIZACION_OTRO_PC.md"; destino = "$RUTA_RED\GUIA_SINCRONIZACION_OTRO_PC.md"; desc = "Guía de sincronización" },
        @{origen = "RESUMEN_CAMBIOS_v3_0.md"; destino = "$RUTA_RED\RESUMEN_CAMBIOS_v3_0.md"; desc = "Resumen técnico" }
    )
    
    foreach ($doc in $DOCS_ARCHIVOS) {
        $origen_full = Join-Path $ESTE_PC_CARPETA $doc.origen
        if (Test-Path $origen_full) {
            Copy-Item -Path $origen_full -Destination $doc.destino -Force -ErrorAction SilentlyContinue
            Write-Host "   ✓ $($doc.desc)" -ForegroundColor Green
        }
    }
}

# Resumen
Write-Host "`n════════════════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "✓ SINCRONIZACIÓN COMPLETADA" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════════════════`n" -ForegroundColor Green

Write-Host "📊 Resultado:" -ForegroundColor Cyan
Write-Host "   ✓ Exitosos: $EXITOS" -ForegroundColor Green
if ($ERRORES -gt 0) {
    Write-Host "   ❌ Errores: $ERRORES" -ForegroundColor Red
}

Write-Host "`n🔄 PRÓXIMOS PASOS EN EL OTRO PC:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Abre PowerShell en la carpeta CreditosPro_v2"
Write-Host ""
Write-Host "2. Ejecuta la limpieza de duplicados (CRÍTICO):"
Write-Host "   " -NoNewline
Write-Host "python limpiar_elruso_duplicado.py" -ForegroundColor Yellow
Write-Host "   (responde 's' cuando pida confirmación)"
Write-Host ""
Write-Host "3. Reinicia el servidor:"
Write-Host "   " -NoNewline
Write-Host "python run.py" -ForegroundColor Yellow
Write-Host ""
Write-Host "4. Abre Chrome y verifica:"
Write-Host "   " -NoNewline
Write-Host "http://127.0.0.1:8000/dashboard" -ForegroundColor Yellow
Write-Host "   (El dashboard debe ser VISIBLE, no transparente)"
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════════════`n" -ForegroundColor Cyan

Read-Host "Presiona Enter para salir"
