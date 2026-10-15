# Change 16-motor-de-descuentos

## Qué resuelve este change

Crea las reglas de descuento por volumen y el motor que las resuelve (DSC-01 a DSC-05, DSC-07), gemelo en Python y TypeScript con casos compartidos, y la evaluación del descuento manual contra el tope del rol (DSC-06). No toca la venta: la consume el 18b.

## Why

`04` §8 (hito 4). Hoy no existe el módulo `descuentos`: solo están los permisos, los topes (`rol.tope_descuento` en cero para Supervisor y Vendedor, sin comando que los cambie) y dos parámetros de la organización. El 18b y el bootstrap del 21 necesitan reglas y un cálculo idéntico en servidor y dispositivo (ADR-004, ADR-016).

## What Changes

- **Reglas de descuento** (tablas `regla_descuento` y `regla_descuento_alcance`, `03` §11): cuatro comandos solo `ONLINE` con `GESTIONAR_DESCUENTOS` (`REGLA_DESCUENTO_CREAR`, `_MODIFICAR`, `_ACTIVAR`, `_PAUSAR`), máquina `BORRADOR → ACTIVA ↔ PAUSADA` con `VENCIDA` derivada (`01` §18) y lecturas.
- **Motor puro** en `descuentos/domain/` y `frontend/src/domain/descuentos/`: condición de volumen con operador explícito sobre cajas equivalentes, unidades base o importe bruto (DSC-03); porcentaje o importe fijo repartido con remanente (DSC-04); orden de resolución (DSC-05); redondeo por línea (DSC-07).
- **Descuento manual** (gobernanza crítica): un porcentaje general por venta y, opcionalmente, uno propio por línea, que lo reemplaza en esa línea (no se suman); aplicación sobre el resultado de cada línea (DSC-05 paso 5) y evaluación de tope y autorización requerida (DSC-06), una por venta y contra el mayor porcentaje manual entre las líneas, como función pura y servicio. No verifica PIN ni persiste nada.
- **Tope por rol** (gobernanza crítica): comando `ROL_TOPE_DESCUENTO_DEFINIR` (`ADMIN_USUARIOS`) y su pantalla.
- **Fixtures compartidos nuevos:** `shared/fixtures/calculo/dsc-05-descuentos.json` (`"motor": "dsc05"`) y `dsc-06-descuento-manual.json` (`"motor": "dsc06"`), escritos antes del código, corridos por pytest y Vitest.
- **Pantallas `/admin`:** reglas (listado, alta, edición de borrador, activar, pausar) y topes por rol.

## Decisiones (bloqueantes)

`design.md` D0 a D20, **aprobadas por el usuario el 2026-10-13**: opción A en todas, salvo D11, aprobada como **A+B combinadas** (porcentaje general por venta más porcentaje propio opcional por línea, que reemplaza al general; el tope se compara contra el mayor). Los dos subpuntos que nacieron de D11 también están aprobados (2026-10-13, opción A): el porcentaje propio de una línea no puede ser 0 (D11.1) y el motivo es uno por venta (D11.2). No queda ninguna decisión abierta. De negocio y sin resolver en `docs/`: alcance frente a `00` §6 (D1), frontera con el 18b (D2), cajas equivalentes (D5), un ganador por venta y desempates (D7, D8), acumulables e importe fijo (D9, D10), forma del manual (D11), autorización (D12), tope por rol (D13), motivo (D14), edición y vigencia (D15, D16). Requieren **ADR-050**.

**Contradicciones de `docs/`:** `00` §6.1 y §6.2 dejan alcance por categoría o marca y "acumulabilidad completa" para la etapa 2; `01` DSC-02, `03` §11, `04` y ADR-004 los ponen en la etapa 1 (D1). ADR-004, ADR-016 y `02` §10.4 ubican el motor en tres lugares distintos (D3).

## Tamaño

Cuatro lotes en un solo change (D0 = A, aprobada). Supera `04` §2; se anota la excepción.

## No incluye

Descuentos en la venta, `venta_linea_descuento`, recálculo y `DESCUENTO_DIFIERE` (DSC-08, DSC-09), verificación del PIN, auditoría de descuentos manuales y la pantalla de venta donde se carga el porcentaje general y el de cada línea (18b). Descuento manual en pesos. Totales e IVA (VTA-04, 18a). Bootstrap de reglas (21). DSC-10 y toda condición fuera de DSC-03 (etapa 2). Simulador de reglas. Tope por usuario, comando de configuración del descuento manual y motivos (D13, D14).

## Invariantes

- **INV-03:** importes y porcentajes como decimal exacto en ambos motores; casos compartidos comparados como texto.
- **INV-01** (regla y alcances, todo o nada), **INV-02, INV-21** (tabla y rutas nuevas en los ratchets), **INV-06** (doble envío).
- **INV-10 e INV-14** no se tocan: los cierra la venta.

## Capabilities

### New Capabilities

- `descuentos/reglas-de-descuento`: alta, edición, estados, vigencia, alcance y consultas (DSC-01, DSC-02, DSC-03; `01` §18).
- `descuentos/motor-de-descuentos`: cálculo compartido (DSC-03, DSC-04, DSC-05, DSC-07).
- `descuentos/descuento-manual`: porcentaje general y por línea, aplicación, tope y autorización requerida (DSC-05, DSC-06).
- `descuentos/administracion-de-descuentos`: pantallas de `/admin`.

### Modified Capabilities

- `identidad/usuarios-y-roles`: el tope de descuento de un rol se define por comando.

## Impact

Backend: módulo nuevo `descuentos/`, `identidad/` (tope por rol), `catalogo/api.py` (lecturas para elegir alcance), `pyproject.toml` (import-linter), `main.py`, una migración, ratchets. Frontend: `domain/descuentos/`, `features/descuentos/`, `areas/admin/descuentos/`. `shared/fixtures/calculo/`. Docs `00` a `04` y ADR-050 al cierre. Gobernanza **media** con piezas **críticas** (autorización y tope) y **altas** (permisos de lectura).
