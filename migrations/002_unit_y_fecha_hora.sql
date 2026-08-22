-- ============================================================
-- Migración 002: unidad de venta (backfill) + fecha/hora separadas
-- ============================================================
-- 1. Rellena products.unit para los productos que ya están guardados,
--    detectando la unidad a partir del nombre (misma lógica que
--    src/unit_extractor.py, reproducida aquí en SQL para no depender de
--    volver a correr el scraper completo). Solo toca filas donde unit
--    todavía está vacío -- no pisa nada que ya tenga un valor.
--
-- 2. Reemplaza la vista current_prices agregando dos columnas nuevas:
--    price_fecha (solo fecha) y price_hora (solo hora), además de
--    conservar price_date (fecha y hora completas) por compatibilidad
--    con lo que ya se haya construido sobre esa columna.
--
-- Uso:
--   psql -h HOST -p PUERTO -U USUARIO -d BASE -f migrations/002_unit_y_fecha_hora.sql
--
-- Es seguro correrla más de una vez.
-- ============================================================

-- --- 1. Backfill de unit ---

-- "305Mt", "100 Mt", "305mts", "305 metros" -> "rollo 305m"
UPDATE products
SET unit = 'rollo ' || (regexp_match(name, '(\d+(?:[.,]\d+)?)\s*(?:[Mm][Tt][Ss]?|[Mm]etros)\b'))[1] || 'm'
WHERE unit IS NULL
  AND name ~ '\d+(?:[.,]\d+)?\s*(?:[Mm][Tt][Ss]?|[Mm]etros)\b';

-- "100m", "305m" (metros a secas, sin "mt"/"metros"), evitando mm/cm/km
UPDATE products
SET unit = 'rollo ' || (regexp_match(name, '(?<![a-zA-Z])(\d+(?:[.,]\d+)?)[Mm](?![a-zA-Z])'))[1] || 'm'
WHERE unit IS NULL
  AND name ~ '(?<![a-zA-Z])\d+(?:[.,]\d+)?[Mm](?![a-zA-Z])';

-- "Caja x50", "caja X 100" -> "caja x50"
UPDATE products
SET unit = 'caja x' || (regexp_match(name, '[Cc]aja\s*[Xx]\s*(\d+)'))[1]
WHERE unit IS NULL
  AND name ~ '[Cc]aja\s*[Xx]\s*\d+';

UPDATE products SET unit = 'bobina' WHERE unit IS NULL AND name ~* '\bbobina\b';
UPDATE products SET unit = 'kit'    WHERE unit IS NULL AND name ~* '\bkit\b';
UPDATE products SET unit = 'juego'  WHERE unit IS NULL AND name ~* '\bjuego\b';
UPDATE products SET unit = 'par'    WHERE unit IS NULL AND name ~* '\bpar\b';
UPDATE products SET unit = 'rollo'  WHERE unit IS NULL AND name ~* '\brollo\b';
UPDATE products SET unit = 'unidad' WHERE unit IS NULL AND name ~* '\bunidad\b';

-- --- 2. Vista current_prices con fecha y hora separadas ---

CREATE OR REPLACE VIEW current_prices AS
SELECT
    p.id                                    AS product_id,
    pr.code                                 AS provider_code,
    pr.name                                 AS provider_name,
    p.sku,
    p.name                                  AS product_name,
    p.category,
    p.brand,
    p.unit,
    p.url,
    p.current_price                         AS price,
    p.current_currency                      AS currency,
    p.current_in_stock                      AS in_stock,
    p.price_updated_at                      AS price_date,
    (p.price_updated_at AT TIME ZONE 'America/Bogota')::date AS price_fecha,
    (p.price_updated_at AT TIME ZONE 'America/Bogota')::time AS price_hora
FROM products p
JOIN providers pr ON pr.id = p.provider_id
WHERE p.is_active;
