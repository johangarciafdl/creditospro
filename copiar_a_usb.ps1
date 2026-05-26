# ============================================================================
# COPIAR A USB - CreditosPro v3.0
# Uso: .\copiar_a_usb.ps1
# Copia los 2 archivos necesarios a USB automáticamente
# ============================================================================

Clear-Host

Write-Host "`n========================================================================" -ForegroundColor Cyan
Write-Host "   COPIAR ARCHIVOS A USB - CreditosPro v3.0" -ForegroundColor Cyan
Write-Host "========================================================================`n" -ForegroundColor Cyan

# Detectar USBs
Write-Host "🔍 Buscando unidades USB..." -ForegroundColor Yellow
$USBS = @()

for ($i = 68; $i -le 90; $i++) {  # D: a Z:
    $LETRA = [char]$i
    $RUTA = "$LETRA`:"
    if (Test-Path $RUTA) {
        $USBS += $RUTA
        Write-Host "   Encontrado: $RUTA" -ForegroundColor Green
    }
}

if ($USBS.Count -eq 0) {
    Write-Host "`n❌ No se detectó USB conectado" -ForegroundColor Red
    Write-Host "Conecta un USB e intenta de nuevo`n"
    Read-Host "Presiona Enter para salir"
    exit 1
}

# Seleccionar USB
if ($USBS.Count -eq 1) {
    $USB_DRIVE = $USBS[0]
    Write-Host "`n✓ Usando: $USB_DRIVE`n" -ForegroundColor Green
} else {
    Write-Host "`nEncontrados varios USB:`n"
    for ($i = 0; $i -lt $USBS.Count; $i++) {
        Write-Host "   [$($i+1)] $($USBS[$i])"
    }
    $OPCION = Read-Host "Selecciona (1-$($USBS.Count))"
    $USB_DRIVE = $USBS[[int]$OPCION - 1]
}

$ORIGEN = Get-Location

Write-Host "`n========================================================================" -ForegroundColor Yellow
Write-Host "ORIGEN:  $ORIGEN" -ForegroundColor White
Write-Host "DESTINO: $USB_DRIVE\" -ForegroundColor White
Write-Host "========================================================================`n" -ForegroundColor Yellow

# Confirmación
$CONFIRMAR = Read-Host "¿Continuar? (s/n)"
if ($CONFIRMAR -ne "s") {
    Write-Host "`n❌ Cancelado`n"
    exit
}

# Copiar archivos
Write-Host "`n📋 Copiando archivos...`n" -ForegroundColor Cyan

$EXITO = $true

# 1. base.html
Write-Host "  [1/2] Copiando templates\base.html..." -ForegroundColor White
$ORIGEN_HTML = Join-Path $ORIGEN "templates\base.html"
$DESTINO_HTML = "$USB_DRIVE\base.html"

if (-not (Test-Path $ORIGEN_HTML)) {
    Write-Host "       ❌ ERROR: No encontrado" -ForegroundColor Red
    $EXITO = $false
} else {
    try {
        Copy-Item -Path $ORIGEN_HTML -Destination $DESTINO_HTML -Force -ErrorAction Stop
        Write-Host "       ✓ Copiado" -ForegroundColor Green
    } catch {
        Write-Host "       ❌ ERROR: $_" -ForegroundColor Red
        $EXITO = $false
    }
}

# 2. limpiar_elruso_duplicado.py
Write-Host "  [2/2] Copiando limpiar_elruso_duplicado.py..." -ForegroundColor White
$ORIGEN_PY = Join-Path $ORIGEN "limpiar_elruso_duplicado.py"
$DESTINO_PY = "$USB_DRIVE\limpiar_elruso_duplicado.py"

if (-not (Test-Path $ORIGEN_PY)) {
    Write-Host "       ❌ ERROR: No encontrado" -ForegroundColor Red
    $EXITO = $false
} else {
    try {
        Copy-Item -Path $ORIGEN_PY -Destination $DESTINO_PY -Force -ErrorAction Stop
        Write-Host "       ✓ Copiado" -ForegroundColor Green
    } catch {
        Write-Host "       ❌ ERROR: $_" -ForegroundColor Red
        $EXITO = $false
    }
}

# Resumen
if ($EXITO) {
    Write-Host "`n========================================================================" -ForegroundColor Green
    Write-Host "✓ ARCHIVOS COPIADOS AL USB EXITOSAMENTE" -ForegroundColor Green
    Write-Host "========================================================================`n" -ForegroundColor Green
    
    Write-Host "📦 USB ($USB_DRIVE\) contiene:" -ForegroundColor Green
    Write-Host "   ✓ base.html" -ForegroundColor White
    Write-Host "   ✓ limpiar_elruso_duplicado.py" -ForegroundColor White
    
    Write-Host "`n🔄 PRÓXIMOS PASOS EN EL OTRO PC:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Conecta este USB al otro PC"
    Write-Host "2. Copia base.html → CreditosPro_v2\templates\"
    Write-Host "3. Copia limpiar_elruso_duplicado.py → CreditosPro_v2\"
    Write-Host ""
    Write-Host "4. Abre PowerShell en CreditosPro_v2:"
    Write-Host "   " -NoNewline
    Write-Host "python limpiar_elruso_duplicado.py" -ForegroundColor Yellow
    Write-Host "5. Luego:"
    Write-Host "   " -NoNewline
    Write-Host "python run.py" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "========================================================================`n" -ForegroundColor Cyan
} else {
    Write-Host "`n❌ Hubo errores al copiar`n" -ForegroundColor Red
}

Read-Host "Presiona Enter para salir"
