## MODIFIED Requirements

### Requirement: Los parámetros de operación viven en la configuración de la organización
La configuración de una organización DEBE contener los parámetros de `01` §4 con las columnas y dominios de `03` §4: condición frente al IVA (`RESPONSABLE_INSCRIPTO`, `MONOTRIBUTO`, `EXENTO`), modo impositivo (`A`, `B`, `C`), lista de precios por defecto, política de crédito por defecto (`ADVERTIR`, `AUTORIZAR`, `BLOQUEAR`), tolerancia de crédito sin conexión (tipo `IMPORTE` o `PORCENTAJE` y valor), habilitación de descuento manual, obligatoriedad de motivo en descuento manual y al usar lista no vigente, redondeo por defecto (múltiplo y dirección `ARRIBA`, `CERCANO`, `ABAJO`), venta a consumidor final genérico y su cliente, estado de facturación inicial (`NO_REQUIERE`, `PENDIENTE`), modalidad de IVA al facturar (`CLIENTE`, `ABSORBIDO`), intentos de PIN antes de bloquear, versión mínima de la aplicación y desvío máximo de reloj en segundos.

#### Scenario: La organización inicial toma los valores por defecto documentados
- **GIVEN** un sistema recién migrado
- **WHEN** se siembra la configuración de la organización inicial
- **THEN** su condición frente al IVA es `MONOTRIBUTO`
- **AND** su modo impositivo es `A`
- **AND** su política de crédito por defecto es `AUTORIZAR`
- **AND** el descuento manual está habilitado
- **AND** el motivo es obligatorio al usar una lista no asignada o una versión anterior
- **AND** el estado de facturación inicial por defecto es `NO_REQUIERE`
- **AND** los intentos de PIN antes de bloquear son `5`
- **Regla:** `01` §4 (columna "Organización inicial"); `00` §5; `design.md` D9

#### Scenario: Un parámetro sin valor definido queda explícitamente sin definir
- **GIVEN** los parámetros que `01` §4 marca como "A definir al configurar" (tolerancia de crédito sin conexión, obligatoriedad de motivo en descuento manual, redondeo por defecto, venta a consumidor final, modalidad de IVA al facturar)
- **WHEN** se siembra la configuración de la organización inicial
- **THEN** esos parámetros quedan sin valor, no con un valor inventado por el sistema
- **AND** el sistema no supone un valor por omisión para ellos
- **Regla:** `01` §4 (valor "A definir al configurar" / "A definir")

#### Scenario: Un valor fuera del dominio de un parámetro se rechaza
- **GIVEN** la configuración de una organización
- **WHEN** se intenta fijar la política de crédito por defecto en un valor distinto de `ADVERTIR`, `AUTORIZAR` o `BLOQUEAR`, o la condición frente al IVA en un valor distinto de `RESPONSABLE_INSCRIPTO`, `MONOTRIBUTO` o `EXENTO`
- **THEN** la operación falla con un error explícito y la configuración no cambia
- **Regla:** `03` §4 (`politica_credito_default`, `condicion_iva`)

#### Scenario: Los parámetros monetarios no usan punto flotante
- **GIVEN** las columnas de tolerancia de crédito sin conexión y de múltiplo de redondeo
- **WHEN** se recorre el catálogo de columnas de la base
- **THEN** ambas son numéricas exactas con 2 decimales, no de punto flotante binario
- **Regla:** INV-03, `03` §4 (`tolerancia_offline_valor` y `redondeo_multiplo`: `numeric(14,2)`)

#### Scenario: Las organizaciones existentes conservan su comportamiento al migrar
- **GIVEN** una base con una organización creada antes de este change, con costos y compras que descontaron IVA
- **WHEN** se aplica la migración
- **THEN** su condición frente al IVA es `RESPONSABLE_INSCRIPTO`
- **AND** sus costos y compras quedan con `computa_credito_fiscal = true` y el mismo costo base
- **Regla:** TR-06; `design.md` D3 y D9

## ADDED Requirements

### Requirement: Solo un responsable inscripto computa crédito fiscal de IVA en compras
El sistema DEBE derivar de la condición frente al IVA una única regla, *computa crédito fiscal de IVA en compras*: verdadera solo para `RESPONSABLE_INSCRIPTO` y falsa para `MONOTRIBUTO` y `EXENTO` (CST-06). Toda parte del sistema que necesite saber si el IVA de una compra es costo DEBE usar esta regla, y no la condición directamente. En una organización no inscripta, el modo impositivo DEBE ser `A` y la modalidad de IVA al facturar DEBE quedar sin definir. ADR-009 y FAC-02, FAC-03, FAC-04 y FAC-08 solo se aplican a responsables inscriptos (ADR-045).

#### Scenario: Responsable inscripto computa crédito fiscal
- **GIVEN** una organización `RESPONSABLE_INSCRIPTO`
- **WHEN** se resuelve si computa crédito fiscal
- **THEN** el resultado es verdadero
- **Regla:** CST-06

#### Scenario: Monotributista y exento no computan crédito fiscal
- **GIVEN** una organización `MONOTRIBUTO` y otra `EXENTO`
- **WHEN** se resuelve si computa crédito fiscal en cada una
- **THEN** en ambas el resultado es falso
- **Regla:** CST-06; `design.md` D1

#### Scenario: Una organización no inscripta con modalidad de IVA se rechaza
- **GIVEN** una organización `MONOTRIBUTO`
- **WHEN** se intenta guardar su configuración con `modalidad_iva_default = ABSORBIDO` o con `modo_impositivo = B`
- **THEN** la base rechaza la escritura y la configuración no cambia
- **Regla:** ADR-009 (solo RI); `design.md` D2

### Requirement: La condición frente al IVA se cambia con permiso, auditada y sin efecto retroactivo
El sistema DEBE cambiar la condición con el comando `ORGANIZACION_CONDICION_IVA_CAMBIAR` (`ONLINE`, permiso `ADMIN_CONFIGURACION`). El cambio y su única auditoría (valor anterior y nuevo) DEBEN ser atómicos. El cambio NO DEBE modificar ningún costo informado, compra ni costo promedio ya registrado: rige para lo que se registre después. NO DEBE pasarse a una condición no inscripta si el modo impositivo no es `A` o hay una modalidad de IVA definida (`MODO_IMPOSITIVO_INCOMPATIBLE`), y cambiar al mismo valor se rechaza con `CONDICION_IVA_SIN_CAMBIO`.

#### Scenario: Monotributista pasa a responsable inscripto
- **GIVEN** una organización `MONOTRIBUTO` con una compra de Caja x12 a `"21780.00"` cuyo costo base es `"1815.000000"`
- **WHEN** un usuario con `ADMIN_CONFIGURACION` envía `ORGANIZACION_CONDICION_IVA_CAMBIAR` a `RESPONSABLE_INSCRIPTO`
- **THEN** el comando queda `ACEPTADO`, la condición es `RESPONSABLE_INSCRIPTO` y hay una sola auditoría con `MONOTRIBUTO` → `RESPONSABLE_INSCRIPTO`
- **AND** la compra previa conserva costo base `"1815.000000"` y `computa_credito_fiscal = false`
- **Regla:** CST-06; TR-06; AUD-01; `design.md` D7

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `ADMIN_CONFIGURACION`
- **WHEN** envía `ORGANIZACION_CONDICION_IVA_CAMBIAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y la condición no cambia
- **Regla:** `01` §19 (`ADMIN_CONFIGURACION`)

#### Scenario: Mismo valor
- **GIVEN** una organización `MONOTRIBUTO`
- **WHEN** se envía el cambio a `MONOTRIBUTO`
- **THEN** se rechaza con 409 `CONDICION_IVA_SIN_CAMBIO` y no se audita ningún cambio
- **Regla:** TR-10; `design.md` D7

#### Scenario: Pasar a no inscripto con modo impositivo incompatible
- **GIVEN** una organización `RESPONSABLE_INSCRIPTO` con modalidad de IVA por defecto `CLIENTE`
- **WHEN** se envía el cambio a `MONOTRIBUTO`
- **THEN** se rechaza con 409 `MODO_IMPOSITIVO_INCOMPATIBLE` y la condición no cambia
- **Regla:** ADR-009; `design.md` D2 y D7

#### Scenario: Doble envío no duplica el cambio
- **GIVEN** un `ORGANIZACION_CONDICION_IVA_CAMBIAR` aceptado con `operation_id` X
- **WHEN** se reenvía con `operation_id` X y el mismo contenido
- **THEN** se devuelve el resultado original y hay una sola auditoría
- **Regla:** INV-06; SYN-02

#### Scenario: Valor desconocido
- **WHEN** se envía el cambio a `CONSUMIDOR_FINAL`
- **THEN** se rechaza con 422 (validación del cuerpo) y la condición no cambia
- **Regla:** `03` §4 (`condicion_iva`)

### Requirement: La condición frente al IVA se consulta
El sistema DEBE exponer `GET /api/v1/configuracion/fiscal`, para cualquier usuario autenticado, con la condición frente al IVA, si computa crédito fiscal, el modo impositivo y la modalidad de IVA por defecto de la organización del token. NO DEBE aceptar una organización tomada del pedido.

#### Scenario: Lectura de la propia organización
- **GIVEN** una organización `MONOTRIBUTO` y un usuario con solo `REGISTRAR_COMPRA`
- **WHEN** pide `GET /api/v1/configuracion/fiscal`
- **THEN** recibe `condicion_iva = MONOTRIBUTO`, `computa_credito_fiscal = false`, `modo_impositivo = A` y `modalidad_iva_default = null`
- **Regla:** CST-06; `design.md` D8

#### Scenario: Aislamiento entre organizaciones
- **GIVEN** la organización A `MONOTRIBUTO` y la B `RESPONSABLE_INSCRIPTO`
- **WHEN** un usuario de A pide la configuración fiscal
- **THEN** recibe la de A y nunca la de B
- **Regla:** TR-08; INV-21

### Requirement: La condición frente al IVA se administra desde una pantalla
La pantalla `/admin/configuracion/fiscal` DEBE mostrar la condición vigente. Con `ADMIN_CONFIGURACION` DEBE permitir cambiarla tras una confirmación que explique que el cambio no recalcula costos ni compras ya registrados e informe cuántos costos informados vigentes se calcularon con la otra regla. Sin ese permiso, la pantalla es de solo lectura.

#### Scenario: Cambio con confirmación
- **GIVEN** un usuario con `ADMIN_CONFIGURACION` en una organización `MONOTRIBUTO` con 12 costos vigentes calculados sin descontar IVA
- **WHEN** elige `RESPONSABLE_INSCRIPTO`
- **THEN** ve una confirmación que dice que el cambio no es retroactivo y que hay 12 costos vigentes para revisar
- **AND** solo al confirmar se envía el comando
- **Regla:** TR-06; `design.md` D10

#### Scenario: Usuario sin permiso
- **GIVEN** un usuario autenticado sin `ADMIN_CONFIGURACION`
- **WHEN** abre la pantalla
- **THEN** ve la condición vigente sin la acción de cambiarla
- **Regla:** ADR-027
