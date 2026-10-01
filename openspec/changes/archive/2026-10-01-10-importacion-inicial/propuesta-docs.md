# Propuesta de cambios a `docs/` — 10-importacion-inicial

> Texto **propuesto** para actualizar `docs/01` a `docs/04`. **No se editó ningún archivo de `docs/` (salvo los ADR-040 a ADR-042, en estado *Propuesto*)**: el usuario revisa y aprueba este texto y recién entonces se aplica (por ejemplo al archivar el change). Cada bloque indica el archivo, la sección y el texto resultante. Prioridad de fuentes: `docs/adr/` > `docs/00` a `docs/04`.

## 1. `01-dominio.md`

### 1.1 §6.1, CST-05 (D8, ADR-042 punto 5)

Reemplazar la fila:

| ID | Regla | Etapa |
| --- | --- | :-: |
| CST-05 | Puede cargarse un costo por producto o varios de un proveedor en una sola operación. La importación **inicial** de costos desde una planilla es de la etapa 1 (change 10, por `informar_costos`); la importación masiva **recurrente** es de la etapa 2. | 1 (importación inicial; masiva recurrente: 2) |

### 1.2 Reglas de importación (nuevas, en la sección de transversales o en una sección "Importación inicial")

| ID | Regla | Etapa |
| --- | --- | :-: |
| IMP-01 | Una importación es una sola operación por archivo: o se escriben todas las filas o ninguna (INV-01). Un archivo con errores se rechaza con el informe completo de errores por fila y columna (`IMPORTACION_CON_ERRORES`). | 1 |
| IMP-02 | Cada fila se valida y se escribe con las mismas reglas que el alta individual de su entidad y produce el mismo código de error ante el mismo dato inválido (TR-10). | 1 |
| IMP-03 | Una importación de maestros solo crea registros; una clave natural que ya existe es un error de duplicado y ningún registro existente se modifica. | 1 |
| IMP-04 | Las referencias entre entidades se escriben por clave natural (categoría y marca por nombre, alícuota por porcentaje, proveedor por nombre, producto por código, cliente por código o documento, ubicación por nombre); no se crean al vuelo. | 1 |
| IMP-05 | Los números de una planilla se leen como decimales exactos: coma decimal y sin separador de miles; un punto se rechaza (INV-03). Las cantidades son enteros (INV-04). | 1 |
| IMP-06 | El stock y los saldos iniciales importados se fechan con el momento de la importación (sin fecha de corte), como los cargados por pantalla (STK-10, CC-08). | 1 |

### 1.3 Catálogo: textos obligatorios (change 10, tarea 12.1)

Agregar a CAT-01 y CAT-02: "El nombre del producto, la unidad base y el nombre de cada presentación no pueden quedar vacíos ni de solo espacios tras recortar: el nombre y el de la presentación dan `NOMBRE_INVALIDO` y la unidad base da `VALOR_OBLIGATORIO` (422). Los textos válidos se guardan recortados."

### 1.4 Clientes: estado de facturación inicial (change 10, tarea 12.2)

Agregar a CLI-01 o a VTA-08: "El estado de facturación inicial del cliente es `NO_REQUIERE`, `PENDIENTE` o nulo (el de la organización); otro valor se rechaza con `ESTADO_FACTURACION_INVALIDO` (422)."

### 1.5 Códigos de error nuevos (catálogo de errores, si `01` o `02` lo lista)

`IMPORTACION_CON_ERRORES` (422, `extension.errores`), `ARCHIVO_INVALIDO`, `ARCHIVO_SIN_FILAS`, `ARCHIVO_DEMASIADO_GRANDE`, `COLUMNAS_INVALIDAS`, `TIPO_IMPORTACION_INVALIDO`, `FILA_DUPLICADA`, `PRODUCTO_INCONSISTENTE`, `REFERENCIA_NO_ENCONTRADA`, `REFERENCIA_AMBIGUA`, `NUMERO_INVALIDO`, `CANTIDAD_INVALIDA`, `FECHA_INVALIDA`, `VALOR_INVALIDO`, `VALOR_OBLIGATORIO` (compartido con catálogo para la unidad base), `ESTADO_FACTURACION_INVALIDO` (clientes).

## 2. `02-arquitectura.md`

### 2.1 §5.1 Módulos (D10, ADR-042)

Agregar la fila:

| Módulo | Responsabilidad | Reglas |
| --- | --- | --- |
| importacion | Lectura de planillas (CSV y `.xlsx`), conversión exacta de valores, informe de errores por fila, comando `IMPORTACION_REGISTRAR`, historial de importaciones y un importador por tipo sobre los servicios de los demás módulos | IMP, TR-10 |

### 2.2 §5.3 Dependencias permitidas

Agregar la línea:

```
importacion ──► catalogo, proveedores, clientes, stock, cuentas_corrientes, configuracion, identidad (solo por service.py; nadie depende de importacion, ADR-042)
```

Y en "stack"/dependencias del backend (si `02` lo lista): `python-multipart` para el cuerpo `multipart/form-data` de la importación (ADR-041).

### 2.3 §6.5 Tipos de comando de la etapa 1

Agregar la fila `IMPORTACION_REGISTRAR` con Online ✓ y Offline vacío (permiso `IMPORTAR_DATOS`). Nota al pie: "Una importación es un comando por archivo: todo o nada, con savepoints por fila dentro del handler (ADR-040)."

### 2.4 §6.1 o sección de API (si lista rutas)

`POST /api/v1/importaciones/{tipo}` (multipart, `Operation-Id` obligatorio), `GET /api/v1/importaciones` (historial paginado por cursor) y `GET /api/v1/importaciones/plantillas/{tipo}` (CSV con solo el encabezado), todas con `IMPORTAR_DATOS`.

## 3. `03-modelo-de-datos.md`

### 3.1 §13, tabla `importacion` (D9, D14, ADR-040)

Reemplazar la descripción por:

`importacion`: `id`, `organizacion_id`, `tipo` (`PRODUCTOS`, `CLIENTES`, `PROVEEDORES`, `PRECIOS`, `COSTOS`, `STOCK_INICIAL`, `SALDOS_INICIALES`), `archivo_nombre`, `estado` (`CONFIRMADA`), `filas_total`, `filas_ok`, `filas_error`, `errores` `jsonb`, y las columnas de operación (`operation_id`, `usuario_id`, `dispositivo_id`, `occurred_at`, `registered_at`, `03` §2.3). `UNIQUE (organizacion_id, id)`; FK compuestas a `usuario` y `dispositivo`; `CHECK` de `tipo` y `estado` y de filas no negativas; índice `(organizacion_id, registered_at DESC, id)` para el historial. De solo inserción (`GRANT SELECT, INSERT`). Con el modo todo-o-nada solo se guardan importaciones confirmadas (`filas_error` = 0, `errores` = `[]`). `PRECIOS` está en el catálogo del `CHECK` pero no tiene importador hasta el change 13.

## 4. `04-roadmap-changes.md`

### 4.1 §4 (change 10): ajuste de alcance

Aclarar la fila del change 10: "Importación de productos, clientes, proveedores y costos desde CSV/Excel; stock inicial y saldos iniciales; informe de errores por fila. No incluye listas de precios (`PRECIOS`, change 13)."

### 4.2 Deuda nominada por el change 10 para el change 13 (`listas-de-precios`)

> **Deuda nominada por el change 10 (`importacion-inicial`) para el change 13 (`listas-de-precios`):** `00` §6.1 incluye "listas" en la importación inicial y `03` §13 declara el tipo `PRECIOS`, pero las listas nacen en el 13 (que no depende del 10). El change 10 deja el tipo `PRECIOS` en el `CHECK` de `importacion.tipo` y la API lo rechaza con 422 `TIPO_IMPORTACION_INVALIDO`. El 13 debe: (a) agregar un importador `PRECIOS` al registro `IMPORTADORES` de `importacion` (`importacion/importadores/__init__.py`) sobre el servicio de listas, con su definición de columnas en `importacion/domain/planilla.py` y su plantilla; (b) resolver las referencias por clave natural (lista por nombre, producto por código, presentación por nombre) con funciones `buscar_*` en su `service.py`; (c) mantener todo o nada (ADR-040) y los mismos códigos de error que la pantalla (TR-10); (d) sumar la opción en la pantalla `/admin/importacion` y en `frontend/src/features/importacion/tipos.ts`, y sacar `PRECIOS` de la lista de tipos rechazados en las pruebas del change 10.

### 4.3 Estado del change 10

Al archivar: marcar el change 10 como archivado con la fecha y listar sus ADR (040 a 042) y las specs nuevas (`importacion/planillas`, `importacion/importacion-de-maestros`, `importacion/puesta-en-marcha`, `importacion/registro-de-importaciones`, `importacion/administracion-de-importaciones`) y las modificadas (`catalogo/productos-y-presentaciones`, `clientes/fichas-de-cliente`).

## 5. `00-vision-y-alcance.md` §6.1

Aclarar en "Importación inicial": "productos, clientes, proveedores, costos, stock y saldos iniciales (change 10); las listas de precios se importan desde el change 13".

## 6. Cambios que el usuario debe aprobar

1. Texto de `01` §1.1 a §1.5 (incluye las dos validaciones de los grupos 12.1 y 12.2).
2. Alta del módulo `importacion` en `02` §5.1/§5.3 y de `IMPORTACION_REGISTRAR` en `02` §6.5.
3. Tabla `importacion` en `03` §13.
4. Deuda nominada para el change 13 en `04`.
5. Los ADR-040, ADR-041 y ADR-042, hoy *Propuestos* (pasan a *Vigentes* con la aprobación).
