"""
Orquestador principal.

Uso:
    python -m src.main                      # corre todos los proveedores activos
    python -m src.main --provider satstore   # corre solo uno (para probar)
    python -m src.main --dry-run             # scrapea pero NO escribe en la BD

Pensado para ejecutarse:
  - manualmente durante desarrollo/pruebas
  - automáticamente cada día vía GitHub Actions (ver .github/workflows/daily_update.yml)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src import db
from src.scraper import scrape_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CONFIG_PATH = CONFIG_DIR / "providers.yaml"
CONFIG_AUTO_PATH = CONFIG_DIR / "providers_auto.yaml"


def load_providers_config() -> list[dict]:
    """
    Combina el archivo curado a mano (providers.yaml) con el generado
    automáticamente por `python -m src.discover` (providers_auto.yaml).
    Si un mismo código existe en ambos, gana la versión curada a mano
    (por si alguien "adoptó" un proveedor auto-descubierto y lo ajustó).
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    manual_providers = cfg.get("providers", [])
    manual_codes = {p["code"] for p in manual_providers}

    auto_providers = []
    if CONFIG_AUTO_PATH.exists():
        with open(CONFIG_AUTO_PATH, "r", encoding="utf-8") as f:
            auto_cfg = yaml.safe_load(f) or {}
        auto_providers = [p for p in auto_cfg.get("providers", []) if p["code"] not in manual_codes]
        if auto_providers:
            logger.info("Cargados %d proveedores auto-descubiertos desde %s", len(auto_providers), CONFIG_AUTO_PATH.name)

    return manual_providers + auto_providers


def run_provider(conn, provider_cfg: dict, dry_run: bool = False) -> int:
    code = provider_cfg["code"]

    if not provider_cfg.get("active", False):
        logger.info("[%s] inactivo en la configuración, se omite.", code)
        return 0

    if dry_run:
        # En modo dry-run no tocamos la base de datos para nada (ni
        # siquiera para registrar el proveedor), así se puede probar un
        # adaptador nuevo sin tener PostgreSQL configurado.
        logger.info("[%s] iniciando scrape (dry-run, sin base de datos)...", code)
        try:
            products = scrape_provider(provider_cfg)
        except Exception:
            logger.exception("[%s] error durante el scrape", code)
            return 0

        logger.info("[%s] %d productos extraídos", code, len(products))
        for p in products[:10]:
            logger.info("  DRY-RUN %s | %s | $%s | stock=%s", p.sku, p.name, p.price, p.in_stock)
        return len(products)

    provider_id = db.ensure_provider(
        conn,
        code=code,
        name=provider_cfg["name"],
        base_url=provider_cfg["base_url"],
        sector=provider_cfg.get("sector", ""),
        requires_js=provider_cfg.get("adapter", "css") != "css",
        notes=provider_cfg.get("notes", ""),
    )

    run_id = db.start_run(conn, provider_id)
    logger.info("[%s] iniciando scrape...", code)

    try:
        products = scrape_provider(provider_cfg)
    except Exception as exc:
        logger.exception("[%s] error durante el scrape", code)
        db.finish_run(conn, run_id, status="error", products_found=0, error_message=str(exc))
        return 0

    logger.info("[%s] %d productos extraídos", code, len(products))

    seen_skus = []
    for p in products:
        db.upsert_product_and_price(
            conn,
            provider_id=provider_id,
            sku=p.sku,
            name=p.name,
            category=p.category,
            brand=p.brand,
            url=p.url,
            image_url=p.image_url,
            unit=p.unit,
            price=p.price,
            currency=p.currency,
            in_stock=p.in_stock,
        )
        seen_skus.append(p.sku)

    db.mark_missing_products_inactive(conn, provider_id, seen_skus)
    db.finish_run(conn, run_id, status="success", products_found=len(products))
    logger.info("[%s] guardado en base de datos correctamente.", code)
    return len(products)


def main():
    parser = argparse.ArgumentParser(description="Actualiza precios de proveedores colombianos en PostgreSQL.")
    parser.add_argument("--provider", help="Código de un solo proveedor a correr (ej: satstore)")
    parser.add_argument("--dry-run", action="store_true", help="No escribe en la base de datos, solo imprime resultados")
    args = parser.parse_args()

    load_dotenv()

    providers = load_providers_config()
    if args.provider:
        providers = [p for p in providers if p["code"] == args.provider]
        if not providers:
            logger.error("No existe un proveedor con código '%s' en config/providers.yaml", args.provider)
            sys.exit(1)

    conn = None if args.dry_run else db.get_connection()

    total = 0
    errors = 0
    try:
        for provider_cfg in providers:
            try:
                total += run_provider(conn, provider_cfg, dry_run=args.dry_run)
            except Exception:
                errors += 1
                logger.exception("Fallo inesperado procesando '%s'", provider_cfg.get("code"))
    finally:
        if conn:
            conn.close()

    logger.info("Listo. Total de productos procesados: %d. Proveedores con error: %d", total, errors)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
