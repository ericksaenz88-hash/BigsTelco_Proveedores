"""
Heurística para detectar la "unidad de venta" de un producto a partir de
su nombre, cuando el proveedor no la expone en un campo aparte.

Ningún adaptador (GVS, SYSCOM, SAT Store, Shopify, WooCommerce, VTEX,
Wix Stores) trae la unidad de venta en un campo propio de su API/HTML --
el esquema tiene una columna `unit` reservada para esto desde el
principio, pero se quedó sin conectar. Esta función se llama de forma
centralizada (en src/main.py, justo antes de guardar cada producto) y
NO reemplaza un valor de unidad si el adaptador algún día sí lo trae
explícito -- solo rellena cuando viene vacío.

Es una heurística sobre texto libre en español/spanglish colombiano, así
que no va a acertar el 100% de las veces; prioriza no inventar (si no
encuentra un patrón conocido, deja el campo vacío) sobre adivinar mal.

IMPORTANTE -- lección aprendida: la primera versión de esta función
también intentaba detectar "100m"/"305m" (metros a secas, sin la palabra
"Mt"/"metros"), pero eso generó falsos positivos graves en productos que
NO son cable: cámaras con especificaciones como "IR 20M" (alcance del
infrarrojo, en metros, pero no es un rollo de cable) o "5M-N" (una
resolución/formato de grabación, la "M" no significa metros ahí). Se
quitó ese patrón: ahora solo se dispara con la palabra completa "Mt",
"Mts" o "metros" explícita, que es mucho menos ambigua.
"""

from __future__ import annotations

import re
from typing import Optional

# Orden importa: los patrones más específicos van primero.

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "305Mt", "305 Mt", "305Mts", "305 metros" -> "rollo 305m"
    # Exige la palabra completa "Mt"/"Mts"/"metros" (no solo "M" suelta),
    # justamente para NO capturar especificaciones técnicas como "IR 20M"
    # o "5M-N" en cámaras/DVRs, que no son unidad de venta.
    (re.compile(r"(?<![a-zA-Z])(\d+(?:[.,]\d+)?)\s*(?:mt|mts|metros)\b", re.IGNORECASE),
     "rollo {0}m"),

    # "Caja x50", "Caja X 100", "cajax24" -> "caja x50"
    (re.compile(r"\bcaja\s*x\s*(\d+)\b", re.IGNORECASE), "caja x{0}"),

    # "Bobina 305m", "Bobina de 305 metros" -> "bobina" (si no cayó ya en
    # el patrón de metros de arriba, ej. "Bobina" sin cantidad explícita)
    (re.compile(r"\bbobina\b", re.IGNORECASE), "bobina"),

    (re.compile(r"\bkit\b", re.IGNORECASE), "kit"),
    (re.compile(r"\bjuego\b", re.IGNORECASE), "juego"),
    (re.compile(r"\bpar\b", re.IGNORECASE), "par"),
    (re.compile(r"\brollo\b", re.IGNORECASE), "rollo"),
    (re.compile(r"\bunidad\b", re.IGNORECASE), "unidad"),
]


def extract_unit(product_name: Optional[str]) -> Optional[str]:
    """
    Intenta deducir la unidad de venta a partir del nombre del producto.
    Devuelve None si no encuentra ningún patrón conocido (no inventa).

    Ejemplos:
        "Cable UTP SAT Cat5E CCA 0.5mm 305Mt Interior" -> "rollo 305m"
        "Cámara domo IR 20M IP67"                       -> None (a propósito:
            "20M" sin la palabra "Mt"/"metros" no se toma como unidad,
            porque en specs de cámaras "M" casi siempre es alcance del
            infrarrojo, no metros de un rollo vendible)
        "Guantes de nitrilo Caja x50"                   -> "caja x50"
    """
    if not product_name:
        return None

    for pattern, template in _PATTERNS:
        match = pattern.search(product_name)
        if match:
            if match.groups():
                cantidad = match.group(1).replace(",", ".")
                if cantidad.endswith(".0"):
                    cantidad = cantidad[:-2]
                return template.format(cantidad)
            return template

    return None
