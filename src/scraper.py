"""
Dispatcher: recibe la configuración de un proveedor y lo enruta al
adaptador correcto (declarado en config/providers.yaml -> adapter).

Ver src/adapters/__init__.py para el registro de adaptadores disponibles.
"""

from __future__ import annotations

from src.adapters import get_adapter
from src.models import ScrapedProduct


def scrape_provider(provider_cfg: dict) -> list[ScrapedProduct]:
    adapter_name = provider_cfg.get("adapter", "css")
    adapter_fn = get_adapter(adapter_name)
    return adapter_fn(provider_cfg)
