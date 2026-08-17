#!/usr/bin/env python3
"""
CreditosPro Renewal Scheduler Setup
Configura la renovación automática de licencias con Windows Task Scheduler.

Uso:
    python setup_auto_renewal.py
    
Esto crea una tarea programada que ejecuta renewal_license.py --auto automáticamente
cada 1 de agosto a las 09:00 AM.
"""
import os
import sys
import subprocess
from pathlib import Path


def setup_task_scheduler():
    """Configura Windows Task Scheduler para renovación automática"""
    
    project_root = Path(__file__).parent.absolute()
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    renewal_script = project_root / "renewal_license.py"
    
    # Validar que los archivos existen
    if not venv_python.exists():
        print(f"❌ ERROR: No se encontró .venv en {project_root}")
        print("   Asegúrate de haber creado el entorno virtual")
        return False
    
    if not renewal_script.exists():
        print(f"❌ ERROR: No se encontró renewal_license.py en {project_root}")
        return False
    
    # XML para Task Scheduler
    task_xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>2026-08-16T00:00:00</Date>
    <Author>CreditosPro</Author>
    <Description>Renovación automática anual de licencias CreditosPro</Description>
    <URI>\\CreditosPro\\RenovarLicenciaAnual</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2027-08-01T09:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonth>
        <DaysOfMonth>
          <Day>1</Day>
        </DaysOfMonth>
        <Months>
          <Month>August</Month>
        </Months>
      </ScheduleByMonth>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-21-0-0-0-1000</UserId>
      <LogonType>InteractiveToken</LogonType>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <Duration>PT10M</Duration>
      <WaitTimeout>PT1H</WaitTimeout>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{venv_python}"</Command>
      <Arguments>"{renewal_script}" --auto</Arguments>
      <WorkingDirectory>{project_root}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>'''
    
    # Guardar XML temporalmente
    temp_xml = Path(project_root) / ".task_temp.xml"
    temp_xml.write_text(task_xml, encoding="utf-16")
    
    print("\n" + "=" * 70)
    print("🔧 CONFIGURANDO RENOVACIÓN AUTOMÁTICA")
    print("=" * 70)
    print(f"\n📝 Datos de la tarea programada:")
    print(f"  Nombre: RenovarLicenciaAnual")
    print(f"  Carpeta: CreditosPro")
    print(f"  Programa: {venv_python}")
    print(f"  Argumentos: {renewal_script} --auto")
    print(f"  Programación: Cada 1 de agosto a las 09:00 AM")
    print(f"  Acción: Renueva automáticamente la licencia")
    print("\n⚠️  NECESITA PRIVILEGIOS DE ADMINISTRADOR")
    print("\nIntentando importar la tarea programada...\n")
    
    try:
        # Importar la tarea (requiere permisos de admin)
        result = subprocess.run(
            [
                "schtasks",
                "/create",
                "/tn", "CreditosPro\\RenovarLicenciaAnual",
                "/xml", str(temp_xml),
                "/f"  # Force (sobrescribir si existe)
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ TAREA CREADA EXITOSAMENTE\n")
            print("=" * 70)
            print("📋 Lo que pasará:")
            print("=" * 70)
            print("""
  ✅ Cada 1 de agosto a las 09:00 AM:
     - Windows ejecuta automáticamente: renewal_license.py --auto
     - Se valida la licencia actual
     - Se genera una nueva licencia con +365 días
     - Se actualiza el .env
     - Se registra en equipos_registro.json
  
  ✅ Tu app seguirá funcionando sin cambios
  ✅ Sin intervención manual requerida
  
  ⚠️  Si tu PC está apagado a las 09:00, Windows ejecutará la tarea
     la próxima vez que inicie
""")
            
            # Mostrar cómo verificar
            print("=" * 70)
            print("🔍 VERIFICAR LA TAREA")
            print("=" * 70)
            print("\nEn PowerShell (Admin):")
            print("  Get-ScheduledTask -TaskName 'RenovarLicenciaAnual' | Select *")
            print("\nEn línea de comandos:")
            print("  schtasks /query /tn \"CreditosPro\\RenovarLicenciaAnual\"")
            print("\n")
            
            # Limpiar
            temp_xml.unlink()
            return True
        
        else:
            print(f"❌ ERROR: {result.stderr}")
            print("\nIntentalo en PowerShell con permisos de admin:")
            print(f"  schtasks /create /tn \"CreditosPro\\RenovarLicenciaAnual\" /xml \"{temp_xml}\" /f")
            return False
    
    except subprocess.TimeoutExpired:
        print("❌ ERROR: La operación tardó demasiado (timeout)")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        print("\n💡 Tip: Ejecuta PowerShell como Administrador y reintenta")
        return False


def setup_manual_reminder():
    """Crea un recordatorio manual alternativo"""
    
    print("\n" + "=" * 70)
    print("📅 ALTERNATIVA: RECORDATORIO MANUAL")
    print("=" * 70)
    print("""
Si no puedes usar Task Scheduler, aquí hay alternativas:

1️⃣  CREAR UN .bat QUE RENUEVE
    Archivo: C:\\MisScripts\\renovar_licencia.bat
    Contenido:
        @echo off
        cd c:\\Users\\johan\\Downloads\\CreditosPro_DEPLOY
        .\\venv\\Scripts\\python.exe renewal_license.py --auto
        pause
    
    Luego crear tarea en Task Scheduler apuntando a este .bat

2️⃣  GOOGLE CALENDAR + GMAIL
    - Recordatorio el 1 de agosto
    - Ejecutas manualmente: renewal_license.py --auto
    - Toma 30 segundos

3️⃣  Windows CALENDAR
    - Crear evento recurrente
    - Recordatorio 1 semana antes
    
4️⃣  SCRIPT PYTHON CON APScheduler
    - Instalar: pip install apscheduler
    - Crear daemon que se ejecuta al iniciar
""")


def setup_powershell_task():
    """Crea la tarea usando PowerShell (más simple para usuarios)"""
    
    project_root = Path(__file__).parent.absolute()
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    renewal_script = project_root / "renewal_license.py"
    
    ps_command = f'''
# Ejecutar como administrador
$action = New-ScheduledTaskAction -Execute '"{venv_python}"' -Argument '"{renewal_script}" --auto' -WorkingDirectory '{project_root}'
$trigger = New-ScheduledTaskTrigger -At 09:00 -DaysOfMonth 1 -Monthly
$task = Register-ScheduledTask -TaskName 'RenovarLicenciaAnual' -TaskPath 'CreditosPro' -Action $action -Trigger $trigger -Force
Write-Host "✅ Tarea creada: $($task.TaskName)"
'''
    
    ps_file = Path(project_root) / "setup_renewal_task.ps1"
    ps_file.write_text(ps_command)
    
    print("\n" + "=" * 70)
    print("🔵 ALTERNATIVA: POWERSHELL")
    print("=" * 70)
    print(f"\nScript generado: {ps_file}")
    print("\nPasos:")
    print("1. Abre PowerShell como ADMINISTRADOR")
    print("2. Ejecuta:")
    print(f"   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser")
    print(f"   & '{ps_file}'")
    print("\n")


def main():
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  🔄 CreditosPro - Automatizar Renovación Anual de Licencias".ljust(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "═" * 68 + "╝")
    
    # Validaciones previas
    if sys.platform != "win32":
        print("\n❌ Este script solo funciona en Windows")
        print("Para otros SO, ver sección 'ALTERNATIVAS'")
        return
    
    # Intentar con Task Scheduler
    success = setup_task_scheduler()
    
    if not success:
        print("\n" + "=" * 70)
        print("⚠️  ALTERNATIVAS")
        print("=" * 70)
        
        setup_powershell_task()
        setup_manual_reminder()
    
    print("\n" + "=" * 70)
    print("✅ PRÓXIMOS PASOS")
    print("=" * 70)
    print("""
1. Verificar que la licencia actual es válida:
   .\\venv\\Scripts\\python.exe renewal_license.py --validate "CPRO-..."

2. Probar manualmente la renovación (si quieres ver cómo funciona):
   .\\venv\\Scripts\\python.exe renewal_license.py --auto

3. Esperar al 1 de agosto para que se ejecute automáticamente

4. Consultar logs (si necesitas verificar si se ejecutó):
   Visor de eventos → Aplicaciones
""")
    print("\n")


if __name__ == "__main__":
    main()
