# ============================================================================
# install.ps1
#
# Instalador de un solo paso. Deja todo listo para que la actualización de
# precios corra sola cada día, sin volver a tocar nada:
#
#   1. Crea el entorno virtual de Python (venv/) si no existe.
#   2. Instala las dependencias (requirements.txt).
#   3. Crea el archivo .env desde .env.example si no existe (falta que
#      edites tus credenciales de PostgreSQL ahí).
#   4. Registra la tarea programada de Windows (setup_scheduled_task.ps1).
#
# CÓMO USARLO (una sola vez):
#   1. Abre PowerShell en la carpeta raíz del proyecto.
#   2. Si nunca has corrido scripts de PowerShell en este PC:
#        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#   3. Corre:
#        .\scripts\install.ps1
#   4. Edita el archivo .env con los datos reales de tu PostgreSQL.
#   5. Corre el esquema una vez en tu base de datos:
#        psql -h TU_HOST -U TU_USUARIO -d TU_BASE -f schema.sql
#   6. Listo. Desde el próximo inicio de sesión, se actualiza solo.
#
# Para probar todo ahora mismo sin esperar (recomendado después del paso 5):
#   .\venv\Scripts\python.exe -m src.discover
#   .\venv\Scripts\python.exe -m src.main --dry-run
# ============================================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "=== 1. Entorno virtual de Python ==="
if (-not (Test-Path "venv")) {
    python -m venv venv
    Write-Host "Creado venv/"
} else {
    Write-Host "venv/ ya existe, se reutiliza."
}

Write-Host ""
Write-Host "=== 2. Instalando dependencias ==="
& ".\venv\Scripts\python.exe" -m pip install --upgrade pip -q
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt -q
Write-Host "Dependencias instaladas."

Write-Host ""
Write-Host "=== 3. Archivo de configuración (.env) ==="
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Se creó .env a partir de .env.example."
    Write-Host "IMPORTANTE: edita .env con los datos reales de tu PostgreSQL antes de seguir."
} else {
    Write-Host ".env ya existe, no se toca."
}

Write-Host ""
Write-Host "=== 4. Registrando tarea programada de Windows ==="
& (Join-Path $PSScriptRoot "setup_scheduled_task.ps1")

Write-Host ""
Write-Host "=== Instalación completa ==="
Write-Host "Falta un paso manual: edita .env con tus credenciales reales de PostgreSQL"
Write-Host "(si no lo hiciste ya) y corre el esquema una vez:"
Write-Host "   psql -h TU_HOST -U TU_USUARIO -d TU_BASE -f schema.sql"
Write-Host ""
Write-Host "Desde el próximo inicio de sesión en este PC, todo corre solo."
