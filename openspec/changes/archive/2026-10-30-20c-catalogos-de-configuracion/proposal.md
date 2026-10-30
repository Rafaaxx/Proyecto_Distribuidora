# Change 20c-catalogos-de-configuracion

## Qué resuelve este change

Permite administrar desde `/admin` los motivos de cada ámbito y las alícuotas de IVA (alta, cambio de nombre, baja y reactivación, sin borrar nada) y definir el redondeo por defecto de la organización, que precarga el formulario de una lista de precios nueva.

## Why

`04` §9 (fila 20c y "Deudas reasignadas", 2026-10-24): TR-09 dice que motivos y alícuotas son datos de la organización, pero hoy solo se siembran por migración y se leen (deudas del 17b, D10, y del 18b); el redondeo por defecto de `01` §4 sigue "a definir" sin comando (deuda de ADR-047, change 13). El 21 baja motivos y alícuotas en el bootstrap: espera a este change.

## What Changes

- **Motivos** (`design.md` D2 a D5): comandos `MOTIVO_CREAR` y `MOTIVO_MODIFICAR` v1 (solo `ONLINE`, por el bus, auditados). El ámbito es de la lista cerrada y no cambia; el nombre se recorta y es único por organización y ámbito sin distinguir mayúsculas; la baja es desactivar y se puede reactivar; ningún ámbito se queda sin motivo activo (`ULTIMO_MOTIVO_ACTIVO`). Lectura de todos los motivos (activos e inactivos) para la pantalla.
- **Alícuotas** (D6 a D9): `ALICUOTA_CREAR` y `ALICUOTA_MODIFICAR` v1. El porcentaje no cambia una vez creada (para otra tasa se crea otra); nombre y valor únicos por organización; no se da de baja una alícuota que use un producto activo (`ALICUOTA_EN_USO`) ni la última activa. El uso lo informa `catalogo` por un verificador registrado.
- **Redondeo por defecto** (D10, D11): `REDONDEO_POR_DEFECTO_DEFINIR` v1 (múltiplo y dirección, o los dos vacíos), con las mismas reglas que el redondeo de una lista (PRC-01, PRC-14). El formulario de una lista nueva lo precarga; cambiarlo no toca las listas existentes.
- **Pantallas** (D12): pestañas "Motivos", "Alícuotas de IVA" y "Redondeo por defecto" en Configuración; ayuda contextual sin ejemplos (D14).
- **Migración**: índices únicos y `CHECK` (valor de la alícuota, coherencia del redondeo). **ADR-061** (*Propuesto*) y `propuesta-docs.md`.

## Decisiones

`design.md` D0 a D15, **todas APROBADAS el 2026-10-30 con la opción A (recomendada)**; ninguna estaba resuelta en `docs/`. De negocio (decide el usuario): D1 (quién administra), D2, D4, D5 (motivos), D6, D8 (alícuotas), D10, D11 (redondeo). Gobernanza **BAJA** (`04` §9).

## No incluye

Ámbitos nuevos de motivos (la lista cerrada de `03` §4 no cambia); borrar motivos o alícuotas (INV-05); cambiar en masa la alícuota de los productos; tocar listas existentes o recalcular precios; el bootstrap con motivos y alícuotas y su uso sin conexión (21, 22a); reportes por motivo (26).

## Reglas e invariantes

- **TR-09, CAT-05, TR-06, `01` §4:** catálogos propios, baja sin borrar, lectura por id de los inactivos.
- **PRC-01, PRC-14:** dominio del redondeo por defecto; no participa del cálculo del precio.
- **CAT-01, IMP-04:** el producto exige una alícuota activa; la importación la resuelve por porcentaje (de ahí el valor único).
- **AUD-01:** cambios de configuración con antes y después.
- **INV-01** (todo o nada), **INV-02/INV-21** (por organización del token; ajeno → 404), **INV-03** (valor y múltiplo como string decimal), **INV-05** (sin `DELETE`), **INV-06** (doble envío). No cierra invariantes de `01` §20.
- No cambia ninguna regla de cálculo de precios, descuentos ni costos: **sin fixtures compartidos**.

## Capabilities

### New Capabilities

- `organizacion/administracion-de-motivos`: comandos, reglas de nombre y de baja, lectura completa y pantalla de motivos por ámbito.
- `organizacion/administracion-de-alicuotas`: comandos, valor inmutable, reglas de baja con el uso por productos, lectura y pantalla.

### Modified Capabilities

- `organizacion/catalogos-configurables`: la lista de ámbitos se completa (faltaban `ANULACION_TRANSFERENCIA` y `ANULACION_AJUSTE`) y nombre y valor pasan a ser únicos.
- `organizacion/parametros-de-organizacion`: el redondeo por defecto se define por comando y desde la pantalla.
- `precios/administracion-de-listas`: el formulario de una lista nueva precarga el redondeo por defecto.
- `sistema/pipeline-de-comandos`: tipos nuevos en el catálogo.
- `sistema/ayuda-contextual`: textos de motivos, alícuotas y redondeo por defecto.

## Impact

Backend: `configuracion/`, `catalogo/` (verificador de uso y bloqueo compartido de la alícuota), `identidad/` (redondeo en `configuracion_organizacion`), una migración, ratchets. Frontend: `areas/admin/configuracion/`, `features/configuracion/`, `ListaFormScreen.tsx`, `ayuda/textos.ts`.
