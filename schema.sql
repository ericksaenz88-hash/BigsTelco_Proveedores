-- ============================================================
-- Esquema PostgreSQL: Precios de proveedores (seguridad electrónica,
-- telecomunicaciones y cableado estructurado en Colombia)
-- ============================================================

CREATE TABLE IF NOT EXISTS providers (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(50)  UNIQUE NOT NULL,   -- ej: 'satstore', 'gvs', 'syscom'
    name            VARCHAR(150) NOT NULL,
    base_url        VARCHAR(300) NOT NULL,
    sector          VARCHAR(100),                   -- 'seguridad_electronica', 'cableado', 'telecomunicaciones'
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    requires_js     BOOLEAN NOT NULL DEFAULT FALSE, -- true si necesita navegador headless
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    id                  SERIAL PRIMARY KEY,
    provider_id         INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    sku                 VARCHAR(150) NOT NULL,           -- referencia/SKU del proveedor
    name                VARCHAR(500) NOT NULL,
    category            VARCHAR(200),
    brand               VARCHAR(150),
    url                 TEXT,
    image_url           TEXT,
    unit                VARCHAR(50),                     -- 'unidad', 'rollo 305m', 'metro', etc.
    -- Precio actual: se SOBRESCRIBE en cada corrida (no se acumula), para
    -- que consultar "¿cuánto vale esto hoy?" sea leer una sola columna,
    -- sin tener que buscar en price_history. El historial de cambios
    -- reales de precio sigue existiendo aparte, en price_history.
    current_price       NUMERIC(14,2),
    current_currency    VARCHAR(10) NOT NULL DEFAULT 'COP',
    current_in_stock    BOOLEAN,
    price_updated_at    TIMESTAMPTZ,                     -- última vez que el precio actual cambió de verdad
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,   -- false si dejó de aparecer en el sitio
    UNIQUE (provider_id, sku)
);

CREATE INDEX IF NOT EXISTS idx_products_provider ON products(provider_id);
CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING gin (name gin_trgm_ops);
-- Nota: idx_products_name_trgm requiere la extensión pg_trgm.
-- Si no la tienes disponible, comenta esa línea o ejecuta antes:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS price_history (
    id              BIGSERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price           NUMERIC(14,2),
    currency        VARCHAR(10) NOT NULL DEFAULT 'COP',
    in_stock        BOOLEAN,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id);
CREATE INDEX IF NOT EXISTS idx_price_history_scraped_at ON price_history(scraped_at);

-- Vista con el precio actual de cada producto (para cotizar rápido).
-- Ahora lee directo de products.current_price (se sobrescribe cada
-- corrida), no de price_history -- más simple y más rápido que antes.
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

-- Registro de cada corrida del script (para monitorear que la actualización diaria funcione)
CREATE TABLE IF NOT EXISTS scrape_runs (
    id              SERIAL PRIMARY KEY,
    provider_id     INTEGER REFERENCES providers(id) ON DELETE SET NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL DEFAULT 'running', -- running | success | error
    products_found  INTEGER DEFAULT 0,
    error_message   TEXT
);
