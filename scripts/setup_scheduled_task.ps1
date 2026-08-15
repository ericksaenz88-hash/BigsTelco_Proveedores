# ============================================================================
# setup_scheduled_task.ps1
#
# Se corre UNA SOLA VEZ para dejar la actualización de precios funcionando
# sola, para siempre: se registra una tarea en el Programador de Tareas de
# Windows que ejecuta scripts/run_daily.ps1:
#
#   - Cada vez que inicias sesión en este PC (con un margen de unos minutos
#     para que Windows termine de cargar), y
#   - Como respaldo, todos los días a las 8:00 a.m. por si ese día no
#     cierras/inicias sesión.
#
# run_daily.ps1 ya se encarga de no correr dos veces el mismo día, así que
# no hay riesgo de que se dispare de más.
#
# CÓMO USARLO:
#   1. Abre PowerShell en esta carpeta (scripts/).
#   2. Si es la primera vez que corres scripts de PowerShell en este PC,
#      puede que necesites permitir su ejecución (una sola vez):
#        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#   3. Corre:
#        .\setup_scheduled_task.ps1
#   4. Listo. Verifica que quedó creada abriendo "Programador de tareas"
#      (Task Scheduler) de Windows y buscando la tarea
#      "ProveedoresColombia_ActualizacionDiaria".
#
# NO necesita permisos de administrador (la tarea queda registrada para tu
# usuario, corre aunque no tengas sesión de admin).
# ============================================================================

$ErrorActionPreference = "Stop"

$TaskName = "ProveedoresColombia_ActualizacionDiaria"
$ScriptPath = Join-Path $PSScriptRoot "run_daily.ps1"

if (-not (Test-Path $ScriptPath)) {
    Write-Error "No se encontró run_daily.ps1 en $PSScriptRoot. ¿Corriste este script desde la carpeta scripts/?"
    exit 1
}

Write-Host "Registrando tarea programada '$TaskName'..."

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`"" `
    -WorkingDirectory $PSScriptRoot

# Disparador 1: al iniciar sesión (con 3 min de margen para que la red esté lista)
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn
$TriggerLogon.Delay = "PT3M"

# Disparador 2: respaldo diario a las 8:00 a.m. (por si ese día no hay logon nuevo)
$TriggerDaily = New-ScheduledTaskTrigger -Daily -At "8:00AM"

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

# Si ya existe (de una corrida anterior de este instalador), la reemplaza.
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger @($TriggerLogon, $TriggerDaily) `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Actualiza precios de proveedores colombianos (seguridad electronica, telecom, cableado) en PostgreSQL. Corre al iniciar sesion y como respaldo diario a las 8am. Ver README.md del proyecto." `
    | Out-Null

Write-Host ""
Write-Host "Listo. La tarea '$TaskName' quedo registrada."
Write-Host "Se ejecutara:"
Write-Host "  - Cada vez que inicies sesion en este PC (3 min despues, para dar tiempo a la red)"
Write-Host "  - Todos los dias a las 8:00 a.m. como respaldo"
Write-Host ""
Write-Host "El log de cada corrida queda en la carpeta logs/ (uno por dia)."
Write-Host ""
Write-Host "Para probarla ahora mismo sin esperar al proximo logon, corre:"
Write-Host "  Start-ScheduledTask -TaskName `"$TaskName`""
Write-Host ""
Write-Host "Para desinstalarla en cualquier momento:"
Write-Host "  Unregister-ScheduledTask -TaskName `"$TaskName`""
