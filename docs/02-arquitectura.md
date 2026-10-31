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
│   │   ├── ayuda/             # archivo único de textos de ayuda y páginas "Ver más" (ADR-051)
│   │   └── components/ui/     # incluye Ayuda, el botón "(?)"
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
ventas ──► precios, descuentos, clientes, stock, costeo, cuentas_corrientes, cobranzas, catalogo, configuracion (motivos), identidad (configuración, dispositivo y permisos) — solo por service.py; ventas/domain alcanza precios.domain (bruto de línea) y descuentos.domain (motor) como código puro con dos ignore_imports (ADR-054)
proveedores ──► catalogo, stock, costeo, cuentas_corrientes, configuracion (compras y pagos de contado, solo por service.py, ADR-043)
cobranzas ──► cuentas_corrientes, clientes, configuracion (medios y motivos; la validación de medios es compartida con proveedores), stock (jornada), identidad (permisos) — solo por service.py, ADR-052
clientes ──► cuentas_corrientes, precios (lista asignada, solo por service.py, ADR-047)
precios ──► catalogo, proveedores (costos informados), identidad (configuración y permisos)
stock ──► catalogo, costeo, configuracion (motivos, solo por service.py, ADR-048)
descuentos ──► catalogo, identidad (alcances, configuración del descuento manual, permisos y tope; solo por service.py, ADR-050)
catalogo ──► costeo (solo lectura del costo promedio de un producto, ADR-036)
facturacion ──► ventas (lectura), cuentas_corrientes, costeo
sync ──► todos los módulos con comandos
importacion ──► catalogo, proveedores, clientes, stock, cuentas_corrientes, configuracion, identidad (solo por service.py; nadie depende de importacion, ADR-042)
auditoria, configuracion, identidad ◄── todos
cuentas_corrientes, costeo ──► (sin dependencias de negocio)
```

Nota: `precios` no depende de `clientes`: este registra en `precios` un verificador de uso de listas (patrón de ADR-023) y no hay ciclo.

Nota: `catalogo` e `identidad` no importan `descuentos`; `ventas` consume el motor y la evaluación del descuento manual solo por `descuentos/service.py`.

Nota: `configuracion/commands.py` no importa otros módulos de negocio; el permiso `ADMIN_CONFIGURACION` de los comandos de medios se comprueba con `configuracion/service.py::exigir_permiso_de_medios_pago`, único archivo del módulo que alcanza a `identidad`.

Nota: `catalogo` no depende de `stock`: este registra en `catalogo` un verificador de stock (`registrar_verificador_de_stock`, patrón de ADR-023 y ADR-025, que falla cerrado) para que un producto con stock no se desactive, y no hay ciclo. El contrato de import-linter `stock-solo-por-service-ajeno` permite a `stock` alcanzar `configuracion` solo por su `service.py`, y `catalogo-solo-por-service-ajeno` prohíbe a `catalogo` importar `stock` (ADR-048).

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

   **1b. Jornada del sobre.** Si el sobre trae `jornada_id`, se comprueba, antes de reservar, que existe en la organización (por `stock/service.py`). Si no existe o es de otra organización, se responde RECHAZADO con `JORNADA_INEXISTENTE` (SYN-06): en el lote el ítem queda rechazado sin fila de `comando` y el lote sigue; por REST la respuesta es 404. El bus no valida que la jornada sea del usuario ni su estado: es regla de cada comando. La clave foránea compuesta de `comando.jornada_id` queda como respaldo.
2. **Reserva de idempotencia.** `INSERT INTO comando (organizacion_id, operation_id, tipo, huella, estado) VALUES (…, 'PROCESANDO') ON CONFLICT DO NOTHING`.
   - Si se insertó, continúa.
   - Si hubo conflicto, se lee el existente. Misma huella: se devuelve el resultado guardado. Distinta huella: RECHAZADO con código `COMANDO_INCONSISTENTE` (SYN-02).
   - Si otra transacción está procesando el mismo `operation_id`, PostgreSQL bloquea el `INSERT` hasta que esa transacción termine; no hace falta lógica adicional.
3. **Validación estructural** del contenido con el esquema Pydantic de su tipo y versión.
4. **Permisos.** Todo tipo declara en el catálogo los permisos que exige (alguno de ellos basta). El bus los compara con los permisos actuales del usuario (inactivo = sin permisos) para todo comando, llegue por REST o por el lote: en `ONLINE`, si falta, rechaza con `PERMISO_REQUERIDO` antes del handler; en `OFFLINE`, acepta con `PERMISO_REVOCADO` (SYN-10). La ruta REST además lo exige antes de tocar la base. En el lote el permiso se evalúa antes de validar el contenido: quien no lo tiene recibe solo `PERMISO_REQUERIDO`, nunca el detalle de la validación (ADR-056). Antes de reservar, un comando `OFFLINE` sin jornada se rechaza con `JORNADA_REQUERIDA` y uno con la jornada de otro usuario o dispositivo con `JORNADA_AJENA`; una jornada `LIBERADA` se acepta con `JORNADA_LIBERADA` (RUT-09) (ADR-052).
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
| `VENTA_ANULAR` | ✓ | (change 22c, VTA-24) |
| `COBRANZA_REGISTRAR` | ✓ | ✓ |
| `COBRANZA_ANULAR` | ✓ | |
| `COMPRA_CONFIRMAR`, `COMPRA_ANULAR` | ✓ | |
| `PAGO_PROVEEDOR_REGISTRAR`, `PAGO_PROVEEDOR_ANULAR` | ✓ | |
| `STOCK_TRANSFERIR`, `STOCK_AJUSTAR`, `STOCK_INICIAL_REGISTRAR` | ✓ | |
| `STOCK_TRANSFERENCIA_ANULAR`, `STOCK_AJUSTE_ANULAR` | ✓ | |
| `COSTO_INFORMAR` | ✓ | |
| `LISTA_PRECIO_CREAR`, `LISTA_PRECIO_MODIFICAR`, `REGLA_MARGEN_CREAR`, `REGLA_MARGEN_MODIFICAR`, `REDONDEO_CATEGORIA_DEFINIR` (con `GESTIONAR_LISTAS`) | ✓ | |
| `LISTA_GENERAR_BORRADOR`, `LISTA_BORRADOR_PRECIO_FIJAR` (con `GESTIONAR_LISTAS`) | ✓ | |
| `LISTA_PUBLICAR`, `LISTA_ANULAR_VERSION` (con `PUBLICAR_LISTAS`) | ✓ | |
| `LISTA_PRECIO_PREDETERMINADA_DEFINIR` (con `ADMIN_CONFIGURACION`) | ✓ | |
| `REGLA_DESCUENTO_CREAR`, `REGLA_DESCUENTO_MODIFICAR`, `REGLA_DESCUENTO_ACTIVAR`, `REGLA_DESCUENTO_PAUSAR` (con `GESTIONAR_DESCUENTOS`) | ✓ | |
| `ROL_TOPE_DESCUENTO_DEFINIR` (con `ADMIN_USUARIOS`) | ✓ | |
| `ROL_PERMISOS_CAMBIAR` (con `ADMIN_USUARIOS`; rechaza `IDENTIDAD_SIN_ADMINISTRADOR`, 409, ADR-053) | ✓ | |
| `MOTIVO_CREAR`, `MOTIVO_MODIFICAR` (con `ADMIN_CONFIGURACION`; `NOMBRE_INVALIDO` y `AMBITO_INVALIDO` 422, `NOMBRE_DUPLICADO` y `ULTIMO_MOTIVO_ACTIVO` 409, ADR-061) | ✓ | |
| `ALICUOTA_CREAR`, `ALICUOTA_MODIFICAR` (con `ADMIN_CONFIGURACION`; `NOMBRE_INVALIDO`, `CONFIGURACION_VALOR_ALICUOTA_INVALIDO` y `VALOR_NO_MODIFICABLE` 422, `NOMBRE_DUPLICADO`, `VALOR_DUPLICADO`, `ALICUOTA_EN_USO` (informa en `productos` la cantidad de productos activos que la usan) y `ULTIMA_ALICUOTA_ACTIVA` 409, ADR-061) | ✓ | |
| `REDONDEO_POR_DEFECTO_DEFINIR` (con `ADMIN_CONFIGURACION`; `REDONDEO_INVALIDO` 422, ADR-061) | ✓ | |
| `DESCUENTO_MANUAL_CONFIGURAR`, `CREDITO_ORGANIZACION_CONFIGURAR` (con `ADMIN_CONFIGURACION`; `TOLERANCIA_OFFLINE_INVALIDA` 422, ADR-055) | ✓ | |
| `PIN_AUTORIZACION_PROPIO_DEFINIR` (con algún permiso de autorización de excepciones; confirma la contraseña: `IDENTIDAD_CONTRASENA_INCORRECTA`, 403, y el límite de intentos del login, `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS`, 429, ADR-018) | ✓ | |
| `USUARIO_MODIFICAR`, `USUARIO_BAJA`, `USUARIO_REACTIVAR`, `USUARIO_ROL_CAMBIAR`, `USUARIO_TOPE_DESCUENTO_DEFINIR` (con `ADMIN_USUARIOS`; `IDENTIDAD_NOMBRE_DE_USUARIO_INVALIDO` 422, `IDENTIDAD_AUTOBAJA`, `IDENTIDAD_SIN_ADMINISTRADOR`, `IDENTIDAD_ROL_INACTIVO` y `IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA` 409, `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`, ADR-060) | ✓ | |
| `USUARIO_CONTRASENA_RESTABLECER` (con `ADMIN_USUARIOS`; `IDENTIDAD_CONTRASENA_INVALIDA` 422; contraseña fuera del contenido, ADR-056) | ✓ | |
| `ROL_CREAR`, `ROL_RENOMBRAR`, `ROL_BAJA`, `ROL_REACTIVAR` (con `ADMIN_USUARIOS`; `IDENTIDAD_NOMBRE_DE_ROL_INVALIDO` 422, `IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO`, `IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS` y `IDENTIDAD_SIN_ADMINISTRADOR` 409, ADR-060) | ✓ | |
| `CLIENTE_VENDEDOR_ASIGNAR` (con `GESTIONAR_CLIENTES`; de 1 a 500 clientes y un vendedor o `null`; `VENDEDOR_INVALIDO` y `CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR` 409, ADR-060) | ✓ | |
| `CONTRASENA_PROPIA_CAMBIAR` (sin permiso: cualquier usuario autenticado y activo, solo la propia; actual y nueva fuera del contenido; `IDENTIDAD_CONTRASENA_INCORRECTA` 403 con el límite de intentos del login, `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS` 429, `IDENTIDAD_CONTRASENA_INVALIDA` y `IDENTIDAD_CONTRASENA_NUEVA_IGUAL_A_ACTUAL` 422, ADR-018, ADR-060) | ✓ | |
| `SALDO_INICIAL_REGISTRAR` | ✓ | |
| `OBSERVACION_RESOLVER` | ✓ | |
| `IMPORTACION_REGISTRAR` (permiso `IMPORTAR_DATOS`) | ✓ | |
| Altas y modificaciones de maestros (productos, clientes, proveedores, reglas, configuración) | ✓ | |

Las altas y modificaciones de maestros también llevan `operation_id` y pasan por el bus, aunque no generen movimientos.

Un handler puede devolver, además del resultado, observaciones de negocio (SYN-04, SYN-07): el comando queda `ACEPTADO_CON_OBSERVACIONES` y las observaciones se registran con la operación afectada. `COMPRA_ANULAR` lleva `devuelve_pago` (obligatorio en compras de contado, prohibido en las de crédito) y emite `ANULACION_COMPRA_SIN_RECALCULO` y `STOCK_NEGATIVO` (ADR-043, ADR-044). Las lecturas de compras exigen `REGISTRAR_COMPRA` o `ANULAR_COMPRA`; el formulario de compra también lee productos, alícuotas, proveedores y ubicaciones con `REGISTRAR_COMPRA` (ADR-043).

`PAGO_PROVEEDOR_REGISTRAR` lleva proveedor, fecha, importe, de 1 a 20 medios y una observación opcional, y exige `REGISTRAR_PAGO_PROVEEDOR`; `PAGO_PROVEEDOR_ANULAR` lleva el pago y un motivo del ámbito `ANULACION_PAGO`, y exige `ANULAR_PAGO_PROVEEDOR`. Los errores propios son `MEDIOS_INVALIDOS` (422), `PAGO_YA_ANULADO` y `PAGO_DE_COMPRA_VIGENTE` (409). Las lecturas son `GET /pagos-proveedores` (filtros de proveedor, estado, origen y fechas, con cursor), `GET /pagos-proveedores/{id}` (ambos con `REGISTRAR_PAGO_PROVEEDOR` o `ANULAR_PAGO_PROVEEDOR`) y `GET /proveedores/{id}/saldo` (con `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `REGISTRAR_COMPRA`); `GET /proveedores/opciones` también se abre, solo en lectura, a `REGISTRAR_PAGO_PROVEEDOR` (ADR-046).

`COBRANZA_REGISTRAR` (`REGISTRAR_COBRANZA`; `ONLINE` y `OFFLINE`) lleva el identificador de la cobranza, cliente, importe, de 1 a 20 medios y una observación opcional; `COBRANZA_ANULAR` (`ANULAR_COBRANZA`, solo `ONLINE`) lleva la cobranza (en la ruta), un motivo del ámbito `ANULACION_COBRANZA` y una observación opcional, y deja el motivo en su fila de auditoría. Con conexión, un medio inactivo o una referencia faltante se rechazan (`MEDIO_PAGO_INACTIVO`, `REFERENCIA_OBLIGATORIA`), igual que en los pagos; sin conexión, `COBRANZA_REGISTRAR` los acepta con `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` por línea, y con `CLIENTE_NO_HABILITADO` la cobranza al consumidor final (SYN-05, SYN-07). Los errores propios son `COBRANZA_DUPLICADA`, `COBRANZA_YA_ANULADA`, `COBRANZA_DE_VENTA`, `CONSUMIDOR_FINAL_SIN_CUENTA` y `JORNADA_AJENA` (409) y `JORNADA_REQUERIDA` (422). Las rutas son `POST /api/v1/cobranzas` y `POST /api/v1/cobranzas/{id}/anulacion`; las lecturas, `GET /api/v1/cobranzas` (filtros de cliente, estado, usuario, jornada y fechas, con cursor), `GET /api/v1/cobranzas/{id}`, `GET /api/v1/clientes/opciones` y `GET /api/v1/clientes/{id}/saldo` (ADR-052). Un tipo de comando con handler registrado pero sin declarar en el catálogo de tipos no tiene modo permitido: el lote lo rechaza en `ONLINE` y en `OFFLINE` (aprobado 2026-10-16, ADR-052). Un handler que intenta `commit`, `rollback` o `close` sobre la sesión del bus es un error de programación: aborta el lote y no se informa como `RECHAZADO` de ese ítem (ADR-052).

`STOCK_TRANSFERIR` lleva origen, destino distinto y de 1 a 200 líneas de producto y cantidad base positiva, y exige `TRANSFERIR_STOCK`; `STOCK_AJUSTAR` lleva una ubicación, un motivo del ámbito `AJUSTE_STOCK` y de 1 a 200 líneas con cantidad con signo, y exige `AJUSTAR_STOCK`; ambos admiten una observación de hasta 500 caracteres. `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` llevan la operación (en la ruta) y un motivo de los ámbitos `ANULACION_TRANSFERENCIA` y `ANULACION_AJUSTE`; anulan todas las líneas, una sola vez, con movimientos inversos al costo original; la primera exige `TRANSFERIR_STOCK` y, si la transferencia es de otro usuario, además `ANULAR_TRANSFERENCIA`, y la segunda `AJUSTAR_STOCK`. Emiten `STOCK_NEGATIVO` cuando el usuario con `PERMITIR_STOCK_NEGATIVO` deja un saldo bajo cero. Los errores propios son `UBICACIONES_IGUALES`, `OBSERVACION_INVALIDA` y `MOTIVO_INVALIDO` (422) y `PRODUCTO_SIN_COSTO`, `PRODUCTO_CON_STOCK`, `TRANSFERENCIA_YA_ANULADA` y `AJUSTE_YA_ANULADO` (409). Las lecturas son `GET /stock/transferencias` y `/{id}` (con `TRANSFERIR_STOCK`) y `GET /stock/ajustes` y `/{id}` (con `AJUSTAR_STOCK`, costos con `VER_COSTOS`), con cursor y límite; el kardex agrega el motivo, la operación de origen y su estado. Los cuatro comandos son solo online. El bus copia el motivo a su fila de auditoría únicamente en `STOCK_AJUSTAR`, `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` (ADR-022, ADR-048).

`JORNADA_ABRIR` (`ABRIR_JORNADA`) lleva solo la ubicación: el usuario y el dispositivo salen de la sesión, nunca del contenido. `JORNADA_RENDIR` y `JORNADA_CERRAR` (`RENDIR_JORNADA`) llevan la jornada (en la ruta); `JORNADA_LIBERAR` (`LIBERAR_UBICACION`) lleva la jornada, un motivo del ámbito `LIBERACION_JORNADA` y una observación opcional de hasta 500 caracteres. Los cuatro son solo online, con `Operation-Id`; la fila de auditoría del bus de `JORNADA_LIBERAR` lleva el motivo (ADR-049). Los errores propios son `UBICACION_TOMADA`, `USUARIO_CON_JORNADA`, `DISPOSITIVO_CON_JORNADA`, `UBICACION_SIN_TOMA` y `JORNADA_ESTADO_INVALIDO` (409), `MOTIVO_INVALIDO` y `OBSERVACION_INVALIDA` (422) y `JORNADA_INEXISTENTE` (404); una jornada ajena o inexistente es 404. Las rutas son `POST /api/v1/stock/jornadas` y `POST /api/v1/stock/jornadas/{id}/rendicion`, `/cierre` y `/liberacion`. Las lecturas son `GET /api/v1/stock/jornadas` (filtros de ubicación, usuario, estado y fechas de negocio, con cursor), `GET /api/v1/stock/jornadas/{id}` y `GET /api/v1/stock/jornadas/actual`, con cualquiera de `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION` (la última, con `ABRIR_JORNADA`). Todo comando que mueve stock sobre una ubicación tomada responde `UBICACION_TOMADA` salvo que sea de la jornada o de quien tiene `LIBERAR_UBICACION` (STK-09).

`VENTA_CONFIRMAR` (`VENDER`; `ONLINE` y `OFFLINE`) lleva el identificador de la venta, su número, cliente, ubicación (con conexión, si no hay jornada abierta), lista o versión elegidas con su motivo, de 1 a 200 líneas (identificador, producto, presentación, cantidad y los valores esperados: versión, precio y unidades de referencia, bruto), el total esperado y la cobranza opcional (identificador, de 1 a 20 medios, observación) y, desde el change 18b y todos opcionales, el porcentaje manual general y el propio de cada línea, los descuentos esperados de cada línea (origen, regla, porcentaje, importe), el motivo y el autorizador del descuento y el objeto `credito` (aceptación del exceso, autorizador y, sin conexión, la evaluación del dispositivo: límite, saldo considerado, política y resolución; sin conexión es obligatorio). Los errores propios son `VENTA_SIN_LINEAS`, `LINEAS_INVALIDAS`, `LINEA_DUPLICADA`, `NUMERO_INVALIDO`, `MOMENTO_FUERA_DE_RANGO`, `CONSUMIDOR_FINAL_CONTADO` y `MOTIVO_INVALIDO` y `UBICACION_REQUERIDA` (422) y `VENTA_DUPLICADA`, `NUMERO_DUPLICADO`, `PRECIO_DIFIERE`, `PRODUCTO_SIN_PRECIO`, `PRODUCTO_SIN_COSTO`, `PRESENTACION_NO_VENDIBLE`, `VERSION_NO_PERMITIDA`, `CLIENTE_SUSPENDIDO`, `CLIENTE_INACTIVO`, `MODO_IMPOSITIVO_NO_SOPORTADO`, `JORNADA_AJENA`, `STOCK_INSUFICIENTE`, `UBICACION_INACTIVA` y `UBICACION_TOMADA` (409); sin conexión, `TOTALES_INCONSISTENTES` y `CREDITO_INCONSISTENTE` (SYN-06). El 18b suma `DESCUENTO_DIFIERE`, `DESCUENTO_MANUAL_DESHABILITADO`, `EXCESO_CREDITO_SIN_ACEPTAR` y `CREDITO_EXCEDIDO` (409), `MOTIVO_REQUERIDO` (422), `AUTORIZACION_REQUERIDA`, `AUTORIZACION_CREDITO_REQUERIDA`, `AUTORIZADOR_SIN_PERMISO` y `PIN_INCORRECTO` (403) y `PIN_BLOQUEADO` (429) (ADR-055). Emite, solo sin conexión, `STOCK_NEGATIVO`, `CLIENTE_NO_HABILITADO`, `CONSUMIDOR_FINAL_CON_DEUDA`, `LISTA_NO_VIGENTE`, `VENTA_SIN_COSTO`, `UBICACION_TOMADA_AL_SINCRONIZAR`, y sobre la cobranza `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE`; `STOCK_NEGATIVO` también con conexión si el usuario tiene `PERMITIR_STOCK_NEGATIVO`. El 18b suma, solo sin conexión, `DESCUENTO_DIFIERE`, `EXCESO_CREDITO_AUTORIZADO_OFFLINE`, `EXCESO_CREDITO_DETECTADO_SYNC` y `AUTORIZACION_OFFLINE`, y con conexión y sin ella, `EXCESO_CREDITO_ADVERTIDO` (CRE-04). La fila de auditoría del bus lleva el motivo de la lista y la constancia de ubicación tomada cuando corresponden; además se auditan `DESCUENTO_MANUAL` y `AUTORIZACION_CREDITO` (AUD-01), sin PIN. Ruta `POST /api/v1/ventas`; lecturas `GET /api/v1/ventas`, `/{id}`, `/precios`, `/versiones`, `/numeracion` (ADR-054), `/contexto` (tope, motivos y autorizadores), `/credito?cliente_id=` y `/descuentos-aplicables` (todas con `VENDER`, ADR-055).

`POST /api/v1/ventas` admite, fuera del contenido, `credenciales` (autorizador y PIN) que el bus entrega al handler sin persistirlas ni incluirlas en la huella; el lote de sincronización no las admite. `POST /api/v1/yo/pin-autorizacion` lleva el PIN nuevo y la contraseña actual del mismo modo, con el contenido del comando vacío; `GET /api/v1/yo/pin-autorizacion` informa `puede_definir` y `tiene_pin_autorizacion` (ADR-055).

`VENTA_ANULAR` (`ANULAR_VENTA`; solo `ONLINE` hasta el change 22c) lleva la venta (`venta_id`, el identificador que generó el dispositivo), un motivo del ámbito `ANULACION_VENTA`, una observación opcional de hasta 500 caracteres y `devuelve_dinero` (booleano estricto: obligatorio si la venta tiene su cobranza confirmada y omitido si no). Errores propios: `VENTA_YA_ANULADA` y `CONSUMIDOR_FINAL_SIN_DEVOLUCION` (409) y `DEVOLUCION_INVALIDA` (422); además `MOTIVO_INVALIDO`, `OBSERVACION_INVALIDA`, `UBICACION_TOMADA` y `UBICACION_INACTIVA`. Ruta `POST /api/v1/ventas/{venta_id}/anulacion`. No emite observaciones de SYN-07: el reingreso nunca deja stock negativo. Una fila de auditoría por comando, con el motivo y, en su observación, la cobranza anulada y la constancia de la ubicación tomada (AUD-01, AUD-02, ADR-058).

Cada tipo declara sus permisos en el catálogo (`permisos`, reemplaza a `permiso_offline`) y, si siempre recibe un secreto (contraseña o PIN), `exige_credenciales_efimeras`: el secreto viaja fuera del contenido y de la huella, y el lote rechaza ese tipo en cualquier modo con `MODO_NO_ADMITIDO_PARA_TIPO` (`USUARIO_CREAR`, `PIN_AUTORIZACION_ROTAR`, `PIN_AUTORIZACION_PROPIO_DEFINIR`, `USUARIO_CONTRASENA_RESTABLECER`, `CONTRASENA_PROPIA_CAMBIAR`); desde un dispositivo revocado se responde `DISPOSITIVO_REVOCADO` y no se guarda en cuarentena. Ningún error de validación devuelve el valor recibido (ADR-055, ADR-056).

Los comandos de listas son solo online. Los errores propios son `MARGEN_INVALIDO`, `ALCANCE_INVALIDO`, `REDONDEO_INVALIDO`, `IMPORTE_INVALIDO`, `PRECIO_NO_POSITIVO`, `VIGENCIA_INVALIDA`, `VERSION_SIN_PRECIOS` (422) y `NOMBRE_DUPLICADO`, `REGLA_DUPLICADA`, `LISTA_INACTIVA`, `LISTA_EN_USO`, `VERSION_NO_ES_BORRADOR`, `VERSION_NO_PUBLICADA`, `VERSION_YA_VIGENTE`, `VIGENCIA_DUPLICADA`, `SIN_LISTA_APLICABLE`, `LISTA_SIN_VERSION_VIGENTE` (409). Las lecturas cuelgan de `/api/v1/precios/…` (listas, reglas, borrador, versiones, precios de una versión paginados por cursor, `vigente?momento=` y `lista-predeterminada`); `CLIENTE_CREAR` y `CLIENTE_MODIFICAR` aceptan `lista_precio_id` (ADR-047).

`REGLA_DESCUENTO_CREAR` lleva nombre, tipo, medida, operador, umbral, acción (tipo y valor, el valor como cadena: fracción de seis decimales para el porcentaje o importe de dos decimales), prioridad entera desde 1, acumulable, los alcances (identificadores de productos, categorías o marcas) y, opcionalmente, la vigencia desde y hasta; la regla nace en `BORRADOR`. `REGLA_DESCUENTO_MODIFICAR` reemplaza un borrador con los mismos campos; en una regla activada o pausada solo admite la vigencia hasta (`REGLA_NO_ES_BORRADOR`, 409, en cualquier otro caso). `REGLA_DESCUENTO_ACTIVAR` (desde `BORRADOR` o `PAUSADA`) y `REGLA_DESCUENTO_PAUSAR` (desde `ACTIVA`) llevan solo la regla; una transición que no corresponde responde `REGLA_ESTADO_INVALIDO` (409). Los errores propios son `UMBRAL_INVALIDO`, `ACCION_INVALIDA`, `PRIORIDAD_INVALIDA`, `NOMBRE_INVALIDO`, `ALCANCE_INVALIDO`, `VIGENCIA_INVALIDA`, `REGLA_DESCUENTO_INVALIDA` (422) y `REGLA_ESTADO_INVALIDO`, `REGLA_NO_ES_BORRADOR` (409). Las rutas cuelgan de `/api/v1/descuentos/reglas` (alta, edición, `/{id}/activacion`, `/{id}/pausa`) y las lecturas, `GET /api/v1/descuentos/reglas` (filtro de estado, que admite `VENCIDA`, y cursor) y `GET /api/v1/descuentos/reglas/{id}`, todas con `GESTIONAR_DESCUENTOS`. `ROL_TOPE_DESCUENTO_DEFINIR` lleva el rol y el tope como cadena (fracción de hasta seis decimales entre 0 y 1; `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`, 422), cambia solo `rol.tope_descuento`, deja una fila de auditoría con el valor anterior y el nuevo y se expone en `PUT /api/v1/identidad/roles/{rol_id}/tope-descuento`; `GET /api/v1/identidad/roles` devuelve los roles con su tope y sus permisos (`ADMIN_USUARIOS`); la pantalla "Topes por rol" exige `GESTIONAR_DESCUENTOS` y `ADMIN_USUARIOS`, y el tope no se expone en `GET /yo` ni en el token (el usuario ve el suyo recién en el 18b, con el bootstrap, SYN-11). La evaluación del descuento manual no es un comando: la consulta la venta por `descuentos/service.py` y devuelve `DESCUENTO_MANUAL_DESHABILITADO` (409), `MOTIVO_REQUERIDO` (422), `AUTORIZACION_REQUERIDA` y `AUTORIZADOR_SIN_PERMISO` (403) cuando corresponde.

`MEDIO_PAGO_CREAR` y `MEDIO_PAGO_MODIFICAR` (ADR-053) son solo `ONLINE`. Cada uno deja dos filas de auditoría con el mismo `operation_id`: la genérica del bus (`entidad = 'comando'`, ADR-022) y la de la entidad (`entidad = 'medio_pago'`) con `despues` en el alta y `antes` y `despues` en la modificación (AUD-01), igual que la condición de IVA y la modificación de crédito. El diseño (D11) describía una sola fila; el usuario aprobó mantener las dos para no romper el patrón establecido. Los comandos de motivos, alícuotas y redondeo por defecto (ADR-061) dejan las mismas dos filas, con la entidad `motivo`, `alicuota_iva` o `configuracion_organizacion`.

Una importación es un comando por archivo: todo o nada, con savepoints por fila dentro del handler (ADR-040).

### 6.6 Compatibilidad de versiones

- Un dispositivo puede tener comandos encolados generados por una versión anterior de la aplicación. **DEBE:** el servidor conserva los handlers de toda versión de comando que pueda estar en colas activas.
- El servidor publica la versión mínima de la aplicación. Una aplicación por debajo de la mínima puede sincronizar su cola pero no confirmar operaciones nuevas hasta actualizarse.
- Retirar una versión de comando requiere verificar que no queden comandos pendientes de esa versión.

## 7. Transacciones y concurrencia

### 7.1 Nivel de aislamiento

READ COMMITTED con bloqueos explícitos de fila. No se usa SERIALIZABLE por defecto. Excepción de solo lectura: el bootstrap (§13.4) se lee en una transacción `REPEATABLE READ READ ONLY` para que todas sus secciones sean del mismo instante (ADR-062).

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
2. `producto` (`FOR SHARE`, por `producto_id` ascendente; todo movimiento de stock lo toma, y la desactivación de un producto lo toma `FOR UPDATE`)
3. `costo_producto` (por `producto_id` ascendente)
4. `stock_saldo` (por `producto_id` y `ubicacion_id` ascendentes)
5. `jornada` (`FOR SHARE`, por `ubicacion_id` ascendente: todo movimiento lee la jornada no cerrada de cada una de sus ubicaciones antes de decidir; `FOR UPDATE` en las transiciones de la propia jornada)

Las filas de la propia operación que el comando corrige o anula se toman **antes** del nivel 1, en este orden: la compra (`FOR UPDATE`) y después su pago (`FOR UPDATE`); o la venta (`FOR UPDATE`) y después su cobranza (`FOR UPDATE`); o la transferencia o el ajuste (`FOR UPDATE`), que se anula una sola vez. `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` usan el mismo orden (compra, pago, `saldo_cuenta`), así que anular una compra y anular su pago a la vez no se interbloquean y dejan una sola `ANULACION_PAGO`. `PAGO_PROVEEDOR_REGISTRAR` parte del nivel 1 (`saldo_cuenta` del proveedor) (ADR-043 punto 15, ADR-046). Las ubicaciones se toman `FOR SHARE` al comienzo del movimiento, como hasta ahora (ADR-038); `JORNADA_ABRIR` toma la ubicación `FOR UPDATE` en ese mismo paso, así que una apertura y un movimiento sobre la misma ubicación se esperan: o el movimiento termina antes de la toma, o ve la ubicación tomada. `JORNADA_RENDIR`, `JORNADA_CERRAR` y `JORNADA_LIBERAR` toman su jornada `FOR UPDATE`, revalidan el estado y no tocan stock ni saldos, por lo que no pueden cerrar un ciclo; una liberación espera a los movimientos en curso de esa jornada y al revés (ADR-049). La rendición del change 24, que necesitará la jornada antes que el stock, debe resolver cómo convive con este nivel. Con el producto como nivel previo a `costo_producto`, un movimiento y la desactivación del mismo producto se esperan: o el movimiento ve el producto inactivo, o la desactivación ve el saldo (`PRODUCTO_CON_STOCK`) (ADR-048). `COBRANZA_ANULAR` toma la cobranza `FOR UPDATE` antes de `saldo_cuenta`; `COBRANZA_REGISTRAR` parte del nivel 1 y lee la jornada `FOR SHARE` en el nivel 5 (ADR-052). `VENTA_ANULAR` toma la venta y después su cobranza de origen `VENTA`, antes de `saldo_cuenta` (nivel 1), y luego un ingreso por línea por el mismo `registrar_movimientos` (niveles 2 a 5); anular una venta y `COBRANZA_ANULAR` sobre su cobranza a la vez no se interbloquean y dejan una sola anulación de la cobranza. Precedencia de rechazos de `VENTA_ANULAR`: contenido, venta (404 y `VENTA_YA_ANULADA`), motivo, dinero cobrado (`DEVOLUCION_INVALIDA`, `CONSUMIDOR_FINAL_SIN_DEVOLUCION`), ubicación (`UBICACION_INACTIVA`, `UBICACION_TOMADA`) (ADR-058).

`ROL_PERMISOS_CAMBIAR`: solo cuando el cambio quita `ADMIN_USUARIOS` bloquea `FOR UPDATE` la fila de configuración de la organización y recién entonces cuenta, en SQL, los usuarios activos con rol activo que conservan el permiso; el resto de los cambios de permisos no paga el bloqueo (ADR-053). `MEDIO_PAGO_MODIFICAR`: bloquea los medios de la organización `FOR UPDATE` antes de contar los activos. `MOTIVO_MODIFICAR` (baja): bloquea `FOR UPDATE` los motivos del ámbito de la organización antes de contar los activos. `ALICUOTA_MODIFICAR` (baja): bloquea `FOR UPDATE` las alícuotas activas de la organización antes de contar las activas y los productos activos que la usan; el alta y la modificación de un producto leen su alícuota `FOR SHARE` (ADR-061).

**Identidad (ADR-060).** `USUARIO_CREAR`, `USUARIO_BAJA`, `USUARIO_REACTIVAR`, `USUARIO_ROL_CAMBIAR`, `ROL_CREAR`, `ROL_RENOMBRAR`, `ROL_BAJA`, `ROL_REACTIVAR` y `ROL_PERMISOS_CAMBIAR` (cuando quita `ADMIN_USUARIOS`) toman **primero** `configuracion_organizacion FOR UPDATE` (el mismo candado de ADR-053), después el rol o los roles involucrados `FOR UPDATE` y el usuario objetivo `FOR UPDATE`, y recién entonces `sesion_refresh`: configuración → rol → usuario → `sesion_refresh`. Con el candado tomado revalidan que quien ejecuta sigue `ACTIVO`, con rol activo y con `ADMIN_USUARIOS` (si no, `PERMISO_REQUERIDO`, sin cambios) y cuentan los administradores restantes en SQL. Ningún comando de otro módulo toma después un usuario o un rol, así que no hay ciclo. "Mi contraseña" (`CONTRASENA_PROPIA_CAMBIAR`) solo toca al propio usuario y a sus familias de refresh y no toma el candado de la organización.

Un orden único impide deadlocks entre operaciones concurrentes. Los handlers no bloquean filas directamente: usan funciones de los servicios que respetan este orden, y la venta reúne todos los productos antes de pedir bloqueos.

La fila de `lista_precio` es el candado de la lista y no entra en el orden de arriba: todo comando que escribe versiones o precios de una lista la toma `FOR UPDATE` primero, revalida el estado de la versión y recién escribe; quien asigna una lista a un cliente la lee `FOR SHARE`, de modo que desactivarla y asignarla no se cruzan. Ningún comando de `precios` toca `saldo_cuenta`, `costo_producto` ni `stock_saldo` (ADR-047 punto 19).

La venta lee la lista `FOR SHARE` (candado propio de la lista, fuera del orden) antes del nivel 1; toma `saldo_cuenta` del cliente (nivel 1) y los productos `FOR SHARE` (nivel 2) **antes** de leer las presentaciones (`FOR KEY SHARE`), así una `PRESENTACION_MODIFICAR` simultánea, que toma el producto `FOR UPDATE`, espera o se ve (INV-18). **Nivel 6:** la fila del `dispositivo` que actualiza el último correlativo, al final de la transacción; solo la toman la venta y la revocación del dispositivo, que no toma otras filas (ADR-054).

Dentro de `VENTA_CONFIRMAR` no hay bloqueos nuevos: cliente y lista, `saldo_cuenta` (nivel 1), productos, motor de descuentos y comparación (precio, descuento, total), evaluación del descuento manual, evaluación de crédito con el saldo bloqueado, verificación de los PIN necesarios (permiso del autorizador, bloqueo vigente, PIN; el contador de fallos va en una transacción aparte), stock, escrituras y dispositivo. Precedencia de rechazos: contenido, cliente, precio, descuento, tope y motivo, crédito, PIN, stock, número (ADR-054 enmendado, ADR-055).

### 7.4 Stock

- Todo movimiento de un producto bloquea su fila de `costo_producto` y la de `stock_saldo`, y toma el producto `FOR SHARE` antes de ambas. Esto serializa las operaciones concurrentes por producto; con el volumen esperado no es un cuello de botella.
- **ONLINE:** `UPDATE stock_saldo SET cantidad = cantidad - :q WHERE … AND cantidad >= :q`. Si no afecta filas y el usuario no tiene `PERMITIR_STOCK_NEGATIVO`, se rechaza (STK-05). Con el permiso se admite solo para la salida de una transferencia, la anulación de una compra, la de una transferencia y la de un ajuste; **nunca** para un ajuste ni para la corrección de un stock inicial, que se rechazan con `STOCK_INSUFICIENTE` tenga o no el permiso (ADR-044 punto 4 enmendado por ADR-048).
- **OFFLINE:** se descuenta sin condición y, si el resultado es negativo, se agrega la observación STOCK_NEGATIVO (STK-06).
- Una ubicación tomada se valida dentro de la misma transacción: después de bloquear los saldos, `registrar_movimientos` lee la jornada no cerrada de cada ubicación (`FOR SHARE`, nivel 5) y decide por ubicación con STK-09 (libre, de la jornada o por excepción de `LIBERAR_UBICACION`; cualquier otro caso es `UBICACION_TOMADA` y no escribe nada). El permiso de excepción llega como dato, como `permitir_negativo`, y falla cerrado (ADR-049).
- El ingreso `ANULACION_VENTA` se acepta con el producto inactivo, como `ANULACION_COMPRA` (ADR-044 punto 5 enmendado por ADR-058); una ubicación inactiva lo rechaza siempre.

### 7.5 Jornadas

Tres índices únicos parciales sobre las jornadas no cerradas (`ABIERTA` o `EN_RENDICION`): una por ubicación (INV-16), una por dispositivo y una por usuario. El intento de abrir una segunda falla por la restricción, no por una verificación previa en código; la violación se traduce a `UBICACION_TOMADA`, `DISPOSITIVO_CON_JORNADA` o `USUARIO_CON_JORNADA`. La apertura toma la ubicación `FOR UPDATE` (§7.3).

### 7.6 Verificación de consistencia

Una tarea diaria compara cada tabla de saldo con la suma de su libro. Cualquier diferencia se registra como error crítico en el log y se notifica al administrador. Nunca se corrige automáticamente: una diferencia indica un defecto que debe investigarse.

### 7.7 Numeración de notas de venta

- Cada dispositivo tiene un prefijo único asignado por el servidor al registrarse (SEG-02).
- El dispositivo lleva el correlativo local y lo incrementa al confirmar.
- El bootstrap devuelve el último correlativo registrado en el servidor para ese dispositivo; el dispositivo usa el mayor entre ese y el local. Esto evita repetir números si se borran los datos del navegador.
- Restricción única (organización, número). Una colisión en sync indica un defecto y se trata como error de consistencia.
- Hasta el bootstrap (change 21), el último correlativo se lee con `GET /api/v1/ventas/numeracion`; el cliente usa el mayor entre ese y el guardado localmente. El servidor no exige que el correlativo supere al último: solo que el número sea del dispositivo y no esté usado; el último pasa al mayor de los dos (ADR-054).
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
- `occurred_at` proviene del dispositivo y puede ser inexacto. El servidor guarda también `registered_at` y registra una advertencia si la diferencia es mayor que un umbral configurable hacia el futuro. El umbral es `desvio_reloj_max_segundos` (300 por defecto si es nulo). Con conexión, una venta cuyo `occurred_at` se aleja del reloj del servidor más que ese margen, en cualquier sentido, se rechaza con `MOMENTO_FUERA_DE_RANGO` (422); sin conexión no se valida, porque el momento es el de la entrega (ADR-054).
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

- `backend/app/modules/precios/domain/bruto_de_linea.py` (PRC-22) y `frontend/src/domain/precios/brutoDeLinea.ts`; el motor de descuentos (DSC-03 a DSC-07), en `backend/app/modules/descuentos/domain/` y `frontend/src/domain/descuentos/`, expuesto por `descuentos/service.py`; el motor de venta —bruto, descuentos y totales— vive en `ventas/domain/calculo.py` y `frontend/src/domain/calculo.ts` desde el change 18a, como orquestadores que consumen las funciones de `precios` y `descuentos` por sus `service.py` (ADR-050); la evaluación de crédito (CRE-01 a CRE-08) vive en `clientes/domain/credito.py` y `frontend/src/domain/credito/`, expuesta por `clientes/service.py` (ADR-016 enmendado, ADR-055).

Para que no diverjan:

- **DEBE:** ambas implementaciones son funciones puras con la misma entrada y la misma salida.
- **DEBE:** los casos de prueba viven una sola vez en `shared/fixtures/calculo/*.json` y los ejecutan tanto pytest como Vitest.
- **DEBE:** todo cambio en una regla de cálculo agrega o modifica casos compartidos antes de modificar el código.
- **DEBE:** CI falla si cualquiera de las dos suites falla.

Los casos de PRC-22 están en `shared/fixtures/calculo/prc-22-bruto-de-linea.json` (`"motor": "prc22"`). Los del motor de descuentos están en `shared/fixtures/calculo/dsc-05-descuentos.json` (`"motor": "dsc05"`: condición, acciones, orden de resolución y descuento manual general y propio, con `porcentaje_manual_maximo`) y los de la evaluación del tope y la autorización, en `shared/fixtures/calculo/dsc-06-descuento-manual.json` (`"motor": "dsc06"`). Los casos de totales (VTA-04) están en `shared/fixtures/calculo/vta-04-totales.json` (`"motor": "vta04"`: líneas con precio, unidades de referencia, cantidad base, alícuota y reglas; salida con descuentos, neto e IVA por línea y `total_neto`, `total_iva`, `total`; modos B y C rechazados con `MODO_IMPOSITIVO_NO_SOPORTADO`). Los de crédito están en `shared/fixtures/calculo/cre-01-credito.json` (`"motor": "cre01"`), y `vta-04-totales.json` suma los casos de descuento manual (ADR-055). El cálculo de costo de referencia, margen y redondeo (PRC-11, PRC-12, PRC-14) corre solo en el servidor y no tiene gemela (ADR-047 punto 11, matiza ADR-016).

Formato de un caso (el de descuentos, con el descuento manual en dos niveles):

```json
{
  "id": "DSC05-res-manual-sin-automaticos",
  "reglas": ["DSC-05", "PRC-22"],
  "comentario": "Sin reglas: 5% de 31250.00 = 1562.50; neto 29687.50. Maximo 0.050000.",
  "entrada": {
    "motor": "dsc05",
    "lineas": [
      { "id": "l-vino", "bruto": "31250.00", "cantidad_base": 15, "unidades_referencia": 6,
        "producto_id": "prod-vino", "categoria_id": "cat-vinos", "marca_id": "marca-bodega-norte",
        "descuento_manual": null }
    ],
    "reglas_descuento": [],
    "descuento_manual_general": "0.050000"
  },
  "salida_esperada": {
    "lineas": [
      { "id": "l-vino",
        "descuentos": [ { "origen": "MANUAL", "regla_id": null, "porcentaje": "0.050000", "importe": "1562.50" } ],
        "descuento_total": "1562.50", "neto": "29687.50" }
    ],
    "porcentaje_manual_maximo": "0.050000"
  }
}
```

El caso completo de venta con IVA y total (`modo_impositivo`, `alicuota`, `iva`, `total`) lo introduce el change 18a sobre este mismo formato; el `descuento_manual` único de nivel venta que traía el ejemplo anterior pasa a `descuento_manual_general` más el `descuento_manual` propio de cada línea.

## 11. API

- REST con JSON bajo `/api/v1`.
- El OpenAPI generado por FastAPI es el contrato. El front genera sus tipos con openapi-typescript en cada cambio; CI verifica que los tipos generados estén actualizados.
- Errores en formato Problem Details (RFC 9457) con un campo `codigo` de dominio estable (`STOCK_INSUFICIENTE`, `CREDITO_EXCEDIDO`, `PERMISO_REQUERIDO`, `COMANDO_INCONSISTENTE`).
- **Códigos de error nuevos**: `IDENTIDAD_AUTOBAJA`, `IDENTIDAD_ROL_INACTIVO`, `IDENTIDAD_USUARIO_DUPLICADO`, `IDENTIDAD_NOMBRE_DE_USUARIO_INVALIDO`, `IDENTIDAD_NOMBRE_DE_ROL_INVALIDO`, `IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO`, `IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS`, `IDENTIDAD_CONTRASENA_INVALIDA`, `IDENTIDAD_CONTRASENA_NUEVA_IGUAL_A_ACTUAL`, `VENDEDOR_INVALIDO` y `CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR`. **Rutas nuevas:** `GET /identidad/usuarios` (filtros `estado`, `rol_id`, `con_tope_propio`), `GET/PUT /identidad/usuarios/{id}`, `POST .../baja`, `POST .../reactivacion`, `PUT .../rol`, `POST .../contrasena`, `PUT .../tope-descuento`, `POST /identidad/roles`, `PUT /identidad/roles/{id}/nombre`, `POST .../baja`, `POST .../reactivacion`, `POST /yo/contrasena`, `POST /clientes/vendedor`, `GET /clientes/vendedores` (`GESTIONAR_CLIENTES`; vendedores elegibles, `id` y `nombre`), y `GET /clientes/opciones?alcance=todos`, `GET /clientes?vendedor_id=&sin_vendedor=`.
- Los listados usan paginación por cursor y un límite máximo por página.
- Las fechas viajan en ISO 8601 con zona horaria.
- **Ruta nueva del change 21:** `GET /api/v1/sync/bootstrap` (jornada `ABIERTA` propia en el dispositivo; 409 `JORNADA_REQUERIDA` sin ella; `since` aceptado e ignorado).

Agrupación de endpoints de la etapa 1:

| Grupo | Ejemplos |
| --- | --- |
| Autenticación | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout` |
| Identidad | usuarios, roles (con su tope de descuento y sus permisos), catálogo de permisos (`GET /identidad/permisos`), dispositivos, PIN |
| Configuración | parámetros, medios de pago (alta y modificación por `POST`/`PUT /configuracion/medios-pago`; activos con cualquier sesión y todos con `GET /configuracion/medios-pago/todos` y `ADMIN_CONFIGURACION`), motivos, alícuotas |
| Catálogo | productos, presentaciones, categorías, marcas |
| Proveedores | proveedores, costos informados, compras, pagos |
| Precios | listas, versiones, reglas de margen, redondeo, generación de borrador, publicación |
| Stock | ubicaciones, saldos, kardex, transferencias, ajustes |
| Jornadas | apertura, rendición, cierre, liberación |
| Clientes | clientes, estado de cuenta |
| Descuentos | reglas (alta, edición del borrador, activación, pausa, consulta) |
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
- **Sesión habilitada (ADR-028):** toda petición autenticada que no sea el lote de sincronización se rechaza si el usuario está `INACTIVO` o su rol tiene `activo = false`, en la petición siguiente y sin esperar al vencimiento del access token. `GET /api/v1/yo` rechaza en vez de devolver una lista vacía. La renovación (`refresh`) revoca las familias de refresh del usuario y deja auditoría antes de rechazar, para que la sesión revocada no pueda revivir con una reactivación. **Excepción (ADR-028 D9.3-B, ADR-049):** si el usuario o su rol están inactivos pero el dispositivo que renueva tiene una jornada `ABIERTA` o `EN_RENDICION` de ese usuario, la renovación se acepta, rota el refresh, no revoca las familias y deja una fila de auditoría `RENOVAR_SESION_CON_JORNADA_PENDIENTE` por cada renovación; el token resultante solo abre el lote de sincronización. Cuando la jornada se cierra o se libera, la renovación siguiente se rechaza. Si el mismo usuario intenta renovar desde otro dispositivo sin jornada, se rechaza y se revocan sus familias menos la del dispositivo con jornada no cerrada. El inicio de sesión sigue rechazando al inactivo. `identidad` consulta la jornada por un puerto que registra `stock` al importarse; sin puerto registrado, la excepción no existe.

### 12.2 Dispositivos

- En el primer inicio, la aplicación genera un `dispositivo_id` y lo guarda en IndexedDB.
- El login lo envía; el servidor registra el dispositivo y le asigna prefijo de numeración.
- Revocar un dispositivo invalida sus refresh tokens y envía a cuarentena sus comandos futuros (SYN-06).

### 12.3 Sesión sin conexión

- El PIN de desbloqueo (6 dígitos, sin triviales) se define con conexión y se guarda en el dispositivo como derivación PBKDF2-SHA256 (Web Crypto) con sal de 32 bytes y 600 000 iteraciones; nunca viaja al servidor. Los fallos se cuentan en la base local; con 10 fallos (constante del código) se borra la derivación (ADR-062).
- El PIN protege el uso casual de la aplicación. No es una barrera frente a alguien con acceso técnico al dispositivo: los datos de IndexedDB no están cifrados en la etapa 1. La mitigación es minimizar datos sensibles en el bootstrap (SYN-11) y poder revocar el dispositivo.
- Al volver la conexión, la aplicación usa el refresh token. Si venció, pide login; la cola se conserva y se sincroniza cuando inicia sesión el mismo usuario.

### 12.4 Autorización de supervisor sin conexión

- Cada supervisor tiene un **PIN de autorización** distinto del de desbloqueo, de al menos 6 dígitos.
- El bootstrap incluye, para los supervisores de la organización, la derivación PBKDF2 de ese PIN con su sal.
- **Riesgo aceptado:** una derivación de un PIN numérico puede atacarse por fuerza bruta con acceso técnico al dispositivo. Mitigaciones: longitud mínima, rotación desde administración, límite de intentos en la interfaz, y toda autorización offline queda con observación y auditoría.
- Con conexión, el PIN viaja fuera del contenido del comando y el servidor lo verifica contra la derivación guardada; los fallos se cuentan por usuario que intenta y supervisor en una transacción aparte: al llegar a `intentos_pin_max` ese usuario no puede usar ese PIN, y con 20 fallos sumando todos los usuarios el PIN se bloquea para todos (`PIN_BLOQUEADO`); cada bloqueo dura 15 minutos desde el último fallo y los intentos durante el bloqueo no cuentan; toda definición del PIN reinicia la cuenta. El servidor rechaza PIN triviales: todos los dígitos iguales o una escalera de paso 1, ascendente o descendente (ADR-019, ADR-055). Cada supervisor puede definir su propio PIN confirmando su contraseña («Mi PIN»); las contraseñas incorrectas cuentan para el límite del login (ADR-018).

## 13. Frontend

### 13.1 Áreas

| Área | Dispositivo | Conexión | Estado |
| --- | --- | --- | --- |
| `/ruta` | Teléfono | Opcional | Dexie + motor de cálculo + cola |
| `/admin` | PC | Requerida | TanStack Query contra la API |

- Las áreas se cargan de forma diferida: el teléfono no descarga el código de administración.
- React Context se usa solo para sesión, permisos, conectividad y tema.
- Las pantallas del área de ruta leen siempre de Dexie, con o sin conexión.
- **Ayuda contextual (ADR-051):** el componente `Ayuda` ("(?)") abre un panel no modal con clic, tap o teclado y cierra con Escape o clic afuera. Todos sus textos viven en `frontend/src/ayuda/textos.ts`, por clave, con los IDs de regla que citan; no piden nada a la red ni dependen de permisos, así que también sirven sin conexión. Las páginas "Ver más" están en `/admin/ayuda/:tema` y en `/ruta/ayuda/:tema`; dentro de `/ruta` y de la aplicación instalada el "Ver más" navega dentro de la aplicación (no abre otra pestaña), de modo que funciona sin conexión (ADR-062 punto 21). Una prueba de Vitest verifica que toda clave usada exista y que todo ID citado exista en `01-dominio.md` o en `docs/adr/`.

### 13.2 Base local (Dexie)

| Tabla | Contenido |
| --- | --- |
| `meta` | Versión de esquema local, dispositivo, último correlativo, fecha de bootstrap |
| `sesion` | Usuario, permisos, topes, derivación del PIN, jornada abierta |
| `configuracion` | Parámetros de la organización |
| `productos`, `presentaciones` | Catálogo activo |
| `clientes` | Clientes con datos de crédito |
| `precios` | Versiones de lista disponibles y sus precios |
| `reglas_descuento` | Reglas activas |
| `stock` | Stock de la ubicación tomada |
| `autorizadores` | Derivaciones de PIN de supervisores |
| `ventas`, `cobranzas` | Operaciones locales con estado de sincronización |
| `movimientos_locales` | Efectos locales sobre stock y saldos, para calcular disponibles |
| `cola` | Comandos pendientes ordenados por secuencia |

**DEBE:** confirmar una venta local es una transacción Dexie que escribe la venta, los movimientos locales y el comando en la cola, todo o nada.
En la versión 2 de Dexie (change 21) el saldo viaja dentro de `clientes` (no hay `saldos_clientes`) y las tablas maestras son las que reemplaza el bootstrap; `meta` guarda también el usuario local, la jornada, la fecha del bootstrap y la derivación del PIN con su contador de fallos (`pin_hash`, `pin_sal`, `pin_iteraciones`, `pin_intentos`). El bootstrap reemplaza las tablas maestras en una sola transacción sobre una lista explícita; `ventas`, `cobranzas`, `movimientos_locales` y `cola` las agrega la versión 3 (change 22a) y el bootstrap no las toca (ADR-062).

### 13.3 Motor de sincronización

- Se ejecuta en el hilo principal de la aplicación, no en el service worker: la sincronización en segundo plano no está disponible en todos los navegadores móviles.
- Se dispara al abrir la aplicación, en el evento `online`, después de cada operación local si hay conexión, cada 2 minutos mientras la aplicación está abierta y con el botón "Sincronizar".
- **DEBE:** una sola sincronización a la vez, garantizada con Web Locks API, incluso con varias pestañas abiertas.
- Envía lotes en orden (§6.4), aplica los resultados a la base local y reintenta errores transitorios con espera exponencial.
- Muestra en todo momento: estado de conexión, cantidad de pendientes, última sincronización exitosa y operaciones con observaciones o rechazadas.
- Pide almacenamiento persistente (`navigator.storage.persist()`) tras el primer bootstrap y en cada arranque hasta que se conceda, y muestra una advertencia si el navegador lo niega (ADR-062 punto 18).

### 13.4 Bootstrap

- `GET /api/v1/sync/bootstrap` se ejecuta al abrir la jornada, al iniciar sesión o desbloquear con conexión si faltan los datos de la jornada abierta, y con "Actualizar datos" (RUT-03); devuelve el contenido de SYN-11 en una sola foto (§7.1). Lo compone el módulo `sync` por el `service.py` de cada módulo (ADR-062).
- El contrato acepta un parámetro `since` para descargas incrementales; en la etapa 1 se ignora y siempre devuelve el conjunto completo (ADR-006).
- El bootstrap reemplaza los datos maestros locales, pero **DEBE NO** tocar `ventas`, `cobranzas`, `movimientos_locales` ni `cola`.

### 13.5 Service worker

- Precachea el shell de la aplicación para abrirla sin conexión.
- **DEBE NO** cachear respuestas de la API: los datos offline viven en Dexie.
- Una nueva versión se instala en segundo plano y se aplica con aviso al usuario. **DEBE NO** recargar automáticamente la aplicación mientras hay un carrito abierto.
- Se implementa con `vite-plugin-pwa` (`generateSW`, `registerType: 'prompt'`); precachea el shell, `/ruta`, la ayuda y pdfmake, no el código de `/admin`; el manifiesto abre en `/ruta` (ADR-062).

### 13.6 Nota de venta

- El contenido de la nota lo arma una función pura (`domain/ventas/notaDeVenta.ts`) a partir de un tipo neutro con los valores congelados de la venta; otra función lo convierte en la definición del documento (`lib/nota/documento.ts`, A4 vertical). Cada origen de datos tiene su adaptador: la API en administración (`GET /api/v1/ventas/{id}/nota`, con `VENDER` o `ANULAR_VENTA`) y, en `/ruta`, Dexie (change 22a). Nada del armado conoce pdfmake ni React.
- El PDF se genera en el dispositivo con pdfmake (versión exacta) y sus fuentes embebidas, cargados con `import()` dinámico solo al generar la nota: no pesan en el bundle inicial.
- Se comparte con Web Share API (archivos) solo si el navegador comparte archivos (`navigator.canShare`); la descarga está siempre. Archivo `nota-de-venta-{numero}.pdf`.
- La nota no se guarda: cada generación sale de los datos congelados. La misma función sirve al original y a la reimpresión.

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
- Límite de intentos en login por par escrito (organización y usuario, 5) y por IP (20): cada bloqueo dura 15 minutos desde el último fallo; los intentos durante el bloqueo no cuentan ni lo extienden (ADR-018 enmendado). Nota de despliegue: detrás de Caddy la IP que ve el backend es la del proxy hasta configurar `uvicorn --proxy-headers --forwarded-allow-ips=<IP de Caddy>`, que corrige el límite por IP del login y de «Mi PIN».
- El servidor exige el permiso de cada comando por cualquier camino (ADR-056).
- El límite de 5 del login se cuenta por el par (slug de la organización, usuario) tal como se escribió, exista o no (un nombre inexistente se bloquea igual que uno real); todo rechazo de credenciales verifica la contraseña (hash ficticio si no hay usuario utilizable); el 429 del login muestra siempre la hora de `America/Argentina/Buenos_Aires` (ADR-057, enmienda a ADR-018).
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
