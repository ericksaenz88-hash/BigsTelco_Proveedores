"""
Adaptador genérico para tiendas VTEX.

VTEX es una plataforma de e-commerce muy usada por retailers grandes en
Latinoamérica. Expone un catálogo público de solo lectura, sin API key, en:
  /api/catalog_system/pub/products/search?_from=N&_to=M

Para saber si un proveedor nuevo es candidato a este adaptador, probar:
  curl https://SU_DOMINIO/api/catalog_system/pub/products/search?_from=0&_to=1
Si responde JSON con una lista de productos (con "items"/"sellers" adentro),
es VTEX.

Nota sobre moneda: a diferencia de Shopify (que expone Shopify.currency) y
WooCommerce (que trae currency_code explícito), esta API de VTEX NO
devuelve el código de moneda en la respuesta. Se asume la moneda declarada
en providers.yaml (currency), que hay que confirmar por otra vía (revisar
el sitio en el navegador, o comparar un precio conocido) antes de activar
el proveedor -- igual precaución que con SYSCOM/AS Security.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import ScrapedProduct
from src.http_utils import new_session

logger = logging.getLogger(__name__)

PAGE_SIZE = 50  # tamaño de página típico soportado por VTEX en este endpoint
DEFAULT_TIMEOUT = 20
MAX_PAGES = 400


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get_page(session: requests.Session, base_url: str, start: int, end: int) -> list[dict]:
    url = f"{base_url.rstrip('/')}/api/catalog_system/pub/products/search"
    resp = session.get(url, params={"_from": start, "_to": end}, timeout=DEFAULT_TIMEOUT)
    if resp.status_code == 206 or resp.status_code == 200:
        return resp.json()
    resp.raise_for_status()
    return []


def _best_offer(item: dict) -> Optional[dict]:
    sellers = item.get("sellers") or []
    for seller in sellers:
        if seller.get("sellerDefault"):
            return seller.get("commertialOffer")
    if sellers:
        return sellers[0].get("commertialOffer")
    return None


def fetch(provider_cfg: dict) -> list[ScrapedProduct]:
    base_url = provider_cfg["base_url"]
    currency = provider_cfg.get("currency", "COP")
    session = new_session()
    products: list[ScrapedProduct] = []

    start = 0
    while start < PAGE_SIZE * MAX_PAGES:
        end = start + PAGE_SIZE - 1
        try:
            items = _get_page(session, base_url, start, end)
        except Exception as exc:
            logger.error("[%s] fallo consultando productos %d-%d: %s", provider_cfg["code"], start, end, exc)
            break

        logger.info("[%s] productos %d-%d -> %d resultados", provider_cfg["code"], start, end, len(items))
        if not items:
            break

        for product in items:
            category = None
            categories = product.get("categories") or []
            if categories:
                # VTEX devuelve categorías como "/Padre/Hijo/Nieto/"; nos quedamos con el último tramo no vacío
                parts = [p for p in categories[0].split("/") if p]
                category = parts[-1] if parts else None
            brand = product.get("brand")

            for sku_item in product.get("items", []):
                offer = _best_offer(sku_item)
                if not offer:
                    continue
                price = offer.get("Price")
                try:
                    price = float(price) if price else None
                    if price is not None and price <= 0:
                        price = None
                except (TypeError, ValueError):
                    price = None

                images = sku_item.get("images") or []
                image_url = images[0].get("imageUrl") if images else None

                products.append(ScrapedProduct(
                    sku=str(sku_item.get("itemId") or sku_item.get("referenceId") or "").strip(),
                    name=sku_item.get("nameComplete") or sku_item.get("name") or product.get("productName", ""),
                    price=price,
                    currency=currency,
                    in_stock=bool(offer.get("IsAvailable")),
                    url=f"{base_url.rstrip('/')}/{product.get('linkText')}/p" if product.get("linkText") else None,
                    image_url=image_url,
                    category=category,
                    brand=brand,
                ))

        if len(items) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return products
