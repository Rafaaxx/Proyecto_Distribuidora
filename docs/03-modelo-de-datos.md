# 03 — Modelo de datos

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Versión | 1.0 |
| Fecha | 2026-09-16 |
| Depende de | `01-dominio.md`, `02-arquitectura.md` |
| Documentos relacionados | `00-vision-y-alcance.md`, `adr/` |

## 1. Propósito

Define el esquema de PostgreSQL: tablas, tipos, claves, restricciones e índices, y su correspondencia con las reglas de `01-dominio.md`. Sustituye al ERD del paquete original, cuyas diferencias se listan en §14.

El alcance es la etapa 1 más la estructura que debe existir desde el inicio (`00` §7). Las tablas de facturación se documentan porque el núcleo referencia su contrato, aunque se creen al desarrollar ese módulo.

## 2. Convenciones

### 2.1 Nombres

- Tablas y columnas en español, `snake_case`, **singular** (`venta`, `venta_linea`, `cuenta_movimiento`).
- Clave foránea: nombre de la entidad más `_id` (`cliente_id`).
- Índices: `ix_<tabla>__<columnas>`; únicos: `ux_<tabla>__<columnas>`; restricciones de verificación: `ck_<tabla>__<regla>`.

### 2.2 Tipos

| Uso | Tipo |
| --- | --- |
| Identificadores | `uuid` (UUIDv7, ver `02` §9) |
| Importes | `numeric(14,2)` |
| Costos por unidad base y precios sin redondear | `numeric(18,6)` |
| Porcentajes y alícuotas | `numeric(9,6)` como fracción (21% = `0.210000`) |
| Cantidades en unidad base | `integer` |
| Cantidades en presentación | `numeric(14,3)` solo en compras; en ventas, `integer` |
| Momentos | `timestamptz` |
| Fechas de negocio sin hora | `date` |
| Estados y tipos fijos | `text` con `CHECK` |
| Datos variables | `jsonb` |

**DEBE NO** usarse `float`, `real`, `double precision`, `money` ni `serial` (INV-03).

Los estados y tipos fijos se modelan como `text` con `CHECK` en lugar de tipos `enum` de PostgreSQL, porque agregar un valor a un `CHECK` es una migración simple y reversible.

### 2.3 Columnas comunes

Toda tabla de negocio tiene:

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | `uuid` | Clave primaria |
| `organizacion_id` | `uuid` | Obligatoria (INV-02) |
| `creado_en` | `timestamptz` | `default now()` |

Excepción: una tabla de saldo cuya clave natural es compuesta y que ninguna otra tabla referencia no lleva `id`; su clave primaria empieza por `organizacion_id` (INV-02). Hoy es el caso de `saldo_cuenta` (ADR-035).

Las tablas de datos maestros agregan `actualizado_en` (obligatoria: la usa el bootstrap incremental, `02` §13.4) y `actualizado_por_id`.

Las tablas de operaciones agregan:

| Columna | Tipo | Notas |
| --- | --- | --- |
| `operation_id` | `uuid` | Comando que la originó (TR-07) |
| `usuario_id` | `uuid` | Quién la registró |
| `dispositivo_id` | `uuid` | Desde dónde |
| `occurred_at` | `timestamptz` | Momento informado por el dispositivo (TR-05) |
| `registered_at` | `timestamptz` | Momento del servidor |

### 2.4 Aislamiento por organización

**DEBE:** toda tabla de negocio declara `UNIQUE (organizacion_id, id)` y las claves foráneas entre entidades de negocio son **compuestas**, incluyendo `organizacion_id`. Así la base impide referencias entre organizaciones distintas, sin depender del código (`02` §8).

```sql
CREATE TABLE venta (
    id                uuid PRIMARY KEY,
    organizacion_id   uuid NOT NULL REFERENCES organizacion (id),
    cliente_id        uuid NOT NULL,
    ...
    CONSTRAINT ux_venta__org_id UNIQUE (organizacion_id, id),
    CONSTRAINT fk_venta__cliente
        FOREIGN KEY (organizacion_id, cliente_id)
        REFERENCES cliente (organizacion_id, id)
);
```

### 2.5 Inmutabilidad

- No hay borrado lógico con `borrado = true`. Los maestros usan `activo` o `estado`; las operaciones se anulan con registros nuevos (TR-06).
- Las tablas de libros (`cuenta_movimiento`, `stock_movimiento`, `costo_producto_mov`, `auditoria`) son de solo inserción. **DEBE:** el usuario de aplicación no tiene permisos de `UPDATE` ni `DELETE` sobre ellas, y una prueba lo verifica (INV-05).
- Las tablas de saldo (`saldo_cuenta`, `stock_saldo`, `costo_producto`) sí se actualizan: son materializaciones verificables (`02` §7.2).

## 3. Mapa de tablas por módulo

```
identidad        organizacion · configuracion_organizacion · usuario · rol · permiso
                 rol_permiso · dispositivo · sesion_refresh
configuracion    alicuota_iva · medio_pago · motivo
catalogo         categoria · marca · producto · presentacion
proveedores      proveedor · costo_informado · compra · compra_linea
                 pago_proveedor · pago_proveedor_medio
costeo           costo_producto · costo_producto_mov
precios          lista_precio · regla_margen · redondeo_categoria
                 lista_version · precio_item
stock            ubicacion · stock_saldo · stock_movimiento · transferencia
                 transferencia_linea · ajuste_stock · ajuste_stock_linea
                 jornada · rendicion · rendicion_linea
clientes         cliente
descuentos       regla_descuento · regla_descuento_alcance
ventas           venta · venta_linea · venta_linea_descuento · venta_anulacion
cobranzas        cobranza · cobranza_medio · cobranza_anulacion
ctas. corrientes cuenta_movimiento · saldo_cuenta
sync             comando · comando_cuarentena · observacion
auditoria        auditoria
importacion      importacion
facturacion      factura · factura_venta · factura_alicuota · ajuste_iva_absorbido
```

## 4. Identidad y configuración

### `organizacion`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | `uuid` | PK |
| `nombre` | `text` | |
| `slug` | `text` | `UNIQUE`. Resuelve la organización en el login antes de que exista un token (`ADR-021`) |
| `cuit` | `text` | Opcional |
| `moneda` | `text` | ISO 4217 |
| `zona_horaria` | `text` | IANA |
| `estado` | `text` | `ACTIVA`, `SUSPENDIDA` |

### `configuracion_organizacion`

Una fila por organización (`01` §4).

| Columna | Tipo | Notas |
| --- | --- | --- |
| `organizacion_id` | `uuid` | PK y FK |
| `modo_impositivo` | `text` | `A`, `B`, `C` |
| `lista_precio_default_id` | `uuid` | |
| `politica_credito_default` | `text` | `ADVERTIR`, `AUTORIZAR`, `BLOQUEAR` |
| `tolerancia_offline_tipo` | `text` | `IMPORTE`, `PORCENTAJE` |
| `tolerancia_offline_valor` | `numeric(14,2)` | |
| `descuento_manual_habilitado` | `boolean` | |
| `motivo_obligatorio_descuento` | `boolean` | |
| `motivo_obligatorio_lista` | `boolean` | |
| `redondeo_multiplo` | `numeric(14,2)` | |
| `redondeo_direccion` | `text` | `ARRIBA`, `CERCANO`, `ABAJO` |
| `permite_consumidor_final` | `boolean` | |
| `cliente_consumidor_final_id` | `uuid` | Opcional |
| `estado_facturacion_default` | `text` | `NO_REQUIERE`, `PENDIENTE` |
| `modalidad_iva_default` | `text` | `CLIENTE`, `ABSORBIDO` |
| `intentos_pin_max` | `integer` | |
| `desvio_reloj_max_segundos` | `integer` | `02` §9 |

### `usuario`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | |
| `usuario` | `text` | `UNIQUE (organizacion_id, usuario)` |
| `nombre`, `email` | `text` | |
| `password_hash` | `text` | Argon2id |
| `rol_id` | `uuid` | |
| `tope_descuento_override` | `numeric(9,6)` | Opcional; si es nulo rige el del rol |
| `pin_autorizacion_hash`, `pin_autorizacion_sal` | `text` | Solo supervisores (`02` §12.4) |
| `pin_autorizacion_iteraciones` | `integer` | |
| `estado` | `text` | `ACTIVO`, `INACTIVO` |

### `rol`, `permiso`, `rol_permiso`

| Tabla | Columnas |
| --- | --- |
| `rol` | `id`, `organizacion_id`, `nombre`, `tope_descuento` `numeric(9,6)`, `activo` |
| `permiso` | `codigo` `text` PK (global, sin organización), `descripcion`, `modulo` |
| `rol_permiso` | `organizacion_id`, `rol_id`, `permiso_codigo`; PK compuesta |

El catálogo de `permiso` se sincroniza por migración con `01` §19. Permisos por usuario fuera del rol: etapa 4.

### `dispositivo`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | `id` generado por el dispositivo |
| `nombre` | `text` | Descriptivo |
| `prefijo` | `text` | `UNIQUE (organizacion_id, prefijo)` (`02` §7.7) |
| `ultimo_correlativo` | `integer` | Último número registrado en el servidor |
| `estado` | `text` | `ACTIVO`, `REVOCADO` |
| `revocado_en`, `revocado_por_id` | | |

### `sesion_refresh`

`id`, `organizacion_id`, `usuario_id`, `dispositivo_id`, `token_hash`, `familia_id`, `emitido_en`, `expira_en`, `usado_en`, `revocado_en`, `motivo_revocacion`. Índice por `token_hash` (`02` §12.1).

### `alicuota_iva`, `medio_pago`, `motivo`

| Tabla | Columnas |
| --- | --- |
| `alicuota_iva` | `id`, `organizacion_id`, `nombre`, `valor` `numeric(9,6)`, `activo` |
| `medio_pago` | `id`, `organizacion_id`, `nombre`, `requiere_referencia` `boolean`, `activo` |
| `motivo` | `id`, `organizacion_id`, `ambito` (`AJUSTE_STOCK`, `ANULACION_VENTA`, `ANULACION_COMPRA`, `ANULACION_COBRANZA`, `DESCUENTO_MANUAL`, `LISTA_ANTERIOR`, `LIBERACION_JORNADA`), `nombre`, `activo` |

## 5. Catálogo

### `categoria`, `marca`

`id`, `organizacion_id`, `nombre` (`UNIQUE (organizacion_id, nombre)`), `activo`, `actualizado_en`.

### `producto`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | |
| `codigo` | `text` | `UNIQUE (organizacion_id, codigo)` (CAT-01) |
| `nombre` | `text` | |
| `categoria_id`, `marca_id` | `uuid` | `marca_id` opcional |
| `proveedor_id` | `uuid` | Obligatorio en etapa 1 (CAT-06) |
| `unidad_base` | `text` | Nombre visible: botella, unidad |
| `alicuota_id` | `uuid` | CAT-01 |
| `activo` | `boolean` | CAT-05 |
| `actualizado_en` | `timestamptz` | |

### `presentacion`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id`, `producto_id` | `uuid` | |
| `nombre` | `text` | "Botella", "Caja x6" |
| `unidades_base` | `integer` | `CHECK (unidades_base >= 1)` |
| `usar_en_venta`, `usar_en_compra` | `boolean` | CAT-02 |
| `es_referencia` | `boolean` | CAT-03 |
| `activo` | `boolean` | |

Restricciones:

```sql
CREATE UNIQUE INDEX ux_presentacion__referencia
    ON presentacion (organizacion_id, producto_id)
    WHERE es_referencia;                      -- CAT-03: exactamente una
ALTER TABLE presentacion ADD CONSTRAINT ck_presentacion__referencia_venta
    CHECK (NOT es_referencia OR usar_en_venta);
```

La presentación de referencia se resuelve por este indicador y no con una clave foránea desde `producto`, para evitar una dependencia circular. CAT-04 (unidades inmutables si la presentación se usó) se valida en el servicio de catálogo; la base no puede expresarlo.

## 6. Proveedores, costos y compras

### `proveedor`

`id`, `organizacion_id`, `nombre`, `cuit`, `contacto`, `telefono`, `email`, `activo`, `actualizado_en`.

**No tiene columna de saldo** (CC-04, INV-13): el saldo vive en `saldo_cuenta`.

**Unicidades** (`design.md` D7 del change 06, aprobadas 2026-09-23):
- `ux_proveedor__nombre` — única `(organizacion_id, nombre)`: el nombre no se repite entre proveedores de la misma organización, activos o no.
- `ux_proveedor__cuit` — índice único parcial `(organizacion_id, cuit) WHERE cuit IS NOT NULL`: el CUIT, cuando se informa, no se repite en la organización; varios proveedores sin CUIT en la misma organización son válidos (la parcialidad los excluye del índice).

### `costo_informado`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | |
| `proveedor_id`, `producto_id`, `presentacion_id` | `uuid` | |
| `valor` | `numeric(14,2)` | Valor informado por presentación |
| `incluye_iva` | `boolean` | |
| `bonificacion` | `numeric(9,6)` | Default 0 |
| `alicuota_aplicada` | `numeric(9,6)` | Congelada para reconstruir el cálculo |
| `costo_base` | `numeric(18,6)` | Derivado (CST-02) |
| `vigencia_desde` | `date` | |
| `observacion` | `text` | |
| `operation_id`, `usuario_id`, `creado_en` | | |

Índice `ix_costo_informado__producto_vigencia (organizacion_id, producto_id, vigencia_desde DESC, creado_en DESC, id DESC)` para CST-03: el desempate por `creado_en DESC, id DESC` (`design.md` D4 del change 06, aprobado 2026-09-23) resuelve qué costo prevalece cuando dos tienen la misma `vigencia_desde` — el registrado último.

### `compra` y `compra_linea`

| Tabla | Columnas |
| --- | --- |
| `compra` | `id`, `organizacion_id`, `proveedor_id`, `ubicacion_id`, `fecha` `date`, `condicion` (`CONTADO`, `CREDITO`), `total_neto`, `estado` (`CONFIRMADA`, `ANULADA`), `anulacion_motivo_id`, `anulada_en`, `anulada_por_id`, columnas de operación |
| `compra_linea` | `id`, `organizacion_id`, `compra_id`, `producto_id`, `presentacion_id`, `unidades_presentacion` `integer` (congelado), `cantidad` `numeric(14,3)`, `cantidad_base` `integer`, `valor_presentacion` `numeric(14,2)`, `incluye_iva`, `bonificacion`, `costo_base` `numeric(18,6)`, `importe_neto` `numeric(14,2)` |

`CHECK (cantidad_base > 0)`. La existencia de al menos una línea (INV-07) se valida en el servicio dentro de la transacción.

### `pago_proveedor` y `pago_proveedor_medio`

| Tabla | Columnas |
| --- | --- |
| `pago_proveedor` | `id`, `organizacion_id`, `proveedor_id`, `fecha`, `importe` `numeric(14,2)` `CHECK (> 0)`, `estado`, columnas de operación |
| `pago_proveedor_medio` | `id`, `organizacion_id`, `pago_id`, `medio_pago_id`, `importe`, `referencia` |

INV-08 (suma de medios = importe) se valida en el servicio y se cubre con prueba de propiedad.

## 7. Costeo

### `costo_producto`

Fila de bloqueo del producto (`02` §7.2 y §7.3).

| Columna | Tipo | Notas |
| --- | --- | --- |
| `organizacion_id`, `producto_id` | `uuid` | PK compuesta |
| `costo_promedio` | `numeric(18,6)` | CST-10 |
| `stock_total` | `integer` | Suma de `stock_saldo` del producto |
| `actualizado_en` | `timestamptz` | |

### `costo_producto_mov`

Historia del promedio (CST-13), de solo inserción.

`id`, `organizacion_id`, `producto_id`, `origen_tipo` (`COMPRA`, `ANULACION_COMPRA`, `STOCK_INICIAL`, `ANULACION_VENTA`), `origen_id`, `cantidad` `integer`, `costo_ingreso` `numeric(18,6)`, `stock_anterior`, `promedio_anterior`, `stock_nuevo`, `promedio_nuevo`, `recalculado` `boolean` (falso cuando se mantuvo el promedio, CMP-06), `operation_id`, `registered_at`.

## 8. Precios

| Tabla | Columnas | Reglas |
| --- | --- | --- |
| `lista_precio` | `id`, `organizacion_id`, `nombre`, `redondeo_multiplo`, `redondeo_direccion`, `activo` | PRC-01, PRC-14 |
| `regla_margen` | `id`, `organizacion_id`, `lista_id`, `alcance_tipo` (`PRODUCTO`, `MARCA`, `CATEGORIA`, `PROVEEDOR`, `LISTA`), `alcance_id` (nulo si `LISTA`), `tipo` (`MARKUP`, `MARGEN_BRUTO`), `valor` `numeric(9,6)`, `activo` | PRC-12, PRC-13 |
| `redondeo_categoria` | `id`, `organizacion_id`, `lista_id`, `categoria_id`, `multiplo`, `direccion` | PRC-14 |
| `lista_version` | `id`, `organizacion_id`, `lista_id`, `numero` `integer`, `estado` (`BORRADOR`, `PUBLICADA`, `ANULADA`), `vigencia_desde` `timestamptz`, `vigencia_hasta` `timestamptz` nulo, `creado_por_id`, `publicado_por_id`, `publicado_en`, `operation_id` | PRC-02 a PRC-06 |
| `precio_item` | `id`, `organizacion_id`, `version_id`, `producto_id`, `costo_referencia` `numeric(18,6)`, `regla_margen_id`, `tipo_margen`, `valor_margen`, `precio_calculado` `numeric(18,6)`, `precio_final` `numeric(14,2)`, `manual` `boolean` | PRC-16 |

Restricciones:

```sql
ALTER TABLE regla_margen ADD CONSTRAINT ck_regla_margen__valor
    CHECK (valor >= 0 AND (tipo <> 'MARGEN_BRUTO' OR valor < 1));   -- PRC-12
CREATE UNIQUE INDEX ux_precio_item__version_producto
    ON precio_item (organizacion_id, version_id, producto_id);      -- PRC-10
CREATE UNIQUE INDEX ux_lista_version__numero
    ON lista_version (organizacion_id, lista_id, numero);
```

`precio_item` guarda un único precio por producto, sobre la presentación de referencia. No existe precio por presentación (PRC-10). La inmutabilidad de una versión publicada (INV-11) se aplica en el servicio.

## 9. Stock y ruta

### `ubicacion`

`id`, `organizacion_id`, `nombre`, `tipo` (`DEPOSITO`, `VEHICULO`, `OTRO`), `requiere_toma` `boolean`, `activo` (STK-02).

### `stock_saldo`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `organizacion_id`, `producto_id`, `ubicacion_id` | `uuid` | PK compuesta |
| `cantidad_base` | `integer` | Puede ser negativa (STK-05, STK-06) |
| `actualizado_en` | `timestamptz` | |

### `stock_movimiento`

Libro de stock, de solo inserción (INV-12).

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | |
| `producto_id`, `ubicacion_id` | `uuid` | |
| `cantidad_base` | `integer` | Con signo; `CHECK (cantidad_base <> 0)` |
| `tipo` | `text` | STK-03 |
| `origen_tipo`, `origen_id` | `text`, `uuid` | Documento que lo generó |
| `costo_unitario` | `numeric(18,6)` | Congelado en ventas y ajustes |
| `jornada_id`, `motivo_id` | `uuid` | Opcionales |
| Columnas de operación | | |

Índices: `(organizacion_id, producto_id, ubicacion_id, occurred_at)` para kardex y verificación de consistencia; `(organizacion_id, origen_tipo, origen_id)` para reversiones.

El origen es genérico (`origen_tipo` + `origen_id`) y no una clave foránea por tipo de documento. Se valida en el servicio y en pruebas.

### `transferencia`, `ajuste_stock` y sus líneas

| Tabla | Columnas |
| --- | --- |
| `transferencia` | `id`, `organizacion_id`, `ubicacion_origen_id`, `ubicacion_destino_id`, `estado`, columnas de operación; `CHECK (origen <> destino)` |
| `transferencia_linea` | `id`, `organizacion_id`, `transferencia_id`, `producto_id`, `cantidad_base` `CHECK (> 0)` |
| `ajuste_stock` | `id`, `organizacion_id`, `ubicacion_id`, `motivo_id`, `observacion`, columnas de operación |
| `ajuste_stock_linea` | `id`, `organizacion_id`, `ajuste_id`, `producto_id`, `cantidad_base` (con signo), `costo_unitario` `numeric(18,6)` |

### `jornada`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | |
| `usuario_id`, `dispositivo_id`, `ubicacion_id` | `uuid` | RUT-01 |
| `estado` | `text` | `ABIERTA`, `EN_RENDICION`, `CERRADA`, `LIBERADA` |
| `abierta_en`, `rendida_en`, `cerrada_en`, `liberada_en` | `timestamptz` | |
| `liberada_por_id`, `motivo_liberacion_id` | `uuid` | RUT-09 |

```sql
CREATE UNIQUE INDEX ux_jornada__ubicacion_abierta
    ON jornada (organizacion_id, ubicacion_id)
    WHERE estado IN ('ABIERTA', 'EN_RENDICION');   -- INV-16
```

### `rendicion` y `rendicion_linea`

| Tabla | Columnas |
| --- | --- |
| `rendicion` | `id`, `organizacion_id`, `jornada_id` (único), columnas de operación |
| `rendicion_linea` | `id`, `organizacion_id`, `rendicion_id`, `producto_id`, `cantidad_esperada`, `cantidad_contada`, `diferencia` `integer` |

Las diferencias generan movimientos `DIFERENCIA_RENDICION` con origen en la rendición (RUT-06).

## 10. Clientes

### `cliente`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | |
| `codigo` | `text` | Opcional. Único por organización con índice parcial `WHERE codigo IS NOT NULL` (`ux_cliente__codigo`, `design.md` D1 del change 07, ADR-031) |
| `nombre`, `razon_social` | `text` | `nombre` NO es único: el mismo nombre puede repetirse en la organización (D1) |
| `documento_tipo`, `documento_numero` | `text` | CUIT o DNI; opcionales como pareja (si se informa uno, el otro es obligatorio). `documento_numero` se normaliza a solo dígitos. Único por organización como pareja, con índice parcial `WHERE documento_numero IS NOT NULL` (`ux_cliente__documento`, D1). Longitud validada por tipo: CUIT 11 dígitos, DNI 7 u 8 (CLI-05) |
| `direccion`, `telefono`, `email` | `text` | `direccion` obligatoria |
| `lista_precio_id` | `uuid` | Columna sin FK hasta que el change 13 cree `lista_precio` y agregue la FK compuesta `(organizacion_id, lista_precio_id)` (D2 del change 07; mismo precedente que `producto.proveedor_id`, ADR-025). No se ofrece en ningún formulario hasta entonces |
| `limite_credito` | `numeric(14,2)` | Nulo = sin control (CRE-01) |
| `politica_credito` | `text` | Nulo = la de la organización (CRE-03) |
| `tolerancia_offline_tipo`, `tolerancia_offline_valor` | `text`, `numeric(14,2)` | Nulos = los de la organización (CRE-06). Misma escala que `configuracion_organizacion.tolerancia_offline_valor` (ADR-032 del change 07) |
| `estado_facturacion_default` | `text` | Nulo = el de la organización (VTA-08) |
| `es_consumidor_final` | `boolean` | CLI-03; solo lo asigna `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` (ADR-029) |
| `estado` | `text` | `ACTIVO`, `SUSPENDIDO`, `INACTIVO`. Nace `ACTIVO`; `INACTIVO` se revierte solo sin operaciones (CLI-06, ADR-030) |
| `creado_en`, `actualizado_en` | `timestamptz` | |

**Deuda consciente (change 07):** `condicion_iva`, que este párrafo listaba, no se crea todavía — `01` §16 y FAC-04 no definen su dominio y el change de facturación la agrega junto con su catálogo (`design.md` D5 del change 07). El modelo en código no tiene esa columna hasta entonces.

## 11. Descuentos

| Tabla | Columnas | Reglas |
| --- | --- | --- |
| `regla_descuento` | `id`, `organizacion_id`, `nombre`, `tipo` (`VOLUMEN_OPERACION`, `VOLUMEN_ALCANCE`), `medida` (`CAJAS_EQUIVALENTES`, `UNIDADES_BASE`, `IMPORTE_BRUTO`), `operador` (`GTE`, `GT`), `umbral` `numeric(14,4)`, `accion_tipo` (`PORCENTAJE`, `IMPORTE_FIJO`), `accion_valor`, `prioridad` `integer`, `acumulable` `boolean`, `vigencia_desde`, `vigencia_hasta`, `estado` (`BORRADOR`, `ACTIVA`, `PAUSADA`) | DSC-01 a DSC-04 |
| `regla_descuento_alcance` | `id`, `organizacion_id`, `regla_id`, `alcance_tipo` (`PRODUCTO`, `CATEGORIA`, `MARCA`), `alcance_id` | DSC-02 |

Una regla `VOLUMEN_OPERACION` no tiene filas de alcance. Una `VOLUMEN_ALCANCE` tiene al menos una.

## 12. Ventas, cobranzas y cuentas corrientes

### `venta`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | `uuid` | Generado en el dispositivo |
| `organizacion_id` | `uuid` | |
| `numero` | `text` | `UNIQUE (organizacion_id, numero)` (VTA-06) |
| `cliente_id`, `usuario_id`, `dispositivo_id`, `ubicacion_id` | `uuid` | |
| `jornada_id` | `uuid` | Nulo en ventas desde PC |
| `lista_version_id` | `uuid` | PRC-23 |
| `modo_impositivo` | `text` | Congelado |
| `modo_confirmacion` | `text` | `ONLINE`, `OFFLINE` |
| `total_neto`, `total_iva`, `total` | `numeric(14,2)` | INV-14 |
| `estado` | `text` | `CONFIRMADA`, `ANULADA` |
| `estado_facturacion` | `text` | `NO_REQUIERE`, `PENDIENTE`, `PARCIAL`, `FACTURADA` |
| `importe_facturado` | `numeric(14,2)` | Default 0 (INV-09) |
| `credito_limite`, `credito_saldo_considerado`, `credito_disponible`, `credito_exceso` | `numeric(14,2)` | CRE-10 |
| `credito_politica`, `credito_resolucion` | `text` | `ADVERTENCIA_ACEPTADA`, `PERMISO_PROPIO`, `PIN_SUPERVISOR`, `TOLERANCIA_OFFLINE`, `SIN_EXCESO` |
| `credito_autorizador_id` | `uuid` | |
| `operation_id`, `occurred_at`, `registered_at` | | |

```sql
ALTER TABLE venta ADD CONSTRAINT ck_venta__facturado
    CHECK (importe_facturado >= 0 AND importe_facturado <= total_neto);   -- INV-09
ALTER TABLE venta ADD CONSTRAINT ck_venta__jornada
    CHECK (modo_confirmacion = 'ONLINE' OR jornada_id IS NOT NULL);
```

Índices: `(organizacion_id, occurred_at)`, `(organizacion_id, cliente_id, occurred_at)`, `(organizacion_id, usuario_id, occurred_at)`, y parcial `(organizacion_id, cliente_id) WHERE estado_facturacion IN ('PENDIENTE','PARCIAL')`.

### `venta_linea`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id`, `venta_id` | `uuid` | |
| `orden` | `integer` | |
| `producto_id`, `presentacion_id` | `uuid` | |
| `unidades_presentacion` | `integer` | Congelado (INV-18) |
| `cantidad` | `integer` | En la presentación |
| `cantidad_base` | `integer` | `CHECK (> 0)` |
| `precio_referencia` | `numeric(14,2)` | Congelado |
| `unidades_referencia` | `integer` | Congelado (PRC-23) |
| `importe_bruto`, `importe_descuento`, `importe_neto` | `numeric(14,2)` | |
| `alicuota` | `numeric(9,6)` | Congelada |
| `importe_iva` | `numeric(14,2)` | Cero en modo A |
| `costo_unitario` | `numeric(18,6)` | VTA-05 |
| `costo_total` | `numeric(14,2)` | |

`CHECK (importe_neto = importe_bruto - importe_descuento)`.

**No existe** una columna de IVA absorbido: ese ajuste va en `ajuste_iva_absorbido` (§13) para no tocar valores congelados (FAC-03, INV-10).

### `venta_linea_descuento`

`id`, `organizacion_id`, `venta_linea_id`, `origen` (`AUTOMATICO`, `MANUAL`), `regla_id` (nulo si manual), `porcentaje` `numeric(9,6)`, `importe` `numeric(14,2)`, `motivo_id`, `autorizador_id` (DSC-08).

### `venta_anulacion`

`id`, `organizacion_id`, `venta_id` (único), `motivo_id`, `observacion`, `devuelve_dinero` `boolean` (VTA-22), columnas de operación.

### `cobranza`, `cobranza_medio`, `cobranza_anulacion`

| Tabla | Columnas |
| --- | --- |
| `cobranza` | `id`, `organizacion_id`, `cliente_id`, `venta_id` (nulo si independiente), `origen` (`VENTA`, `INDEPENDIENTE`), `importe` `CHECK (> 0)`, `estado`, `jornada_id`, columnas de operación |
| `cobranza_medio` | `id`, `organizacion_id`, `cobranza_id`, `medio_pago_id`, `importe`, `referencia` |
| `cobranza_anulacion` | `id`, `organizacion_id`, `cobranza_id` (único), `motivo_id`, columnas de operación |

### `cuenta_movimiento`

Libro único para clientes y proveedores, de solo inserción (CC-01).

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | `UNIQUE (organizacion_id, id)` |
| `cuenta_tipo` | `text` | `CLIENTE`, `PROVEEDOR` |
| `entidad_id` | `uuid` | Cliente o proveedor |
| `cliente_id` | `uuid` | **Generada** por la base: `entidad_id` si `cuenta_tipo = CLIENTE`, si no nulo. FK compuesta `(organizacion_id, cliente_id) → cliente` |
| `proveedor_id` | `uuid` | **Generada** por la base: `entidad_id` si `cuenta_tipo = PROVEEDOR`, si no nulo. FK compuesta `(organizacion_id, proveedor_id) → proveedor` |
| `tipo` | `text` | CC-02, CC-03. `CHECK` de catálogo y de coherencia con `cuenta_tipo` (sin los tipos de IVA, que agrega el módulo de facturación) |
| `sentido` | `text` | `AUMENTA`, `REDUCE` |
| `importe` | `numeric(14,2)` | `CHECK (importe > 0)` |
| `origen_tipo`, `origen_id` | `text`, `uuid` | |
| `occurred_at`, `registered_at`, `usuario_id`, `operation_id` | | `usuario_id` con FK compuesta a `usuario` |
| `dispositivo_id` | `uuid` | `NOT NULL`. FK compuesta `(organizacion_id, dispositivo_id) → dispositivo` (§2.3) |

`cliente_id` y `proveedor_id` no las escribe nadie: las calcula PostgreSQL, y existen para que la referencia a `cliente` o a `proveedor` sea una clave foránea compuesta (§2.4) aunque `entidad_id` apunte a dos tablas según `cuenta_tipo`. El emparejamiento entre `tipo` y `sentido` (por ejemplo, `VENTA` siempre `AUMENTA`) no tiene `CHECK` en la base: lo verifica el dominio (ADR-034).

**No tiene columna de saldo acumulado.** El saldo se calcula (CC-04) y se materializa en `saldo_cuenta`.

Índice principal: `(organizacion_id, cuenta_tipo, entidad_id, occurred_at, id)`.

### `saldo_cuenta`

`organizacion_id`, `cuenta_tipo`, `entidad_id` (PK compuesta, sin `id`: ninguna tabla referencia una fila de saldo), `cliente_id` y `proveedor_id` (generadas, con las mismas FK compuestas que `cuenta_movimiento`), `saldo` `numeric(14,2) NOT NULL DEFAULT 0`, `actualizado_en`. Es la fila que se bloquea al evaluar crédito y al registrar movimientos (`02` §7.3). La fila nace de forma perezosa con el primer movimiento de la cuenta (`INSERT ... ON CONFLICT DO NOTHING` y `SELECT ... FOR UPDATE`).

## 13. Sincronización, auditoría, importación y facturación

### `comando`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id`, `organizacion_id` | `uuid` | |
| `operation_id` | `uuid` | `UNIQUE (organizacion_id, operation_id)` (INV-06) |
| `tipo`, `version` | `text`, `integer` | |
| `modo` | `text` | `ONLINE`, `OFFLINE` |
| `usuario_id`, `dispositivo_id`, `jornada_id` | `uuid` | |
| `secuencia` | `integer` | Orden en la cola del dispositivo |
| `huella` | `text` | SHA-256 del contenido canónico |
| `app_version` | `text` | |
| `estado` | `text` | `PROCESANDO`, `ACEPTADO`, `ACEPTADO_CON_OBSERVACIONES`, `RECHAZADO` |
| `resultado` | `jsonb` | Respuesta devuelta al cliente |
| `error_codigo` | `text` | |
| `occurred_at`, `registered_at` | | |

El índice único es el mecanismo de idempotencia (`02` §6.3). El contenido completo del comando no se almacena: lo relevante queda en las entidades que creó y en `resultado`.

### `comando_cuarentena`

`id`, `organizacion_id`, `dispositivo_id`, `usuario_id`, `operation_id`, `tipo`, `contenido` `jsonb`, `motivo`, `recibido_en`, `revisado_en`, `revisado_por_id` (SYN-06).

### `observacion`

`id`, `organizacion_id`, `comando_id`, `operacion_tipo`, `operacion_id`, `codigo` (SYN-07), `detalle` `jsonb`, `estado` (`PENDIENTE`, `RESUELTA`), `resuelto_por_id`, `resuelto_en`, `comentario`.

Índice parcial `(organizacion_id, codigo) WHERE estado = 'PENDIENTE'`.

### `auditoria`

`id`, `organizacion_id`, `usuario_id`, `dispositivo_id`, `accion`, `entidad`, `entidad_id`, `antes` `jsonb`, `despues` `jsonb`, `motivo_id`, `observacion`, `autorizador_id`, `operation_id`, `occurred_at`, `registered_at` (AUD-02). Solo inserción.

### `importacion`

`id`, `organizacion_id`, `tipo` (`PRODUCTOS`, `CLIENTES`, `PROVEEDORES`, `PRECIOS`, `STOCK_INICIAL`, `SALDOS_INICIALES`), `archivo_nombre`, `estado`, `filas_total`, `filas_ok`, `filas_error`, `errores` `jsonb`, columnas de operación.

### Facturación (se crea al desarrollar el módulo)

| Tabla | Columnas | Reglas |
| --- | --- | --- |
| `factura` | `id`, `organizacion_id`, `cliente_id`, `fecha`, `modalidad_iva` (`CLIENTE`, `ABSORBIDO`), `punto_venta`, `numero`, `neto`, `iva`, `total`, `estado` (`EMITIDA`, `ANULADA`), `anulacion_motivo_id`, columnas de operación | FAC-04, FAC-06 |
| `factura_venta` | `id`, `organizacion_id`, `factura_id`, `venta_id`, `importe_facturado`; `UNIQUE (organizacion_id, factura_id, venta_id)` | FAC-07 |
| `factura_alicuota` | `id`, `organizacion_id`, `factura_id`, `alicuota`, `neto`, `iva` | FAC-08 |
| `ajuste_iva_absorbido` | `id`, `organizacion_id`, `factura_id`, `venta_linea_id`, `importe` | FAC-03 |

El débito de IVA en modalidad CLIENTE es un `cuenta_movimiento` de tipo `IVA_FACTURA` con origen en la factura (FAC-02). El núcleo lo registra a pedido del módulo (FAC-10).

## 14. Diferencias con el ERD original

| ERD original | Este modelo | Motivo |
| --- | --- | --- |
| `PROVEEDOR.saldo` | Eliminado; `saldo_cuenta` | CC-04, INV-13 |
| `CC_CLIENTE_MOV.saldo` por fila | Eliminado; saldo calculado y materializado | Operaciones offline con fecha anterior obligarían a recalcular filas |
| `CAPA_COSTO` y consumo FIFO | `costo_producto` y `costo_producto_mov` | ADR-002 |
| Sin saldo de stock | `stock_saldo` | Fila que bloquear ante concurrencia |
| Sin stock total por producto | `costo_producto.stock_total` | Recálculo consistente del promedio |
| `MOV_STOCK` solo con `venta_item_id` | `origen_tipo` + `origen_id` | Compras, transferencias, ajustes, rendiciones |
| Sin tabla de comandos | `comando`, `comando_cuarentena`, `observacion` | INV-06, SYN |
| Sin roles ni permisos | `rol`, `permiso`, `rol_permiso` | `01` §19 |
| Sin dispositivos | `dispositivo`, `sesion_refresh` | SEG-02, numeración |
| `VENTA_ITEM.descuento` único | `venta_linea_descuento` | DSC-08 |
| Sin anulaciones | `venta_anulacion`, `cobranza_anulacion`, estados de compra | VTA-20, COB-05 |
| `PRECIO_ITEM` por presentación con un solo precio | `precio_item` por producto con costo, regla, precio calculado y final | PRC-10, PRC-16 |
| `VENTA` sin vendedor, estado ni número | Agregados | Reportes, trazabilidad, VTA-06 |
| Sin jornadas ni rendición | `jornada`, `rendicion`, `rendicion_linea` | RUT |
| Sin costo informado del proveedor | `costo_informado` | El precio se calcula con un costo distinto del de compra |
| Sin snapshot de unidades por presentación | `unidades_presentacion` y `unidades_referencia` en `venta_linea` | INV-18 |
| Sin evaluación de crédito | Columnas `credito_*` en `venta` | CRE-10 |

## 15. Restricciones que la base garantiza

| Invariante | Mecanismo |
| --- | --- |
| INV-02 | `organizacion_id` obligatorio y claves foráneas compuestas |
| INV-03 | Tipos `numeric`; prueba que recorre el catálogo de columnas |
| INV-04 | `integer` en cantidades base |
| INV-05 | Permisos del usuario de aplicación sobre tablas de libro |
| INV-06 | `UNIQUE (organizacion_id, operation_id)` en `comando` |
| INV-09 | `CHECK` en `venta.importe_facturado` |
| INV-16 | Índice único parcial en `jornada` |
| INV-18 | Columnas congeladas en `venta_linea` más validación de servicio |
| VTA-06 | `UNIQUE (organizacion_id, numero)` en `venta` |
| CAT-03 | Índice único parcial en `presentacion` |
| PRC-10 | `UNIQUE (organizacion_id, version_id, producto_id)` |

El resto (INV-01, INV-07, INV-08, INV-10 a INV-15, INV-17, INV-19 a INV-21) se garantiza en los servicios y se verifica con las pruebas de `02` §15.

## 16. Consultas frecuentes e índices

| Consulta | Índice |
| --- | --- |
| Saldo de un cliente | `saldo_cuenta` por PK |
| Estado de cuenta | `cuenta_movimiento (organizacion_id, cuenta_tipo, entidad_id, occurred_at, id)` |
| Stock de una ubicación | `stock_saldo` por PK; `ix_stock_saldo__ubicacion` |
| Kardex de un producto | `stock_movimiento (organizacion_id, producto_id, ubicacion_id, occurred_at)` |
| Ventas de un período | `venta (organizacion_id, occurred_at)` |
| Ventas de un vendedor o jornada | `venta (organizacion_id, usuario_id, occurred_at)`; `ix_venta__jornada` |
| Ventas pendientes de facturar | Índice parcial por estado de facturación |
| Observaciones pendientes | Índice parcial por estado |
| Precio vigente de un producto | `precio_item (organizacion_id, version_id, producto_id)` |
| Costo informado vigente | `costo_informado (organizacion_id, producto_id, vigencia_desde DESC)` |
| Verificación de consistencia | Recorridos completos por producto y por cuenta, en tarea nocturna |

Los reportes de utilidad por producto, cliente o proveedor se implementan como vistas (`vista_venta_utilidad`) que combinan `venta_linea` con `ajuste_iva_absorbido`. En la etapa 1 son vistas simples; si el volumen lo exige, pasan a vistas materializadas con actualización programada.

## 17. Migraciones

- **DEBE:** todo cambio de esquema es una migración de Alembic con `upgrade` y `downgrade` probados.
- **DEBE:** una migración que agrega una columna obligatoria lo hace en pasos: agregar como opcional, completar datos, agregar la restricción.
- **DEBE:** los datos de catálogo que dependen del código (`permiso`) se sincronizan por migración.
- **DEBE:** las migraciones no borran columnas ni tablas con datos sin un cambio previo que deje de usarlas.
- Los datos de ejemplo para desarrollo se cargan con un comando separado, nunca desde una migración.

## 18. Volumen estimado

Con la organización inicial (unos 100 productos, unos 200 clientes, unas 100 ventas diarias con 8 líneas promedio):

| Tabla | Filas por año |
| --- | --- |
| `venta` | ~25.000 |
| `venta_linea` | ~200.000 |
| `stock_movimiento` | ~250.000 |
| `cuenta_movimiento` | ~50.000 |
| `comando` | ~60.000 |

Son volúmenes que PostgreSQL maneja sin particionado ni archivado. La estructura admite crecer uno o dos órdenes de magnitud con los índices indicados; recién más allá de eso conviene evaluar particionar `stock_movimiento` y `venta_linea` por período.
