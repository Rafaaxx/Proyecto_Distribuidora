"""Errores de dominio de `clientes` (`design.md`, tareas 1.3 y 6.1): código
estable, heredan de `DomainError` (`CLAUDE.md` §5), mismo criterio de
`status_http` que `proveedores/domain/errores.py` (409 duplicados y estado en
conflicto, 422 validaciones de contenido, 404 no encontrado). Una referencia a
un cliente que no existe en la organización del token, o que pertenece a otra,
es `RecursoNoEncontradoError` (INV-21, SEG-07: "un recurso de otra
organización responde 404, no 403").

Los códigos que aparecen acá son los que las specs nombran textualmente:
`NOMBRE_INVALIDO`, `CODIGO_DUPLICADO`, `DOCUMENTO_DUPLICADO`,
`DOCUMENTO_INCOMPLETO`, `DOCUMENTO_INVALIDO`, `FICHA_INCOMPLETA`,
`ESTADO_INVALIDO`, `TRANSICION_ESTADO_INVALIDA`, `LIMITE_CREDITO_INVALIDO`,
`POLITICA_CREDITO_INVALIDA`, `TOLERANCIA_OFFLINE_INVALIDA`,
`CONSUMIDOR_FINAL_SIN_CREDITO`, `CONSUMIDOR_FINAL_NO_INACTIVABLE` y
`CONSUMIDOR_FINAL_YA_HABILITADO`. Los que las specs describen como
"malformado" (`contenido de comando`) NO son de este módulo: los levanta el bus
antes de llegar al dominio (`CONTENIDO_DE_COMANDO_INVALIDO`, SYN-01)."""

from __future__ import annotations

from app.core.errors import DomainError


class RecursoNoEncontradoError(DomainError):
    """Un cliente que no existe en la organización del token (o que pertenece a
    otra) responde como inexistente (INV-21, SEG-07)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class NombreInvalidoError(DomainError):
    """Nombre vacío o solo espacios tras recortar (TR-10, CLI-01, D1)."""

    codigo = "NOMBRE_INVALIDO"
    status_http = 422


class FichaIncompletaError(DomainError):
    """Falta `direccion` o `contacto`, los dos campos que CLI-01 no marca como
    opcionales. Se validan acá y no en el esquema del comando para que la
    respuesta sea `FICHA_INCOMPLETA` y no el genérico de contenido malformado
    (INV-03, SEG-07)."""

    codigo = "FICHA_INCOMPLETA"
    status_http = 422


class CodigoInvalidoError(DomainError):
    """Código que queda vacío tras recortar."""

    codigo = "CODIGO_INVALIDO"
    status_http = 422


class CodigoDuplicadoError(DomainError):
    """Código ya usado por otro cliente de la organización (D1,
    `ux_cliente__codigo`)."""

    codigo = "CODIGO_DUPLICADO"
    status_http = 409


class DocumentoIncompletoError(DomainError):
    """Documento a medias (un tipo sin número, o un número con letras) (CLI-01,
    D1). No es lo mismo que un documento inválido: acá el problema es que la
    pareja no está completa o tiene basura, y el error dice cuál de las dos
    cosas pasó."""

    codigo = "DOCUMENTO_INCOMPLETO"
    status_http = 422


class DocumentoInvalidoError(DomainError):
    """Tipo fuera del catálogo (CUIT, DNI) o longitud que no corresponde al
    tipo (CUIT 11 dígitos, DNI entre 7 y 8) (CLI-05, D1)."""

    codigo = "DOCUMENTO_INVALIDO"
    status_http = 422


class DocumentoDuplicadoError(DomainError):
    """Pareja tipo/número ya usada por otro cliente de la organización, después
    de normalizar a dígitos (D1, `ux_cliente__documento`)."""

    codigo = "DOCUMENTO_DUPLICADO"
    status_http = 409


class EstadoInvalidoError(DomainError):
    """Estado que no es `ACTIVO`, `SUSPENDIDO` ni `INACTIVO` (`01` §18, VTA-08)."""

    codigo = "ESTADO_INVALIDO"
    status_http = 422


class TransicionEstadoInvalidaError(DomainError):
    """Transición que la máquina de `01` §18 no permite (`design.md` D7)."""

    codigo = "TRANSICION_ESTADO_INVALIDA"
    status_http = 409


class ClienteConOperacionesError(DomainError):
    """`INACTIVO -> ACTIVO` sobre un cliente con operaciones (CLI-06, ADR-030).
    Todavía ningún módulo registra operaciones sobre clientes, así que la
    transición sigue disponible; el error queda declarado desde ahora para que el
    verificador que se active en el change 08/10/17/18a no tenga que inventar un
    código."""

    codigo = "CLIENTE_CON_OPERACIONES"
    status_http = 409


class LimiteCreditoInvalidoError(DomainError):
    """Límite negativo, con más decimales que la columna o de tipo que no sea
    dinero exacto (CRE-01, INV-03, `core/money.py`)."""

    codigo = "LIMITE_CREDITO_INVALIDO"
    status_http = 422


class PoliticaCreditoInvalidaError(DomainError):
    """Política fuera del catálogo `ADVERTIR`, `AUTORIZAR`, `BLOQUEAR` (CRE-03,
    `03` §4)."""

    codigo = "POLITICA_CREDITO_INVALIDA"
    status_http = 422


class ToleranciaOfflineInvalidaError(DomainError):
    """Tolerancia a medias (tipo sin valor o valor sin tipo), con tipo fuera del
    catálogo o con valor negativo (CRE-06, D6)."""

    codigo = "TOLERANCIA_OFFLINE_INVALIDA"
    status_http = 422


class ConsumidorFinalSinCreditoError(DomainError):
    """Se intentó dar crédito propio al consumidor final, cuyo límite es cero y
    fijo por definición (CLI-03, CRE-01)."""

    codigo = "CONSUMIDOR_FINAL_SIN_CREDITO"
    status_http = 422


class ConsumidorFinalNoInactivableError(DomainError):
    """Se intentó llevar al consumidor final a `INACTIVO` (CLI-03, ADR-029: solo
    puede estar `ACTIVO` o `SUSPENDIDO`)."""

    codigo = "CONSUMIDOR_FINAL_NO_INACTIVABLE"
    status_http = 422


class ConsumidorFinalYaHabilitadoError(DomainError):
    """Segundo `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` sobre una organización que
    ya lo tiene (CLI-03, D4)."""

    codigo = "CONSUMIDOR_FINAL_YA_HABILITADO"
    status_http = 409


class ConfiguracionDeOrganizacionAusenteError(DomainError):
    """La organización no tiene fila de `configuracion_organizacion`, así que no
    hay a qué apuntar `cliente_consumidor_final_id` (D4, ADR-029).

    Es un hueco de datos, no una regla de negocio: una organización que llega al
    bootstrap sin fila de configuración está incompleta. No se puede habilitar el
    consumidor final sin señalar una fila, y `identidad.service.configurar_
    consumidor_final` devuelve `None` en ese caso sin tocar nada. Si el caller
    ignorara ese `None`, confirmaría un cliente marcado como consumidor final sin
    el par de configuración, que es exactamente el estado intermedio que D4
    prohíbe -- y no se detectaría hasta el bootstrap del change 21 (SYN-11)."""

    codigo = "CONFIGURACION_DE_ORGANIZACION_AUSENTE"
    status_http = 409
