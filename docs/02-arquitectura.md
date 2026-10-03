# 02 — Arquitectura

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Versión | 1.0 |
| Fecha | 2026-09-16 |
| Depende de | `00-vision-y-alcance.md`, `01-dominio.md` |
| Documentos relacionados | `03-modelo-de-datos.md`, `adr/` |

## 1. Propósito

Define cómo se construye el sistema: componentes, stack, estructura del código, pipeline de comandos, transacciones, sincronización, seguridad, pruebas y despliegue. Las reglas de negocio están en `01-dominio.md` y se citan por identificador; este documento no las redefine.

Cuando este documento dice **DEBE**, es obligatorio. **CONVIENE** indica la opción preferida, que puede cambiarse con justificación registrada en un ADR.

## 2. Vista general

```
┌──────────────────────────── Navegador ────────────────────────────┐
│  PWA React + TypeScript (una sola aplicación)                     │
│                                                                   │
│  /ruta/*  (teléfono, offline)        /admin/*  (PC, online)       │
│  ├─ Dexie (IndexedDB)                ├─ TanStack Query            │
│  ├─ Motor de cálculo TS              └─ Formularios y reportes    │
│  ├─ Cola de comandos                                              │
│  └─ Motor de sincronización                                       │
│  Service worker: solo shell de la aplicación                      │
└───────────────────────────────┬───────────────────────────────────┘
                                │ HTTPS (JSON)
┌───────────────────────────────▼───────────────────────────────────┐
│  Caddy: TLS, archivos estáticos del front, proxy /api             │
└───────────────────────────────┬───────────────────────────────────┘
┌───────────────────────────────▼───────────────────────────────────┐
│  Backend FastAPI (monolito modular)                               │
│  API REST ─► Bus de comandos ─► Handlers ─► Dominio puro          │
│                    │                                              │
│                    └─► Idempotencia, permisos, transacción, audit │
└───────────────────────────────┬───────────────────────────────────┘
┌───────────────────────────────▼───────────────────────────────────┐
│  PostgreSQL (fuente única de verdad)  ──►  Backups verificados    │
└───────────────────────────────────────────────────────────────────┘
```

Principios de arquitectura:

- **Un solo backend desplegable** con módulos internos de límites explícitos. No hay microservicios (ver `00` §8).
- **Una sola aplicación front** con dos áreas. El área de ruta funciona sin conexión; el área de administración requiere conexión.
- **Toda escritura de negocio pasa por el bus de comandos**, venga de un formulario online o de la cola offline (ADR-012).
- **El servidor es la autoridad.** El cliente calcula solo lo necesario para operar sin señal y el servidor valida todo (TR-10).

## 3. Stack

Las versiones se fijan al iniciar el proyecto en `backend/requirements.txt`, `backend/requirements-dev.txt`, `frontend/package-lock.json` y las imágenes de Docker. Se usa la última versión estable de cada herramienta en ese momento.

- **DEBE:** `requirements.txt` contiene todas las dependencias de producción, incluidas las transitivas, con versión exacta (`==`). Se genera con `pip freeze` desde un entorno virtual limpio que solo tiene las dependencias de producción.
- **DEBE:** `requirements-dev.txt` empieza con `-r requirements.txt` y agrega las herramientas de desarrollo y pruebas, también con versión exacta.
- **DEBE:** `package-lock.json` se versiona en el repositorio. En desarrollo se usa `npm install`; en CI y Docker, `npm ci`, que instala exactamente lo que dice el lock y falla si no coincide con `package.json`.

### 3.1 Backend

| Uso | Herramienta | Notas |
| --- | --- | --- |
| Lenguaje | Python 3.12 o superior | Tipado estricto |
| Framework HTTP | FastAPI | Endpoints síncronos (`def`) |
| Validación y serialización | Pydantic v2 | Decimales serializados como string |
| Acceso a datos | SQLAlchemy 2.x, estilo 2.0, **modo síncrono** | Ver §3.4 |
| Driver | psycopg 3 | |
| Migraciones | Alembic | Única vía para cambiar el esquema |
| Hash de contraseñas | Argon2id | |
| Cuerpo `multipart/form-data` | python-multipart | Recepción de planillas en la importación (ADR-041) |
| Gestión de dependencias | pip con `requirements.txt` y `requirements-dev.txt` | Configuración de herramientas (Ruff, mypy, pytest) en `pyproject.toml` |
| Calidad | Ruff (lint y formato), mypy o pyright, import-linter | import-linter valida límites entre módulos |
| Pruebas | pytest, Testcontainers, Hypothesis | Ver §15 |

### 3.2 Frontend

| Uso | Herramienta | Notas |
| --- | --- | --- |
| Lenguaje | TypeScript en modo `strict` | |
| Build | Vite | |
| UI | React, Tailwind CSS | |
| Ruteo | React Router | Áreas `/ruta` y `/admin` con carga diferida |
| Estado remoto | TanStack Query | Solo área de administración |
| Base local | Dexie (IndexedDB) | Solo área de ruta |
| Formularios | React Hook Form + Zod | |
| Dinero | decimal.js | Configurado en un único módulo |
| Cliente API | Tipos generados con openapi-typescript desde el OpenAPI del backend | |
| PWA | vite-plugin-pwa (Workbox) | |
| Nota de venta | pdfmake | Generación en el dispositivo |
| Gestión de dependencias | npm con `package-lock.json` | `npm ci` en CI y Docker |
| Calidad | ESLint, typecheck en CI | |
| Pruebas | Vitest, Playwright | |

### 3.3 Infraestructura

| Uso | Herramienta |
| --- | --- |
| Base de datos | PostgreSQL 17 o superior |
| Contenedores | Docker, Docker Compose |
| Proxy y TLS | Caddy |
| CI | GitHub Actions |
| Backups | `pg_dump` programado con retención y copia fuera del servidor |

### 3.4 Decisiones de stack que requieren justificación

- **SQLAlchemy síncrono.** El sistema es transaccional, con bloqueos de fila y lógica secuencial. El modo síncrono evita errores de carga diferida en contexto asíncrono y simplifica las transacciones. FastAPI ejecuta los endpoints `def` en un pool de hilos, suficiente para el volumen esperado. Cambiar a asíncrono no requiere tocar el dominio.
- **Monolito modular.** Un desarrollador, un solo cliente inicial y transacciones que cruzan módulos (una venta toca stock, costos, cuenta corriente y cobranzas) hacen que separar servicios sea costo sin beneficio.
- **Sin cola de mensajes ni caché distribuida en la etapa 1.** PostgreSQL resuelve la persistencia, los bloqueos y las tareas programadas simples.

## 4. Estructura del repositorio

Monorepo:

```
/
├── CLAUDE.md
├── README.md
├── docker-compose.yml
├── docker-compose.prod.yml
├── .github/workflows/
├── docs/                      # fuente de verdad (00–04, adr/, referencia/)
├── openspec/                  # specs y changes
├── shared/
│   └── fixtures/
│       └── calculo/           # casos compartidos entre pytest y Vitest (§10.4)
├── backend/
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pyproject.toml         # configuración de herramientas, no dependencias
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/              # config, db, seguridad, errores, logging, dinero, reloj, ids
│   │   ├── commands/          # bus, sobre, registro de handlers, idempotencia
│   │   └── modules/
│   │       ├── identidad/
│   │       ├── configuracion/
│   │       ├── catalogo/
│   │       ├── proveedores/
│   │       ├── costeo/
│   │       ├── precios/
│   │       ├── stock/
│   │       ├── clientes/
│   │       ├── descuentos/
│   │       ├── ventas/
│   │       ├── cuentas_corrientes/
│   │       ├── cobranzas/
│   │       ├── sync/
│   │       ├── auditoria/
│   │       ├── reportes/
│   │       └── facturacion/   # etapa de facturación
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── concurrency/
│       ├── properties/
│       └── fixtures_compartidos/
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── src/
│   │   ├── app/               # ruteo, layouts, providers
│   │   ├── areas/
│   │   │   ├── ruta/
│   │   │   └── admin/
│   │   ├── features/          # por módulo de negocio
│   │   ├── domain/            # motor de cálculo TS (§10.4)
│   │   ├── sync/              # base local, cola, bootstrap, motor de sincronización
│   │   ├── lib/               # dinero, cliente API, fechas, ids
│   │   └── components/ui/
│   └── tests/
│       ├── unit/
│       └── e2e/
└── infra/
    ├── caddy/
    └── backup/
```

## 5. Backend: monolito modular

### 5.1 Módulos

| Módulo | Responsabilidad | Reglas |
| --- | --- | --- |
| identidad | Organización, configuración de la organización, usuarios, roles, permisos, dispositivos, autenticación, PIN | SEG |
| configuracion | Catálogos configurables: alícuotas de IVA, medios de pago, motivos | §4 de `01` |
| catalogo | Productos, presentaciones, categorías, marcas, alícuotas | CAT |
| proveedores | Proveedores, costos informados, compras, pagos | CST-01..05, CMP, PAG |
| costeo | Costo promedio y costo de venta | CST-10..15 |
| precios | Listas, versiones, márgenes, redondeo, resolución de precio | PRC |
| stock | Ubicaciones, saldos, movimientos, transferencias, ajustes, jornadas, rendición | STK, RUT |
| clientes | Clientes y evaluación de crédito | CLI, CRE |
| descuentos | Reglas y motor de descuentos | DSC |
| ventas | Venta, anulación, nota de venta | VTA |
| cuentas_corrientes | Libros de clientes y proveedores, saldos | CC |
| cobranzas | Cobranzas y medios | COB |
| sync | Bootstrap, lote de comandos, observaciones, cuarentena | SYN |
| auditoria | Registro de auditoría | AUD |
| reportes | Consultas de solo lectura | REP |
| facturacion | Facturas y efecto fiscal | FAC |
| importacion | Lectura de planillas (CSV y `.xlsx`), conversión exacta de valores, informe de errores por fila, comando `IMPORTACION_REGISTRAR`, historial de importaciones y un importador por tipo sobre los servicios de los demás módulos | IMP, TR-10 |

### 5.2 Capas dentro de cada módulo

```
modules/ventas/
├── api.py            # routers FastAPI: traducen HTTP ⇄ comandos y consultas
├── schemas.py        # modelos Pydantic de entrada y salida
├── commands.py       # handlers de comandos (casos de uso de escritura)
├── queries.py        # casos de uso de lectura
├── domain/           # lógica pura: cálculos, validaciones, decisiones
├── models.py         # modelos SQLAlchemy
├── repository.py     # acceso a datos del módulo
└── service.py        # interfaz pública para otros módulos
```

Reglas:

- **DEBE:** `domain/` no importa FastAPI, SQLAlchemy ni nada de infraestructura. Recibe datos y devuelve resultados o errores de dominio. Es lo que se prueba con Hypothesis.
- **DEBE:** un módulo usa a otro solo a través de su `service.py`. No importa sus modelos ni su repositorio.
- **DEBE:** los handlers no hacen `commit`. La transacción la abre y la cierra el bus (§6).
- **EXCEPCIÓN:** `reportes` puede leer tablas de cualquier módulo con SQL de solo lectura.
- **DEBE:** import-linter verifica en CI las dos reglas anteriores.

### 5.3 Dependencias permitidas entre módulos

```
ventas ──► precios, descuentos, clientes, stock, costeo, cuentas_corrientes, cobranzas, catalogo
proveedores ──► catalogo, stock, costeo, cuentas_corrientes, configuracion (compras y pagos de contado, solo por service.py, ADR-043)
cobranzas ──► cuentas_corrientes
clientes ──► cuentas_corrientes
precios ──► catalogo, proveedores (costos informados)
stock ──► catalogo, costeo
catalogo ──► costeo (solo lectura del costo promedio de un producto, ADR-036)
facturacion ──► ventas (lectura), cuentas_corrientes, costeo
sync ──► todos los módulos con comandos
importacion ──► catalogo, proveedores, clientes, stock, cuentas_corrientes, configuracion, identidad (solo por service.py; nadie depende de importacion, ADR-042)
auditoria, configuracion, identidad ◄── todos
cuentas_corrientes, costeo ──► (sin dependencias de negocio)
```

No se permiten ciclos. Si aparece la necesidad de uno, se resuelve moviendo la lógica al módulo que orquesta (normalmente `ventas`) o registrando un ADR.

## 6. Pipeline de comandos (ADR-012)

### 6.1 Puntos de entrada

| Entrada | Uso | Transacción |
| --- | --- | --- |
| Endpoints REST de escritura (`POST /api/v1/ventas`, etc.) | Formularios online | Una por comando |
| `POST /api/v1/sync/comandos` | Lote de la cola del dispositivo | Una por comando, en orden |

Ambos construyen un sobre y llaman al mismo bus. No existe una segunda implementación de ninguna operación.

### 6.2 Sobre del comando

| Campo | Origen | Descripción |
| --- | --- | --- |
| `operation_id` | Cliente | UUIDv7. En REST llega en el encabezado `Operation-Id`; en sync, en el cuerpo. Obligatorio en toda escritura. |
| `tipo` | Cliente | Por ejemplo `VENTA_CONFIRMAR`. |
| `version` | Cliente | Versión del esquema del contenido. |
| `modo` | Entrada | `ONLINE` en REST; `OFFLINE` solo en sync con jornada abierta. |
| `organizacion_id`, `usuario_id` | Token | Nunca del contenido. |
| `dispositivo_id` | Token | Vinculado al refresh token. |
| `jornada_id` | Cliente | Obligatorio en comandos de ruta. |
| `occurred_at` | Cliente | Momento en el dispositivo. |
| `secuencia` | Cliente | Correlativo de la cola del dispositivo. |
| `app_version` | Cliente | Versión de la aplicación que generó el comando. |
| `contenido` | Cliente | Datos del comando. |
| `huella` | Servidor | SHA-256 del contenido en JSON canónico (claves ordenadas, decimales como string). El servidor la calcula; no confía en la del cliente. |

### 6.3 Procesamiento

Dentro de una transacción:

1. **Dispositivo.** Si está revocado, el comando se guarda en cuarentena en una transacción aparte y se responde RECHAZADO (SYN-06).
2. **Reserva de idempotencia.** `INSERT INTO comando (organizacion_id, operation_id, tipo, huella, estado) VALUES (…, 'PROCESANDO') ON CONFLICT DO NOTHING`.
   - Si se insertó, continúa.
   - Si hubo conflicto, se lee el existente. Misma huella: se devuelve el resultado guardado. Distinta huella: RECHAZADO con código `COMANDO_INCONSISTENTE` (SYN-02).
   - Si otra transacción está procesando el mismo `operation_id`, PostgreSQL bloquea el `INSERT` hasta que esa transacción termine; no hace falta lógica adicional.
3. **Validación estructural** del contenido con el esquema Pydantic de su tipo y versión.
4. **Permisos.** En `ONLINE`, un permiso faltante rechaza. En `OFFLINE`, se valida contra los permisos vigentes al abrir la jornada y, si fueron revocados después, se acepta con observación (SYN-10).
5. **Handler.** Ejecuta la operación usando los servicios de los módulos. En `ONLINE`, una regla de negocio incumplida lanza un error de dominio. En `OFFLINE`, las reglas que no pueden rechazar (SYN-05) producen observaciones.
6. **Resultado.** Se actualiza el registro del comando con estado final, resultado y observaciones; se registra la auditoría.
7. **Commit.**

Si el handler falla en modo `ONLINE`, se revierte toda la transacción, incluida la reserva de idempotencia: el mismo `operation_id` puede reintentarse con el contenido corregido.

Errores transitorios de PostgreSQL (serialización `40001`, deadlock `40P01`) se reintentan hasta 3 veces con espera incremental. Agotados los reintentos, se responde error transitorio y el dispositivo reintenta más tarde sin cambiar el `operation_id`.

### 6.4 Lote de sincronización

- El dispositivo envía hasta 50 comandos por lote, ordenados por `secuencia`.
- El servidor los procesa en orden y responde un resultado por comando.
- Un resultado ACEPTADO, ACEPTADO_CON_OBSERVACIONES o RECHAZADO no detiene el lote.
- Un error transitorio detiene el lote en ese comando: los siguientes no se procesan, para preservar el orden (SYN-03).
- La cola pertenece al usuario que generó los comandos. Solo ese usuario, autenticado en ese dispositivo, puede sincronizarla.

### 6.5 Tipos de comando de la etapa 1

| Tipo | Online | Offline |
| --- | :-: | :-: |
| `JORNADA_ABRIR`, `JORNADA_RENDIR`, `JORNADA_CERRAR`, `JORNADA_LIBERAR` | ✓ | |
| `VENTA_CONFIRMAR` | ✓ | ✓ |
| `VENTA_ANULAR` | ✓ | ✓ (VTA-24) |
| `COBRANZA_REGISTRAR` | ✓ | ✓ |
| `COBRANZA_ANULAR` | ✓ | |
| `COMPRA_CONFIRMAR`, `COMPRA_ANULAR` | ✓ | |
| `PAGO_PROVEEDOR_REGISTRAR`, `PAGO_PROVEEDOR_ANULAR` | ✓ | |
| `STOCK_TRANSFERIR`, `STOCK_AJUSTAR`, `STOCK_INICIAL_REGISTRAR` | ✓ | |
| `COSTO_INFORMAR` | ✓ | |
| `LISTA_GENERAR_BORRADOR`, `LISTA_PUBLICAR`, `LISTA_ANULAR_VERSION` | ✓ | |
| `SALDO_INICIAL_REGISTRAR` | ✓ | |
| `OBSERVACION_RESOLVER` | ✓ | |
| `IMPORTACION_REGISTRAR` (permiso `IMPORTAR_DATOS`) | ✓ | |
| Altas y modificaciones de maestros (productos, clientes, proveedores, reglas, configuración) | ✓ | |

Las altas y modificaciones de maestros también llevan `operation_id` y pasan por el bus, aunque no generen movimientos.

Un handler puede devolver, además del resultado, observaciones de negocio (SYN-04, SYN-07): el comando queda `ACEPTADO_CON_OBSERVACIONES` y las observaciones se registran con la operación afectada. `COMPRA_ANULAR` lleva `devuelve_pago` (obligatorio en compras de contado, prohibido en las de crédito) y emite `ANULACION_COMPRA_SIN_RECALCULO` y `STOCK_NEGATIVO` (ADR-043, ADR-044). Las lecturas de compras exigen `REGISTRAR_COMPRA` o `ANULAR_COMPRA`; el formulario de compra también lee productos, alícuotas, proveedores y ubicaciones con `REGISTRAR_COMPRA` (ADR-043).

Una importación es un comando por archivo: todo o nada, con savepoints por fila dentro del handler (ADR-040).

### 6.6 Compatibilidad de versiones

- Un dispositivo puede tener comandos encolados generados por una versión anterior de la aplicación. **DEBE:** el servidor conserva los handlers de toda versión de comando que pueda estar en colas activas.
- El servidor publica la versión mínima de la aplicación. Una aplicación por debajo de la mínima puede sincronizar su cola pero no confirmar operaciones nuevas hasta actualizarse.
- Retirar una versión de comando requiere verificar que no queden comandos pendientes de esa versión.

## 7. Transacciones y concurrencia

### 7.1 Nivel de aislamiento

READ COMMITTED con bloqueos explícitos de fila. No se usa SERIALIZABLE por defecto.

### 7.2 Tablas de saldo

Además de los libros de movimientos, se mantienen tablas de saldo actualizadas en la misma transacción que cada movimiento. Son las filas que se bloquean.

| Tabla | Clave | Contenido |
| --- | --- | --- |
| `costo_producto` | organización, producto | Costo promedio y **stock total** del producto en la organización |
| `stock_saldo` | organización, producto, ubicación | Cantidad base |
| `saldo_cuenta` | organización, tipo (cliente/proveedor), entidad | Saldo |

Los libros son la verdad (INV-12, INV-13). Las tablas de saldo son una materialización verificable (§7.6).

`costo_producto.stock_total` se mantiene junto con cada movimiento de stock del producto. Así el recálculo del promedio (CST-11) usa un stock total consistente sin sumar movimientos bajo concurrencia.

### 7.3 Orden global de bloqueo

**DEBE:** toda transacción que bloquee varias filas lo hace en este orden, y dentro de cada nivel ordenando por clave:

1. `saldo_cuenta` (cliente o proveedor de la operación)
2. `costo_producto` (por `producto_id` ascendente)
3. `stock_saldo` (por `producto_id` y `ubicacion_id` ascendentes)
4. `jornada` (si la operación la valida)

Un orden único impide deadlocks entre operaciones concurrentes. Los handlers no bloquean filas directamente: usan funciones de los servicios que respetan este orden, y la venta reúne todos los productos antes de pedir bloqueos.

### 7.4 Stock

- Todo movimiento de un producto bloquea su fila de `costo_producto` y la de `stock_saldo`. Esto serializa las operaciones concurrentes por producto; con el volumen esperado no es un cuello de botella.
- **ONLINE:** `UPDATE stock_saldo SET cantidad = cantidad - :q WHERE … AND cantidad >= :q`. Si no afecta filas y el usuario no tiene `PERMITIR_STOCK_NEGATIVO`, se rechaza (STK-05).
- **OFFLINE:** se descuenta sin condición y, si el resultado es negativo, se agrega la observación STOCK_NEGATIVO (STK-06).
- Una ubicación con toma se valida contra la jornada abierta dentro de la misma transacción (STK-09).

### 7.5 Jornadas

Índice único parcial: una sola jornada no cerrada por ubicación (INV-16). El intento de abrir una segunda falla por la restricción, no por una verificación previa en código.

### 7.6 Verificación de consistencia

Una tarea diaria compara cada tabla de saldo con la suma de su libro. Cualquier diferencia se registra como error crítico en el log y se notifica al administrador. Nunca se corrige automáticamente: una diferencia indica un defecto que debe investigarse.

### 7.7 Numeración de notas de venta

- Cada dispositivo tiene un prefijo único asignado por el servidor al registrarse (SEG-02).
- El dispositivo lleva el correlativo local y lo incrementa al confirmar.
- El bootstrap devuelve el último correlativo registrado en el servidor para ese dispositivo; el dispositivo usa el mayor entre ese y el local. Esto evita repetir números si se borran los datos del navegador.
- Restricción única (organización, número). Una colisión en sync indica un defecto y se trata como error de consistencia.
- Los dispositivos de PC siguen el mismo mecanismo.

## 8. Aislamiento por organización

- **DEBE:** `organizacion_id` se toma del token y nunca del contenido de la petición.
- **DEBE:** todo repositorio recibe la organización como parámetro obligatorio y la incluye en cada consulta. No existen funciones de repositorio sin organización.
- **DEBE:** las claves foráneas entre entidades de negocio incluyen la organización (claves compuestas), de modo que la base impide referencias cruzadas entre organizaciones (detalle en `03`).
- **DEBE:** un recurso de otra organización responde 404 (SEG-07).
- **DEBE:** existe una prueba automatizada que recorre todos los endpoints con un usuario de otra organización y verifica que ninguno expone ni modifica datos ajenos (INV-21).
- Row Level Security de PostgreSQL se evalúa como defensa adicional en la etapa 4.

## 9. Identificadores y tiempo

- Las entidades usan UUIDv7 como clave primaria: son ordenables por tiempo, lo que mejora la localidad de los índices.
- Ventas, líneas, cobranzas, anulaciones y comandos generados en el dispositivo reciben su UUID en el dispositivo. El resto, en el servidor.
- En la etapa 1 no se crean clientes ni productos sin conexión.
- Los timestamps se almacenan como `timestamptz` (TR-04).
- `occurred_at` proviene del dispositivo y puede ser inexacto. El servidor guarda también `registered_at` y registra una advertencia si la diferencia es mayor que un umbral configurable hacia el futuro.
- El backend obtiene la hora de un componente de reloj inyectable, para poder fijarla en pruebas.

## 10. Dinero y cálculo compartido

### 10.1 Backend

- **DEBE:** tipo `Decimal` en todo el dominio; nunca `float`.
- **DEBE:** un único módulo `core/money.py` con las funciones de redondeo (`redondear_importe`, `redondear_costo`), configuradas con `ROUND_HALF_UP` de forma explícita. El contexto decimal por defecto de Python redondea al par y no debe usarse para cuantizar.
- Columnas `NUMERIC(14,2)` para importes, `NUMERIC(18,6)` para costos por unidad base, `NUMERIC(9,6)` para porcentajes y alícuotas.

### 10.2 API

- **DEBE:** los importes, costos y porcentajes viajan en JSON como string (`"31250.00"`).
- Las cantidades base viajan como entero.

### 10.3 Frontend

- **DEBE:** un único módulo `lib/money.ts` que configura decimal.js con `ROUND_HALF_UP` y expone las mismas funciones de redondeo que el backend.
- **DEBE:** ningún importe se convierte a `number` para calcular. Solo se formatea para mostrar.

### 10.4 Motor de cálculo compartido

El dispositivo necesita calcular sin conexión: bruto de línea (PRC-22), descuentos (DSC-05), totales (VTA-04) y evaluación de crédito (CRE-01 a CRE-08). Esa lógica existe en dos implementaciones:

- `backend/app/modules/ventas/domain/calculo.py` (y los módulos de dominio que use)
- `frontend/src/domain/calculo.ts`

Para que no diverjan:

- **DEBE:** ambas implementaciones son funciones puras con la misma entrada y la misma salida.
- **DEBE:** los casos de prueba viven una sola vez en `shared/fixtures/calculo/*.json` y los ejecutan tanto pytest como Vitest.
- **DEBE:** todo cambio en una regla de cálculo agrega o modifica casos compartidos antes de modificar el código.
- **DEBE:** CI falla si cualquiera de las dos suites falla.

Formato de un caso:

```json
{
  "id": "PRC-22-caja-y-sueltas",
  "reglas": ["PRC-22"],
  "entrada": {
    "modo_impositivo": "A",
    "lineas": [
      { "producto_id": "p1", "precio_referencia": "12500.00", "unidades_referencia": 6, "cantidad_base": 15, "alicuota": "0.210000" }
    ],
    "reglas_descuento": [],
    "descuento_manual": null
  },
  "salida_esperada": {
    "lineas": [ { "bruto": "31250.00", "descuentos": "0.00", "neto": "31250.00", "iva": "0.00" } ],
    "total": "31250.00"
  }
}
```

## 11. API

- REST con JSON bajo `/api/v1`.
- El OpenAPI generado por FastAPI es el contrato. El front genera sus tipos con openapi-typescript en cada cambio; CI verifica que los tipos generados estén actualizados.
- Errores en formato Problem Details (RFC 9457) con un campo `codigo` de dominio estable (`STOCK_INSUFICIENTE`, `CREDITO_EXCEDIDO`, `PERMISO_REQUERIDO`, `COMANDO_INCONSISTENTE`).
- Los listados usan paginación por cursor y un límite máximo por página.
- Las fechas viajan en ISO 8601 con zona horaria.

Agrupación de endpoints de la etapa 1:

| Grupo | Ejemplos |
| --- | --- |
| Autenticación | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout` |
| Identidad | usuarios, roles, dispositivos, PIN |
| Configuración | parámetros, medios de pago, motivos, alícuotas |
| Catálogo | productos, presentaciones, categorías, marcas |
| Proveedores | proveedores, costos informados, compras, pagos |
| Precios | listas, versiones, reglas de margen, redondeo, generación de borrador, publicación |
| Stock | ubicaciones, saldos, kardex, transferencias, ajustes |
| Jornadas | apertura, rendición, cierre, liberación |
| Clientes | clientes, estado de cuenta |
| Descuentos | reglas |
| Ventas | confirmación, anulación, consulta |
| Cobranzas | registro, anulación, consulta |
| Sync | `GET /sync/bootstrap`, `POST /sync/comandos` |
| Observaciones | listado, resolución |
| Importación | carga de planillas, puesta en marcha: `POST /api/v1/importaciones/{tipo}` (multipart, `Operation-Id` obligatorio), `GET /api/v1/importaciones` (historial paginado por cursor) y `GET /api/v1/importaciones/plantillas/{tipo}` (CSV con solo el encabezado), todas con `IMPORTAR_DATOS` |
| Reportes | ventas por período, rendición, saldos |
| Auditoría | consulta |
| Sistema | `GET /salud`, `GET /version` |

## 12. Autenticación, dispositivos y sesión (ADR-011)

### 12.1 Tokens

- **Access token:** JWT firmado con vida de 15 minutos. Contiene usuario, organización y dispositivo. Se guarda solo en memoria.
- **Refresh token:** opaco, rotativo en cada uso, guardado en base como hash, vinculado a usuario y dispositivo, con vencimiento deslizante de 30 días. Se envía en cookie `HttpOnly`, `Secure`, `SameSite=Strict`, restringida a `/api/v1/auth`.
- Reutilizar un refresh token ya rotado revoca toda la familia de tokens de ese dispositivo.
- **DEBE:** los permisos no viajan en el token. Se cargan por petición (con caché breve en memoria del proceso), para que una revocación tenga efecto inmediato con conexión.
- **Permisos para la interfaz (ADR-027):** `/admin` los obtiene de `GET /api/v1/yo`, que se vuelve a consultar en cada renovación del access token; `/ruta` usa los del bootstrap (SYN-10, SYN-11). Ocultar una acción nunca reemplaza la validación del servidor (SEG-06).
- **Sesión habilitada (ADR-028):** toda petición autenticada que no sea el lote de sincronización se rechaza si el usuario está `INACTIVO` o su rol tiene `activo = false`, en la petición siguiente y sin esperar al vencimiento del access token. `GET /api/v1/yo` rechaza en vez de devolver una lista vacía. La renovación (`refresh`) revoca las familias de refresh del usuario y deja auditoría antes de rechazar, para que la sesión revocada no pueda revivir con una reactivación.

### 12.2 Dispositivos

- En el primer inicio, la aplicación genera un `dispositivo_id` y lo guarda en IndexedDB.
- El login lo envía; el servidor registra el dispositivo y le asigna prefijo de numeración.
- Revocar un dispositivo invalida sus refresh tokens y envía a cuarentena sus comandos futuros (SYN-06).

### 12.3 Sesión sin conexión

- El PIN de desbloqueo se define con conexión y se guarda en el dispositivo como derivación PBKDF2 (Web Crypto) con sal e iteraciones altas.
- El PIN protege el uso casual de la aplicación. No es una barrera frente a alguien con acceso técnico al dispositivo: los datos de IndexedDB no están cifrados en la etapa 1. La mitigación es minimizar datos sensibles en el bootstrap (SYN-11) y poder revocar el dispositivo.
- Al volver la conexión, la aplicación usa el refresh token. Si venció, pide login; la cola se conserva y se sincroniza cuando inicia sesión el mismo usuario.

### 12.4 Autorización de supervisor sin conexión

- Cada supervisor tiene un **PIN de autorización** distinto del de desbloqueo, de al menos 6 dígitos.
- El bootstrap incluye, para los supervisores de la organización, la derivación PBKDF2 de ese PIN con su sal.
- **Riesgo aceptado:** una derivación de un PIN numérico puede atacarse por fuerza bruta con acceso técnico al dispositivo. Mitigaciones: longitud mínima, rotación desde administración, límite de intentos en la interfaz, y toda autorización offline queda con observación y auditoría.

## 13. Frontend

### 13.1 Áreas

| Área | Dispositivo | Conexión | Estado |
| --- | --- | --- | --- |
| `/ruta` | Teléfono | Opcional | Dexie + motor de cálculo + cola |
| `/admin` | PC | Requerida | TanStack Query contra la API |

- Las áreas se cargan de forma diferida: el teléfono no descarga el código de administración.
- React Context se usa solo para sesión, permisos, conectividad y tema.
- Las pantallas del área de ruta leen siempre de Dexie, con o sin conexión.

### 13.2 Base local (Dexie)

| Tabla | Contenido |
| --- | --- |
| `meta` | Versión de esquema local, dispositivo, último correlativo, fecha de bootstrap |
| `sesion` | Usuario, permisos, topes, derivación del PIN, jornada abierta |
| `configuracion` | Parámetros de la organización |
| `productos`, `presentaciones` | Catálogo activo |
| `clientes` | Clientes con datos de crédito |
| `saldos_clientes` | Saldo al bootstrap |
| `precios` | Versiones de lista disponibles y sus precios |
| `reglas_descuento` | Reglas activas |
| `stock` | Stock de la ubicación tomada |
| `autorizadores` | Derivaciones de PIN de supervisores |
| `ventas`, `cobranzas` | Operaciones locales con estado de sincronización |
| `movimientos_locales` | Efectos locales sobre stock y saldos, para calcular disponibles |
| `cola` | Comandos pendientes ordenados por secuencia |

**DEBE:** confirmar una venta local es una transacción Dexie que escribe la venta, los movimientos locales y el comando en la cola, todo o nada.

### 13.3 Motor de sincronización

- Se ejecuta en el hilo principal de la aplicación, no en el service worker: la sincronización en segundo plano no está disponible en todos los navegadores móviles.
- Se dispara al abrir la aplicación, en el evento `online`, después de cada operación local si hay conexión, cada 2 minutos mientras la aplicación está abierta y con el botón "Sincronizar".
- **DEBE:** una sola sincronización a la vez, garantizada con Web Locks API, incluso con varias pestañas abiertas.
- Envía lotes en orden (§6.4), aplica los resultados a la base local y reintenta errores transitorios con espera exponencial.
- Muestra en todo momento: estado de conexión, cantidad de pendientes, última sincronización exitosa y operaciones con observaciones o rechazadas.
- Al iniciar, solicita almacenamiento persistente (`navigator.storage.persist()`) y muestra una advertencia si el navegador lo niega.

### 13.4 Bootstrap

- `GET /api/v1/sync/bootstrap` se ejecuta al abrir la jornada (RUT-03) y devuelve el contenido de SYN-11.
- El contrato acepta un parámetro `since` para descargas incrementales; en la etapa 1 se ignora y siempre devuelve el conjunto completo (ADR-006).
- El bootstrap reemplaza los datos maestros locales, pero **DEBE NO** tocar `ventas`, `cobranzas`, `movimientos_locales` ni `cola`.

### 13.5 Service worker

- Precachea el shell de la aplicación para abrirla sin conexión.
- **DEBE NO** cachear respuestas de la API: los datos offline viven en Dexie.
- Una nueva versión se instala en segundo plano y se aplica con aviso al usuario. **DEBE NO** recargar automáticamente la aplicación mientras hay un carrito abierto.

### 13.6 Nota de venta

- Se genera en el dispositivo con pdfmake, con fuentes embebidas, a partir de los datos locales de la venta (VTA-13).
- Se comparte con Web Share API (archivos) cuando está disponible; si no, se descarga.
- La misma función genera la nota desde administración para reimpresión.

## 14. Datos

- **DEBE:** todo cambio de esquema es una migración de Alembic revisada. No se usa `create_all` fuera de las pruebas.
- **DEBE:** las migraciones son compatibles hacia adelante con la versión anterior del backend durante el despliegue (agregar antes de quitar).
- **DEBE:** los handlers cargan relaciones de forma explícita; la carga diferida implícita se desactiva en los modelos.
- Los reportes usan SQL con agregaciones en la base (SQLAlchemy Core o vistas). Nunca traen filas a Python para sumar.
- El modelo detallado está en `03-modelo-de-datos.md`.

## 15. Estrategia de pruebas

| Nivel | Herramienta | Qué cubre | Base de datos |
| --- | --- | --- | --- |
| Unitarias de dominio | pytest | Reglas puras de `domain/` | No |
| Propiedades | Hypothesis | INV-12, INV-13, INV-15, INV-19; CST-11; DSC-05 | No, o Postgres real con máquina de estados |
| Integración | pytest + Testcontainers | Handlers completos, constraints, migraciones, idempotencia, aislamiento | PostgreSQL real |
| Concurrencia | pytest + Testcontainers + hilos | Última unidad de stock, doble sync simultáneo, compra y venta concurrentes, jornada duplicada | PostgreSQL real con commits |
| Cálculo compartido | pytest y Vitest | `shared/fixtures/calculo` | No |
| Unitarias front | Vitest | Motor de cálculo, cola, conversiones | No |
| Punta a punta | Playwright | Criterios de `00` §9, incluido corte de red | Entorno completo |

Reglas:

- **DEBE:** las pruebas de integración usan PostgreSQL real. No se usa SQLite.
- **DEBE:** cada invariante de `01` §20 tiene al menos una prueba que lo cite por identificador.
- **DEBE:** cada escenario de una spec de OpenSpec tiene al menos una prueba.
- Las pruebas de integración aíslan con una transacción revertida al final de cada prueba. Las de concurrencia **DEBEN** confirmar sus transacciones y limpiar la base al terminar, porque un rollback externo impediría que las conexiones concurrentes se vean entre sí.
- La prueba de corte a mitad de venta inyecta una falla después de escribir el movimiento de stock y verifica que no quedó ningún registro de la operación (INV-01).
- La prueba de aislamiento recorre dinámicamente todas las rutas registradas (INV-21).

CI en cada push:

1. Lint, formato y tipos (backend y frontend)
2. import-linter
3. Tipos del cliente API actualizados
4. Unitarias, propiedades y cálculo compartido
5. Integración y concurrencia con Testcontainers
6. Build del frontend

En la rama principal, además: suite de Playwright contra el entorno levantado con Docker Compose.

## 16. Entornos y despliegue

### 16.1 Desarrollo

- `docker compose up` levanta PostgreSQL, backend con recarga automática y frontend con Vite.
- Datos de ejemplo cargables con un comando (`make seed` o equivalente), que incluyen el escenario de la demo de aceptación.
- Los service workers requieren HTTPS salvo en `localhost`. Para probar desde un teléfono se usa un túnel HTTPS o certificados locales con mkcert.

### 16.2 Producción (etapa 1)

Un servidor con Docker Compose:

| Servicio | Función |
| --- | --- |
| `caddy` | TLS automático, sirve el build del frontend, proxy de `/api` al backend |
| `backend` | FastAPI con varios workers |
| `postgres` | Volumen persistente, puerto no expuesto |
| `backup` | `pg_dump` diario comprimido, retención de 14 diarios y 8 semanales, copia a almacenamiento externo |

- Los secretos se cargan desde un archivo de entorno fuera del repositorio.
- El despliegue ejecuta las migraciones antes de iniciar la nueva versión del backend.
- **DEBE:** una restauración de backup se prueba en un entorno separado antes de salir a producción y luego al menos una vez por mes (`00` §9, criterio 12).

## 17. Observabilidad

- Logs estructurados en JSON con `request_id`, `operation_id`, organización, usuario y dispositivo.
- Nunca se registran contraseñas, PIN, tokens ni contenido completo de comandos con datos personales en nivel INFO.
- `GET /api/v1/salud` verifica la conexión con la base.
- Métricas mínimas en logs: duración por comando, comandos por resultado, reintentos transitorios, tamaño de lotes de sync.
- Seguimiento de errores con una herramienta externa es opcional en la etapa 1.

## 18. Seguridad

- HTTPS obligatorio, HSTS.
- Frontend y API en el mismo origen: sin CORS abierto.
- Límite de intentos en login por usuario y por IP.
- Encabezados de seguridad, incluida una política CSP restrictiva.
- El usuario de base de datos de la aplicación no es superusuario ni dueño del esquema; las migraciones usan un usuario distinto.
- Validación de toda entrada con Pydantic; SQL siempre parametrizado.
- Dependencias con actualizaciones de seguridad revisadas periódicamente.

## 19. Decisiones de este documento

Además de las listadas en `00` §12, este documento establece las siguientes, que se registran como ADR:

| ADR | Decisión |
| --- | --- |
| ADR-013 | Monolito modular con límites verificados por import-linter |
| ADR-014 | Acceso a datos síncrono con SQLAlchemy 2.x |
| ADR-015 | Tablas de saldo materializadas, orden global de bloqueo y verificación diaria de consistencia |
| ADR-016 | Motor de cálculo duplicado en Python y TypeScript con casos compartidos obligatorios |
| ADR-017 | Tokens: access en memoria, refresh rotativo en cookie vinculado a dispositivo |

## 20. Riesgos técnicos

| Riesgo | Mitigación |
| --- | --- |
| Un usuario envía como offline una operación hecha con conexión para evitar bloqueos online (stock, crédito, descuentos) | El servidor no puede verificar si hubo señal; el efecto es equivalente a activar el modo avión, por lo que se trata como riesgo de política comercial y no de seguridad. El modo OFFLINE solo se admite por sync, con usuario autenticado, dispositivo activo y jornada abierta; toda excepción genera observación y auditoría; las tolerancias offline se configuran por cliente; los reportes de observaciones por vendedor hacen visible el abuso |
| Divergencia entre cálculo del dispositivo y del servidor | Casos compartidos obligatorios; DESCUENTO_DIFIERE como red de seguridad |
| Deadlocks por nuevas operaciones | Orden global de bloqueo implementado en servicios; pruebas de concurrencia |
| Comandos encolados de versiones viejas | Handlers versionados; versión mínima de aplicación |
| Pérdida de datos locales por el navegador | Almacenamiento persistente, sincronización frecuente, advertencia visible |
| Datos locales accesibles en un dispositivo robado | Bootstrap mínimo, revocación de dispositivo, cifrado local evaluado en etapa posterior |
| Limitaciones de PWA en iPhone | Validar en dispositivo real antes del change de offline |
| Tablas de saldo desincronizadas por un defecto | Verificación diaria; nunca corrección automática |
