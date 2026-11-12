## Qué resuelve este change

Crea la organización como raíz de todo dato de negocio: tablas `organizacion`, `configuracion_organizacion` y los catálogos configurables (`alicuota_iva`, `medio_pago`, `motivo`), con el patrón de aislamiento (clave única compuesta, FK compuestas, repositorios con `organizacion_id` obligatorio) que todos los changes siguientes copian.

## Why

TR-08 exige que todo dato de negocio pertenezca a una organización y solo sea visible desde ella; INV-02 lo eleva a invariante. Ninguna tabla de negocio puede crearse antes de que exista `organizacion` y el patrón de FK compuestas de `03` §2.4, porque cada tabla posterior lo referencia. TR-09 exige además que motivos, medios de pago y alícuotas sean datos de la organización y no constantes en código: si el change 05 (catálogo) llega antes que `alicuota_iva`, el producto no tiene a qué apuntar. `04` §3 lo ordena explícitamente: "la base primero".

## What Changes

- **Módulo `identidad`** (`03` §3): modelos, repositorio y servicio de `organizacion` y `configuracion_organizacion`, con las columnas exactas de `03` §4 y los parámetros de `01` §4.
- **Módulo `configuracion`** (`03` §3): modelos, repositorio y servicio de `alicuota_iva`, `medio_pago` y `motivo` (TR-09), con `ambito` de `motivo` restringido a la lista cerrada de `03` §4.
- **Migración de Alembic** con `UNIQUE (organizacion_id, id)` en toda tabla de negocio y las FK compuestas de `03` §2.4; `configuracion_organizacion` con PK = FK a `organizacion`.
- **Contrato de repositorio**: ningún método de repositorio existe sin `organizacion_id` como primer parámetro obligatorio (`02` §8). Se verifica con una prueba que inspecciona las firmas.
- **Ratchet de INV-21**: prueba de integración que recorre dinámicamente las rutas registradas de FastAPI (`02` §15) y falla si aparece una ruta de negocio no cubierta por la verificación de aislamiento. Hoy solo existen `/salud` y `/version` (rutas de sistema), así que la prueba es el portón que obliga a cada change siguiente a declarar sus rutas.
- **Siembra idempotente de la organización inicial** con los valores de la columna "Organización inicial" de `01` §4 (ARS, `America/Argentina/Mendoza`, modo A, política `AUTORIZAR`, alícuotas 21 / 10,5 / 0, cinco medios de pago, seis motivos de ajuste, `intentos_pin_max` = 5), fuera de las migraciones (ver `design.md` D4).

## No incluye

- Usuario, rol, permiso, `rol_permiso`, dispositivo, `sesion_refresh`, login, JWT, refresh rotativo y PIN: todo eso es el change 03.
- Endpoints HTTP de negocio y la dependencia que extrae `organizacion_id` del token: requieren el JWT del change 03 (`design.md` D1). Este change no expone ninguna ruta nueva.
- Pantalla de administración: sin login no hay dónde colgarla (`design.md` D5).
- FK reales de `lista_precio_default_id` (change 13) y `cliente_consumidor_final_id` (change 07): las columnas se crean nulables y sin restricción; la FK compuesta la agrega la migración del change que crea la tabla destino (`design.md` D3).
- Alta y edición de organizaciones por comando: el bus llega en el change 04.
- Fixtures compartidos de cálculo: este change no toca precios, descuentos ni costos.

## Invariantes

- **INV-02** (todo dato de negocio pertenece a exactamente una organización): lo cierra con `organizacion_id NOT NULL`, `UNIQUE (organizacion_id, id)` y FK compuestas verificadas contra `information_schema`.
- **INV-21** (ningún usuario obtiene ni modifica datos de otra organización): lo cierra parcialmente a nivel de datos (dos organizaciones, un repositorio, cero filtraciones) y deja instalado el ratchet de rutas que lo completa a medida que aparecen endpoints.

## Capabilities

### New Capabilities
- `organizacion/aislamiento-multiorganizacion`: contrato de aislamiento — columna obligatoria, unicidad compuesta, FK compuestas, repositorios sin acceso sin organización, y el ratchet de rutas (INV-02, INV-21).
- `organizacion/parametros-de-organizacion`: qué es una organización y qué parámetros configurables tiene (`01` §4, `03` §4).
- `organizacion/catalogos-configurables`: alícuotas de IVA, medios de pago y motivos como datos de la organización (TR-09).

### Modified Capabilities
(ninguna)

## Impact

- Código nuevo: `backend/app/modules/identidad/`, `backend/app/modules/configuracion/`, una revisión de Alembic, `backend/tests/{unit,integration}/`.
- Configuración: contratos de import-linter para los dos módulos nuevos.
- Dependencias: ninguna nueva.
