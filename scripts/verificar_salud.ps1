# ============================================================================
# verificar_salud.ps1
#
# "Vigilante" independiente de la actualización diaria. Se registra como una
# tarea programada APARTE de "ProveedoresColombia_ActualizacionDiaria", para
# que siga funcionando incluso si esa tarea principal se desactiva, se borra
# por error, o deja de dispararse por completo (por ejemplo, si el PC pasa
# varios días sin encenderse en un logon, o si alguien la deshabilita sin
# querer).
#
# Revisa el archivo marcador scripts/.last_run (el mismo que usa
# run_daily.ps1) y si la última corrida EXITOSA fue hace más de 1 día,
# muestra una notificación de Windows avisando que la actualización de
# precios lleva atrasada.
#
# No hace falta correr esto manualmente -- setup_scheduled_task.ps1 ya lo
# registra para correr una vez al día.
# ============================================================================

$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "lib_alertas.ps1")

$MarkerFile = Join-Path $PSScriptRoot ".last_run"
$Today = Get-Date

if (-not (Test-Path $MarkerFile)) {
    Show-Alert -Titulo "Bigs Telco - Actualización de precios sin iniciar" `
               -Mensaje "Todavía no se ha registrado ninguna corrida exitosa de la actualización diaria de precios. Revisa que la tarea 'ProveedoresColombia_ActualizacionDiaria' esté activa." `
               -Tipo "Warning"
    exit 0
}

$lastRunText = Get-Content $MarkerFile -ErrorAction SilentlyContinue
$lastRunDate = $null
if ($lastRunText) {
    try { $lastRunDate = [DateTime]::ParseExact($lastRunText, "yyyy-MM-dd", $null) } catch { $lastRunDate = $null }
}

if (-not $lastRunDate) {
    Show-Alert -Titulo "Bigs Telco - No se pudo verificar la última actualización" `
               -Mensaje "El archivo scripts/.last_run existe pero no se pudo leer la fecha. Revisa manualmente." `
               -Tipo "Warning"
    exit 0
}

$diasSinCorrer = ($Today.Date - $lastRunDate.Date).Days

if ($diasSinCorrer -gt 1) {
    Show-Alert -Titulo "Bigs Telco - Precios desactualizados" `
               -Mensaje "La actualización diaria de precios no corre exitosamente desde hace $diasSinCorrer días (última vez: $lastRunText). Revisa la tarea programada y los logs en la carpeta logs/." `
               -Tipo "Error" `
               -DuracionMs 20000
}
