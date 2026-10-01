# ADR-042 — El módulo `importacion` orquesta la puesta en marcha y depende de los demás solo por su `service.py`

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-10-01 |
| Referenciado en | `openspec/changes/10-importacion-inicial/design.md` D4, D6, D8, D9 y D10 y `specs/importacion/importacion-de-maestros`; `02-arquitectura.md` §5.1 y §5.3; `03-modelo-de-datos.md` §3 y §13; ADR-013 (monolito modular) |

**Decisiones D4, D6, D8, D9 y D10 (opción A en cada una) aprobadas por el usuario el 2026-10-01. Texto del ADR aprobado por el usuario el 2026-10-01; estado *Vigente*.**

## Contexto

`03` §3 ya prevé un módulo `importacion`, pero `02` §5.1 y §5.3 no lo listan ni dicen de quién depende. Además `01` CST-05 dice que la importación masiva de costos es de la etapa 2, mientras `04` §6 pone los costos en el change 10, y `03` §13 tiene el tipo `PRECIOS` aunque las listas de precios nacen en el change 13 (que no depende del 10), sin un tipo `COSTOS`.

## Decisión

1. **Un módulo, un lector, un todo-o-nada.** `importacion` contiene la lectura de planillas, la conversión de valores, el informe de errores, el comando `IMPORTACION_REGISTRAR` y un importador por tipo, que es un adaptador fino sobre el servicio del módulo dueño. Las reglas de negocio **no** se duplican: cada fila se valida y se escribe con el servicio que usa la pantalla (TR-10), de modo que un mismo dato inválido da el mismo código de error.
2. **Dependencias.** `importacion ──► catalogo, proveedores, clientes, stock, cuentas_corrientes, configuracion, identidad`, solo por `service.py`. Nadie depende de `importacion`. `costeo` no se alcanza (lo usa `stock` por dentro). `importacion.api` llama a `sync.service.procesar_comando`, como el resto de las APIs de escritura. `importacion.domain` no importa FastAPI, SQLAlchemy ni el bus. Contratos de import-linter: `importacion-domain-no-infraestructura` e `importacion-solo-por-service-ajeno`.
3. **Claves naturales (D4).** Categoría y marca por nombre; alícuota por porcentaje; proveedor por nombre; producto por código; presentación por nombre dentro del producto; cliente por código o, si no, por documento (en dígitos); ubicación por nombre. Comparación sin mayúsculas ni espacios al borde. Más de una coincidencia es `REFERENCIA_AMBIGUA`; ninguna, `REFERENCIA_NO_ENCONTRADA` (nunca 404: es un error de fila y no revela datos de otra organización). No se crean categorías ni marcas al vuelo. Las búsquedas viven en los `service.py` dueños (`buscar_*_por_*`), con filtro de organización.
4. **Solo altas (D6).** Una clave que ya existe da el error de duplicado de su entidad; un duplicado dentro del archivo da `FILA_DUPLICADA` indicando la fila anterior. En la planilla de clientes `codigo` es obligatorio (CLI-01 lo deja opcional en la pantalla) para poder referenciar clientes en los saldos y para que una reimportación no duplique.
5. **Costos incluidos (D8).** La importación de costos entra en este change por `informar_costos` (lote de una fila): `04` §6 es posterior a CST-05 y el change 06 nominó la deuda. CST-05 se aclara: importación **inicial** en la etapa 1; importación masiva **recurrente** en la etapa 2.
6. **Catálogo de tipos (D9).** `importacion.tipo` acepta `PRODUCTOS`, `CLIENTES`, `PROVEEDORES`, `PRECIOS`, `COSTOS`, `STOCK_INICIAL` y `SALDOS_INICIALES`, igual que el precedente de declarar el catálogo completo de la etapa (ADR-034 punto 7). `PRECIOS` no tiene importador hasta el change 13 (deuda nominada): la API lo rechaza con 422 `TIPO_IMPORTACION_INVALIDO`.
7. **Momento (D7-A).** El stock y los saldos iniciales se fechan con el `occurred_at` del sobre, como la pantalla (ADR-034, ADR-037 punto 5); no hay fecha de corte. STK-10 y CC-08 impiden cargar después de la primera operación, así que nada operativo queda antes.
8. **Orden de bloqueo.** Los importadores de puesta en marcha escriben el stock por (producto, ubicación) y los saldos por (`cuenta_tipo`, entidad), ascendentes y con un orden estable que deja una corrección negativa después de su ingreso (`02` §7.3, ADR-015, ADR-039), para no interbloquearse con un `STOCK_INICIAL_REGISTRAR` por pantalla.

## Consecuencias

- El lector, el todo-o-nada y el informe están en un solo lugar y se prueban una vez.
- Cada módulo dueño expone funciones de búsqueda por clave natural (con su propia prueba) y conserva sus reglas; si una regla faltaba en la pantalla (nombres vacíos de producto, `estado_facturacion_default` inválido), se agrega al dominio del módulo dueño y la importación la hereda (change 10, grupo 12).
- Cuando el change 13 cree las listas de precios, agrega su importador al registro `IMPORTADORES` sin migrar la tabla.
- `02` §5.1 y §5.3, `03` §13 y `01` CST-05 requieren la actualización propuesta en `openspec/changes/10-importacion-inicial/propuesta-docs.md`.

## Alternativas consideradas

- **Cada módulo expone su importador y un lector común vive en `core/`:** descartada: repite seis veces el todo-o-nada y el informe, y `core` quedaría acoplado a planillas.
- **Crear al vuelo las categorías y marcas que no existan:** descartada: un error de tipeo ("Vinoss") crea una categoría que después hay que desactivar a mano.
- **Alta o modificación (upsert) por clave natural:** descartada: una reimportación por error pisaría datos sin aviso.
- **Excluir costos (CST-05 literal):** descartada: deja sin cargar el dato que el change 13 necesita para generar listas, y la deuda del change 06 queda sin dueño.
- **Declarar solo los seis tipos implementados:** descartada: obliga a migrar la tabla en el change 13.
