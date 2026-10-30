# ADR-061 — Catálogos de configuración: motivos por ámbito y alícuotas administrables sin borrar, ámbito y porcentaje fijos, ningún ámbito sin motivo ni producto activo con alícuota de baja, y redondeo por defecto que solo precarga la lista nueva

| Campo | Valor |
| --- | --- |
| Estado | Vigente (2026-10-30, archivo del change 20c) |
| Fecha | 2026-10-30 |
| Referenciado en | `openspec/changes/20c-catalogos-de-configuracion/design.md` D0 a D15 y `specs/organizacion/administracion-de-motivos`, `specs/organizacion/administracion-de-alicuotas`, `specs/organizacion/catalogos-configurables`, `specs/organizacion/parametros-de-organizacion`, `specs/precios/administracion-de-listas`, `specs/sistema/pipeline-de-comandos`, `specs/sistema/ayuda-contextual`; `01-dominio.md` §4, §19, TR-09, CAT-01, CAT-05, IMP-04, PRC-01, PRC-14, AUD-01, INV-01, INV-02, INV-03, INV-05, INV-06, INV-21; `02-arquitectura.md` §6.5, §11; `03-modelo-de-datos.md` §4; ADR-023 (puerto de verificación), ADR-043, ADR-047 (deuda del redondeo por defecto), ADR-051, ADR-053 (patrón de medios de pago), ADR-056 |

**Change 20c. Gobernanza BAJA. El usuario aprobó el 2026-10-30 todas las decisiones de `design.md` (D0 a D15) con la opción A y los seis textos de ayuda de D14.**

## Contexto

TR-09 dice que motivos y alícuotas son datos de la organización, pero hasta el change 20c solo se sembraban por migración y se leían: no había comando para agregarlos, renombrarlos ni darlos de baja (deudas del 17b, D10, y del 18b). `01` §4 dejaba "a definir" el redondeo por defecto de la organización y ADR-047 lo dejó como deuda; el formulario de lista nueva precargaba 100 / ARRIBA fijos en el código. ADR-053 estableció el patrón para los medios de pago (crear y modificar con reemplazo completo, nombre único, baja sin borrar con un mínimo activo, dos filas de auditoría).

## Decisión (aprobada 2026-10-30)

1. **Alcance (D0).** Un change en tres lotes: migración y motivos; alícuotas y redondeo por defecto; pantallas, ayuda, ADR, docs y prueba manual.
2. **Permiso (D1).** `ADMIN_CONFIGURACION` para motivos, alícuotas y redondeo por defecto; sin permiso nuevo.
3. **Motivos (D2, D3, D5).** `MOTIVO_CREAR` (ámbito, nombre) y `MOTIVO_MODIFICAR` (nombre y activo), v1, solo `ONLINE`. El ámbito es de la lista cerrada (los diez de `03` §4, sin ámbitos nuevos) y no cambia después del alta. Nombre recortado, único por organización y ámbito sin distinguir mayúsculas, activo o no (`ux_motivo__nombre`). Renombrar está permitido.
4. **Baja de motivos (D4).** Libre y reversible, salvo que el ámbito se quede sin motivo activo (`ULTIMO_MOTIVO_ACTIVO`, 409), con bloqueo `FOR UPDATE` de los motivos del ámbito antes de contar.
5. **Alícuotas (D6, D7).** `ALICUOTA_CREAR` (nombre, valor) y `ALICUOTA_MODIFICAR` (nombre y activo), v1, solo `ONLINE`. **El valor no cambia** (`VALOR_NO_MODIFICABLE`): otra tasa es otra alícuota. Nombre y valor únicos por organización, activa o no (`ux_alicuota_iva__nombre`, `ux_alicuota_iva__valor`; IMP-04). Valor en `[0, 1)` con hasta 6 decimales (`ck_alicuota_iva__valor`).
6. **Baja de alícuotas (D8, D9).** Rechazada si la usa un producto activo (`ALICUOTA_EN_USO`, con la cantidad) o si es la última activa (`ULTIMA_ALICUOTA_ACTIVA`). `configuracion` expone un puerto de verificación que `catalogo` registra (precedente ADR-023); la baja bloquea `FOR UPDATE` la alícuota y la lectura de la alícuota en el alta o modificación de un producto usa `FOR SHARE`.
7. **Redondeo por defecto (D10, D11).** `REDONDEO_POR_DEFECTO_DEFINIR` v1, solo `ONLINE`: múltiplo y dirección, los dos o ninguno, con el dominio de PRC-01 y PRC-14 (`REDONDEO_INVALIDO`). `CHECK` de coherencia y de múltiplo positivo. Lectura con `ADMIN_CONFIGURACION` o `GESTIONAR_LISTAS`. Solo precarga el formulario de una lista nueva; sin definir, el formulario empieza vacío (se quita el 100 / ARRIBA del código). No toca listas existentes ni el cálculo del precio.
8. **Pantallas, auditoría y ayuda (D12 a D14).** Pestañas "Motivos", "Alícuotas de IVA" y "Redondeo por defecto" en Configuración; lectura completa de motivos (`/motivos/todos`); auditoría como medios de pago (fila del bus y fila de la entidad con antes y después); seis claves de ayuda sin ejemplos.
9. **Change 21 (D15).** Funciones públicas para listar motivos y alícuotas activos y leer el redondeo por defecto; sin ruta de bootstrap.

## Precisiones del apply

- **Códigos de error.** `ULTIMO_MOTIVO_ACTIVO`, `VALOR_DUPLICADO`, `ALICUOTA_EN_USO` y `ULTIMA_ALICUOTA_ACTIVA` responden 409; `VALOR_NO_MODIFICABLE`, `NOMBRE_INVALIDO`, `AMBITO_INVALIDO`, `REDONDEO_INVALIDO` y `CONFIGURACION_VALOR_ALICUOTA_INVALIDO` responden 422 (este último pasó de 400 a 422 al alinearse con los demás errores de validación del cuerpo).
- **`ALICUOTA_EN_USO` informa la cantidad.** El Problem Details trae la clave `productos` con la cantidad de productos activos que usan la alícuota; la pantalla la muestra.
- **Lecturas.** `GET /configuracion/motivos/todos` (con `ambito` opcional) lista activos e inactivos. `GET /configuracion/alicuotas` sigue paginada, incluye las inactivas y admite también `ADMIN_CONFIGURACION`. `GET /configuracion/redondeo-por-defecto` devuelve `{multiplo, direccion}`, ambos nulos si no está definido.
- **Porcentaje en pantalla.** La pantalla de alícuotas pide el porcentaje ("10,5") y lo envía como fracción string de seis decimales (`"0.105000"`) con una división exacta por 100 en `decimal.js`; más de cuatro decimales en el porcentaje, negativo o 100 o más se rechazan antes de enviar. El servidor valida igual.
- **Formulario de lista nueva.** Con redondeo por defecto definido, el formulario de lista nueva lo trae; sin definir, el múltiplo queda vacío y la dirección sin elegir, y no se envía hasta completarlos. La lista que se edita muestra siempre el suyo.
- **Historia congelada.** Una compra y una venta confirmadas conservan su `alicuota_aplicada` aunque la alícuota se renombre o se dé de baja (TR-06, VTA-03).

## Consecuencias

- Ninguna operación queda imposible por falta de motivo o de alícuota activa, y ningún producto activo queda con una alícuota de baja.
- Cambiar una tasa de IVA son varios pasos (crear, mover productos, dar de baja); a cambio, ningún cálculo futuro cambia en silencio.
- Renombrar un motivo o una alícuota cambia cómo se lee la historia (las operaciones guardan el id), igual que con los medios de pago.
- Sin fixtures compartidos: ninguna regla de cálculo cambia.

## Deudas nominadas

- **Al 21 (`pwa-y-bootstrap`):** bajar motivos y alícuotas activos en el bootstrap (SYN-11) con las funciones públicas del 20c.
- **Al 22a/22c:** qué pasa con un motivo dado de baja usado en un comando sin conexión fuera del descuento manual (que ya tiene la causa `MOTIVO` de `DESCUENTO_DIFIERE`, DSC-09).
- **Pestañas de Configuración por permiso (14.2).** La prueba manual mostró que `vendedor` veía "Fiscal" y "Lista predeterminada" porque estaban fuera de `<SiTienePermiso>`. "Fiscal" se ofrece con `ADMIN_CONFIGURACION`; "Lista predeterminada" con `ADMIN_CONFIGURACION`, `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`, los permisos de su lectura. El backend no cambia.
