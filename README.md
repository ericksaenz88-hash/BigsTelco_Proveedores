# Cotizador de precios — proveedores Colombia (seguridad electrónica, telecom y cableado)

Sistema en Python que consulta catálogos de proveedores colombianos
(seguridad electrónica, telecomunicaciones, cableado estructurado y
material de montaje), guarda los precios en PostgreSQL con historial
diario, y **crece solo**: agregar un proveedor nuevo es escribir su
dominio en un archivo de texto, no programar nada. Se actualiza
automáticamente cada día — en la nube (GitHub Actions) y/o en tu PC cada
vez que inicias sesión en Windows.

## Qué incluye

```
proveedores-colombia-bot/
├── config/
│   ├── providers.yaml            # matriz curada a mano (investigaciones profundas: GVS, SYSCOM, SAT Store...)
│   ├── providers_auto.yaml        # matriz 100% auto-generada por discover.py — NO editar a mano
│   └── candidates.txt             # ← el ÚNICO archivo que hay que tocar para sumar un proveedor nuevo
├── schema.sql                    # esquema PostgreSQL (providers, products, price_history)
├── src/
│   ├── models.py                  # estructura común ScrapedProduct
│   ├── http_utils.py               # sesión HTTP compartida (User-Agent de navegador real)
│   ├── discover.py                 # DESCUBRIMIENTO AUTOMÁTICO: prueba candidates.txt y se auto-registra
│   ├── scraper.py                  # dispatcher: enruta cada proveedor a su adaptador
│   ├── adapters/
│   │   ├── css_scraper.py           # motor genérico por selectores CSS (sitios pequeños/medianos)
│   │   ├── shopify.py                # motor genérico: cualquier tienda Shopify
│   │   ├── woocommerce.py            # motor genérico: cualquier WordPress+WooCommerce
│   │   ├── gvs_api.py                # adaptador a medida: API interna de GVS Colombia
│   │   └── syscom_algolia.py         # adaptador a medida: API pública (Algolia) de SYSCOM
│   ├── db.py                       # capa de acceso a PostgreSQL (upserts)
│   └── main.py                     # orquestador (corre todos los proveedores activos)
├── scripts/
│   ├── install.ps1                 # instalador de un solo paso (Windows)
│   ├── setup_scheduled_task.ps1     # registra el arranque automático al iniciar sesión
│   └── run_daily.ps1                # lo que corre cada día: discover + main
├── logs/                          # un log por día de cada corrida automática (se crea solo)
├── .github/workflows/daily_update.yml   # cron diario en GitHub Actions (respaldo en la nube)
├── requirements.txt
└── .env.example
```

## Instalación en un solo paso (Windows) — arranque automático al iniciar sesión

```powershell
# Desde la carpeta raíz del proyecto, en PowerShell:
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # solo la primera vez, si hace falta
.\scripts\install.ps1
```

Esto instala Python (entorno virtual + dependencias) y registra una tarea
en el Programador de Tareas de Windows que corre **cada vez que inicias
sesión** (con margen de unos minutos para que cargue la red), y como
respaldo todos los días a las 8:00 a.m. por si ese día no cierras sesión.
Cada corrida:

1. **Descubre proveedores nuevos** automáticamente (`src/discover.py`, ver
   abajo) — sin que nadie tenga que escribir código.
2. **Actualiza los precios** de todos los proveedores activos en tu
   PostgreSQL (`src/main.py`).

Solo te falta un paso manual la primera vez: editar `.env` con los datos
reales de tu PostgreSQL, y correr `schema.sql` una vez en tu base de
datos (el instalador te lo recuerda al final). Desde ahí, todo corre
solo — no tienes que volver a ejecutar nada a mano.

No corre dos veces el mismo día aunque inicies sesión varias veces
(se controla solo). Los logs de cada corrida quedan en `logs/` con fecha,
por si algún día necesitas revisar qué pasó.

Esto es un respaldo local, no un reemplazo del cron en GitHub Actions
(sección 4 más abajo) — puedes tener los dos activos a la vez sin
problema: si un día tu PC está apagado, GitHub Actions corre igual en la
nube.

## Cómo se suma un proveedor nuevo, sin programar nada

Este es el cambio más importante del sistema: **agregar un proveedor ya
no requiere escribir código ni YAML a mano.**

```bash
echo "nombredeldominio.com" >> config/candidates.txt
python -m src.discover
```

`discover.py` prueba automáticamente si ese dominio es una tienda
**Shopify** o **WooCommerce** (las dos plataformas más comunes entre
proveedores colombianos de este sector), y si lo es:

- Confirma la **moneda real** antes de activarlo (para no repetir el
  problema de SYSCOM, donde no se pudo confirmar, o de Security Solution
  Shop, que resultó estar en USD).
- Se auto-registra en `config/providers_auto.yaml` — un archivo que el
  propio script genera y regenera, nunca hay que editarlo a mano.
- Queda disponible en la próxima corrida diaria, junto con todos los
  demás.

Si el dominio no es Shopify ni WooCommerce, `discover.py` lo reporta como
"sin clasificar" — esos sí necesitan una investigación puntual (como se
hizo con GVS, SYSCOM o SAT Store), pero siguen sin tener límite: se
pueden ir agregando uno por uno a `config/providers.yaml` a medida que se
resuelven, igual que ya se hizo con 21 proveedores.

Esta corrida automática de `discover.py` está incluida en el arranque
automático de Windows (arriba) y también corre en la actualización diaria
de GitHub Actions — así que la matriz **crece sola** con cualquier
dominio nuevo que agregues a `candidates.txt`, sin que nadie tenga que
tocar el código nunca más.

## La matriz no tiene tope — hoy son 24, mañana pueden ser 100

No es una lista cerrada. Cualquier proveedor colombiano nuevo que aparezca
en el mercado se agrega en segundos con el flujo de arriba. Mientras más
proveedores, mejor: más precios para comparar y ofertar al mejor costo.

**Estado actual: 37 proveedores en la matriz, 25 activos**
(34 en `providers.yaml`, curados a mano con investigación profunda —
22 activos + 12 investigados y descartados/pendientes con el motivo
documentado; más 3 nuevos en `providers_auto.yaml`, encontrados y
activados 100% automático por `discover.py`, sin intervención manual).

**Activos** (traen productos reales hoy):

| Proveedor | Sector | Adaptador | Moneda |
|---|---|---|---|
| GVS Colombia | Seguridad electrónica, cableado, redes | `gvs_api` | COP |
| SYSCOM Colombia | Seguridad, cableado, radiocomunicación | `syscom_algolia` | ⚠️ sin confirmar |
| SAT Store | Seguridad electrónica, cableado | `css` | COP |
| IZC Mayorista | Cableado y redes | `css` | COP |
| MARWA (tiendamarwa.com.co) | Cableado, redes, energía | `woocommerce` | COP |
| Security Solution Shop | Seguridad electrónica, redes | `shopify` | **USD** |
| Energitel Telco | Fibra óptica, FTTx | `woocommerce` | COP |
| GSP | Seguridad electrónica (Hikvision) | `woocommerce` | COP |
| Equiredes | Seguridad electrónica (Hikvision) | `woocommerce` | COP |
| AS Security | Seguridad electrónica (Hikvision) | `shopify` | COP (no confirmada al 100%, ver notas) |
| Quality and Price | Radiocomunicación (Motorola/Kenwood) | `shopify` | COP |
| Grupo Control | Control de acceso, biometría | `shopify` | COP |
| Energi Tienda UPS | Energía, UPS, baterías | `woocommerce` | COP |
| Fireline Shop | Detección de incendios | `shopify` | COP |
| SH Ingeniería | Detección de incendios, seguridad | `woocommerce` | COP |
| Domocol | Domótica, automatización, energía | `woocommerce` | COP |
| CRC Comunicaciones | Radiocomunicación | `woocommerce` | COP |
| Sumitelco | Domótica/IoT (sensores relevantes a seguridad) | `shopify` | COP |
| **Global Matik** *(auto)* | Control de acceso vehicular | `woocommerce` | COP |
| **Tecnología Mayorista** *(auto)* | Tecnología en general — revisar relevancia | `shopify` | COP |
| **Soelco** *(auto)* | UPS, baterías | `woocommerce` | COP |
| VTA (vta.co) | Seguridad electrónica, cableado, redes | `vtex` | COP (no confirmada al 100%, ver notas) |
| Steren Colombia | Videoporteros, intercomunicadores, electrónica | `css` | COP |
| Servisistemas | Cableado estructurado, data center | `css` | COP |
| Bioentrada | Control de acceso, biometría, detección de metales | `wix_stores` | COP |

Los tres marcados *(auto)* llegaron por `discover.py`, sin que nadie
investigara el sitio a mano — solo estaban en `candidates.txt`. VTA,
Steren, Servisistemas y Bioentrada son los cuatro nuevos de la ronda de
investigación de los 13 "sin clasificar" (ver abajo).

**3 pendientes** (investigados a fondo, sin activar todavía — motivo real de
cada uno documentado en `config/providers.yaml`):

- **Mayorista Tecnológico (Maitek)** — oculta TODOS los precios sin iniciar
  sesión (dice "[Más Información]" en vez de precio). No es un problema de
  scraping: el proveedor exige cuenta B2B para ver precios. Si ustedes ya
  tienen cuenta ahí, avísame y vemos cómo automatizar el login.
- **Novelec** — confirmé que corre sobre SAP Commerce Cloud (Hybris), que
  sí tiene una API REST pública, pero no encontré el identificador exacto
  del catálogo ("base site") desde el HTML público. Se resuelve abriendo
  el sitio con las herramientas de red del navegador (F12 → pestaña
  Network) mientras se carga una categoría, y copiando la URL de la
  llamada a `/occ/v2/...` que aparezca ahí.
- **Redatel** — su sitio institucional no tiene catálogo propio con
  precios (solo vitrina). Al investigarlo encontré que enlaza a
  **sumitelco.com**, que sí es una tienda real y sí quedó activada — pero
  es domótica/IoT, no el catálogo de cámaras que uno esperaría de Redatel.
  Para el catálogo real de Redatel tocaría contactarlos directamente.

**Resultado de investigar los 13 candidatos "sin clasificar"** (los que
`discover.py` no pudo clasificar solo por no ser Shopify/WooCommerce):

- ✅ **4 activados** — VTA (VTEX, adaptador nuevo `src/adapters/vtex.py`),
  Steren Colombia (Magento, mismo patrón que SAT Store/IZC), Servisistemas
  (PrestaShop, moneda COP confirmada explícitamente por el propio sitio) y
  Bioentrada (**Wix Stores**, con un adaptador genérico nuevo construido
  específicamente para esto — ver sección "Wix Stores" más abajo). Los
  cuatro traen precios reales y ya están en la tabla de arriba.
- ❌ **3 sin precios públicos** (modelo "solo cotización", falso positivo
  de WooCommerce por el theme, no el plugin real): Colombia GPS,
  Rastreadores GPS Colombia, ZKTeco Colombia.
- ❌ **1 con login obligatorio**: MercaElectronico (PrestaShop, exige
  iniciar sesión para ver precios — el dominio correcto es
  `mercaelectronico.com`, sin el subdominio "tienda." que traía la lista
  original).
- ❌ **1 dominio muerto**: VZ Latam (no resuelve por DNS).
- ❌ **1 en Wix sin tienda real**: Fichet Colombia — es Wix, pero no tiene
  Wix Stores instalado (solo página institucional, sin
  store-products-sitemap.xml). El adaptador nuevo lo detectaría solo si
  algún día activan una tienda.
- ⏸️ **3 en WordPress sin WooCommerce activo, sin precios visibles en la
  home** (necesitan revisión manual de páginas de producto para confirmar
  si de verdad no hay catálogo público): Ecom Shops, Telavip, Battery
  Power.

### Nuevo: adaptador genérico para Wix Stores

Muchos proveedores pequeños/medianos usan Wix, no solo Bioentrada — así
que en vez de resolver un caso puntual, construí un adaptador genérico
(`src/adapters/wix_stores.py`) que sirve para **cualquier** tienda Wix
Stores futura, sin escribir código nuevo. Wix no tiene un endpoint público
simple como `/products.json` de Shopify, pero sí genera dos cosas
públicas automáticamente para SEO que sirven igual de bien:

1. Un sitemap de productos (`/store-products-sitemap.xml`) que enumera
   todas las URLs de producto — esto también sirve para *detectar* si un
   sitio Wix tiene tienda real (si no aparece, no hay Wix Stores
   instalado, como pasó con Fichet Colombia).
2. Cada página de producto trae, en el HTML que sirve el servidor (sin
   necesidad de JavaScript ni login), un bloque de datos con SKU, nombre,
   precio, **moneda explícita**, inventario y marca.

`discover.py` ya lo usa automáticamente: si agregas un dominio Wix nuevo
a `candidates.txt` y corres `python -m src.discover`, lo detecta, confirma
la moneda con un producto de muestra, y lo activa solo — igual que
Shopify/WooCommerce. Es más lento que los demás adaptadores (una petición
HTTP por producto en vez de una API paginada), así que en catálogos
grandes (Bioentrada tiene 856 productos) puede tardar varios minutos.

El detalle de cada uno (por qué se descartó, qué se probó) queda
documentado en `config/providers.yaml`, sección "CANDIDATOS DESCARTADOS".

Nota: es la cantidad de **fuentes** en la matriz, no de marcas — muchos de
estos proveedores venden las mismas marcas (Hikvision, Dahua, etc.) a
precios distintos, que es justo lo que sirve para comparar y ofertar al
mejor precio.

## 0. Cómo quedaron GVS y SYSCOM (los proveedores grandes)

Ambos parecían requerir un navegador porque cargan el catálogo con
JavaScript. En vez de eso, investigué el tráfico de red que hacen sus
propios sitios y encontré que los dos tienen una API pública (visible desde
cualquier navegador, sin necesitar cuenta) que consumen directamente:

- **GVS Colombia**: tiene una API REST propia. El sitio genera un token de
  "invitado" (JWT) con una llave que viene en su JavaScript público, y con
  eso consulta `/listaDeProductos`. El adaptador (`src/adapters/gvs_api.py`)
  reproduce exactamente eso: pide primero todas las líneas de producto
  (`/lineasv2`, 26 detectadas al día de hoy) y luego pagina cada una. Si GVS
  agrega una categoría nueva, este adaptador la recoge solo, sin editar nada.
  **Precio, stock y marca vienen confirmados y confiables.**

- **SYSCOM Colombia**: usa Algolia (un buscador SaaS) para mostrar su
  catálogo, con una llave de "solo búsqueda" pública en su JavaScript. El
  adaptador (`src/adapters/syscom_algolia.py`) descubre las categorías de
  primer nivel automáticamente (10 detectadas) y pagina cada una.
  **SKU, nombre, marca y existencias vienen confirmados y confiables.**

### ⚠️ SYSCOM: moneda del precio sin confirmar — léelo antes de cotizar

No pude confirmar con certeza si el campo de precio que devuelve la API de
SYSCOM (`precio_calculo` / `precio_1`) está en pesos colombianos o en
dólares. El sitio tiene un selector de moneda (US$ / CO$) y el precio final
que le muestra al usuario se arma con JavaScript de una forma que no logré
reproducir por fuera del navegador sin iniciar sesión con una cuenta real
de distribuidor.

**Antes de usar precios de SYSCOM en una cotización real**, por favor:
1. Entra a syscomcolombia.com con tu cuenta de distribuidor.
2. Busca un SKU cualquiera que ya hayamos importado (ej. `DS1LN6UG`) y
   compara el precio que ves ahí contra el que quedó guardado en
   `price_history` para ese producto.
3. Avísame el resultado — si hay que multiplicar por la TRM o aplicar un
   factor, lo ajusto en `src/adapters/syscom_algolia.py` (una sola línea).

Mientras tanto, los precios de SYSCOM en la base de datos deben tratarse
como referencia, no como precio final de venta. El resto de sus datos
(SKU, nombre, marca, existencias) sí son confiables.

Si alguno de estos dos sitios cambia su API interna en el futuro y el
adaptador deja de traer datos, el mensaje de error lo va a decir
explícitamente (no falla en silencio); en ese caso hay que repetir el
mismo proceso de investigación (ver la sección "Añadir un proveedor grande
con su propia API" en `config/providers.yaml`).

## 1. Preparar la base de datos

Conéctate a tu PostgreSQL existente y ejecuta:

```bash
psql -h TU_HOST -U TU_USUARIO -d TU_BASE -f schema.sql
```

Esto crea las tablas `providers`, `products`, `price_history`, `scrape_runs`
y la vista `current_prices` (el último precio conocido de cada producto,
lista para usarse directamente en tus cotizaciones).

Si tu PostgreSQL no tiene la extensión `pg_trgm` disponible, comenta la
línea del índice `idx_products_name_trgm` en `schema.sql` (no es crítica,
solo acelera búsquedas de texto por nombre de producto).

## 2. Configurar credenciales

```bash
cp .env.example .env
# edita .env con host, usuario, password y base de datos reales
```

## 3. Instalar y probar localmente

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Prueba sin escribir en la base de datos:
python -m src.main --provider satstore --dry-run

# Corrida real (escribe en PostgreSQL):
python -m src.main --provider satstore
```

Si todo funciona, corre todos los proveedores activos:

```bash
python -m src.main
```

## 4. Automatizar la actualización diaria (GitHub Actions)

1. Sube este proyecto a un repositorio de GitHub (puede ser privado).
2. En el repo: **Settings → Secrets and variables → Actions → New repository secret**,
   crea: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`.
3. El workflow `.github/workflows/daily_update.yml` ya está listo y corre
   todos los días a las 9:00 a.m. hora Colombia. Puedes cambiar la hora
   editando la línea `cron`.
4. También puedes dispararlo manualmente desde la pestaña **Actions** del
   repo (botón "Run workflow").

**Importante:** para que GitHub Actions pueda conectarse, tu PostgreSQL
debe ser alcanzable desde internet (un servidor cloud, RDS, Supabase, etc.
con el puerto abierto y, idealmente, restringido por IP o con SSL). Si tu
PostgreSQL está detrás de un firewall corporativo sin acceso externo,
avísame y ajustamos el runner (por ejemplo, con un self-hosted runner
dentro de tu red, o un túnel).

## 5. Consultar precios para armar una cotización

```sql
SELECT provider_name, product_name, brand, unit, price, price_date
FROM current_prices
WHERE product_name ILIKE '%cable utp cat6%'
ORDER BY price ASC;
```

La vista `current_prices` siempre muestra el precio más reciente conocido
de cada producto, por proveedor.

## 6. Cómo funciona el scraping (arquitectura de adaptadores)

`src/scraper.py` es un dispatcher: lee el campo `adapter` de cada proveedor
en `config/providers.yaml` y lo enruta al adaptador correspondiente
(`src/adapters/`). Hay tres hoy:

- **`css`** — motor genérico por selectores CSS, para sitios que
  renderizan el catálogo en el servidor (ej. SAT Store, IZC).
- **`shopify`** — **genérico y reutilizable**: cualquier tienda Shopify
  expone `/products.json` públicamente. Basta con poner `base_url` y la
  `currency` correcta (ver más abajo por qué esto no se puede asumir).
  Ya lo usan 5 proveedores de la matriz sin escribir código nuevo.
- **`woocommerce`** — **genérico y reutilizable**: cualquier WordPress +
  WooCommerce expone su Store API pública en `/wp-json/wc/store/v1/products`,
  con moneda explícita en cada respuesta (el más confiable de los tres).
  Ya lo usan 7 proveedores de la matriz sin escribir código nuevo.
- **`gvs_api`** — adaptador a medida para la API interna de GVS Colombia.
- **`syscom_algolia`** — adaptador a medida para la API pública (Algolia)
  de SYSCOM Colombia.

**Dato clave para seguir creciendo la matriz:** la mayoría de tiendas
colombianas de este sector corren sobre Shopify o WooCommerce. Antes de
mapear selectores CSS a mano para un proveedor nuevo, prueba primero:

```bash
curl https://SU_DOMINIO/products.json?limit=1                      # ¿es Shopify?
curl https://SU_DOMINIO/wp-json/wc/store/v1/products?per_page=1    # ¿es WooCommerce?
```

Si alguno responde con JSON de productos, actívalo con el adaptador
genérico correspondiente — literalmente sin escribir código, solo un
bloque en `config/providers.yaml`.

### ⚠️ Nunca asumas que un proveedor cotiza en COP

Al menos dos proveedores de esta matriz (SYSCOM y Security Solution Shop)
NO manejan pesos colombianos por defecto — SSS confirmado en **USD**, y
SYSCOM sin poder confirmarse con certeza (ver sección de arriba). Antes de
activar `active: true` en un proveedor nuevo, verifica su moneda real:

- **Shopify:** `curl -s https://SU_DOMINIO | grep -o 'Shopify.currency[^;]*'`
- **WooCommerce:** el propio JSON de `/wp-json/wc/store/v1/products` trae
  `prices.currency_code` explícito — revísalo, no lo des por sentado.
- **APIs a medida (como GVS):** revisa si el sitio muestra explícitamente
  "COP" o "$" junto al precio, o compara contra un producto que conozcas.

Ambos proveedores grandes (GVS y SYSCOM) parecían necesitar un navegador
porque cargan el catálogo con JavaScript, pero investigando el tráfico de
red de sus propios sitios encontré que los dos exponen una API pública
consumible directamente con `requests` — sin necesidad de Playwright ni
navegador headless (ver sección 0 arriba para el detalle completo).

## 7. Añadir un proveedor nuevo a la matriz (sin límite de cantidad)

**Paso 0, siempre primero — probar los adaptadores genéricos:**

```bash
curl https://SU_DOMINIO/products.json?limit=1                      # ¿es Shopify?
curl https://SU_DOMINIO/wp-json/wc/store/v1/products?per_page=1    # ¿es WooCommerce?
```

Si alguno responde JSON con productos, listo: agrega un bloque en
`config/providers.yaml` con `adapter: shopify` o `adapter: woocommerce`,
`base_url`, y (si es Shopify) la moneda confirmada — sin escribir código.
Este fue el caso de 12 de los 18 proveedores activos de hoy.

**Si no es ninguno de los dos, sitio pequeño/mediano con catálogo en el servidor:**
1. Verifica que el sitio muestre precios sin necesitar login ni JavaScript
   (abre la página con JavaScript deshabilitado, o revisa el "Ver código
   fuente" del navegador — si ves los precios ahí, es candidato fácil).
2. Copia un bloque `adapter: css` en `config/providers.yaml` y ajusta
   `base_url`, `categories` (URLs de listado) y `selectors` (CSS de
   tarjeta de producto, nombre, precio, y paginación).
3. Prueba: `python -m src.main --provider tu_codigo --dry-run`
4. Cuando funcione, cambia `active: true`.

**Si es un proveedor grande con su propia API/JS (como GVS o SYSCOM):**
1. Abre la pestaña "Network" del navegador (F12) mientras navegas el
   catálogo del sitio, y busca la llamada que trae los productos.
2. Si es una API JSON pública (aunque no esté documentada — muchos sitios
   exponen una "search-only key" o token de invitado pensados para
   usarse desde el navegador del cliente), reprodúcela con `requests` en
   un archivo nuevo `src/adapters/tu_proveedor.py` con una función
   `fetch(provider_cfg) -> list[ScrapedProduct]`.
3. Regístrala en `src/adapters/__init__.py` (diccionario `ADAPTERS`).
4. Agrega el bloque en `config/providers.yaml` con `adapter: tu_proveedor`.
5. Si de verdad no hay ninguna API accesible (poco común, pero pasa),
   ahí sí hace falta Playwright/navegador headless — avísame y lo agrego.

**Lección aprendida (aplica a cualquier proveedor nuevo que dé timeout o
conexión rechazada):** algunos sitios bloquean el User-Agent por defecto
de la librería `requests` ("python-requests/x.x"), aunque la misma
petición funcione perfecto desde un navegador. Todos los adaptadores usan
`src/http_utils.new_session()`, que ya manda un User-Agent de navegador
real — si escribes un adaptador nuevo, usa esa misma función en vez de
`requests.Session()` a secas.

**Candidatos que quedaron identificados pero sin investigar todavía**
(quedan como ideas para la próxima ronda): Novelec (falta el "base site" de
su API SAP Commerce Cloud), Redatel (contactar directamente), Hikvision
Colombia, Dahua distribuidores locales, VZ Latam, Steren Colombia,
Tecnología Mayorista, Batterypower, Soelco, Bioentrada, Servisistemas.

## 8. Aspectos legales y buenas prácticas — léelo antes de escalar esto

- El script usa un `User-Agent` identificable, espera unos segundos entre
  peticiones (`rate_limit_seconds`) y solo lee páginas públicas de listado
  de productos — no evade logins, CAPTCHAs ni medidas antibot.
- Antes de monitorear un proveedor nuevo de forma automática y diaria,
  revisa su archivo `robots.txt` y sus Términos de Uso. Algunos catálogos
  B2B consideran el scraping automatizado una violación de sus condiciones,
  incluso si el requests es técnicamente posible.
- Para proveedores con los que ya tienen relación comercial, lo más robusto
  y menos frágil a largo plazo suele ser pedirles directamente una lista
  de precios (Excel/CSV) o acceso a su API/portal B2B — un scraper siempre
  se puede romper cuando el proveedor cambia el diseño de su sitio.
- Este script no ejecuta compras ni modifica nada en los sitios de los
  proveedores: solo lee catálogos públicos.

## 9. Próximos pasos sugeridos

- [ ] **Confirmar la moneda real de los precios de SYSCOM** (ver sección 0) —
      es lo más importante antes de cotizar con esos datos.
- [ ] Confirmar selectores/API para los candidatos pendientes (IZC, MARWA,
      Redatel, Mayorista Tecnológico, Novelec, Security Solution Shop).
- [ ] Alertas automáticas cuando un producto sube/baja de precio más de X%.
- [ ] Endpoint o vista simple para generar cotizaciones directamente desde `current_prices`.
