"""
Adaptador genérico dirigido por selectores CSS.

Para sitios que renderizan el catálogo en el servidor (ej. SAT Store,
plataformas Magento/similares). Lee config/providers.yaml -> selectors.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import ScrapedProduct

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; CotizadorPreciosBot/1.0; "
    "+contacto: ericksaenz88@gmail.com)"
)
DEFAULT_TIMEOUT = 20
MAX_PAGES_PER_CATEGORY = 50


def _clean_price(raw_text: str) -> Optional[float]:
    if not raw_text:
        return None
    match = re.search(r"[\d\.,]+", raw_text)
    if not match:
        return None
    number = match.group(0).replace(".", "").replace(",", ".")
    try:
        value = float(number)
        return value if value > 0 else None
    except ValueError:
        return None


def _extract_sku(text: str, href: str) -> str:
    match = re.search(r"sku[:\s]*([A-Za-z0-9\-_]+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    slug = href.rstrip("/").split("/")[-1]
    return slug.replace(".html", "") or text[:80]


class _RequestsScraper:
    def __init__(self, provider_cfg: dict, rate_limit_seconds: float = 2.0):
        self.cfg = provider_cfg
        self.base_url = provider_cfg["base_url"]
        self.selectors = provider_cfg["selectors"]
        self.rate_limit_seconds = provider_cfg.get("rate_limit_seconds", rate_limit_seconds)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
    def _get(self, url: str) -> str:
        resp = self.session.get(url, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.text

    def scrape_all(self) -> list[ScrapedProduct]:
        products: list[ScrapedProduct] = []
        for category in self.cfg.get("categories", []):
            cat_name = category.get("name")
            url = category.get("start_url")
            page_count = 0
            visited = set()
            while url and url not in visited and page_count < MAX_PAGES_PER_CATEGORY:
                visited.add(url)
                logger.info("  [%s] descargando página: %s", self.cfg["code"], url)
                try:
                    html = self._get(url)
                except Exception as exc:
                    logger.error("  [%s] fallo al descargar %s: %s", self.cfg["code"], url, exc)
                    break

                soup = BeautifulSoup(html, "lxml")
                cards = soup.select(self.selectors["product_card"])
                logger.info("  [%s] %d productos encontrados en esta página", self.cfg["code"], len(cards))

                for card in cards:
                    product = self._parse_card(card, cat_name)
                    if product:
                        products.append(product)

                url = self._find_next_page(soup)
                page_count += 1
                if url:
                    time.sleep(self.rate_limit_seconds)
        return products

    def _parse_card(self, card, category_name: str) -> Optional[ScrapedProduct]:
        sel = self.selectors
        try:
            name_el = card.select_one(sel["name"])
            if not name_el:
                return None
            raw_name_text = re.sub(r"\s+", " ", name_el.get_text(" ", strip=True)).strip()

            href = name_el.get("href", "")
            full_url = urljoin(self.base_url, href) if href else None

            price_el = card.select_one(sel["price"])
            price = _clean_price(price_el.get_text(strip=True)) if price_el else None

            sku = _extract_sku(raw_name_text, href)
            name = re.sub(r"^sku[:\s]*[A-Za-z0-9\-_]+\s*", "", raw_name_text, flags=re.IGNORECASE).strip()
            name = name or raw_name_text

            stock_text = card.get_text(" ", strip=True)
            out_of_stock_marker = sel.get("stock_out_of_stock_text")
            in_stock = None
            if out_of_stock_marker:
                in_stock = out_of_stock_marker.lower() not in stock_text.lower()

            image_el = card.select_one("img")
            image_url = image_el.get("src") if image_el else None

            return ScrapedProduct(
                sku=sku, name=name, price=price, in_stock=in_stock,
                url=full_url, image_url=image_url, category=category_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("  no se pudo parsear una tarjeta de producto: %s", exc)
            return None

    def _find_next_page(self, soup: BeautifulSoup) -> Optional[str]:
        next_sel = self.selectors.get("next_page")
        if not next_sel:
            return None
        next_el = soup.select_one(next_sel)
        if not next_el:
            return None
        href = next_el.get("href")
        return urljoin(self.base_url, href) if href else None


def fetch(provider_cfg: dict) -> list[ScrapedProduct]:
    if not provider_cfg.get("selectors"):
        raise ValueError(
            f"El proveedor '{provider_cfg['code']}' usa adapter=css pero no tiene "
            f"selectores CSS configurados en config/providers.yaml."
        )
    return _RequestsScraper(provider_cfg).scrape_all()
