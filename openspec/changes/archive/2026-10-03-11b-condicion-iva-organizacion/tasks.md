# Tareas — 11b-condicion-iva-organizacion

> Modo TDD estricto: en cada tarea de los grupos 1 a 9, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente, se corre su suite como red de seguridad. El grupo 10 completa la cobertura por escenario e invariante; no la reemplaza. Las tareas están escritas con la **opción A (recomendada)** de cada decisión de `design.md`. Si la tarea 0.1 aprueba otra, se actualizan con `/opsx:update` antes de empezar.
>
> **Lotes de apply:** Lote 1 = grupos 0 a 6 (fixtures, migración, regla, cálculo, comando, lecturas e importación por API). Lote 2 = grupos 7 a 12 (frontend, concurrencia, cobertura, docs y verificación manual).

## 0. Aprobación (bloqueante)

- [x] 0.1 El usuario revisa y aprueba (o cambia) D0 a D10 de `design.md`. Debe elegir activamente en D9 (valor inicial de las organizaciones existentes en la migración y de la siembra), D4/D6 (rechazar `incluye_iva` en una organización no inscripta, en el comando y en la planilla), D7 (permiso `ADMIN_CONFIGURACION` o uno nuevo) y D2 (forzar modo `A` y modalidad nula en una organización no inscripta), y confirmar el ID de regla nuevo **CST-06**. Se anotan la fecha y la opción en cada decisión. La pregunta abierta sobre las facturas de proveedores inscriptos no bloquea. Verificable: `design.md` sin decisiones "Pendiente".

## 1. Fixtures compartidos (Lote 1, antes de cualquier cálculo)

- [x] 1.1 Red de seguridad: las suites de fixtures en verde (`python -m pytest backend/tests/fixtures_compartidos/` y `npm run test -- tests/unit/calculo`). Modificar `shared/fixtures/calculo/cst-02-costo-base.json`: agregar `"computa_credito_fiscal": true` a todos los casos existentes (sus salidas no cambian) y los casos nuevos con `false`: Caja x12 `"21780.00"` → `"1815.000000"`; con bonificación `0.10` → `"1633.500000"`; `incluye_iva = false` con alícuota `0.21` → sin división. RED: los casos nuevos fallan en pytest y Vitest porque la firma no tiene el parámetro.
- [x] 1.2 Modificar `cmp-02-compra.json`: `computa_credito_fiscal` en todos los casos (los existentes con `true`); línea de monotributista (Caja x12, 1, `"21780.00"` → 12, `"1815.000000"`, `"21780.00"`); total de la compra del criterio 2 a valores pagados (`"7260.00"` × 10 cajas x6 + `"1331.00"` × 60 → neto y sugerido `"152460.00"`, D5); el caso existente de sugerido `"152460.00"` sobre neto `"126000.00"` sigue con `true`. RED en las dos suites.

## 2. Migración (Lote 1)

- [x] 2.1 RED: `tests/integration/test_condicion_iva_migracion.py` exige `configuracion_organizacion.condicion_iva text NOT NULL` con `CHECK` de dominio y el `CHECK` de D2; `computa_credito_fiscal boolean NOT NULL` en `costo_informado` y `compra_linea` con `CHECK (computa_credito_fiscal OR NOT incluye_iva)`; organizaciones existentes migradas a `RESPONSABLE_INSCRIPTO` y filas existentes con `true` y el mismo costo base (D9, cita TR-06); privilegios de `app_runtime` sin `DELETE` y sin `UPDATE` nuevo sobre los libros (INV-05). GREEN: revisión de Alembic. Verificable con `alembic upgrade head`, `downgrade -1` y `upgrade head` sobre una base con costos y compras.

## 3. Regla, modelo y siembra (Lote 1)

- [x] 3.1 RED en `tests/unit/test_identidad_valores.py`: `validar_condicion_iva` (dominio cerrado), `computa_credito_fiscal` (verdadero solo para `RESPONSABLE_INSCRIPTO`, falso para `MONOTRIBUTO` y `EXENTO`, cita CST-06) y la compatibilidad con modo y modalidad (D2). GREEN en `identidad/domain/valores.py`.
- [x] 3.2 RED: los modelos `ConfiguracionOrganizacion`, `CostoInformado` y `CompraLinea` iguales a la migración (`alembic revision --autogenerate` sin diferencias); `identidad/service.py::obtener_condicion_iva` con lectura `FOR SHARE` opcional. GREEN.
- [x] 3.3 RED en `tests/unit/test_seed.py`: una organización inicial nueva nace `MONOTRIBUTO`, modo `A` y modalidad sin definir (D9). La re-siembra no pisa una condición cambiada. GREEN en `app/seed.py`.

## 4. Cálculo y validación en `proveedores` (Lote 1)

- [x] 4.1 Red de seguridad: las suites de `proveedores` (06 y 11) en verde. RED: `calcular_costo_base(..., computa_credito_fiscal)` pasa 1.1; motor TS `costoBase.ts` igual. GREEN en `proveedores/domain/costo_base.py` y `frontend/src/domain/proveedores/costoBase.ts`.
- [x] 4.2 RED en `tests/unit/test_proveedores_domain_compras.py`: la línea y el total sugerido según `computa_credito_fiscal` (D5) pasan 1.2; `INCLUYE_IVA_NO_APLICA` con el número de línea (D4). Propiedad Hypothesis: con `computa_credito_fiscal = false`, el costo base no depende de la alícuota y el sugerido es igual al total neto. GREEN en `proveedores/domain/compras.py` y `frontend/src/domain/compras/`.
- [x] 4.3 RED en `tests/integration/test_costos_informar.py`: un costo de monotributista (`"1815.000000"`, `computa_credito_fiscal = false`), `INCLUYE_IVA_NO_APLICA` sin efectos y un inscripto sin cambios. GREEN: `COSTO_INFORMAR` lee la condición `FOR SHARE` y congela la regla.
- [x] 4.4 RED en `tests/integration/test_compras_confirmar.py`: la compra del criterio 2 de un monotributista (deuda `"152460.00"`, promedios `"1210.000000"` y `"1331.000000"`); línea con `incluye_iva = true` rechazada; el detalle expone `computa_credito_fiscal`. GREEN en el servicio y el handler `COMPRA_CONFIRMAR` (v1, sin campo nuevo en la huella).

## 5. Cambio y lectura de la condición (Lote 1)

- [x] 5.1 RED en `tests/integration/test_condicion_iva_cambiar.py`: `ORGANIZACION_CONDICION_IVA_CAMBIAR` `MONOTRIBUTO` → `RESPONSABLE_INSCRIPTO` con una auditoría de valor anterior y nuevo; costos y compras previos intactos (cita TR-06); `CONDICION_IVA_SIN_CAMBIO`; `MODO_IMPOSITIVO_INCOMPATIBLE`; valor desconocido 422; 403 sin `ADMIN_CONFIGURACION`; idempotencia y `COMANDO_INCONSISTENTE` (cita INV-06); falla inyectada después del cambio y antes de la auditoría → sin efecto (cita INV-01). GREEN: handler en `identidad/commands.py`, ruta `POST /api/v1/configuracion/fiscal/condicion-iva`.
- [x] 5.2 RED: `GET /api/v1/configuracion/fiscal` (cualquier usuario autenticado, aislamiento, cita INV-21) y `GET /api/v1/costos/resumen-regla-iva?fecha=` (permisos, conteo por regla con SQL). GREEN. Las rutas nuevas entran en los ratchets de aislamiento y de permisos. Tipos de OpenAPI regenerados (`npm run generate:api-types`).

## 6. Importación de costos (Lote 1)

- [x] 6.1 Red de seguridad: suite de `importacion` en verde. RED en `tests/integration/test_importacion_costos.py`: un monotributista con columna vacía → `"1815.000000"`; `S` en la fila 7 de 40 → `INCLUYE_IVA_NO_APLICA` y ningún costo (cita ADR-040); un inscripto con columna vacía → error de valor obligatorio; un inscripto con `S` → `"1239.669421"` como hoy. GREEN en `importacion/domain/costos.py` y `planilla.py` (columna opcional según la condición) y en la ayuda de la plantilla ("valor pagado"; costo del stock inicial por unidad base tal como se pagó).

## 7. Frontend (Lote 2)

- [x] 7.1 RED en `frontend/tests/unit/features/configuracion/`: hook `useConfiguracionFiscal` y mutación de cambio con `Operation-Id` estable al reintentar. GREEN en `frontend/src/features/configuracion/`.
- [x] 7.2 RED en `CompraFormScreen.test.tsx`: un monotributista no ve "Incluye IVA" ni "IVA sugerido", ve "Valor pagado", costo base `1.815,000000` y total de factura prellenado `21.780,00`, y envía `incluye_iva = false`; un inscripto sigue igual (`1.239,669421` / `14.876,03`); `INCLUYE_IVA_NO_APLICA` junto a la línea. GREEN.
- [x] 7.3 RED en `CostosCargaScreen.test.tsx`: lo mismo para la carga de costos (D4). El historial y el detalle de compra muestran "IVA descontado: Sí/No" desde la columna congelada. GREEN.
- [x] 7.4 RED en `frontend/tests/unit/areas/admin/configuracion/`: la pantalla `/admin/configuracion/fiscal` en solo lectura sin `ADMIN_CONFIGURACION`; con el permiso, una confirmación que avisa que no es retroactivo y muestra el resumen de D10; el comando solo se envía al confirmar; entrada de menú por permiso. GREEN. Verificable con `npm run test`, `npm run typecheck` y `npm run lint`.

## 8. Concurrencia (Lote 2)

- [x] 8.1 RED en `tests/concurrency/test_condicion_iva_concurrencia.py` (commits reales): una `COMPRA_CONFIRMAR` simultánea con `ORGANIZACION_CONDICION_IVA_CAMBIAR` → todas las líneas de la compra con la misma regla, sin interbloqueo. Dos cambios simultáneos al mismo valor → uno aceptado y otro `CONDICION_IVA_SIN_CAMBIO`. GREEN si hace falta.

## 9. Ratchets y límites (Lote 2)

- [x] 9.1 RED: la prueba de catálogo de columnas (INV-03/INV-04) sigue sin `float`; import-linter: `proveedores` e `importacion` leen la condición solo por `identidad/service.py`. GREEN. Verificable con `lint-imports`.

## 10. Pruebas de integración finales y cobertura (Lote 2)

- [x] 10.1 Cada escenario de las seis specs delta tiene al menos una prueba (tabla escenario → prueba en el resumen del lote). TR-06, INV-01, INV-03, INV-05, INV-06 e INV-21 citados por ID. Suite completa de backend (`pytest`, `ruff`, `mypy`, `lint-imports`) y de frontend en verde, sin `skip`/`xfail` injustificados. Las suites del 06, 10 y 11 sin cambios de expectativa para un responsable inscripto.

## 11. ADR y documentación (Lote 2)

- [x] 11.1 Redactar **ADR-045** (condición frente al IVA de la organización; enmienda ADR-009: D1 a D10), en estado *Propuesto* hasta la aprobación del usuario.
- [x] 11.2 Proponer cambios a `docs/` para revisión del usuario: `00` §5 (organización inicial monotributista, sin modalidad de IVA al facturar; ventas a precio final, Factura C); `01` §4 (fila "Condición frente al IVA"), §6.1 (CST-02 con la condición y CST-06 nueva), §6.3 (CMP-01 "valor pagado" y CMP-02 con el sugerido según la condición), §16 (nota: FAC-02/03/04/08 y ADR-009 solo para responsables inscriptos) y §19 si D7 cambia de permiso; `03` §4 (`condicion_iva`, `CHECK` de D2) y §6 (`computa_credito_fiscal` y el significado de `total_neto`); `04` (11b en el hito 3 antes del 12 y del 13, dependencias, impacto en 13, 18a, nota de venta y facturación, e idea futura del reporte de tope del monotributo).

## 12. Verificación manual (Lote 2, último paso)

- [x] 12.1 Si algún lote agregó una dependencia a `requirements.txt` o `package.json`, reconstruir antes las imágenes (`docker compose up -d --build backend`, y `frontend` si corresponde). Si no se agregó ninguna, anotarlo.
- [x] 12.2 El usuario prueba en el navegador: pasar la organización de desarrollo a `MONOTRIBUTO` desde `/admin/configuracion/fiscal` (confirmación y resumen de costos vigentes), cargar un costo de Caja x12 a $21.780 sin la casilla de IVA (`1.815,000000`), registrar una compra de un monotributista (total sugerido igual a la suma de las líneas, deuda y promedio), ver una compra y un costo previos intactos con "IVA descontado: Sí", importar una planilla de costos con la columna vacía y otra con `S` (rechazada) y volver a `RESPONSABLE_INSCRIPTO` para comprobar que reaparece la casilla. El resultado se registra en `verificacion.md`.
