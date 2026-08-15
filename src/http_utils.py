"""
Utilidades HTTP compartidas por todos los adaptadores.

Algunos proveedores (confirmado con CRC Comunicaciones) rechazan o cortan
la conexión si detectan el User-Agent por defecto de la librería `requests`
("python-requests/x.x"). Usar un User-Agent de navegador real evita ese
bloqueo sin necesidad de nada más sofisticado.
"""

from __future__ import annotations

import requests

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def new_session() -> requests.Session:
    """Sesión de requests con headers de navegador real por defecto."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    })
    return session
