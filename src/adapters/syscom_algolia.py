"""
Adaptador para SYSCOM Colombia (www.syscomcolombia.com).

SYSCOM usa Algolia (buscador SaaS) para mostrar su catálogo en el sitio,
con una API Key de "solo búsqueda" embebida en el JavaScript público del
sitio (este tipo de key de Algolia está diseñada para exponerse en el
navegador del cliente; no es una credencial privada).

Este adaptador:
  1. Pide a Algolia los valores del facet "menu_1" (categorías de primer
     nivel) — así descubre automáticamente TODAS las categorías del
     catálogo, incluyendo si SYSCOM agrega una línea nueva.
  2. Para cada categoría, pagina resultados (hasta 1000 por página) usando
     el filtro `menu_1:"<categoría>"`.
  3. Solo conserva ítems con mostrar_precio=true (los que el sitio expone
     públicamente).

Si SYSCOM cambia de índice/atributos, este adaptador dejará de funcionar y
tocaría re-investigar (ver README, sección "si un adaptador se rompe").
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import ScrapedProduct
from src.http_utils import new_session

logger = logging.getLogger(__name__)

ALGOLIA_APP_ID = "H16JEIUT0Z"
ALGOLIA_API_KEY = "6fc0b9437658ca79e8d4fb4f8718e949"  # search-only key, pública en el JS del sitio
ALGOLIA_INDEX = "Colombia_productos"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries"

PAGE_SIZE = 1000
DEFAULT_TIMEOUT = 20

HEADERS = {
    "X-Algolia-API-Key": ALGOLIA_API_KEY,
    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    "Content-Type": "application/json",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _query(session: requests.Session, params: str) -> dict:
    resp = session.post(
        ALGOLIA_URL,
        json={"requests": [{"indexName": ALGOLIA_INDEX, "params": params}]},
        headers=HEADERS,
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["results"][0]


def _discover_categories(session: requests.Session) -> list[str]:
    """Lee el facet menu_1 para obtener todas las categorías de primer nivel."""
    result = _query(session, "query=&hitsPerPage=1&facets=menu_1")
    facet = result.get("facets", {}).get("menu_1", {})
    return list(facet.keys())


def _price(hit: dict) -> Optional[float]:
    # ADVERTENCIA DE CONFIABILIDAD (ver README, sección "SYSCOM: moneda sin confirmar"):
    # No se pudo verificar con certeza si precio_calculo/precio_1 vienen en COP o
    # en USD. El sitio tiene un selector de moneda (US$/CO$) y el precio final que
    # se muestra al usuario se renderiza por JavaScript con datos que no se
    # lograron reproducir por fuera del navegador. Hasta que alguien con una
    # cuenta real de distribuidor SYSCOM confirme un SKU de referencia contra
    # este valor, TRÁTALO COMO DATO DE REFERENCIA, NO COMO PRECIO FINAL DE VENTA.
    if not hit.get("mostrar_precio"):
        return None
    val = hit.get("precio_calculo") or hit.get("precio_1")
    try:
        val = float(val)
        return val if val > 0 else None
    except (TypeError, ValueError):
        return None


def fetch(provider_cfg: dict) -> list[ScrapedProduct]:
    session = new_session()
    products: list[ScrapedProduct] = []

    categories = _discover_categories(session)
    if not categories:
        raise RuntimeError("[syscom] no se pudo leer el facet de categorías (Algolia caído o cambió).")

    logger.info("[syscom] %d categorías detectadas", len(categories))
    logger.warning(
        "[syscom] ADVERTENCIA: la moneda real de precio_calculo/precio_1 no está "
        "confirmada (podría no ser COP). Verifica manualmente antes de cotizar. "
        "Ver README, sección 'SYSCOM: moneda sin confirmar'."
    )

    for cat_name in categories:
        page = 0
        while True:
            filt = urllib.parse.quote(f'menu_1:"{cat_name}"')
            params = f"query=&hitsPerPage={PAGE_SIZE}&page={page}&filters={filt}"
            try:
                result = _query(session, params)
            except Exception as exc:
                logger.error("[syscom] fallo consultando categoría '%s' página %d: %s", cat_name, page, exc)
                break

            hits = result.get("hits", [])
            n_pages = result.get("nbPages", 0)
            logger.info("[syscom] categoría '%s' página %d/%d -> %d resultados", cat_name, page + 1, n_pages, len(hits))

            for hit in hits:
                sku = str(hit.get("modelo_limpio") or hit.get("objectID") or "").strip()
                if not sku:
                    continue
                stock_qty = hit.get("cantidad_stock_public")
                products.append(ScrapedProduct(
                    sku=sku,
                    name=(hit.get("titulo") or hit.get("modelo_limpio") or "").strip() or sku,
                    price=_price(hit),
                    currency="COP",
                    in_stock=bool(hit.get("tiene_stock")) if "tiene_stock" in hit else (stock_qty or 0) > 0,
                    url=("https://" + hit["links"]) if hit.get("links") else None,
                    image_url=hit.get("imagen"),
                    category=cat_name,
                    brand=hit.get("marca"),
                ))

            page += 1
            if page >= n_pages or not hits:
                break

    return products
