# Datos de crédito — Especificación

## Purpose

Definir los tres campos de crédito por cliente —límite, política y tolerancia offline— como datos que se guardan por comando con permiso propio, se auditan y nunca se evalúan aquí. La evaluación del crédito, con disponible, exceso, políticas aplicadas, tolerancia consumida y autorización del supervisor, es del change 18b (CRE-01 a CRE-10).

## Requirements

### Requirement: El crédito del cliente se modifica con un comando propio

El sistema DEBE modificar el crédito de un cliente con el comando `CLIENTE_CREDITO_MODIFICAR` (`ONLINE`, permiso `GESTIONAR_CREDITO`), cuyo contenido lleva el cliente y, opcionales, `limite_credito`, `politica_credito`, `tolerancia_offline_tipo` y `tolerancia_offline_valor`; un campo ausente o nulo se guarda como nulo. El comando NO DEBE aceptar campos de la ficha, y `CLIENTE_CREAR` y `CLIENTE_MODIFICAR` NO DEBEN aceptar campos de crédito (`design.md` D3). Todo cambio DEBE quedar auditado con el valor anterior y el nuevo (AUD-01).

#### Scenario: Fijar el límite y la política de un cliente

- **GIVEN** el cliente `Kiosco La Esquina` `ACTIVO` en A, con crédito en nulo
- **WHEN** un usuario con `GESTIONAR_CREDITO` envía `CLIENTE_CREDITO_MODIFICAR` con `limite_credito = "150000.00"` y `politica_credito = AUTORIZAR`
- **THEN** el comando queda `ACEPTADO`, el cliente guarda el límite `"150000.00"` y la política `AUTORIZAR`, y se registra una fila de auditoría con el valor anterior (nulo) y el nuevo
- **Regla:** CRE-01; CRE-03; AUD-01; INV-03

#### Scenario: Doble envío del cambio de crédito

- **GIVEN** un `CLIENTE_CREDITO_MODIFICAR` aceptado con `operation_id` X
- **WHEN** se reenvía con `operation_id` X y el mismo contenido
- **THEN** se devuelve el resultado original y hay una sola fila de auditoría del cambio
- **Regla:** INV-06; SYN-02

#### Scenario: Mismo `operation_id` con contenido distinto

- **GIVEN** un `CLIENTE_CREDITO_MODIFICAR` aceptado con `operation_id` X y límite `"150000.00"`
- **WHEN** se reenvía con `operation_id` X y límite `"90000.00"`
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` y el límite sigue siendo `"150000.00"`
- **Regla:** SYN-02

#### Scenario: Sin permiso de crédito se rechaza sin efectos

- **GIVEN** un usuario con `GESTIONAR_CLIENTES` y sin `GESTIONAR_CREDITO` (rol Supervisor comercial)
- **WHEN** envía `CLIENTE_CREDITO_MODIFICAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`, el crédito del cliente no cambia y no queda reserva del `operation_id`
- **Regla:** `01` §19 (`GESTIONAR_CREDITO`); `design.md` D3; SEG

#### Scenario: Cliente de otra organización

- **GIVEN** un cliente de B
- **WHEN** un usuario de A envía `CLIENTE_CREDITO_MODIFICAR` sobre él
- **THEN** la respuesta es 404 y el crédito del cliente de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: Límite negativo o con más decimales que el tipo

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREDITO_MODIFICAR` con `limite_credito = "-1.00"` o con `"100.005"`
- **THEN** se rechaza con `LIMITE_CREDITO_INVALIDO` y no cambia ninguna fila
- **Regla:** INV-03; `core/money.py`; `design.md` D6

#### Scenario: Política fuera del catálogo

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREDITO_MODIFICAR` con `politica_credito = IGNORAR`
- **THEN** se rechaza con `POLITICA_CREDITO_INVALIDA` y no cambia ninguna fila
- **Regla:** `03` §4 (`politica_credito_default`); CRE-03

#### Scenario: Tolerancia a medias o con tipo desconocido

- **GIVEN** la organización A
- **WHEN** se envía `tolerancia_offline_valor` sin `tolerancia_offline_tipo`, o con un tipo que no sea `IMPORTE` ni `PORCENTAJE`
- **THEN** se rechaza con `TOLERANCIA_OFFLINE_INVALIDA` y no cambia ninguna fila
- **Regla:** `03` §4 (`tolerancia_offline_tipo`); CRE-06

#### Scenario: El comando de crédito no acepta campos de la ficha

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREDITO_MODIFICAR` cuyo contenido incluye `nombre` o `estado`
- **THEN** se rechaza como malformado y no cambia ninguna fila
- **Regla:** `01` §19; `design.md` D3

### Requirement: Guardar el crédito no evalúa el crédito

El sistema DEBE guardar los tres campos como datos, sin resolverlos: NO DEBE calcular crédito disponible ni exceso, NO DEBE aplicar la política ni la tolerancia, NO DEBE crear observaciones, NO DEBE bloquear ni autorizar nada y NO DEBE modificar ningún saldo. Ninguna respuesta de consulta DEBE incluir `disponible`, `exceso` ni `politica_aplicada`. La resolución del crédito ocurre en la venta y en la sincronización, con el saldo real (CRE-01, CRE-09, CRE-10; `design.md` D8).

#### Scenario: Guardar un límite no altera ninguna otra fila

- **GIVEN** la organización A con sus tablas de libros y saldos
- **WHEN** se envía `CLIENTE_CREDITO_MODIFICAR` con `limite_credito = "150000.00"`
- **THEN** la única fila que cambia es la del cliente y su auditoría, y no se inserta ningún movimiento ni cambia ningún saldo
- **Regla:** CRE-01; CC-04; INV-13

#### Scenario: Guardar la política BLOQUEAR no bloquea nada

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_CREDITO_MODIFICAR` con `politica_credito = BLOQUEAR`
- **THEN** el comando queda `ACEPTADO` y ninguna otra operación cambia de comportamiento
- **Regla:** CRE-03; CRE-07; `design.md` D8

#### Scenario: Las consultas no exponen cálculos de crédito

- **GIVEN** un cliente con límite `"150000.00"`
- **WHEN** se pide su detalle
- **THEN** la respuesta trae `limite_credito`, `politica_credito` y la tolerancia, y no trae `disponible`, `exceso` ni `politica_aplicada`
- **Regla:** CRE-01; CRE-10; `design.md` D8

### Requirement: Los nulos del cliente heredan el comportamiento de la organización

Un cliente sin `limite_credito` DEBE quedar sin control de crédito: la organización no tiene columna de límite y un límite vacío significa sin control (CRE-01). Un cliente sin `politica_credito` DEBE heredar `politica_credito_default` de la organización en el momento de la evaluación, y un cliente sin tolerancia DEBE heredar `tolerancia_offline_tipo` y `tolerancia_offline_valor` de la organización (CRE-03, CRE-06). El sistema NO DEBE copiar los valores de la organización en la fila del cliente al escribir, ni resolver la herencia en el momento del alta o de la modificación: la fila guarda el nulo y la herencia se resuelve cuando el crédito se evalúa.

#### Scenario: Un cliente nuevo nace con los tres campos en nulo

- **GIVEN** la organización A con `politica_credito_default = ADVERTIR` y `tolerancia_offline_valor = "25.00"`
- **WHEN** se da de alta el cliente `Kiosco La Esquina`
- **THEN** su `limite_credito`, `politica_credito`, `tolerancia_offline_tipo` y `tolerancia_offline_valor` quedan en nulo, sin copiar los de la organización
- **Regla:** CRE-01; CRE-03; CRE-06; `03` §4

#### Scenario: La política del cliente manda sobre la de la organización

- **GIVEN** la organización A con `politica_credito_default = ADVERTIR` y el cliente `Kiosco La Esquina` con `politica_credito = AUTORIZAR`
- **WHEN** se pide el detalle del cliente
- **THEN** trae `AUTORIZAR`, y la fila de la organización sigue con `ADVERTIR` sin cambio
- **Regla:** CRE-03

#### Scenario: Dejar el crédito en nulo devuelve al comportamiento de la organización

- **GIVEN** el cliente `Kiosco La Esquina` con `limite_credito = "150000.00"` y `politica_credito = AUTORIZAR`
- **WHEN** se envía `CLIENTE_CREDITO_MODIFICAR` con ambos campos en nulo
- **THEN** el cliente vuelve a quedar sin control y con la política de la organización, y el cambio queda auditado
- **Regla:** CRE-01; CRE-03; AUD-01
