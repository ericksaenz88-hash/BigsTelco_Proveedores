"""
Capa de acceso a PostgreSQL.

Responsable de:
  - Abrir/cerrar la conexión.
  - Registrar proveedores (upsert desde config/providers.yaml).
  - Guardar productos y su historial de precios (upsert).
  - Registrar cada corrida en scrape_runs para poder auditar si la
    actualización diaria realmente corrió y qué encontró.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "proveedores_colombia"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
    )


@contextmanager
def db_cursor(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def ensure_provider(conn, code: str, name: str, base_url: str, sector: str,
                     requires_js: bool, notes: str = "") -> int:
    """Inserta el proveedor si no existe y devuelve su id (upsert por code)."""
    with db_cursor(conn) as cur:
        cur.execute(
            """
            INSERT INTO providers (code, name, base_url, sector, requires_js, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE
                SET name = EXCLUDED.name,
                    base_url = EXCLUDED.base_url,
                    sector = EXCLUDED.sector,
                    requires_js = EXCLUDED.requires_js,
                    notes = EXCLUDED.notes
            RETURNING id
            """,
            (code, name, base_url, sector, requires_js, notes),
        )
        return cur.fetchone()["id"]


def upsert_product_and_price(conn, provider_id: int, sku: str, name: str,
                              category: Optional[str], brand: Optional[str],
                              url: Optional[str], image_url: Optional[str],
                              unit: Optional[str], price: Optional[float],
                              currency: str, in_stock: Optional[bool]) -> int:
    """
    Crea o actualiza el producto (por provider_id+sku).

    El precio "de hoy" vive en products.current_price/current_currency/
    current_in_stock y se SOBRESCRIBE en cada corrida (no se acumula) --
    así consultar el precio actual es leer una columna directa, sin tener
    que buscar en price_history.

    price_history, aparte, solo recibe una fila NUEVA cuando el precio,
    moneda o disponibilidad realmente cambiaron respecto a la corrida
    anterior (o si el producto es nuevo) -- así se conserva el historial
    de cambios reales sin llenarse de filas idénticas repetidas día a día
    cuando un proveedor no cambia sus precios.

    "last_seen_at" se actualiza siempre en cada corrida (aunque el precio
    no haya cambiado), para saber cuándo fue la última vez que el producto
    se vio en el sitio del proveedor.
    """
    now = datetime.now(timezone.utc)
    with db_cursor(conn) as cur:
        # 1. Leer el precio actual guardado (si el producto ya existía)
        #    para poder comparar y decidir si hubo un cambio real.
        cur.execute(
            "SELECT current_price, current_currency, current_in_stock "
            "FROM products WHERE provider_id = %s AND sku = %s",
            (provider_id, sku),
        )
        existing = cur.fetchone()

        # price viene de PostgreSQL como Decimal; se compara como float
        # (redondeado a los mismos 2 decimales que la columna NUMERIC(14,2))
        # para evitar falsos "cambios" por diferencias de representación.
        old_price = (
            float(existing["current_price"])
            if existing and existing["current_price"] is not None
            else None
        )
        new_price = round(float(price), 2) if price is not None else None

        changed = (
            existing is None
            or old_price != new_price
            or existing["current_currency"] != currency
            or existing["current_in_stock"] != in_stock
        )

        # 2. Crear o actualizar el producto, sobrescribiendo siempre el
        #    precio "de hoy" (current_price y compañía). price_updated_at
        #    solo se mueve a "ahora" cuando de verdad hubo un cambio; si
        #    el precio sigue igual, conserva la fecha del último cambio
        #    real (para que refleje "hace cuánto cambió", no "cuándo se
        #    volvió a ver el mismo precio").
        cur.execute(
            """
            INSERT INTO products (provider_id, sku, name, category, brand, url,
                                   image_url, unit, current_price, current_currency,
                                   current_in_stock, price_updated_at,
                                   first_seen_at, last_seen_at, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (provider_id, sku) DO UPDATE
                SET name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    brand = EXCLUDED.brand,
                    url = EXCLUDED.url,
                    image_url = EXCLUDED.image_url,
                    unit = EXCLUDED.unit,
                    current_price = EXCLUDED.current_price,
                    current_currency = EXCLUDED.current_currency,
                    current_in_stock = EXCLUDED.current_in_stock,
                    price_updated_at = CASE WHEN %s THEN EXCLUDED.price_updated_at
                                             ELSE products.price_updated_at END,
                    last_seen_at = EXCLUDED.last_seen_at,
                    is_active = TRUE
            RETURNING id
            """,
            (
                provider_id, sku, name, category, brand, url, image_url, unit,
                price, currency, in_stock, now,
                now, now,
                changed,
            ),
        )
        product_id = cur.fetchone()["id"]

        # 3. price_history solo recibe una fila nueva si hubo un cambio real.
        if changed:
            cur.execute(
                """
                INSERT INTO price_history (product_id, price, currency, in_stock, scraped_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (product_id, price, currency, in_stock, now),
            )

        return product_id


def mark_missing_products_inactive(conn, provider_id: int, seen_skus: Iterable[str]):
    """
    Productos de este proveedor que NO aparecieron en la corrida actual se
    marcan como inactivos (probablemente descontinuados) en vez de borrarse,
    para no perder el historial de precios.
    """
    seen_skus = list(seen_skus)
    with db_cursor(conn) as cur:
        if seen_skus:
            cur.execute(
                """
                UPDATE products
                SET is_active = FALSE
                WHERE provider_id = %s AND sku <> ALL(%s) AND is_active = TRUE
                """,
                (provider_id, seen_skus),
            )
        else:
            cur.execute(
                "UPDATE products SET is_active = FALSE WHERE provider_id = %s AND is_active = TRUE",
                (provider_id,),
            )


def start_run(conn, provider_id: int) -> int:
    with db_cursor(conn) as cur:
        cur.execute(
            "INSERT INTO scrape_runs (provider_id, status) VALUES (%s, 'running') RETURNING id",
            (provider_id,),
        )
        return cur.fetchone()["id"]


def finish_run(conn, run_id: int, status: str, products_found: int, error_message: str = None):
    with db_cursor(conn) as cur:
        cur.execute(
            """
            UPDATE scrape_runs
            SET status = %s, products_found = %s, error_message = %s, finished_at = now()
            WHERE id = %s
            """,
            (status, products_found, error_message, run_id),
        )
