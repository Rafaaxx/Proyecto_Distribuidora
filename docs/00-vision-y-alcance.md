# 00 — Visión y alcance

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Versión | 1.0 |
| Fecha | 2026-09-16 |
| Reemplaza a | `docs/referencia/` (paquete original v1.0/v1.1, solo consulta) |
| Documentos relacionados | `01-dominio.md`, `02-arquitectura.md`, `03-modelo-de-datos.md`, `04-roadmap-changes.md`, `adr/` |

## 1. Propósito de este documento

Define qué es el sistema, para quién es, qué problema resuelve y **qué entra en cada etapa**. Es el punto de partida para cualquier decisión de alcance: si una funcionalidad no figura en la etapa en curso, no se implementa en esa etapa.

### 1.1 Precedencia de fuentes

1. Los ADR en `docs/adr/` prevalecen sobre cualquier otro texto en la decisión que tratan.
2. Los documentos `docs/00` a `docs/04` son la fuente de verdad del proyecto.
3. Los documentos en `docs/referencia/` son antecedentes. Contienen contradicciones ya resueltas y **no deben usarse como especificación**. Si un documento de referencia contradice a `docs/`, vale `docs/`.
4. Las specs en `openspec/specs/` describen lo que el sistema ya implementa. Se generan a partir de estos documentos, change por change.

Todo cambio de alcance o de una decisión vigente se registra como ADR nuevo o como actualización de este documento, nunca solo en una conversación.

## 2. Visión

### 2.1 Contexto operativo

La organización inicial es una distribuidora de bebidas y alimentos (vinos, cervezas, vermuts y alfajores). El vendedor visita al cliente con mercadería cargada en el vehículo, toma el pedido, entrega en el momento y cobra total, parcialmente o a cuenta corriente. Hoy gran parte del trabajo se hace con papel y planillas, lo que genera carga administrativa, demoras y errores. Hay zonas de la ruta sin señal.

### 2.2 Problema

- La venta en ruta se registra en papel y se transcribe después, con errores y demoras.
- El stock del depósito y del vehículo no se conoce con certeza.
- Los saldos de clientes y proveedores se reconstruyen a mano.
- Los precios se recalculan manualmente ante cada cambio de costo.
- No se conoce la utilidad real por venta, producto, cliente o proveedor.

### 2.3 Objetivo

Un sistema de gestión con una sola fuente de verdad que permita **vender, entregar y cobrar desde el teléfono con o sin señal**, y que mantenga stock, cuentas corrientes, precios, costos y utilidad consistentes de forma automática y auditable.

### 2.4 Horizonte de producto

El sistema se construye para la distribuidora, pero **debe poder comercializarse a otras distribuidoras** sin rediseño. Consecuencias desde el primer día:

- Toda entidad de negocio pertenece a una organización (`organization_id`).
- Nada específico de esta distribuidora se codifica fijo: márgenes, redondeos, unidades por caja, políticas de crédito y stock, modo impositivo, nombres y permisos viven en configuración o datos.
- El diseño no asume volúmenes chicos. La organización inicial tiene unos 10 proveedores y unos 100 productos, pero el sistema debe escalar a volúmenes varios órdenes de magnitud mayores sin cambiar su arquitectura.

## 3. Principios rectores

Detallados en `01-dominio.md` y `02-arquitectura.md`. Resumen:

| Principio | Significado operativo |
| --- | --- |
| Fuente única de verdad | PostgreSQL central. Reportes y saldos se derivan de las operaciones; no hay cifras mantenidas a mano. |
| Atomicidad | Una operación de negocio se registra completa o no se registra. |
| Historia inmutable | Nada confirmado se edita ni se borra: se anula o se revierte con movimientos inversos. Precios, costos y evaluaciones se congelan en cada operación. |
| Offline como arquitectura | La venta online y la offline usan el mismo pipeline de comandos idempotentes desde la base técnica. |
| La realidad física manda | Una venta offline ya entregada nunca se rechaza al sincronizar: se acepta y se marca para revisión. |
| Configuración antes que código | Reglas comerciales y políticas se parametrizan por organización. |
| Servidor como autoridad | Toda validación se repite en el servidor. El cliente solo calcula lo imprescindible para operar sin señal. |
| Simplicidad por etapas | Se construye la estructura de datos completa cuando postergarla obligaría a rediseñar; las pantallas y funciones se postergan cuando pueden esperar. |

## 4. Usuarios

| Rol estándar | Uso principal | Dispositivo habitual |
| --- | --- | --- |
| Administrador | Configuración, usuarios, permisos, costos, listas, compras, auditoría | PC |
| Administración | Compras, pagos a proveedores, cuentas corrientes, cobranzas, ajustes autorizados | PC |
| Vendedor / Repartidor | Carga y rendición del vehículo, venta, cobranza, nota de venta | Teléfono (PWA) |
| Supervisor comercial | Todo lo del vendedor, autorizaciones de excepciones (crédito, descuentos, listas anteriores) | Teléfono o PC |
| Consulta / Dirección | Reportes, solo lectura | PC |

Los roles son plantillas de permisos granulares (por ejemplo `VER_COSTOS`, `SUPERAR_CREDITO`, `ANULAR_VENTA`). Una organización puede crear roles propios combinando permisos. El catálogo de permisos está en `01-dominio.md`.

## 5. Parámetros de la organización inicial

Estos valores son **configuración de la primera organización**, no reglas del sistema. El sistema debe soportar las alternativas indicadas.

| Tema | Organización inicial | El sistema debe soportar además |
| --- | --- | --- |
| Condición frente al IVA | Monotributo: no recupera el IVA de compra, así que el IVA pagado es costo (CST-06, ADR-045) | Responsable inscripto (computa crédito fiscal) y exento |
| IVA en precios | Ventas a precio final, sin IVA discriminado (modo A); Factura C al facturar | Modo B (neto + IVA en la venta) y modo C (precios con IVA incluido), solo para un responsable inscripto |
| IVA al facturar | No aplica: un monotributista no discrimina IVA y no elige modalidad | Elegible por factura (a cargo del cliente o absorbido, con valor por defecto por organización y cliente), solo para un responsable inscripto (ADR-009, ADR-045) |
| Impuestos internos | No aplica | Queda fuera del alcance hasta que otra organización lo requiera |
| Facturación fiscal | Módulo separado; hoy la venta genera una nota de venta sin validez fiscal | Integración fiscal electrónica en una etapa posterior |
| Precio de unidad suelta | Proporcional al precio de la caja | — |
| Carga de costo | Por caja o por unidad, según cómo informe cada proveedor; el valor cargado es el pagado (con IVA incluido, que es costo) | Cualquier presentación de compra; un responsable inscripto puede indicar que el valor incluye IVA y el sistema lo descuenta |
| Proveedores por producto | Uno | Modelo con proveedor principal; múltiples proveedores como evolución |
| Costeo | Promedio ponderado móvil (ADR-002) | FIFO como estrategia futura desde fecha de corte |
| Cuenta corriente | General: la cobranza reduce el saldo global | Imputación por operación (etapa de producto comercial) |
| Stock | Depósito y vehículo como ubicaciones genéricas | N ubicaciones de cualquier tipo |
| Volumen | ~10 proveedores, ~100 productos | Volúmenes mucho mayores sin cambio de arquitectura |

## 6. Etapas

El alcance se divide en etapas que cierran circuitos completos. Cada etapa debe poder usarse en producción antes de empezar la siguiente, salvo el módulo de facturación, que tiene desarrollo independiente.

```
Etapa 1 — Ruta sin papel ─────────┬──> Etapa 2 — Circuito comercial y administrativo ──> Etapa 4 — Producto comercial ──> Evolución
                                  │
                                  └──> Módulo de facturación (independiente, en paralelo a la etapa 2)
```

### 6.1 Etapa 1 — Ruta sin papel

**Objetivo:** reemplazar el papel en la operación diaria de ruta y en el control de stock, cuentas corrientes y precios, con o sin señal.

| Capacidad | Incluye | No incluye (etapa posterior) |
| --- | --- | --- |
| Base técnica | Repositorio, entornos, Docker, CI, migraciones, logging estructurado, backups automáticos con restauración probada, HTTPS | Monitoreo avanzado |
| Organización y seguridad | Organización con configuración, usuarios, roles estándar, permisos granulares, auditoría de operaciones sensibles, dispositivos registrados y revocables, desbloqueo local con PIN | Onboarding de nuevas organizaciones, roles personalizados desde UI |
| Pipeline de comandos | Comandos idempotentes con UUID generado en cliente, usado tanto online como offline | — |
| Catálogo | Productos, categorías, marcas, presentaciones con unidades por caja, presentaciones de compra y de venta, alícuota de IVA por producto, proveedor del producto | Códigos de barras, fotos, catálogo para clientes |
| Clientes | Ficha, lista asignada, límite y política de crédito (ADR-003), estado | Segmentos para promociones, agenda de visitas |
| Proveedores | Ficha, cuenta corriente, compras a crédito y pagos | Vencimientos, notas de crédito/débito de proveedor |
| Importación inicial | Productos, clientes, proveedores, costos, stock y saldos iniciales (change 10) desde planillas (CSV/Excel); las listas de precios se importan desde el change 13 | Importadores genéricos para otras organizaciones |
| Puesta en marcha | Stock inicial valorizado por ubicación, saldos iniciales de clientes y proveedores | — |
| Costos | Carga de costo del proveedor por caja o unidad con vigencia; conversión a unidad base; costo promedio ponderado actualizado por compras | FIFO, fletes capitalizables |
| Compras | Registro de compra, ingreso de stock, actualización de costo promedio, deuda con proveedor, anulación por reversión | Órdenes de compra, recepción parcial |
| Precios | Listas múltiples versionadas con vigencia, margen (markup o margen bruto) con precedencia, redondeo configurable, generación de versión borrador desde nuevos costos, publicación, uso de lista anterior con permiso | Programación masiva, duplicación de listas con reglas porcentuales |
| Stock | Stock por ubicación en unidad base, visualización en cajas + unidades, transferencias, ajustes con motivo, kardex | Recuento físico guiado, alertas de stock bajo |
| Ruta | Carga del vehículo, toma de ubicación por jornada, rendición con conteo, diferencias como ajustes auditados, cierre y liberación | Rendición de caja completa, rutas y geolocalización |
| Venta | Pedido en cajas y unidades, precio desde lista, descuento manual controlado por permiso y tope, una o dos reglas de descuento por volumen, control de crédito, pago total/parcial/cuenta corriente con varios medios, confirmación atómica, costo congelado, anulación por reversión | Fidelización por historial, devoluciones parciales, bonificación en unidades |
| Offline | Bootstrap completo al abrir jornada, base local, cola de comandos, venta y cobranza sin señal, sincronización idempotente, marcas de revisión y pantalla de conflictos | Bootstrap incremental (queda previsto en el contrato) |
| Nota de venta | Comprobante interno sin validez fiscal, numeración por dispositivo, generación en el teléfono, compartir con Web Share API y descarga como respaldo | Plantillas personalizables por organización |
| Cuenta corriente y cobranzas | Libro de movimientos del cliente, cobranzas independientes con varios medios, estado de cuenta en pantalla | Estado de cuenta en PDF, antigüedad de deuda, imputación por operación |
| Reportes | Ventas por período en cajas, unidades, importe y utilidad (según permiso); rendición por vendedor y jornada; saldos de clientes y proveedores | Reportes completos de la etapa 2, exportación |

### 6.2 Etapa 2 — Circuito comercial y administrativo

- Devoluciones totales y parciales con reingreso de stock según estado.
- Notas de crédito y débito de clientes; ajustes de cuenta corriente con permiso y motivo.
- Fidelización por historial de compras y ampliación del motor de descuentos (reglas por categoría, marca, cliente, promociones temporales, acumulabilidad completa).
- Autorización remota de excepciones (crédito, descuentos).
- Antigüedad de deuda y política de bloqueo por deuda vencida.
- Vencimientos y calendario de pagos a proveedores; notas de crédito y débito de proveedor.
- Caja y tesorería: apertura, cierre, rendición de efectivo del vendedor, conciliación simple.
- Recuento físico e inventarios parciales o totales; alertas de stock bajo.
- Reportes completos: utilidad por producto, cliente, proveedor y categoría; costo vendido por proveedor frente a deuda real; rankings; comparativos entre períodos; filtros guardados.
- Exportación a Excel/CSV y PDF; estado de cuenta compartible.

### 6.3 Módulo de facturación (independiente)

Se desarrolla como módulo separado dentro del mismo backend, con su propio contrato hacia el núcleo. Puede comenzar una vez estable la venta de la etapa 1 y avanzar en paralelo a la etapa 2.

- Ventas pendientes de facturar por cliente y período.
- Factura individual o consolidada de varias ventas del mismo cliente.
- Modalidad de IVA elegible (a cargo del cliente o absorbido) con cascada organización → cliente → factura e invariantes FAC-01 a FAC-05.
- Prevención de doble facturación.
- Anulación mediante nota de crédito con reversión del efecto fiscal.
- Sin integración con organismos fiscales en esta etapa; el modelo queda preparado para incorporarla.

Hasta que este módulo esté en producción, la organización inicial factura por fuera del sistema. Las ventas registran su estado de facturación desde la etapa 1, por lo que las pendientes quedan identificadas.

### 6.4 Etapa 4 — Producto comercial

- Alta y onboarding de nuevas organizaciones; configuración de negocio desde la interfaz.
- Modos impositivos B y C operativos (el modelo existe desde la etapa 1).
- Imputación de cobranzas por operación como alternativa configurable.
- Roles personalizados desde la interfaz.
- Importadores genéricos y migración de saldos.
- Bootstrap incremental y filtrado de datos offline por vendedor o zona.
- Estrategia de costeo FIFO seleccionable desde fecha de corte.
- Múltiples proveedores por producto.
- Documentación de usuario y ayuda contextual.

### 6.5 Evolución (sin etapa asignada)

Integración con facturación electrónica, códigos de barras, geolocalización y rutas, portal de pedidos B2B, aplicación nativa si la PWA resulta insuficiente, inteligencia de negocio.

## 7. Estructura preparada desde la etapa 1

Estos elementos se incluyen en el modelo de datos y en los contratos desde el inicio, aunque su funcionalidad o interfaz llegue después, porque agregarlos más tarde obligaría a migrar datos históricos:

| Elemento | Se usa plenamente en |
| --- | --- |
| `organization_id` en toda entidad de negocio y aislamiento por organización en toda consulta | Etapa 4 |
| Alícuota de IVA por producto y modo impositivo por organización | Facturación y etapa 4 |
| Estado de facturación por venta y estructura de vínculo factura–venta | Módulo de facturación |
| Registro de descuentos por línea con origen, regla y autorizador | Etapa 2 |
| Costo congelado por línea de venta y servicio de costeo encapsulado | Etapa 4 (FIFO) |
| Proveedor asociado al producto con posibilidad de varios | Etapa 4 |
| Movimientos de stock con origen genérico | Etapa 2 (devoluciones, recuentos) |
| Libro de cuenta corriente con tipos de movimiento extensibles | Etapa 2 y facturación |
| `updated_at` o versión en tablas maestras y parámetro `since` en el bootstrap | Etapa 4 |
| Evaluación de crédito congelada en la venta | Etapa 2 (antigüedad de deuda) |

## 8. Fuera de alcance

Salvo nuevo ADR, el sistema no incluye:

- Contabilidad general de doble partida. El sistema mantiene libros auxiliares consistentes de clientes, proveedores y stock.
- Impuestos internos, percepciones y retenciones.
- Liquidación de sueldos y gastos generales. La utilidad es comercial por venta; la rentabilidad operativa es una capa futura separada.
- Aplicación nativa Android/iOS mientras la PWA cubra la operación.
- Microservicios o despliegues separados por módulo.

## 9. Criterios de éxito de la etapa 1

La etapa 1 se considera terminada cuando la siguiente demostración funciona de punta a punta en un teléfono real y en una PC, con datos realistas:

1. Se importan productos, clientes y proveedores desde planillas y se cargan stock inicial y saldos iniciales.
2. Se registra una compra a crédito de vino por caja y de cerveza por unidad, a costos distintos; el stock, el costo promedio y la deuda con el proveedor son correctos.
3. Se carga un nuevo costo, se genera una nueva versión de lista con margen y redondeo, y las ventas anteriores conservan su precio.
4. Se transfiere mercadería al vehículo y el vendedor toma la ubicación y abre la jornada.
5. Con la red cortada, el vendedor abre un cliente con saldo previo, arma un pedido de cajas y unidades sueltas, se aplica una regla de volumen y un descuento manual permitido, cobra una parte con efectivo y transferencia, y deja el resto en cuenta corriente.
6. Una segunda venta offline supera el crédito disponible y se resuelve según la política configurada.
7. Se genera la nota de venta y se comparte por WhatsApp sin señal.
8. Al recuperar la señal se sincroniza dos veces deliberadamente: existe una sola venta, con stock, saldo, costo y utilidad correctos.
9. Se anula una venta y el stock y el saldo vuelven a su estado anterior sin borrar historia.
10. En la rendición, el conteo del vehículo coincide con el stock esperado, o la diferencia queda registrada como ajuste auditado.
11. El reporte de ventas del período concilia con las operaciones registradas.
12. Se restaura un backup en un entorno separado y los datos coinciden.

Además, en todo momento: un usuario de otra organización no puede ver ni modificar datos ajenos, y ningún usuario puede ejecutar desde la API una acción que su rol no permite.

## 10. Supuestos y restricciones

- Un solo desarrollador, con desarrollo asistido por IA mediante Spec-Driven Development (OpenSpec).
- Stack definido en ADR-001: FastAPI + PostgreSQL en backend, React + TypeScript como PWA en frontend.
- Los vendedores usan teléfonos con navegador moderno. Si se usan iPhone, las limitaciones de PWA en Safari se validan antes de la etapa de offline.
- Cada vehículo es operado por un solo vendedor por jornada (ADR-005).
- La nota de venta no tiene validez fiscal. Su nombre y leyenda definitivos se validan con el contador de la organización.
- Moneda única por organización; la organización inicial opera en pesos argentinos con zona horaria America/Argentina/Mendoza.

## 11. Riesgos principales

| Riesgo | Mitigación |
| --- | --- |
| Alcance excesivo antes de validar en la calle | Etapas cerradas; la etapa 1 va a producción antes de ampliar funciones |
| Offline tratado como agregado final | Pipeline de comandos idempotentes en la base técnica |
| Diferencias entre el cálculo del teléfono y el del servidor | Motor de precios mínimo, fixtures compartidos entre ambos lenguajes, redondeo explícito |
| Contradicciones heredadas de la documentación original | Precedencia de `docs/` sobre `docs/referencia/`; decisiones registradas como ADR |
| Reglas comerciales codificadas fijas | Configuración por organización desde el inicio |
| Pérdida de datos locales en el teléfono | Almacenamiento persistente solicitado, nada se borra sin confirmación del servidor, sincronización frecuente |
| Datos históricos alterados | Snapshots, reversiones y prohibición de DELETE sobre operaciones confirmadas |

## 12. Decisiones vigentes

| ADR | Decisión |
| --- | --- |
| ADR-001 | Stack: FastAPI, PostgreSQL, React + TypeScript PWA |
| ADR-002 | Costeo por promedio ponderado móvil, encapsulado, con costo congelado por línea |
| ADR-003 | Límite de crédito con política configurable, autorización por permiso o PIN y tolerancia offline |
| ADR-004 | Descuentos: mejor beneficio entre automáticos salvo acumulables; manual sobre el resultado con tope por rol |
| ADR-005 | Ubicación de vehículo asignada a un dispositivo por jornada; stock negativo bloqueado online salvo permiso; ventas offline nunca rechazadas |
| ADR-006 | Bootstrap completo al abrir jornada, contrato preparado para modo incremental |
| ADR-007 | Integración fiscal electrónica postergada; facturación como módulo independiente |
| ADR-008 | Nota de venta con numeración por dispositivo |
| ADR-009 | Modo impositivo por organización (A/B/C) y modalidad de IVA elegible al facturar |
| ADR-010 | Precio de referencia por caja, unidades proporcionales, costo cargable en cualquier presentación |
| ADR-011 | Sesión offline con desbloqueo por PIN y dispositivos revocables |
| ADR-012 | Pipeline único de comandos idempotentes para operaciones online y offline |

El detalle de cada decisión está en `docs/adr/`.
