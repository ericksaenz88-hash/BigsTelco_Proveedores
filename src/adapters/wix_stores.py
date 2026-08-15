"""
Adaptador genérico para tiendas Wix Stores.

Wix no expone un endpoint público simple tipo "/products.json" (como
Shopify) ni una Store API abierta (como WooCommerce): su API real de
e-commerce exige un token de visitante autenticado contra un
WIX_CLIENT_ID, que normalmente solo lo tiene el dueño del sitio (no sirve
para leer catálogos de terceros sin su colaboración).

En cambio, SÍ se puede leer el catálogo completo sin token, aprovechando
dos piezas públicas que Wix genera automáticamente para SEO en cualquier
sitio con la app "Wix Stores" instalada:

  1. El sitemap general (`/sitemap.xml`) enlaza a un sitemap específico
     de productos: `.../store-products-sitemap.xml`. Si ese sitemap NO
     aparece, el sitio no tiene Wix Stores instalado (o no tiene
     productos publicados) — es la forma de "detectar" si vale la pena
     usar este adaptador (ver discover.py, probe_wix_stores()).
  2. Cada página de producto (".../product-page/<slug>") trae, en el
     HTML servido por el servidor (SSR), un bloque
     <script type="application/json" id="wix-warmup-data"> con TODO el
     estado inicial de la página — incluyendo un objeto "catalog.product"
     con sku, nombre, precio, precio formateado, moneda explícita
     (currency: "COP", por ejemplo — sin ambigüedad, a diferencia de
     VTEX/SYSCOM), inventario (in_stock/out_of_stock) y marca.

Este adaptador combina ambas piezas: primero enumera todas las URLs de
producto vía el sitemap, y después visita cada una para extraer el
bloque de datos. Es más lento que los adaptadores basados en API (una
petición HTTP por producto), así que respeta un rate_limit_seconds igual
que el adaptador "css".

Para saber si un proveedor nuevo es candidato a este adaptador, probar:
  curl https://SU_DOMINIO/sitemap.xml
Si el índice incluye un sitemap con "store-products" en el nombre, es
candidato.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import ScrapedProduct
from src.http_utils import new_session

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20
DEFAULT_RATE_LIMIT_SECONDS = 1.0
MAX_PRODUCTS = 5000  # límite de seguridad, no un tope real de negocio

_SITEMAP_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")
_SITEMAP_ENTRY_RE = re.compile(r"<sitemap>(.*?)</sitemap>", re.S)
_WARMUP_RE = re.compile(
    r'<script type="application/json" id="wix-warmup-data">(.*?)</script>',
    re.S,
)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get(session: requests.Session, url: str) -> requests.Response:
    resp = session.get(url, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp


def discover_product_sitemap_url(session: requests.Session, base_url: str) -> Optional[str]:
    """Busca, en el índice de sitemaps del sitio, el sitemap de productos de Wix Stores.

    Nota: se parsea con regex en vez de un parser XML estricto porque varios
    sitios Wix generan sitemaps con entidades HTML sin escapar (ej. "&" suelto
    en un título de producto), que rompen xml.etree. Para extraer únicamente
    URLs dentro de <loc> esto es suficiente y más tolerante a HTML/XML mal
    formado en sitios de terceros que no controlamos.
    """
    root_url = f"{base_url.rstrip('/')}/sitemap.xml"
    try:
        resp = _get(session, root_url)
    except Exception as exc:
        logger.warning("[wix] no se pudo leer %s: %s", root_url, exc)
        return None

    for entry in _SITEMAP_ENTRY_RE.findall(resp.text):
        loc_match = _SITEMAP_LOC_RE.search(entry)
        if loc_match and "store-products" in loc_match.group(1):
            return loc_match.group(1).strip()
    return None


def list_product_urls(session: requests.Session, sitemap_url: str) -> list[str]:
    resp = _get(session, sitemap_url)
    # cada <url>...</url> trae varias <loc> (una para la página, más una por
    # cada <image:loc>); nos quedamos solo con la primera <loc> de cada bloque
    urls = []
    for block in re.findall(r"<url>(.*?)</url>", resp.text, re.S):
        loc_match = _SITEMAP_LOC_RE.search(block)
        if loc_match:
            urls.append(loc_match.group(1).strip())
    return urls


def _find_product_block(obj) -> Optional[dict]:
    """Busca recursivamente, dentro del JSON de wix-warmup-data, el objeto
    de producto (tiene sku + formattedPrice + currency + productItems)."""
    if isinstance(obj, dict):
        if "formattedPrice" in obj and "sku" in obj and "currency" in obj and "productItems" in obj:
            return obj
        for v in obj.values():
            found = _find_product_block(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_product_block(item)
            if found is not None:
                return found
    return None


def _parse_product_page(html: str, product_url: str) -> Optional[ScrapedProduct]:
    match = _WARMUP_RE.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    block = _find_product_block(data)
    if block is None:
        return None

    price = block.get("discountedPrice") or block.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    inventory = block.get("inventory") or {}
    in_stock = block.get("isInStock")
    if in_stock is None:
        in_stock = inventory.get("status") == "in_stock"

    media = block.get("media") or []
    image_url = media[0].get("fullUrl") if media else None

    brand = block.get("brand") or None

    return ScrapedProduct(
        sku=str(block.get("sku") or block.get("urlPart") or "").strip(),
        name=block.get("name", ""),
        price=price,
        currency=block.get("currency", "COP"),
        in_stock=in_stock,
        url=product_url,
        image_url=image_url,
        brand=brand if isinstance(brand, str) else None,
    )


def fetch(provider_cfg: dict) -> list[ScrapedProduct]:
    base_url = provider_cfg["base_url"]
    code = provider_cfg.get("code", base_url)
    rate_limit = provider_cfg.get("rate_limit_seconds", DEFAULT_RATE_LIMIT_SECONDS)
    session = new_session()

    sitemap_url = provider_cfg.get("sitemap_url") or discover_product_sitemap_url(session, base_url)
    if not sitemap_url:
        logger.error("[%s] no se encontró store-products-sitemap.xml; ¿el sitio tiene Wix Stores instalado?", code)
        return []

    try:
        product_urls = list_product_urls(session, sitemap_url)
    except Exception as exc:
        logger.error("[%s] fallo leyendo el sitemap de productos (%s): %s", code, sitemap_url, exc)
        return []

    logger.info("[%s] %d URLs de producto encontradas en el sitemap", code, len(product_urls))
    product_urls = product_urls[:MAX_PRODUCTS]

    products: list[ScrapedProduct] = []
    for i, url in enumerate(product_urls):
        try:
            resp = _get(session, url)
        except Exception as exc:
            logger.warning("[%s] fallo consultando %s: %s", code, url, exc)
            continue

        product = _parse_product_page(resp.text, url)
        if product is not None:
            products.append(product)
        else:
            logger.debug("[%s] no se encontró bloque de producto en %s", code, url)

        if rate_limit:
            time.sleep(rate_limit)

    logger.info("[%s] %d/%d productos extraídos correctamente", code, len(products), len(product_urls))
    return products
