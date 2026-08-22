# ============================================================================
# setup_scheduled_task.ps1
#
# Se corre UNA SOLA VEZ para dejar la actualización de precios funcionando
# sola, para siempre: registra DOS tareas en el Programador de Tareas de
# Windows:
#
#   1. "ProveedoresColombia_ActualizacionDiaria" -- corre run_daily.ps1:
#        - Cada vez que inicias sesión en este PC (con margen de unos
#          minutos para que Windows termine de cargar), y
#        - Como respaldo, todos los días a las 8:00 a.m.
#
#   2. "ProveedoresColombia_VerificacionSalud" -- corre verificar_salud.ps1:
#        - Todos los días a las 9:00 a.m. (una hora después del respaldo
#          de arriba, para darle tiempo a terminar).
#        - Revisa si la actualización de precios lleva más de 1 día sin
#          correr exitosamente, y si es así, muestra una notificación de
#          Windows avisando -- así te enteras aunque la tarea #1 se rompa
#          o deje de dispararse por completo.
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
#      (si da "Acceso denegado", vuelve a intentarlo desde PowerShell
#      abierto como Administrador)
#   4. Listo. Verifica que quedaron creadas abriendo "Programador de
#      tareas" (Task Scheduler) de Windows y buscando
#      "ProveedoresColombia_ActualizacionDiaria" y
#      "ProveedoresColombia_VerificacionSalud".
#
# NO necesita permisos de administrador en la mayoría de los PCs (la tarea
# queda registrada para tu usuario), pero en algunos equipos con políticas
# más restrictivas sí hace falta correrlo como Administrador.
# ============================================================================

$ErrorActionPreference = "Stop"

$ScriptsDir = $PSScriptRoot

function Install-Task {
    param(
        [string]$TaskName,
        [string]$ScriptFileName,
        [string]$Description,
        [array]$Triggers
    )

    $ScriptPath = Join-Path $ScriptsDir $ScriptFileName
    if (-not (Test-Path $ScriptPath)) {
        Write-Error "No se encontró $ScriptFileName en $ScriptsDir. ¿Corriste este script desde la carpeta scripts/?"
        exit 1
    }

    Write-Host "Registrando tarea programada '$TaskName'..."

    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`"" `
        -WorkingDirectory $ScriptsDir

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
        -Trigger $Triggers `
        -Settings $Settings `
        -Principal $Principal `
        -Description $Description `
        | Out-Null

    Write-Host "  OK: '$TaskName' quedó registrada."
}

# --- Tarea 1: actualización diaria de precios ---
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn
$TriggerLogon.Delay = "PT3M"
$TriggerDaily8am = New-ScheduledTaskTrigger -Daily -At "8:00AM"

Install-Task `
    -TaskName "ProveedoresColombia_ActualizacionDiaria" `
    -ScriptFileName "run_daily.ps1" `
    -Description "Actualiza precios de proveedores colombianos (seguridad electronica, telecom, cableado) en PostgreSQL. Corre al iniciar sesion y como respaldo diario a las 8am. Ver README.md del proyecto." `
    -Triggers @($TriggerLogon, $TriggerDaily8am)

# --- Tarea 2: vigilante de salud (avisa si la #1 deja de correr) ---
$TriggerDaily9am = New-ScheduledTaskTrigger -Daily -At "9:00AM"
$TriggerLogonSalud = New-ScheduledTaskTrigger -AtLogOn
$TriggerLogonSalud.Delay = "PT5M"

Install-Task `
    -TaskName "ProveedoresColombia_VerificacionSalud" `
    -ScriptFileName "verificar_salud.ps1" `
    -Description "Revisa si la actualizacion diaria de precios (ProveedoresColombia_ActualizacionDiaria) lleva mas de 1 dia sin correr exitosamente, y avisa con una notificacion de Windows si es asi." `
    -Triggers @($TriggerDaily9am, $TriggerLogonSalud)

Write-Host ""
Write-Host "Listo. Las dos tareas quedaron registradas."
Write-Host ""
Write-Host "ProveedoresColombia_ActualizacionDiaria se ejecutara:"
Write-Host "  - Cada vez que inicies sesion en este PC (3 min despues, para dar tiempo a la red)"
Write-Host "  - Todos los dias a las 8:00 a.m. como respaldo"
Write-Host ""
Write-Host "ProveedoresColombia_VerificacionSalud se ejecutara:"
Write-Host "  - Todos los dias a las 9:00 a.m."
Write-Host "  - Cada vez que inicies sesion (5 min despues)"
Write-Host "  - Solo muestra una notificacion si la actualizacion lleva mas de 1 dia atrasada"
Write-Host ""
Write-Host "El log de cada corrida de la actualizacion queda en la carpeta logs/ (uno por dia)."
Write-Host ""
Write-Host "Para probar cualquiera de las dos ahora mismo sin esperar:"
Write-Host "  Start-ScheduledTask -TaskName `"ProveedoresColombia_ActualizacionDiaria`""
Write-Host "  Start-ScheduledTask -TaskName `"ProveedoresColombia_VerificacionSalud`""
Write-Host ""
Write-Host "Para desinstalar cualquiera de las dos en cualquier momento:"
Write-Host "  Unregister-ScheduledTask -TaskName `"ProveedoresColombia_ActualizacionDiaria`""
Write-Host "  Unregister-ScheduledTask -TaskName `"ProveedoresColombia_VerificacionSalud`""
