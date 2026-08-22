-- ============================================================
-- Migración 003: corrige falsos positivos de la migración 002
-- ============================================================
-- La migración 002 detectaba "metros" también con solo un número seguido
-- de "m" (ej. "100m"), sin exigir la palabra completa "Mt"/"metros". Eso
-- generó falsos positivos graves en productos que NO son cable: cámaras
-- con specs como "IR 20M" (alcance del infrarrojo) o "5M-N" (una
-- resolución de grabación) quedaron marcadas como "rollo 20m"/"rollo 5m",
-- lo cual es incorrecto.
--
-- Esta migración:
--   1. Deshace (vuelve a NULL) cualquier unit tipo "rollo Xm" cuyo
--      producto NO tenga la palabra completa "Mt"/"Mts"/"metros" en el
--      nombre (es decir, los que solo cayeron por el patrón suelto y
--      ahora sabemos que son falsos positivos).
--   2. No toca nada más (caja x50, bobina, kit, etc. no tenían este
--      problema).
--
-- Uso:
--   psql -h HOST -p PUERTO -U USUARIO -d BASE -f migrations/003_corregir_unit_falsos_positivos.sql
--
-- Es seguro correrla más de una vez.
-- ============================================================

UPDATE products
SET unit = NULL
WHERE unit ~ '^rollo \d+(\.\d+)?m$'
  AND name !~ '\d+(?:[.,]\d+)?\s*(?:[Mm][Tt][Ss]?|[Mm]etros)\b';

-- Verificación rápida (informativa, no cambia nada): cuenta cuántos
-- productos quedaron con unit tipo "rollo" después de la limpieza.
SELECT COUNT(*) AS productos_con_unit_rollo
FROM products
WHERE unit ~ '^rollo';
