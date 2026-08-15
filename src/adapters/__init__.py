"""
Registro de adaptadores de scraping.

Cada proveedor en config/providers.yaml declara un campo "adapter" que dice
qué función usar para traer sus productos. Así la "matriz" de proveedores
puede crecer sin tocar el orquestador (src/main.py):

  - "css"     -> motor genérico por selectores CSS (sitios que renderizan
                 el catálogo en el servidor, ej. SAT Store).
  - "gvs_api" -> adaptador específico para la API interna de GVS Colombia.
  - "syscom_algolia" -> adaptador específico para la API pública de
                 búsqueda (Algolia) que usa SYSCOM Colombia.

Para añadir un proveedor grande nuevo que tenga su propia API/estructura,
se agrega un archivo nuevo en esta carpeta con una función
`fetch(provider_cfg) -> list[ScrapedProduct]` y se registra aquí.
"""

from __future__ import annotations

from typing import Callable

from src.models import ScrapedProduct
from src.adapters.css_scraper import fetch as fetch_css
from src.adapters.gvs_api import fetch as fetch_gvs
from src.adapters.syscom_algolia import fetch as fetch_syscom
from src.adapters.shopify import fetch as fetch_shopify
from src.adapters.woocommerce import fetch as fetch_woocommerce
from src.adapters.vtex import fetch as fetch_vtex
from src.adapters.wix_stores import fetch as fetch_wix_stores

ADAPTERS: dict[str, Callable[[dict], list[ScrapedProduct]]] = {
    "css": fetch_css,
    "gvs_api": fetch_gvs,
    "syscom_algolia": fetch_syscom,
    "shopify": fetch_shopify,       # genérico: cualquier tienda Shopify (/products.json)
    "woocommerce": fetch_woocommerce,  # genérico: cualquier WordPress+WooCommerce (Store API)
    "vtex": fetch_vtex,              # genérico: cualquier tienda VTEX
    "wix_stores": fetch_wix_stores,  # genérico: cualquier tienda Wix Stores (sitemap + SSR)
}


def get_adapter(name: str):
    if name not in ADAPTERS:
        raise ValueError(
            f"Adaptador '{name}' no existe. Adaptadores disponibles: {list(ADAPTERS)}"
        )
    return ADAPTERS[name]
