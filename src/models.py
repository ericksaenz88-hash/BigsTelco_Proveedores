"""Estructura de datos común que todos los adaptadores devuelven."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ScrapedProduct:
    sku: str
    name: str
    price: Optional[float]
    currency: str = "COP"
    in_stock: Optional[bool] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    unit: Optional[str] = None
