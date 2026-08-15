"""
Adaptador genérico para tiendas WordPress + WooCommerce.

WooCommerce expone una API pública de solo lectura (el "Store API", pensado
para los bloques de carrito/checkout del propio tema) en:
  /wp-json/wc/store/v1/products

No requiere API key y trae precio, moneda explícita, sku, categorías y
disponibilidad — más confiable que leer HTML.

Config esperada en providers.yaml:
  base_url: "https://tudominio.com"     # dominio del WordPress/WooCommerce

Para saber si un proveedor nuevo es candidato a este adaptador, probar:
  curl https://SU_DOMINIO/wp-json/wc/store/v1/products?per_page=1
Si responde JSON con una lista de productos (no un 404 de WordPress), es
candidato.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import ScrapedProduct
from src.http_utils import new_session

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
DEFAULT_TIMEOUT = 20
MAX_PAGES = 300


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get_page(session: requests.Session, base_url: str, page: int) -> list[dict]:
    url = f"{base_url.rstrip('/')}/wp-json/wc/store/v1/products"
    resp = session.get(url, params={"per_page": PAGE_SIZE, "page": page}, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def _price(item: dict) -> Optional[float]:
    prices = item.get("prices", {})
    minor_unit = prices.get("currency_minor_unit", 0)
    raw = prices.get("sale_price") or prices.get("price") or prices.get("regular_price")
    try:
        val = float(raw)
        if minor_unit:
            val = val / (10 ** minor_unit)
        return val if val > 0 else None
    except (TypeError, ValueError):
        return None


def fetch(provider_cfg: dict) -> list[ScrapedProduct]:
    base_url = provider_cfg["base_url"]
    session = new_session()
    products: list[ScrapedProduct] = []

    page = 1
    while page <= MAX_PAGES:
        try:
            items = _get_page(session, base_url, page)
        except Exception as exc:
            logger.error("[%s] fallo consultando Store API página %d: %s", provider_cfg["code"], page, exc)
            break

        logger.info("[%s] página %d -> %d productos", provider_cfg["code"], page, len(items))
        if not items:
            break

        for item in items:
            sku = str(item.get("sku") or item.get("id") or "").strip()
            if not sku:
                continue
            prices = item.get("prices", {})
            categories = item.get("categories") or []
            category = categories[0]["name"] if categories else None
            brands = item.get("brands") or []
            brand = brands[0]["name"] if brands else None
            images = item.get("images") or []
            image_url = images[0]["src"] if images else None
            stock_status = item.get("is_in_stock")

            products.append(ScrapedProduct(
                sku=sku,
                name=item.get("name", "").strip(),
                price=_price(item),
                currency=prices.get("currency_code", "COP"),
                in_stock=stock_status if isinstance(stock_status, bool) else None,
                url=item.get("permalink"),
                image_url=image_url,
                category=category,
                brand=brand,
            ))

        page += 1

    return products
