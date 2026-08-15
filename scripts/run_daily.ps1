# ============================================================================
# run_daily.ps1
#
# Esto es lo que corre automáticamente cada día (registrado por
# setup_scheduled_task.ps1). Hace, en orden:
#   1. Descubrimiento automático de proveedores nuevos (config/candidates.txt)
#   2. Actualización de precios de todos los proveedores activos -> PostgreSQL
#
# No corre dos veces el mismo día aunque el Programador de Tareas lo dispare
# varias veces (por ejemplo, si cierras e inicias sesión más de una vez) --
# se controla con un archivo marcador en scripts/.last_run.
#
# Todo el output queda registrado en logs/ con fecha, para poder revisar si
# algo falló sin tener que estar mirando la pantalla.
#
# NOTA IMPORTANTE sobre $ErrorActionPreference: se deja en "Continue" (el
# valor por defecto de PowerShell) alrededor de las llamadas a Python, y NO
# en "Stop". Si se pone en "Stop" y se redirige stderr de un programa externo
# a un archivo (como hacemos con *>>), PowerShell trata CUALQUIER línea que
# Python escriba en stderr -- incluyendo sus logs normales de nivel INFO,
# que Python manda a stderr por defecto -- como un error fatal y corta el
# script, aunque Python no haya fallado en absoluto. En su lugar, revisamos
# $LASTEXITCODE después de cada llamada para saber si de verdad falló.
# ============================================================================

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Today = Get-Date -Format "yyyy-MM-dd"
$MarkerFile = Join-Path $PSScriptRoot ".last_run"
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir "$Today.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (Test-Path $MarkerFile) {
    $lastRun = Get-Content $MarkerFile -ErrorAction SilentlyContinue
    if ($lastRun -eq $Today) {
        Add-Content -Path $LogFile -Value "[$( Get-Date -Format 'HH:mm:ss')] Ya se corrió hoy ($Today). Se omite esta ejecución."
        exit 0
    }
}

function Log($msg) {
    $line = "[$( Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

Log "=== Inicio de la actualización diaria ==="

# Usa el Python del entorno virtual del proyecto si existe; si no, el del sistema.
$VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
Log "Usando Python: $Python"

$HadError = $false

Log "--- Paso 1: descubrimiento de proveedores nuevos (src.discover) ---"
& $Python -m src.discover *>> $LogFile
if ($LASTEXITCODE -ne 0) {
    Log "!!! src.discover terminó con código $LASTEXITCODE (revisa el log de arriba para el detalle)"
    $HadError = $true
}

Log "--- Paso 2: actualización de precios (src.main) ---"
& $Python -m src.main *>> $LogFile
if ($LASTEXITCODE -ne 0) {
    Log "!!! src.main terminó con código $LASTEXITCODE (revisa el log de arriba para el detalle)"
    $HadError = $true
}

if ($HadError) {
    Log "=== Corrida diaria terminó CON ERRORES (ver detalle arriba) ==="
    # No se actualiza el marcador .last_run si falló, para que el próximo
    # logon del mismo día vuelva a intentarlo.
    exit 1
} else {
    Set-Content -Path $MarkerFile -Value $Today
    Log "=== Corrida diaria completada correctamente ==="
    exit 0
}
