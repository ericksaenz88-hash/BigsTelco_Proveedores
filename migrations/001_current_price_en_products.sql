-- ============================================================
-- Migración: agrega el "precio actual" directo en products
-- ============================================================
-- Para bases de datos que ya corrieron schema.sql ANTES de este cambio
-- (como Bigs_Telco). Agrega las columnas nuevas sin borrar nada de lo
-- que ya está cargado, y las llena con el último precio conocido de
-- price_history para no perder continuidad.
--
-- Uso:
--   psql -h HOST -p PUERTO -U USUARIO -d BASE -f migrations/001_current_price_en_products.sql
--
-- Es seguro correrla más de una vez (usa IF NOT EXISTS / no destruye datos).
-- ============================================================

ALTER TABLE products ADD COLUMN IF NOT EXISTS current_price    NUMERIC(14,2);
ALTER TABLE products ADD COLUMN IF NOT EXISTS current_currency VARCHAR(10) NOT NULL DEFAULT 'COP';
ALTER TABLE products ADD COLUMN IF NOT EXISTS current_in_stock BOOLEAN;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price_updated_at TIMESTAMPTZ;

-- Rellena las columnas nuevas con el último precio ya guardado en
-- price_history, para que ningún producto quede con precio_actual vacío
-- por haber cargado datos antes de este cambio.
UPDATE products p
SET current_price    = last_price.price,
    current_currency = last_price.currency,
    current_in_stock = last_price.in_stock,
    price_updated_at = last_price.scraped_at
FROM (
    SELECT DISTINCT ON (product_id)
        product_id, price, currency, in_stock, scraped_at
    FROM price_history
    ORDER BY product_id, scraped_at DESC
) AS last_price
WHERE p.id = last_price.product_id
  AND p.current_price IS NULL;

-- Reemplaza la vista current_prices para que lea directo de products
-- (más simple y más rápido que el DISTINCT ON sobre price_history de antes).
CREATE OR REPLACE VIEW current_prices AS
SELECT
    p.id               AS product_id,
    pr.code            AS provider_code,
    pr.name            AS provider_name,
    p.sku,
    p.name             AS product_name,
    p.category,
    p.brand,
    p.unit,
    p.url,
    p.current_price    AS price,
    p.current_currency AS currency,
    p.current_in_stock AS in_stock,
    p.price_updated_at AS price_date
FROM products p
JOIN providers pr ON pr.id = p.provider_id
WHERE p.is_active;
