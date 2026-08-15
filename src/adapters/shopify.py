"""
Adaptador genérico para tiendas Shopify.

Cualquier tienda Shopify (a menos que el dueño lo desactive explícitamente)
expone un endpoint público de solo lectura en /products.json — pensado
originalmente para integraciones, y es mucho más confiable que leer HTML.
No requiere API key.

Config esperada en providers.yaml:
  base_url: "https://tudominio.com"     # dominio de la tienda Shopify
  currency: "COP"                        # moneda en la que Shopify muestra los precios en ese store

Para saber si un proveedor nuevo es candidato a este adaptador, probar:
  curl https://SU_DOMINIO/products.json?limit=1
Si responde JSON con "products", es Shopify.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import ScrapedProduct
from src.http_utils import new_session

logger = logging.getLogger(__name__)

PAGE_SIZE = 250  # máximo permitido por Shopify en este endpoint
DEFAULT_TIMEOUT = 20
MAX_PAGES = 200  # límite de seguridad


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get_page(session: requests.Session, base_url: str, page: int) -> list[dict]:
    url = f"{base_url.rstrip('/')}/products.json"
    resp = session.get(url, params={"limit": PAGE_SIZE, "page": page}, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("products", [])


def _price(variant: dict) -> Optional[float]:
    val = variant.get("price")
    try:
        val = float(val)
        return val if val > 0 else None
    except (TypeError, ValueError):
        return None


def fetch(provider_cfg: dict) -> list[ScrapedProduct]:
    base_url = provider_cfg["base_url"]
    currency = provider_cfg.get("currency", "COP")
    session = new_session()
    products: list[ScrapedProduct] = []

    page = 1
    while page <= MAX_PAGES:
        try:
            items = _get_page(session, base_url, page)
        except Exception as exc:
            logger.error("[%s] fallo consultando products.json página %d: %s", provider_cfg["code"], page, exc)
            break

        logger.info("[%s] página %d -> %d productos", provider_cfg["code"], page, len(items))
        if not items:
            break

        for item in items:
            category = item.get("product_type") or (item.get("tags") or [None])[0]
            brand = item.get("vendor")
            handle = item.get("handle")
            product_url = f"{base_url.rstrip('/')}/products/{handle}" if handle else None
            image_url = None
            images = item.get("images") or []
            if images:
                image_url = images[0].get("src")

            for variant in item.get("variants", []):
                sku = str(variant.get("sku") or variant.get("id") or "").strip()
                if not sku:
                    continue
                available = variant.get("available")
                name = item.get("title") or ""
                variant_title = variant.get("title")
                if variant_title and variant_title.lower() != "default title":
                    name = f"{name} - {variant_title}"

                products.append(ScrapedProduct(
                    sku=sku,
                    name=name,
                    price=_price(variant),
                    currency=currency,
                    in_stock=available if isinstance(available, bool) else None,
                    url=product_url,
                    image_url=image_url,
                    category=category,
                    brand=brand,
                ))

        page += 1

    return products
