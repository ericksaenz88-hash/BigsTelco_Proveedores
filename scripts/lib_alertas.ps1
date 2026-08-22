# ============================================================================
# lib_alertas.ps1
#
# Función compartida para mostrar una notificación emergente de Windows
# (globo en la bandeja del sistema). No requiere instalar ningún módulo
# adicional (usa System.Windows.Forms, que viene con Windows).
#
# Uso desde otro script:
#   . "$PSScriptRoot\lib_alertas.ps1"
#   Show-Alert -Titulo "Algo pasó" -Mensaje "Detalle del problema" -Tipo "Error"
# ============================================================================

function Show-Alert {
    param(
        [string]$Titulo,
        [string]$Mensaje,
        [ValidateSet("Info", "Warning", "Error")]
        [string]$Tipo = "Warning",
        [int]$DuracionMs = 15000
    )

    try {
        Add-Type -AssemblyName System.Windows.Forms | Out-Null
        Add-Type -AssemblyName System.Drawing | Out-Null

        $icon = New-Object System.Windows.Forms.NotifyIcon
        $icon.Icon = [System.Drawing.SystemIcons]::Information
        $icon.BalloonTipIcon = switch ($Tipo) {
            "Error"   { [System.Windows.Forms.ToolTipIcon]::Error }
            "Warning" { [System.Windows.Forms.ToolTipIcon]::Warning }
            default   { [System.Windows.Forms.ToolTipIcon]::Info }
        }
        $icon.BalloonTipTitle = $Titulo
        $icon.BalloonTipText  = $Mensaje
        $icon.Visible = $true
        $icon.ShowBalloonTip($DuracionMs)

        # Se deja el ícono visible un momento para que el globo alcance a
        # mostrarse (si se destruye el objeto de inmediato, a veces Windows
        # no llega a pintarlo). Luego se limpia solo.
        Start-Sleep -Seconds ([Math]::Ceiling($DuracionMs / 1000) + 1)
        $icon.Dispose()
    } catch {
        # Si por alguna razón no se puede mostrar la notificación gráfica
        # (por ejemplo, corriendo sin sesión de escritorio activa), que no
        # rompa el script que la llamó -- solo se pierde el aviso visual.
        Write-Host "No se pudo mostrar la notificación de Windows: $_"
    }
}
