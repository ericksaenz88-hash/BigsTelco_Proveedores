"""
Adaptador para GVS Colombia (www.gvscolombia.com).

GVS es una Single Page Application (Vue/Nuxt) que NO renderiza productos en
el HTML inicial: los carga desde una API JSON propia después de cargar la
página. En vez de usar un navegador headless (lento y frágil), este
adaptador habla directamente con esa API REST interna:

  1. Genera un token de "invitado" (JWT firmado con una llave que viene
     embebida en el bundle de JavaScript público del sitio — no es una
     credencial privada, cualquier visitante del sitio genera el mismo
     tipo de token en su navegador).
  2. Descubre automáticamente TODAS las líneas de producto disponibles
     (POST /lineasv2) — así si GVS agrega una categoría nueva, este
     adaptador la recoge sola, sin tocar configuración.
  3. Para cada línea, pagina POST /listaDeProductos hasta agotar
     TotalPaginas y arma un ScrapedProduct por ítem.

Si GVS cambia esta API interna, este adaptador dejará de funcionar y
tocaría re-investigar (ver README, sección "si un adaptador se rompe").
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import jwt
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import ScrapedProduct
from src.http_utils import new_session

logger = logging.getLogger(__name__)

API_BASE = "https://www.gvscolombia.com/rest.gvscolombia.com/RestFull/public"
JWT_SECRET = "P5!8CK;TJQumApt["  # llave pública embebida en el JS del sitio, no privada
PAGE_SIZE = 100
DEFAULT_TIMEOUT = 20


def _guest_token() -> str:
    now_ms = int(time.time() * 1000)
    return jwt.encode({"iat": now_ms, "exp": now_ms + 60_000}, JWT_SECRET, algorithm="HS256")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _post(session: requests.Session, path: str, body: dict) -> dict:
    token = _guest_token()
    resp = session.post(
        f"{API_BASE}{path}",
        json=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_lineas(session: requests.Session) -> list[dict]:
    """Devuelve todas las líneas/categorías activas hoy en GVS. Auto-descubre catálogo nuevo."""
    data = _post(session, "/lineasv2?", {"key": "gKey"})
    if not isinstance(data, list):
        logger.warning("[gvs] respuesta inesperada en /lineasv2: %s", str(data)[:200])
        return []
    return data


def _price(item: dict) -> Optional[float]:
    # PrecioFinal ya incluye descuentos vigentes; si no viene, cae a Precio base.
    val = item.get("PrecioFinal") or item.get("Precio")
    try:
        val = float(val)
        return val if val > 0 else None
    except (TypeError, ValueError):
        return None


def fetch(provider_cfg: dict) -> list[ScrapedProduct]:
    session = new_session()
    products: list[ScrapedProduct] = []

    lineas = _fetch_lineas(session)
    if not lineas:
        raise RuntimeError("[gvs] no se pudo obtener el listado de líneas de producto (API caída o cambió).")

    logger.info("[gvs] %d líneas de producto detectadas", len(lineas))

    for linea in lineas:
        id_linea = linea.get("id_Linea")
        nombre_linea = linea.get("Linea", "")
        page = 1
        total_pages = None

        while total_pages is None or page <= total_pages:
            body = {"key": "gKey", "RegsxPagina": PAGE_SIZE, "PaginaActual": page, "id_linea": id_linea}
            try:
                data = _post(session, "/listaDeProductos", body)
            except Exception as exc:
                logger.error("[gvs] fallo consultando línea '%s' página %d: %s", nombre_linea, page, exc)
                break

            items = data.get("Productos", [])
            total_pages = data.get("TotalPaginas") or 0
            logger.info("[gvs] línea '%s' página %d/%s -> %d productos", nombre_linea, page, total_pages, len(items))

            for item in items:
                sku = str(item.get("ItemCode") or "").strip()
                if not sku:
                    continue
                existencia = item.get("Existencia")
                products.append(ScrapedProduct(
                    sku=sku,
                    name=(item.get("Descripcion") or "").strip(),
                    price=_price(item),
                    currency="COP",
                    in_stock=(existencia is not None and existencia > 0),
                    url=None,  # GVS no expone una URL de detalle estable vía esta API
                    image_url=None,
                    category=item.get("Linea") or nombre_linea,
                    brand=item.get("Marca"),
                ))

            if not items:
                break
            page += 1

    return products
