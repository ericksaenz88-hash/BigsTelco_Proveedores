"""
Descubrimiento automático de proveedores.

Lee config/candidates.txt (una lista simple de dominios, sin código) y para
cada uno prueba si es una tienda Shopify, WooCommerce o Wix Stores -- las
plataformas más comunes entre proveedores colombianos de este sector, y
las que se pueden confirmar y activar 100% automáticamente, porque:
  - Shopify expone /products.json públicamente.
  - WooCommerce expone /wp-json/wc/store/v1/products, que además incluye
    la moneda explícita en cada respuesta (así no repetimos el problema de
    SYSCOM: activar un proveedor sin saber en qué moneda cotiza).
  - Wix Stores expone un sitemap de productos (.../store-products-sitemap.xml)
    y cada página de producto trae la moneda explícita en su bloque SSR
    (ver src/adapters/wix_stores.py para el detalle).

Los que califican se escriben en config/providers_auto.yaml -- un archivo
100% generado por este script, que se puede borrar y regenerar en
cualquier momento. NUNCA edites ese archivo a mano; para agregar o quitar
un proveedor auto-descubierto, edita config/candidates.txt.

config/providers.yaml (el archivo curado a mano, con las investigaciones
más profundas como GVS/SYSCOM/SAT Store) NO se toca -- main.py combina los
dos archivos al arrancar.

Uso:
    python -m src.discover              # corre el descubrimiento completo
    python -m src.discover --report     # solo muestra qué haría, sin escribir nada
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Optional

import requests
import yaml

from src.http_utils import new_session
from src.adapters.wix_stores import discover_product_sitemap_url, list_product_urls, _parse_product_page

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = ROOT / "config" / "candidates.txt"
PROVIDERS_PATH = ROOT / "config" / "providers.yaml"
PROVIDERS_AUTO_PATH = ROOT / "config" / "providers_auto.yaml"

DEFAULT_TIMEOUT = 15


def load_candidates() -> list[str]:
    if not CANDIDATES_PATH.exists():
        return []
    domains = []
    for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            domains.append(line)
    return domains


def _normalize_domain(url_or_domain: str) -> str:
    """'https://www.Tienda.com/' -> 'tienda.com' -- para comparar por dominio real,
    no por código, ya que un mismo proveedor puede tener códigos distintos en el
    archivo curado a mano (ej. 'security_solution_shop') y en el auto-generado
    (ej. 'auto_securitysolution')."""
    d = url_or_domain.lower().strip()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    d = d.split("/")[0]
    return d


def load_existing() -> tuple[set[str], set[str]]:
    """Códigos y dominios ya registrados (a mano o auto) para no duplicar proveedores."""
    codes, domains = set(), set()
    for path in (PROVIDERS_PATH, PROVIDERS_AUTO_PATH):
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for p in data.get("providers", []):
                if p.get("code"):
                    codes.add(p["code"])
                if p.get("base_url"):
                    domains.add(_normalize_domain(p["base_url"]))
    return codes, domains


def domain_to_code(domain: str) -> str:
    code = re.sub(r"^www\.", "", domain)
    code = re.sub(r"\.(com|co|com\.co|shop|net|store)$", "", code)
    code = re.sub(r"[^a-z0-9]+", "_", code.lower()).strip("_")
    return f"auto_{code}"


def probe_shopify(session: requests.Session, base_url: str) -> Optional[dict]:
    try:
        resp = session.get(f"{base_url}/products.json", params={"limit": 1}, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if "products" not in data:
            return None
    except Exception:
        return None

    # Intentar detectar la moneda real (crítico -- ver caso Security Solution Shop, que factura en USD)
    currency = None
    try:
        home = session.get(base_url, timeout=DEFAULT_TIMEOUT).text
        m = re.search(r'Shopify\.currency\s*=\s*\{"active":"([A-Z]{3})"', home)
        if m:
            currency = m.group(1)
    except Exception:
        pass

    return {"adapter": "shopify", "currency": currency, "sample_count": len(data.get("products", []))}


def probe_woocommerce(session: requests.Session, base_url: str) -> Optional[dict]:
    try:
        resp = session.get(
            f"{base_url}/wp-json/wc/store/v1/products", params={"per_page": 3}, timeout=DEFAULT_TIMEOUT
        )
        if resp.status_code != 200:
            return None
        items = resp.json()
        if not isinstance(items, list) or not items:
            return None
        if "prices" not in items[0]:
            return None
    except Exception:
        return None

    currency = items[0]["prices"].get("currency_code")
    return {"adapter": "woocommerce", "currency": currency, "sample_count": len(items)}


def probe_wix_stores(session: requests.Session, base_url: str) -> Optional[dict]:
    """Confirma si el sitio tiene Wix Stores instalado (sitemap de productos
    presente) y trae al menos un producto real para confirmar moneda."""
    try:
        sitemap_url = discover_product_sitemap_url(session, base_url)
        if not sitemap_url:
            return None
        product_urls = list_product_urls(session, sitemap_url)
        if not product_urls:
            return None

        # Confirmar moneda con el primer producto real (evita el mismo
        # problema que SYSCOM/VTEX: nunca asumir COP sin verificar)
        currency = None
        sample = session.get(product_urls[0], timeout=DEFAULT_TIMEOUT)
        if sample.status_code == 200:
            product = _parse_product_page(sample.text, product_urls[0])
            if product:
                currency = product.currency
    except Exception:
        return None

    return {
        "adapter": "wix_stores",
        "currency": currency,
        "sample_count": len(product_urls),
        "sitemap_url": sitemap_url,
    }


def discover_one(domain: str) -> dict:
    base_url = f"https://{domain}"
    session = new_session()

    result = {"domain": domain, "base_url": base_url, "status": "sin_clasificar"}

    shopify_result = probe_shopify(session, base_url)
    if shopify_result:
        result.update(shopify_result)
        result["status"] = "confirmado" if shopify_result["currency"] else "moneda_sin_confirmar"
        return result

    woo_result = probe_woocommerce(session, base_url)
    if woo_result:
        result.update(woo_result)
        result["status"] = "confirmado"
        return result

    wix_result = probe_wix_stores(session, base_url)
    if wix_result:
        result.update(wix_result)
        result["status"] = "confirmado" if wix_result["currency"] else "moneda_sin_confirmar"
        return result

    return result


def build_provider_block(result: dict) -> dict:
    code = domain_to_code(result["domain"])
    active = result["status"] == "confirmado"
    block = {
        "code": code,
        "name": result["domain"],
        "sector": "sin_clasificar_auto_descubierto",
        "base_url": result["base_url"],
        "active": active,
        "adapter": result["adapter"],
        "notes": "Auto-descubierto por src/discover.py. Revisa el sector y el nombre, "
                 "y ajústalos a mano en config/providers.yaml si quieres 'adoptarlo' "
                 "como entrada curada (opcional).",
    }
    if result["adapter"] == "shopify":
        if result["currency"]:
            block["currency"] = result["currency"]
        else:
            block["active"] = False
            block["notes"] += (
                " ADVERTENCIA: no se pudo confirmar la moneda real de esta tienda "
                "Shopify (igual que pasó con Security Solution Shop, que resultó "
                "estar en USD). Queda inactivo hasta confirmar manualmente."
            )
    elif result["adapter"] == "wix_stores":
        block["sitemap_url"] = result.get("sitemap_url")
        block["rate_limit_seconds"] = 1.0
        if result["currency"]:
            block["currency"] = result["currency"]
        else:
            block["active"] = False
            block["notes"] += (
                " ADVERTENCIA: no se pudo confirmar la moneda del primer producto "
                "de muestra. Queda inactivo hasta confirmar manualmente."
            )
    return block


def run(write: bool = True) -> None:
    domains = load_candidates()
    existing_codes, existing_domains = load_existing()

    if not domains:
        logger.warning("config/candidates.txt está vacío o no existe. Nada que hacer.")
        return

    logger.info("Probando %d dominios candidatos...", len(domains))

    auto_blocks = []
    report = {"confirmado": [], "moneda_sin_confirmar": [], "sin_clasificar": [], "ya_existentes": []}

    for domain in domains:
        code = domain_to_code(domain)
        if code in existing_codes or _normalize_domain(domain) in existing_domains:
            report["ya_existentes"].append(domain)
            continue

        result = discover_one(domain)
        logger.info("  %-40s -> %s", domain, result["status"])

        if result["status"] in ("confirmado", "moneda_sin_confirmar"):
            block = build_provider_block(result)
            auto_blocks.append(block)
            report[result["status"]].append(domain)
        else:
            report["sin_clasificar"].append(domain)

    print("\n" + "=" * 70)
    print("REPORTE DE DESCUBRIMIENTO")
    print("=" * 70)
    print(f"Ya existentes en la matriz:      {len(report['ya_existentes'])}")
    print(f"Confirmados y activados:         {len(report['confirmado'])}  {report['confirmado']}")
    print(f"Detectados pero moneda dudosa:   {len(report['moneda_sin_confirmar'])}  {report['moneda_sin_confirmar']}")
    print(f"Sin clasificar (necesitan investigación manual): {len(report['sin_clasificar'])}")
    for d in report["sin_clasificar"]:
        print(f"    - {d}")
    print("=" * 70)

    if write and auto_blocks:
        existing_auto = []
        if PROVIDERS_AUTO_PATH.exists():
            data = yaml.safe_load(PROVIDERS_AUTO_PATH.read_text(encoding="utf-8")) or {}
            existing_auto = data.get("providers", [])
        existing_auto_codes = {p["code"] for p in existing_auto}
        new_blocks = [b for b in auto_blocks if b["code"] not in existing_auto_codes]
        merged = existing_auto + new_blocks

        header = (
            "# ============================================================\n"
            "# ARCHIVO 100% GENERADO AUTOMÁTICAMENTE por src/discover.py\n"
            "# NO EDITAR A MANO -- los cambios se pierden en la próxima corrida.\n"
            "# Para agregar/quitar proveedores de aquí, edita config/candidates.txt\n"
            "# y vuelve a correr: python -m src.discover\n"
            "# ============================================================\n\n"
        )
        content = header + yaml.dump({"providers": merged}, allow_unicode=True, sort_keys=False)
        PROVIDERS_AUTO_PATH.write_text(content, encoding="utf-8")
        logger.info("Escrito %s con %d proveedores auto-descubiertos (%d nuevos esta corrida).",
                    PROVIDERS_AUTO_PATH, len(merged), len(new_blocks))
    elif not write:
        logger.info("Modo --report: no se escribió nada.")


def main():
    parser = argparse.ArgumentParser(description="Descubre proveedores nuevos automáticamente.")
    parser.add_argument("--report", action="store_true", help="Solo mostrar qué encontraría, sin escribir archivos")
    args = parser.parse_args()
    run(write=not args.report)


if __name__ == "__main__":
    main()
