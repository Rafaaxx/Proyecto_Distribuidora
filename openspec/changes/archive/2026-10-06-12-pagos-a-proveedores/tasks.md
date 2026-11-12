# Tareas — 12-pagos-a-proveedores

> Modo TDD estricto: en cada tarea de los grupos 1 a 10, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como red de seguridad y se anota la línea base. El grupo 11 completa la cobertura por escenario e invariante; no la reemplaza. Las tareas están escritas con la **opción A (recomendada)** de cada decisión de `design.md`; si la tarea 0.1 aprueba otra, se actualizan con `/opsx:update` antes de empezar.
>
> **Lotes de apply:** Lote 1 = grupos 0 a 4 (migración, dominio y registro del pago de punta a punta por API). Lote 2 = grupos 5 a 7 (anulación, consultas y saldo). Lote 3 = grupos 8 a 13 (pantallas, concurrencia, cobertura, docs y verificación manual). El usuario revisa cada lote antes de seguir con el siguiente.
>
> **Fixtures compartidos:** este change no agrega ni modifica reglas de cálculo de precios, descuentos ni costos; no hay tarea de fixtures. Si durante el apply aparece un cálculo compartido entre Python y TypeScript más allá de sumar medios, se detiene y se agrega el fixture antes del código.

## 0. Aprobación (bloqueante)

- [x] 0.1 El usuario revisa y aprueba (o cambia) D0 a D11 de `design.md`, de a una y con su ejemplo: las tres deudas del change 11 (D1 motivo de anulación y nombres de los motivos; D2 pago de una compra de contado; D3 pago mayor que la deuda y saldo a favor), D4 fecha, D5 proveedor inactivo, D6 medios y observación, D7 permisos de lectura, D8 saldo de proveedor, D9 migración, D10 bloqueos y D11 pantallas. Se anota fecha y opción en cada decisión. Si alguna difiere de la recomendada, se actualizan proposal, specs y tareas con `/opsx:update`. Verificable: `design.md` sin decisiones "PENDIENTE".

## 1. Migración (Lote 1)

- [x] 1.1 RED: `backend/tests/integration/test_pagos_proveedor_migracion.py` exige (D9): `ck_motivo__ambito` admite `ANULACION_PAGO` y rechaza un ámbito desconocido; motivos "Error de carga", "Pago rechazado o devuelto" y "Otro" sembrados una sola vez en organizaciones existentes sin motivos de ese ámbito; `pago_proveedor.observacion` nulable; `CHECK` de anulación estricto (una fila `ANULADA` sin motivo se rechaza); índices de listado; privilegios de `app_runtime` sin cambios (sin `DELETE`, `UPDATE` solo sobre estado y anulación, `observacion` no actualizable; cita INV-05). GREEN: una revisión de Alembic; el `upgrade` aborta con mensaje claro si existe un pago `ANULADA` sin motivo. Verificable: la prueba pasa.
- [x] 1.2 RED: ciclo `upgrade → downgrade → upgrade` sobre una base con datos sembrados (un pago de contado, un pago anulado junto con su compra y un pago anulado con motivo `ANULACION_PAGO`): sube y baja limpio, no duplica motivos y deja como aserción explícita qué pierde el `downgrade` (motivos de `ANULACION_PAGO` y observaciones). GREEN si hace falta. Verificable: `04` §2.1 punto 4.
- [x] 1.3 RED: la prueba de catálogo de columnas (INV-03) y `test_modelos_coinciden_con_migracion.py` incluyen la columna nueva. GREEN en el paso 2.1.

## 2. Modelos, catálogo de ámbitos y siembra (Lote 1)

- [x] 2.1 Red de seguridad: suites de `configuracion`, `compras` y `seed` en verde. RED: `AMBITOS_MOTIVO` incluye `ANULACION_PAGO` (unitaria de dominio de `configuracion`) y `GET /configuracion/motivos?ambito=ANULACION_PAGO` devuelve solo los activos de la organización (spec `organizacion/catalogos-configurables`). GREEN: `configuracion/domain/valores.py` y `PagoProveedor.observacion` y el `CHECK` nuevo en `proveedores/models.py`, iguales a la migración (`alembic revision --autogenerate` sin diferencias).
- [x] 2.2 RED: la prueba de siembra exige los motivos de `ANULACION_PAGO` de D1 en una organización nueva. GREEN en `app/seed.py`.

## 3. Dominio de pagos (Lote 1, funciones puras)

- [x] 3.1 Red de seguridad: `tests/unit` de dominio de compras y `test_compras_contado.py` en verde. RED en `backend/tests/unit/test_proveedores_domain_pagos.py`: `validar_medios(importe, medios)` (D6) con suma exacta (`MEDIOS_NO_SUMAN_IMPORTE`), sin medios y más de 20 (`MEDIOS_INVALIDOS`), importe de medio no positivo o con tres decimales (`IMPORTE_INVALIDO`), referencia obligatoria vacía o de solo espacios (`REFERENCIA_OBLIGATORIA`), mismo medio repetido válido; propiedad Hypothesis: todo pago aceptado tiene suma de medios igual al importe (cita INV-08). GREEN en `proveedores/domain/pagos.py`, sin imports de infraestructura.
- [x] 3.2 RED: `validar_pago_independiente` (importe mayor que cero con 2 decimales, fecha no futura con `FECHA_INVALIDA`, observación recortada y vacía como nula, D4 y D6) y las reglas puras de anulación (`PAGO_YA_ANULADO`; pago de origen `COMPRA` con compra `CONFIRMADA` → `PAGO_DE_COMPRA_VIGENTE`, con compra `ANULADA` admitido, D2). GREEN con los errores nuevos como `DomainError` de código estable en `proveedores/domain/errores.py`.
- [x] 3.3 REFACTOR con red de seguridad: `validar_pago` de compras delega la parte de medios en `validar_medios` sin cambiar su contrato ni sus códigos. Verificable: suite completa de compras (unitarias, integración y fixtures `cmp-02`) en verde, igual que la línea base.

## 4. Registro del pago de punta a punta (Lote 1)

- [x] 4.1 RED en `backend/tests/integration/test_pagos_proveedor_registrar.py` con los escenarios de la spec `proveedores/pagos-a-proveedores`: efectivo + transferencia por `"152460.00"`; pago parcial (`"153720.00"` → `"53720.00"`); pago mayor que la deuda (`"-6280.00"`, D3) y compra a crédito siguiente (`"93720.00"`); medio inactivo, de otra organización (404) y sin referencia; proveedor ajeno (404, cita INV-21) e inactivo admitido (D5); fecha futura; `OFFLINE` rechazado; costo promedio y stock intactos (PAG-02); `SALDO_INICIAL_REGISTRAR` posterior rechazado (CC-08); idempotencia y `COMANDO_INCONSISTENTE` (cita INV-06); 403 sin `REGISTRAR_PAGO_PROVEEDOR`; una sola fila de auditoría (AUD-01). GREEN: `proveedores/service.py::registrar_pago` (`bloquear_saldo`, luego pago, medios y `PAGO`, D10), repositorio `insertar_pago` generalizado sin cambiar lo que escribe la compra, y el handler `PAGO_PROVEEDOR_REGISTRAR` v1 (`ONLINE`).
- [x] 4.2 RED: falla inyectada después de insertar el pago y antes del movimiento de cuenta → ningún efecto (cita INV-01). GREEN si hace falta.
- [x] 4.3 RED en `backend/tests/integration/test_pagos_proveedor_api.py`: `POST /api/v1/pagos-proveedores` (`Operation-Id` obligatorio, importes como string, Problem Details con el índice del medio en errores de medio, 201 con el pago y el saldo resultante). GREEN: ruta, esquemas Pydantic y tipos de OpenAPI regenerados (`npm run generate:api-types`). Verificable: `ruff`, `mypy` y `lint-imports` limpios.

## 5. Anulación del pago (Lote 2)

- [x] 5.1 Red de seguridad: `test_compras_anular.py` y `test_compras_concurrencia.py` en verde. RED en `backend/tests/integration/test_pagos_proveedor_anular.py` con los escenarios de la spec `proveedores/anulacion-de-pagos`: pago independiente anulado (saldo vuelve a `"152460.00"`, pago `ANULADA` con motivo, usuario y momento, `ANULACION_PAGO` con origen en el pago); `PAGO_YA_ANULADO`; `MOTIVO_INVALIDO` (otro ámbito, inactivo, ajeno); 403 sin `ANULAR_PAGO_PROVEEDOR`; 404 ajeno (cita INV-21); proveedor inactivo; `OFFLINE` rechazado; idempotencia (cita INV-06); auditoría única. GREEN: `proveedores/service.py::anular_pago` con el orden compra → pago `FOR UPDATE` → `saldo_cuenta` (D10) y el handler `PAGO_PROVEEDOR_ANULAR` v1.
- [x] 5.2 RED: pago de origen `COMPRA` (D2): compra `CONFIRMADA` → `PAGO_DE_COMPRA_VIGENTE`; compra anulada con `devuelve_pago = false` → se anula y el saldo pasa de `"-152460.00"` a `"0.00"`; compra anulada con `devuelve_pago = true` → `PAGO_YA_ANULADO`. GREEN.
- [x] 5.3 RED: falla inyectada después de marcar el pago y antes del movimiento → el pago sigue `CONFIRMADA` sin efectos (cita INV-01); tras anular, el pago, sus medios y el `PAGO` original siguen intactos y `app_runtime` no puede borrarlos (cita INV-05). GREEN si hace falta.
- [x] 5.4 RED: `POST /api/v1/pagos-proveedores/{id}/anulacion` en `test_pagos_proveedor_api.py`. GREEN y tipos regenerados.

## 6. Consultas y saldo (Lote 2)

- [x] 6.1 RED: `GET /api/v1/pagos-proveedores` (filtros proveedor, estado, origen y fechas; cursor; límite 1 a 200 con 422 fuera de rango; `RANGO_DE_FECHAS_INVALIDO`; `CURSOR_INVALIDO`; pagos de origen `COMPRA` incluidos con su `compra_id`; 403 sin ninguno de los dos permisos; aislamiento) y `GET /api/v1/pagos-proveedores/{id}` (medios con nombre, observación, compra, anulación; 404 ajeno). GREEN en `proveedores/queries.py` y `api.py`, con carga explícita de relaciones.
- [x] 6.2 RED: `GET /api/v1/proveedores/{id}/saldo` (D8): string desde `cuentas_corrientes/service.py::obtener_saldo`, `"0.00"` sin movimientos, permitido con `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o `REGISTRAR_COMPRA`, 403 sin ninguno, 404 ajeno. GREEN.
- [x] 6.3 RED: `GET /api/v1/proveedores/opciones` también responde con solo `REGISTRAR_PAGO_PROVEEDOR` y sigue respondiendo con los permisos anteriores (D7). GREEN.

## 7. Ratchets (Lote 2)

- [x] 7.1 RED: las rutas nuevas entran en los ratchets de aislamiento (`test_inv21_aislamiento_endpoints_proveedores.py`, `test_inv21_ratchet_rutas.py`; cita INV-21), de permiso por ruta (`test_ratchet_permiso_por_ruta.py`) y de escritura por el bus (`test_bus_cobertura_rutas_de_escritura.py`); `organizacion_id` solo del token. GREEN. Verificable: suite completa de backend en verde.

## 8. Frontend: dominio y datos (Lote 3)

- [x] 8.1 RED en `frontend/tests/unit/domain/pagos-proveedores/`: suma de medios, faltante o sobrante y saldo resultante con `decimal.js` (sin `number`), rótulo del saldo resultante ("Le debemos" / "Saldo a nuestro favor"), esquema Zod del formulario (importe, fecha no futura, referencia obligatoria por medio, 1 a 20 medios). GREEN en `frontend/src/domain/pagos-proveedores/`.
- [x] 8.2 RED en `frontend/tests/unit/features/pagos-proveedores/`: hooks de TanStack Query para listar, detallar, registrar y anular (mismo `Operation-Id` al reintentar tras error de red, nuevo al cambiar el contenido), saldo del proveedor, e invalidación del saldo y del estado de cuenta al registrar o anular. GREEN en `frontend/src/features/pagos-proveedores/`.

## 9. Pantallas `/admin` (Lote 3)

- [x] 9.1 RED en `frontend/tests/unit/areas/admin/pagos-proveedores/`: menú y rutas por permiso (spec `proveedores/administracion-de-pagos`); alta con saldo actual y resultante, faltante de medios con el botón deshabilitado, referencia obligatoria, confirmación explícita cuando queda saldo a nuestro favor ($ 6.280,00), error del servidor junto a su medio, aviso de conexión. GREEN en `frontend/src/areas/admin/pagos-proveedores/` (sin lógica de negocio en componentes).
- [x] 9.2 RED: listado paginado con filtros, detalle con medios y enlace a la compra, anulación con motivo de `ANULACION_PAGO` y saldo resultante, "Anular" ausente en el pago de una compra vigente, mensaje ante `PAGO_YA_ANULADO`. GREEN.
- [x] 9.3 RED en las pruebas de `cuentas-corrientes`: "Registrar pago" solo con `REGISTRAR_PAGO_PROVEEDOR` y con el proveedor precargado; enlaces de `PAGO`/`ANULACION_PAGO` y `COMPRA`/`ANULACION_COMPRA` a su operación solo con permiso de lectura. GREEN en `CuentaCorrienteScreen.tsx`.
- [x] 9.4 Red de seguridad: pruebas de `CompraFormScreen` en verde. RED: aviso de saldo a nuestro favor al elegir un proveedor con saldo negativo, ausente con saldo cero o positivo y cuando la lectura falla (spec `proveedores/administracion-de-compras`). GREEN. Verificable con `npm run test`, `npm run typecheck` y `npm run lint`.

## 10. Concurrencia (Lote 3)

- [x] 10.1 RED en `backend/tests/concurrency/test_pagos_proveedor_concurrencia.py` (commits reales, limpieza al final): dos pagos simultáneos al mismo proveedor → ambos aplicados y saldo igual a la suma del libro (cita INV-13); dos anulaciones simultáneas del mismo pago → una `PAGO_YA_ANULADO` y una sola `ANULACION_PAGO`; `COMPRA_ANULAR` con `devuelve_pago = true` en paralelo con `PAGO_PROVEEDOR_ANULAR` de su pago → sin interbloqueo y una sola `ANULACION_PAGO` (D10); pago en paralelo con una compra a crédito del mismo proveedor; mismo `Operation-Id` en paralelo → un solo efecto (cita INV-06). GREEN si hace falta. Una falla intermitente no se ignora.

## 11. Cobertura por escenario e invariante (Lote 3)

- [x] 11.1 Propiedad contra PostgreSQL real (`backend/tests/properties/test_pagos_inv08_inv13.py`): secuencias aleatorias válidas de compras a crédito, pagos y anulaciones dejan `saldo_cuenta` igual a la suma de `cuenta_movimiento` (cita INV-13) y cada pago con suma de medios igual a su importe, comprobado con SQL (cita INV-08); registrar y anular sin movimientos intermedios devuelve el saldo exacto.
- [x] 11.2 Pruebas de integración finales: cada escenario de las cinco specs delta tiene al menos una prueba (tabla escenario → prueba en el resumen del lote); INV-01, INV-05, INV-06, INV-08, INV-13 e INV-21 citados por ID. Suite completa de backend (`pytest` por carpeta, `ruff`, `mypy`, `lint-imports`) y de frontend en verde, sin `skip` ni `xfail` injustificados.

## 12. ADR, documentación y cierre (Lote 3)

- [x] 12.1 Redactar `docs/adr/ADR-046` (pagos a proveedores: motivo y ámbito, pago de una compra de contado, pago mayor que la deuda y saldo a favor, fecha, proveedor inactivo, contenido del pago, permisos y lecturas, saldo, modelo de datos y orden de bloqueo; precisa ADR-043 puntos 3 y 15), en estado *Propuesto* hasta la aprobación del usuario.
- [x] 12.2 Propuesta de cambios a `docs/` para revisión del usuario (no se aplican sin su visto bueno): `01` §6.4 (PAG-01 a PAG-03 con lo aprobado), §19 (lecturas) y §21 (fila "Anulación de pago"); `02` §6.5 (comandos y lecturas) y §7.3 (fila de la operación antes del orden global); `03` §4 (`ANULACION_PAGO` y sus motivos) y §6 (`observacion`, `CHECK` e índices); `04` (deuda del 11 saldada, INV-08 cerrado para pagos y pendiente para cobranzas en el 17, deudas nuevas si las hay). La corrección de "`ANULADO`" por "`ANULADA`" (ADR-043 y spec `proveedores/anulacion-de-compras`) y el estado *Vigente* de ADR-043 y ADR-044 ya se resolvieron el 2026-10-03 y no forman parte de esta tarea.

## 13. Verificación manual (Lote 3, último paso)

- [x] 13.1 Si algún lote agregó una dependencia a `requirements.txt` o `package.json`, reconstruir antes las imágenes (`docker compose up -d --build backend`, y `frontend` si corresponde); si no se agregó ninguna, anotarlo. — 2026-10-06: el change 12 no agregó ninguna dependencia (`requirements*.txt`, `package.json` y `package-lock.json` sin cambios respecto de `7a33a8f`); no hace falta reconstruir.
- [x] 13.2 El usuario prueba en el navegador el flujo principal y se registra el resultado en `verificacion.md`: compra a crédito y pago parcial con dos medios (saldo actual y resultante); pago mayor que la deuda con su confirmación y compra a crédito posterior que lo absorbe; anulación de un pago con motivo; compra de contado anulada sin devolución y anulación posterior de su pago; intento de anular el pago de una compra vigente; pago a un proveedor inactivo desde su cuenta corriente; enlaces del estado de cuenta; aviso de saldo a favor en "Nueva compra"; un usuario con solo `REGISTRAR_PAGO_PROVEEDOR` y otro sin permisos de pago.
