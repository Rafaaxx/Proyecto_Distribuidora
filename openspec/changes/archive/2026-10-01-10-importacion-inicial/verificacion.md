# Verificación — 10-importacion-inicial

Fecha de la verificación automática: 2026-10-01. La verificación manual en el navegador (tarea 11.3) la ejecuta el usuario y **no está marcada**.

## 1. Definición de terminado (`docs/04` §2.1)

| # | Criterio | Estado | Evidencia |
| --- | --- | --- | --- |
| 1 | Las pruebas que exige `02` §15 pasan | Cumplido (local; CI no se ejecutó desde esta sesión) | Backend: 2.883 pruebas sin concurrencia, 34 de concurrencia, 74 de fixtures compartidos. Frontend: 602 pruebas. Ver §2. |
| 2 | Cada escenario de las specs tiene una prueba | Cumplido | Repaso de la tarea 10.1 en §3. |
| 3 | Los invariantes tocados tienen prueba que los cita por ID | Cumplido | §4. |
| 4 | La migración sube y baja limpia sobre una base con datos | Cumplido | `tests/integration/test_importacion_migracion.py::test_downgrade_elimina_la_tabla_y_upgrade_la_recrea_vacia_y_utilizable` (inserta una importación, `downgrade -1`, `upgrade head`, vuelve a insertar). |
| 5 | Se probó a mano el flujo principal en el navegador | **Pendiente** (tarea 11.3, a cargo del usuario) | Guía en §6. |
| 6 | Las specs delta se archivaron y `04` quedó actualizado | **Pendiente** (al archivar) | Texto propuesto en `propuesta-docs.md` §4. Deltas: 5 specs nuevas de `importacion` y 2 modificadas (`catalogo/productos-y-presentaciones`, `clientes/fichas-de-cliente`). |
| 7 | Las decisiones nuevas quedaron como ADR | Cumplido, a la espera de aprobación | ADR-040, ADR-041 y ADR-042, en estado *Propuesto*. |

## 2. Comandos y resultados (2026-10-01)

| Comando | Resultado |
| --- | --- |
| `python -m pytest --ignore=tests/concurrency` | 2.883 pasaron |
| `python -m pytest tests/concurrency` | 34 pasaron |
| `python -m pytest tests/fixtures_compartidos` | 74 pasaron |
| `python -m ruff check .` / `ruff format --check .` | sin hallazgos / 365 archivos formateados |
| `python -m mypy app` | sin errores (155 archivos) |
| `lint-imports` | 22 contratos cumplidos, 0 rotos |
| `npm run test` | 65 archivos, 602 pruebas pasaron |
| `npm run typecheck` | sin errores |
| `npm run lint` | 0 errores; 2 advertencias preexistentes (`react-hooks/incompatible-library` en `ProductoFormScreen` y `CostosCargaScreen`) |
| `npm run build` | correcto |
| `npm run generate:api-types` | `openapi.json` y `schema.gen.ts` idénticos a los del árbol de trabajo (sin deriva) |
| `openspec validate 10-importacion-inicial` | válido |

Nota: `tests/unit/app-routing.test.tsx` ("redirige /admin al inicio de sesión") falló una vez de 603 corridas bajo carga (la ruta `/admin` carga de forma diferida y la espera de 1 s se agotó) y pasó en la corrida aislada y en la siguiente completa; el área de importación suma otro `import()` diferido, pero la prueba es sensible al reloj de la máquina.

## 3. Cobertura por escenario (tarea 10.1)

| Spec | Escenarios | Pruebas principales |
| --- | --- | --- |
| `planillas` | CSV UTF-8, CSV de Excel en español, Excel, formato no admitido, columnas (faltante, desconocida, otro orden), número de fila, números decimales (coma, punto, miles, celda de Excel), cantidades, fechas y booleanos, límites, plantillas | `tests/unit/test_importacion_lector_csv.py`, `..._lector_xlsx.py`, `..._lectores.py`, `..._domain_planilla.py`, `..._domain_valores.py`; `tests/integration/test_importacion_api.py` (límite de 2.000 filas, 5 MB, plantillas, 403) |
| `importacion-de-maestros` | Mismo error que la pantalla, producto ya existente, clave repetida en el archivo, categoría inexistente, proveedor de otra organización, alícuota por porcentaje, proveedores, productos (5 escenarios), clientes (3), costos (5) | `test_importacion_comando.py`, `test_importacion_productos.py`, `test_importacion_clientes.py`, `test_importacion_costos.py` y sus pruebas de dominio |
| `puesta-en-marcha` | Stock inicial (8 escenarios), saldos iniciales (8), orden de bloqueo concurrente | `test_importacion_stock_inicial.py`, `test_importacion_saldos_iniciales.py`, `tests/concurrency/test_importacion_concurrencia.py` |
| `registro-de-importaciones` | Aceptada, sin permiso, sin `Operation-Id`, offline, una fila mala, falla inyectada, corregir y reenviar, doble envío, mismo `Operation-Id` con otro archivo, columna de organización, historial y su permiso | `test_importacion_comando.py`, `test_importacion_api.py`, `test_inv21_aislamiento_endpoints_importacion.py` |
| `administracion-de-importaciones` | Menú sin permiso, importación exitosa, errores por fila, error de columnas, reintento tras corte de red, historial | `frontend/tests/unit/areas/admin/importacion/ImportacionScreen.test.tsx` (18 casos), `rutas.test.tsx`, `features/importacion/envio.test.ts` |
| `catalogo/productos-y-presentaciones` (delta, grupo 12) | Nombre en blanco, unidad base vacía, presentación vacía | `test_catalogo_validaciones_de_alta.py`, `test_catalogo_api.py` (alta con textos vacíos, 422) |
| `clientes/fichas-de-cliente` (delta, grupo 12) | Estado de facturación fuera del catálogo; válido o nulo | `test_clientes_estado_facturacion.py`, `tests/unit/test_clientes_domain_estado_facturacion.py`, `test_clientes_api.py` (422, nunca 500) |

## 4. Invariantes citados por ID (tarea 10.2)

`grep` de cada ID en `backend/tests` sobre archivos de importación: INV-01 (comando, api, clientes, costos, productos, stock inicial, saldos), INV-03 (lector xlsx, valores, costos, saldos, stock inicial, productos; el esquema entero lo revisa `tests/integration/test_inv03_sin_punto_flotante.py`, que incluye la tabla `importacion`), INV-04 (valores, productos, stock inicial), INV-05 (`test_importacion_migracion.py`: sin `UPDATE` ni `DELETE`), INV-06 (comando, api, stock inicial, saldos, concurrencia), INV-12 e INV-13 (`tests/properties/test_importacion_inv12_inv13.py`, concurrencia), INV-18 (`test_importacion_costos.py`), INV-21 (api, productos, clientes, costos, stock inicial, saldos, `test_inv21_aislamiento_endpoints_importacion.py`).

## 5. Medición con 2.000 filas (tarea 10.3)

`tests/integration/test_importacion_api.py::TestImportar::test_el_limite_de_filas_se_acepta_y_una_mas_se_rechaza` envía 2.001 filas (rechazo inmediato por `ARCHIVO_DEMASIADO_GRANDE`) y luego 2.000 filas de proveedores (un savepoint por fila, un `crear_proveedor` por fila, una auditoría y un `importacion`). Medición en esta máquina (PostgreSQL en Testcontainers, 2026-10-01): **8,7 s para el caso completo** (ambos envíos y las comprobaciones), con la base ya creada (la preparación de 6,7 s es aparte). Es decir, unos 4 ms por fila incluyendo la lectura del CSV: el costo de los savepoints no es un riesgo con el límite de 2.000 filas.

## 6. Guía de verificación manual (tarea 11.3, a cargo del usuario)

### Preparación

1. Levantar la base y la aplicación (`docker compose up`) con la migración al día (`alembic upgrade head`) y entrar a `/admin` con un **Administrador** de la organización (con `IMPORTAR_DATOS`).
2. Crear a mano, si no existen (pantallas `/admin/catalogo` y `/admin/stock`): categoría `Vinos`; alícuota `21` (IVA 21%); una ubicación de tipo depósito llamada `Depósito` y una de vehículo llamada `Vehículo 1`. Las importaciones no crean categorías, marcas ni ubicaciones.
3. Crear un archivo de texto por cada planilla de abajo (Bloc de notas, **UTF-8**) con extensión `.csv`; también sirve guardar desde Excel en español como "CSV (delimitado por comas)" (usa `;`). Los decimales van **con coma** y sin separador de miles.

### Pasos

**Paso 1: plantillas.** En `/admin/importacion` aparece la entrada "Importación" en el menú. Para cada uno de los seis tipos (Proveedores, Productos, Clientes, Costos, Stock inicial, Saldos iniciales) pulsar "Descargar plantilla". Esperado: se baja un `.csv` con solo el encabezado. No hay un tipo "Precios".

**Paso 2: proveedores.** Tipo Proveedores, archivo `proveedores.csv`:

```
nombre,cuit,contacto,telefono,email
Bodega Sur,30-71234567-4,Laura,2615550101,ventas@bodegasur.example
Distribuidora Norte,,Marcos,2615550102,
```

Esperado: "2 filas importadas". Aparecen en `/admin/proveedores`.

**Paso 3: productos (Vino A caja x6 + botella).** Tipo Productos, archivo `productos.csv` (una fila por presentación):

```
codigo,nombre,categoria,marca,proveedor,unidad_base,alicuota,presentacion,unidades_base,usar_en_venta,usar_en_compra,es_referencia
VA-750,Vino A,Vinos,,Bodega Sur,botella,21,Caja x6,6,S,S,N
VA-750,Vino A,Vinos,,Bodega Sur,botella,21,Botella,1,S,N,S
```

Esperado: "2 filas importadas" (un producto con dos presentaciones). En `/admin/catalogo` aparece Vino A con "Botella" como referencia y "Caja x6" de 6 unidades. Para ver un error, reimportar el mismo archivo: "No se importó ninguna fila" y un error `CODIGO_DUPLICADO` en la fila 2.

**Paso 4: clientes con dos filas malas.** Tipo Clientes, archivo `clientes-con-errores.csv`:

```
nombre,codigo,razon_social,documento_tipo,documento_numero,direccion,contacto,telefono,email,estado_facturacion_default
Kiosco La Esquina,C001,,DNI,30111222,Av. San Martín 1420,Rocío,,,
Almacén El Faro,C002,,DNI,123456,San Lorenzo 55,Julián,,,
Despensa Sol,C003,,CUIT,30712345674,Belgrano 900,Marta,,,FACTURADA
```

Esperado: no se importa nada; se muestra la tabla de errores y el aviso "No se importó ninguna fila":

| Fila | Columna | Código |
| --- | --- | --- |
| 3 | `documento_numero` | `DOCUMENTO_INVALIDO` (un DNI de 6 dígitos) |
| 4 | `estado_facturacion_default` | `ESTADO_FACTURACION_INVALIDO` |

Comprobar en `/admin/clientes` que **no** existe ninguno de los tres (tampoco `C001`).

**Paso 5: corregir y reimportar clientes.** Guardar como `clientes.csv` con los datos corregidos (DNI `30222333` en la fila 3 y `estado_facturacion_default` vacío o `PENDIENTE` en la fila 4) y subirlo. Esperado: "3 filas importadas"; los tres clientes están `ACTIVO` en `/admin/clientes`.

**Paso 6: costos.** Tipo Costos, archivo `costos.csv`. El costo se informa sobre la caja del Vino A, que es la única presentación de compra (la botella no es de compra):

```
producto_codigo,presentacion,valor,incluye_iva,bonificacion,vigencia_desde,observacion
VA-750,Caja x6,18000,N,,2026-10-01,Lista de octubre
```

Esperado: "1 fila importada". En la pantalla de costos del proveedor Bodega Sur el costo derivado por unidad base de Vino A es `3000.000000` (18.000 / 6 botellas). Variantes opcionales (otro archivo cada una, con otra `vigencia_desde` posterior): `18000` con `incluye_iva` `S` da `2479.338843` (18.000 / 1,21 / 6); `18000` con `incluye_iva` `N` y `bonificacion` `10` da `2700.000000` (16.200 / 6). (Corregido 2026-10-01: la versión anterior usaba los valores de una caja x12.)

**Paso 7: stock inicial en depósito y vehículo.** Tipo Stock inicial, archivo `stock.csv` (cantidad en unidades base, costo por unidad base):

```
ubicacion,producto_codigo,cantidad_base,costo_unitario
Depósito,VA-750,60,1000
Vehículo 1,VA-750,60,1100
```

Esperado: "2 filas importadas". En `/admin/stock` el producto tiene 60 en el depósito y 60 en el vehículo, 120 en total, y el kardex muestra dos movimientos `STOCK_INICIAL`; el costo promedio de Vino A es `1050.000000`. Para ver un error, reimportar con otro archivo que tenga `Depósito,VA-750,-100,` (corrección que deja negativo): `STOCK_INSUFICIENTE` en la fila 2 y nada cambia.

**Paso 8: saldos iniciales.** Tipo Saldos iniciales, archivo `saldos.csv`:

```
cuenta_tipo,entidad,importe,sentido
CLIENTE,C001,150000,Nos debe
CLIENTE,C001,20000,Saldo a favor
PROVEEDOR,Bodega Sur,80000,Le debemos
```

Esperado: "3 filas importadas". El estado de cuenta de `C001` muestra "Nos debe" `130000.00` (150.000 menos la corrección de 20.000, en dos movimientos `SALDO_INICIAL`) y el de Bodega Sur, "Le debemos" `80000.00`. Para ver un error: `CLIENTE,C001,1.500,Nos debe` da `NUMERO_INVALIDO` (el punto no se admite) en la fila 2.

**Paso 9: reintento seguro y historial.** En el paso 8, con las herramientas del navegador (pestaña Red, "Sin conexión") cortar la red justo antes de pulsar "Importar", pulsar y reponer la red: al reintentar con el mismo archivo no se duplica nada (mismo `Operation-Id`). Luego abrir el historial al pie de la pantalla: aparecen las importaciones confirmadas (proveedores, productos, clientes, costos, stock, saldos) con tipo, archivo, filas, usuario y la fecha en la zona de la organización (Mendoza); las rechazadas no figuran.

**Paso 10: Vendedor.** Entrar con un **Vendedor**. Esperado: el menú no muestra "Importación"; entrar por URL directa a `/admin/importacion` muestra que no tiene permiso. Por API (PowerShell 5.1, con el token del Vendedor en `$token`):

```powershell
curl.exe -i -H "Authorization: Bearer $token" http://localhost:8000/api/v1/importaciones
```

Esperado: `403` con `codigo` `PERMISO_REQUERIDO`. Y la subida:

```powershell
curl.exe -i -X POST -H "Authorization: Bearer $token" -H "Operation-Id: 00000000-0000-7000-8000-000000000001" -F "archivo=@proveedores.csv" http://localhost:8000/api/v1/importaciones/PROVEEDORES
```

Esperado: `403`. (El campo del archivo se llama `archivo`; si la API está publicada por otro puerto o por el proxy, ajustar la URL.)

### Después de la verificación

Si algo difiere, anotarlo con el paso. Si todo coincide, marcar 11.3 y archivar con `/opsx:archive`, aplicando antes (si se aprueba) el texto de `propuesta-docs.md`.
